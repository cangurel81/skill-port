---
name: skill-port
description: Audit, convert, verify and install SKILL.md skills across Claude Code, OpenCode and OpenClaw with one deterministic stdlib CLI.
---

# Skill Port

Move a skill between harnesses without guessing which frontmatter fields survive.
The CLI is deterministic, dependency-free and reports every dropped field and
untranslatable token.

## Run

From this skill's own directory:

```
python scripts/skill-port.py targets
python scripts/skill-port.py audit <path> --target claude|portable|opencode|openclaw
python scripts/skill-port.py convert <source-dir> --to <target> --out <output-dir>
python scripts/skill-port.py verify <dir> --target <target>
python scripts/skill-port.py install <source-dir> --to <target> [--root <skills-root>]
```

Add `--json` for machine-readable output. Exit codes: `0` clean, `1` findings,
`2` tool/input error. Use `--fail-on error|warning|never` to control what fails.

## Targets

- `claude` - Claude Code local (`~/.claude/skills`), accepts all documented fields.
- `portable` - Agent Skills spec for claude.ai upload / Skills API; only
  `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`.
- `opencode` - OpenCode V2 (`.opencode/skills` or `~/.config/opencode/skills`);
  `disable-model-invocation` and `metadata.opencode/autoinvoke` control discovery.
- `openclaw` - OpenClaw (`~/.openclaw/workspace/skills`); lowercase kebab-case
  name, one-line description under 160 characters, `{baseDir}` supported.

## Workflow

1. `audit` the source skill for every target you care about.
2. `convert` to the chosen target. Read `PORT_REPORT.md` in the output folder.
3. Fix anything listed under **Manual action required**.
4. `verify` the result, then `install` it (or copy the folder yourself).

## Rules

- Never silently drop a host-specific field: `PORT_REPORT.md` lists it.
- Claude's project-dir, session-id and argument variables, plus dynamic-context
  expressions, have no portable equivalent - flag them for manual rewrite.
- Keep the frontmatter minimal when the destination is unknown: `name` plus a
  clear one-line `description` works in all four targets.
- Re-run `verify` after any manual edit.
