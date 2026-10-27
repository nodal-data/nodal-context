"""Verified SQL lifecycle using customer-installed age/SOPS, never custom crypto.

Private identities are passed by filename/environment to the external executable;
this module never reads, prints, generates or stores their contents.
"""
from contextlib import contextmanager
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile

from .loader import read_yaml, Schemas


class VerificationError(ValueError):
    def __init__(self, category, code=2):
        super().__init__(category)
        self.category, self.code = category, code


def contained(root, relative, area=None):
    """Reject traversal and all symlink components, including dangling symlinks."""
    root = Path(root).resolve()
    text = str(relative)
    path = PurePosixPath(text)
    if not text or "\\" in text or path.is_absolute() or ".." in path.parts:
        raise VerificationError("unsafe_verification_path", 6)
    result = root / path
    if area and not result.is_relative_to(root / area):
        raise VerificationError("verification_path_outside_ignored_area", 6)
    current = root
    for part in path.parts:
        current /= part
        if current.is_symlink():
            raise VerificationError("verification_symlink_rejected", 6)
    if not result.resolve().is_relative_to(root):
        raise VerificationError("verification_path_escapes_root", 6)
    return result


def atomic_private(path, payload, *, overwrite=False):
    """Atomic publication; a failed transform never truncates the prior artifact."""
    if path.is_symlink():
        raise VerificationError("verification_symlink_rejected", 6)
    if path.exists():
        if not path.is_file():
            raise VerificationError("verification_target_not_file", 6)
        if path.read_bytes() == payload:
            path.chmod(0o600)
            return
        if not overwrite:
            raise VerificationError("different_output_exists_use_overwrite", 7)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".verified-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary, path)
        else:
            # link() gives create-if-absent semantics even if another writer races.
            try:
                os.link(temporary, path)
            except FileExistsError as exc:
                raise VerificationError("different_output_exists_use_overwrite", 7) from exc
    finally:
        temporary.unlink(missing_ok=True)


