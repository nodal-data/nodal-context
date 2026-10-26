#!/usr/bin/env python3
"""Verified SQL lifecycle; optional real age/SOPS round trips use synthetic keys."""
import argparse
from pathlib import Path
import os
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from acf_runtime.verified import VerifiedSQL, VerificationError, atomic_private
from acf_runtime.loader import read_yaml
from acf_fixtures import context, write


def expect(category, fn):
    try:
        fn()
    except VerificationError as exc:
        assert exc.category == category, (exc.category, category)
        assert "PRIVATE_CONTENT" not in str(exc)
        return exc
    raise AssertionError("expected refusal: " + category)


def run(crypto_dir=None):
    with TemporaryDirectory() as temp:
        root = Path(temp) / "context"
        context(root)
        config = read_yaml(root / "context.config.yaml")
        manager = VerifiedSQL(root)
        query = "evals/verified/orders.sql"
        payload = b"SELECT 2 AS orders -- PRIVATE_CONTENT\n"
        capture = manager.capture(query, payload)
        assert capture == {"status": "local_only", "portable": False}
        plain = root / query
        assert plain.read_bytes() == payload and stat.S_IMODE(plain.stat().st_mode) == 0o600
        assert manager.decrypt(query)["status"] == "local_only"
        expect("different_output_exists_use_overwrite", lambda: manager.capture(query, b"SELECT 3"))
        assert plain.read_bytes() == payload
        for path in ("../secret.sql", "/tmp/secret.sql", "evals/verified/../secret.sql", "evals/verified/a/b.sql", "evals/verified/a\\b.sql"):
            expect("invalid_verified_query_file", lambda: manager.paths(path))
        outside = Path(temp) / "outside.sql"
        outside.write_bytes(b"outside")
        plain.unlink(); plain.symlink_to(outside)
        expect("verification_symlink_rejected", lambda: manager.encrypt(query))
        plain.unlink(); manager.capture(query, payload)
        bad = {**config, "verified_sql": {"encryption": "age", "decrypt_to": "company"}}
        expect("verification_path_outside_ignored_area", lambda: VerifiedSQL(root, config=bad))
        bad["verified_sql"]["decrypt_to"] = "evals/verified/../company"
        expect("unsafe_verification_path", lambda: VerifiedSQL(root, config=bad))
        # Backend failures are distinguishable and never leak process diagnostics.
        fail = Path(temp) / "fail-tool"
        fail.write_text("#!/bin/sh\nprintf 'PRIVATE_CONTENT private key' >&2\nexit 1\n")
        fail.chmod(0o700)
        configured = {**config, "verified_sql": {"encryption": "age", "recipients": ["age1synthetic"]}}
        failing = VerifiedSQL(root, config=configured, executables={"age": str(fail)})
        result = failing.capture(query, payload)
        assert result["status"] == "local_unpublished" and not result["portable"] and result["exit_code"] == 4
        assert plain.read_bytes() == payload and not Path(str(plain) + ".age").exists()
        missing = VerifiedSQL(root, config=configured, executables={"age": "/does-not-exist/age"})
        assert expect("crypto_executable_unavailable", lambda: missing.encrypt(query)).code == 3
        without_recipients = VerifiedSQL(root, config={**config, "verified_sql": {"encryption": "age"}}, executables={"age": str(fail)})
        expect("public_recipients_required", lambda: without_recipients.encrypt(query))
        # A wrong identity is not a reason to use an existing local plaintext copy.
        cipher = Path(str(plain) + ".age"); cipher.write_bytes(b"not an encrypted artifact")
        expect("identity_file_unavailable", lambda: failing.decrypt(query, overwrite=True))
        assert plain.read_bytes() == payload
        probe = failing.probe(query)
        assert probe["ciphertext_present"] and probe["decryptability"] == "unchecked"
        assert failing.probe(query, decrypt=True)["decryptability"] == "unavailable"
        cipher.unlink()
        # Explicit temporary decryption/local replay leaves the authored file alone.
        try:
            with manager.temporary_plaintext(query) as temporary:
                parent = temporary.parent
                assert temporary.read_bytes() == payload
                assert stat.S_IMODE(temporary.stat().st_mode) == 0o600
                raise RuntimeError("executor failure")
        except RuntimeError:
            pass
        assert not parent.exists() and plain.read_bytes() == payload
        # Ignore-rule migration: ciphertext is eligible, never plaintext or temp runs.
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        (root / ".gitignore").write_text((ROOT / "template/.gitignore").read_text())
        for path, ignored in ((query, True), (query + ".age", False), (query + ".sops", False),
                              ("evals/verified/.regression-test/key.txt", True),
                              (".nodal/crypto/test/key.txt", True)):
            result = subprocess.run(["git", "check-ignore", "--no-index", "-q", path], cwd=root)
            assert (result.returncode == 0) == ignored, path
        (root / ".gitignore").write_text("evals/verified/*\n")
        assert subprocess.run(["git", "check-ignore", "-q", query + ".age"], cwd=root).returncode == 0

        if crypto_dir:
            tools = {name: str(Path(crypto_dir) / name) for name in ("age", "sops")}
            keygen = str(Path(crypto_dir) / "age-keygen")
            identity, other_identity = Path(temp) / "identity.txt", Path(temp) / "other.txt"
            for path in (identity, other_identity):
                result = subprocess.run([keygen, "-o", str(path)], capture_output=True)
                assert result.returncode == 0, "synthetic test key generation failed"
                path.chmod(0o600)
            recipient = subprocess.run([keygen, "-y", str(identity)], capture_output=True, text=True, check=True).stdout.strip()
            for backend in ("age", "sops"):
                cfg = {**config, "verified_sql": {"encryption": backend, "recipients": [recipient]}}
                crypto = VerifiedSQL(root, config=cfg, identity=identity, executables=tools)
                result = crypto.encrypt(query)
                assert result["portable"] and result["status"] == "encrypted"
                encrypted = Path(str(plain) + (".age" if backend == "age" else ".sops"))
                assert payload not in encrypted.read_bytes()
                expect("ciphertext_exists_use_overwrite", lambda: crypto.encrypt(query))
                assert crypto.probe(query, decrypt=True)["decryptability"] == "decryptable"
                plain.unlink()
                assert crypto.probe(query, decrypt=True)["decryptability"] == "decryptable"
                assert not plain.exists(), "probe wrote plaintext"
                assert crypto.decrypt(query)["status"] == "decrypted" and plain.read_bytes() == payload
                assert stat.S_IMODE(plain.stat().st_mode) == 0o600
                wrong = VerifiedSQL(root, config=cfg, identity=other_identity, executables=tools)
                assert expect("decrypt_failed", lambda: wrong.decrypt(query, overwrite=True)).code == 5
                assert plain.read_bytes() == payload
                # Encryption failure preserves an older ciphertext for explicit repair.
                before = encrypted.read_bytes()
                broken = VerifiedSQL(root, config=cfg, identity=identity, executables={backend: str(fail)})
                result = broken.capture(query, b"SELECT 3 -- newly approved", overwrite=True)
                assert result["status"] == "local_unpublished" and encrypted.read_bytes() == before
                expect("different_output_exists_use_overwrite", lambda: crypto.decrypt(query))
                crypto.decrypt(query, overwrite=True)
                assert plain.read_bytes() == payload
                crypto.encrypt(query, overwrite=True)  # recipient rotation/re-encryption path
                assert crypto.plaintext(query) == payload
            print("test_verified: real age and SOPS round trips passed (synthetic keys)")
    print("test_verified: OK")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--crypto-dir", type=Path)
    run(parser.parse_args().crypto_dir)
