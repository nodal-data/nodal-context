@AGENTS.md

# Claude-specific notes

Claude discovers the canonical skills through `.claude/skills/` symlinks during
in-repository development. Native installs namespace explicit invocations, for
example `/nodal-analytics:setup-nodal`. Keep Claude-only behavior in skill
frontmatter and `.claude-plugin/`; shared contributor policy belongs in
`AGENTS.md`.