class VerifiedSQL:
    def __init__(self, root, *, config=None, identity=None, executables=None, timeout=60):
        self.root = Path(root).resolve()
        if config is None:
            try:
                config = read_yaml(self.root / "context.config.yaml")
            except Exception as exc:
                raise VerificationError("invalid_verification_config") from exc
        schema_dir = self.root / "schemas"
        if not schema_dir.is_dir():
            schema_dir = Path(__file__).resolve().parents[1] / "schemas"
        if not isinstance(config, dict) or Schemas(schema_dir).errors("config", config):
            raise VerificationError("invalid_verification_config")
        settings = config.get("verified_sql", {"encryption": "none"})
        self.backend = settings["encryption"]
        self.recipients = settings.get("recipients", [])
        self.decrypt_root = contained(self.root, settings.get("decrypt_to", "evals/verified"), "evals/verified")
        self.identity = Path(identity).expanduser().absolute() if identity else None
        if self.identity and not self.identity.is_file():
            raise VerificationError("identity_file_unavailable", 5)
        self.executables = executables or {}
        self.timeout = timeout

    def paths(self, query):
        if not isinstance(query, str) or not re.fullmatch(r"evals/verified/[A-Za-z0-9_][A-Za-z0-9_.-]*\.sql", query):
            raise VerificationError("invalid_verified_query_file", 6)
        plain = contained(self.root, query, "evals/verified")
        cipher = contained(self.root, query + (".sops" if self.backend == "sops" else ".age"), "evals/verified")
        destination = contained(self.root, (self.decrypt_root / plain.name).relative_to(self.root), "evals/verified")
        return plain, cipher, destination

    def _transform(self, payload, operation):
        executable = self.executables.get(self.backend) or shutil.which(self.backend)
        if not executable:
            raise VerificationError("crypto_executable_unavailable", 3)
        env = os.environ.copy()
        if operation == "encrypt":
            if not self.recipients:
                raise VerificationError("public_recipients_required")
            if any(not isinstance(r, str) or not r.startswith("age1") or any(c.isspace() for c in r)
                   for r in self.recipients):
                raise VerificationError("configured_recipients_must_be_public_age_keys")
        identity = self.identity or (Path(env["NODAL_AGE_IDENTITY"]).expanduser().absolute() if env.get("NODAL_AGE_IDENTITY") else None)
        if operation == "decrypt" and identity and not identity.is_file():
            raise VerificationError("identity_file_unavailable", 5)
        if env.get("SOPS_AGE_KEY_FILE"):
            env["SOPS_AGE_KEY_FILE"] = str(Path(env["SOPS_AGE_KEY_FILE"]).expanduser().absolute())
        if self.backend == "age":
            args = [str(executable), "--" + operation]
            if operation == "encrypt":
                for recipient in self.recipients:
                    args.extend(["--recipient", recipient])
            elif identity:
                args.extend(["--identity", str(identity)])
            else:
                raise VerificationError("identity_file_unavailable", 5)
        else:
            args = [str(executable), operation, "--input-type",
                    "binary" if operation == "encrypt" else "json", "--output-type",
                    "json" if operation == "encrypt" else "binary", "--filename-override", "verified.sql"]
            if operation == "encrypt":
                args.extend(["--age", ",".join(self.recipients)])
                # Configured public recipients are authoritative. Do not silently
                # add another recipient from unrelated host SOPS configuration.
                for key in ("SOPS_KMS_ARN", "SOPS_GCP_KMS_IDS", "SOPS_HUAWEICLOUD_KMS_IDS",
                            "SOPS_AZURE_KEYVAULT_URLS", "SOPS_VAULT_URIS", "SOPS_PGP_FP", "SOPS_AGE_RECIPIENTS"):
                    env.pop(key, None)
            elif identity:
                env["SOPS_AGE_KEY_FILE"] = str(identity)
        work_root = contained(self.root, ".nodal/crypto")
        work_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="operation-", dir=work_root) as work:
            if self.backend == "sops":
                settings = Path(work) / "sops.yaml"
                settings.write_text("creation_rules:\n  - path_regex: .*\n")
                args[1:1] = ["--config", str(settings)]
            try:
                result = subprocess.run(args, input=payload, capture_output=True, cwd=work,
                                        env=env, timeout=self.timeout, check=False)
            except FileNotFoundError as exc:
                raise VerificationError("crypto_executable_unavailable", 3) from exc
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise VerificationError(operation + "_failed", 4 if operation == "encrypt" else 5) from exc
            if result.returncode or not result.stdout:
                # Never include stderr: backend diagnostics may contain secret material.
                raise VerificationError(operation + "_failed", 4 if operation == "encrypt" else 5)
            return result.stdout

    def encrypt(self, query, *, overwrite=False):
        plain, cipher, _ = self.paths(query)
        if not plain.is_file():
            raise VerificationError("approved_plaintext_missing", 8)
        if self.backend == "none":
            return {"status": "local_only", "portable": False}
        if cipher.exists() and not overwrite:
            raise VerificationError("ciphertext_exists_use_overwrite", 7)
        ciphertext = self._transform(plain.read_bytes(), "encrypt")
        atomic_private(cipher, ciphertext, overwrite=overwrite)
        return {"status": "encrypted", "portable": True}

    def plaintext(self, query):
        """Read/decrypt for an explicit local operation, never fallback on failure."""
        plain, cipher, _ = self.paths(query)
        if self.backend == "none":
            if not plain.is_file():
                raise VerificationError("approved_plaintext_missing", 8)
            return plain.read_bytes()
        if not cipher.is_file():
            raise VerificationError("ciphertext_missing", 8)
        return self._transform(cipher.read_bytes(), "decrypt")

    def decrypt(self, query, *, overwrite=False):
        _, _, destination = self.paths(query)
        payload = self.plaintext(query)
        atomic_private(destination, payload, overwrite=overwrite)
        return {"status": "local_only" if self.backend == "none" else "decrypted", "portable": self.backend != "none"}

    def capture(self, query, approved_sql, *, overwrite=False):
        """Stage 5: save human-approved plaintext and encrypt in one operation.

        Crypto failure intentionally retains the local approved file, with an
        explicit local_unpublished receipt; it never pretends a portable key exists.
        """
        plain, _, _ = self.paths(query)
        atomic_private(plain, approved_sql, overwrite=overwrite)
        try:
            return self.encrypt(query, overwrite=overwrite)
        except VerificationError as exc:
            return {"status": "local_unpublished", "portable": False, "category": exc.category, "exit_code": exc.code}

    @contextmanager
    def temporary_plaintext(self, query):
        """Regression-only plaintext in an owned ignored room, cleaned on every exit."""
        payload = self.plaintext(query)
        self.decrypt_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".regression-", dir=self.decrypt_root) as work:
            path = Path(work) / Path(query).name
            atomic_private(path, payload)
            yield path

    def probe(self, query, *, decrypt=False):
        plain, cipher, destination = self.paths(query)
        result = {"backend": self.backend, "plaintext_present": plain.is_file() or destination.is_file(),
                  "ciphertext_present": self.backend != "none" and cipher.is_file(), "decryptability": "unchecked"}
        if self.backend == "none":
            result["decryptability"] = "local_only" if plain.is_file() else "missing"
        elif not cipher.is_file():
            result["decryptability"] = "missing"
        elif decrypt:
            try:
                self.plaintext(query)
                result["decryptability"] = "decryptable"
            except VerificationError as exc:
                result["decryptability"] = "unavailable"
                result["category"] = exc.category
        return result
