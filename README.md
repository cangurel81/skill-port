# skill-port

Port `SKILL.md` skills between **Claude Code**, **OpenCode V2**, **OpenClaw** and the portable **Agent Skills spec**. One deterministic, dependency-free Python CLI: audit, convert, verify, install.

## Why

A catalog of 4231 unique skills was measured on the author's machine:

| Signal | Count | Share |
|---|---:|---:|
| Skills containing real code/assets | 444 | 10.5% |
| Skills with portable frontmatter (`name` + `description` only) | 136 | 3.2% |
| Skills using `disable-model-invocation` | 3657 | 86.4% |
| Skills using `source` / `risk` / `date_added` | 2851 | 67.4% |
| Duplicate skills | 652 | 32.0% |
| Existing harness converters | 0 | — |

Most skills are not portable by accident, not by design. `skill-port` turns that into a deterministic, auditable operation instead of hand-editing YAML.

A later audit of the four local skill roots on 2026-11-19 scanned **11263 `SKILL.md` files** (duplicates across vendored trees included):

| Target | Errors | Warnings | Dominant finding |
|---|---:|---:|---|
| `portable` | 56538 | 1424 | `non-spec-field` (56096, error) |
| `openclaw` | 4941 | 47536 | `unknown-field` (45710, warning), `description-too-long` (4396, error) |

Reproduce with `skill-port audit <root> --target portable --json --fail-on never`.

## Targets

| Target | Install root | Frontmatter rules |
|---|---|---|
| `claude` | `~/.claude/skills/<name>/` | All documented Claude Code fields accepted; unknown fields ignored |
| `portable` | `skills/<name>/` | Only `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`; extra key = hard error |
| `opencode` | `.opencode/skills/<name>/` (global: `~/.config/opencode/skills`) | `disable-model-invocation` / `metadata.opencode/autoinvoke`; folder name is the ID |
| `openclaw` | `~/.openclaw/workspace/skills/<name>/` | lowercase kebab-case name, one-line description under 160 chars, `{baseDir}` supported |

Rules were checked against the official documentation on 2026-11-19:
[OpenCode skills](https://opencode.ai/docs/skills/),
[OpenClaw creating skills](https://docs.openclaw.ai/tools/creating-skills),
[Claude Code skills](https://docs.claude.com/en/docs/claude-code/skills).

## Install

No dependencies, no build step. Python 3.9+.

```sh
git clone https://github.com/cangurel81/skill-port.git
cd skill-port
python scripts/skill-port.py targets
```

To use the skill itself in an agent, copy the `skill-port/` folder into the harness skills directory:

```sh
# Claude Code
cp -r . ~/.claude/skills/skill-port/
# OpenCode
cp -r . ~/.config/opencode/skills/skill-port/
# OpenClaw
cp -r . ~/.openclaw/workspace/skills/skill-port/
```

The skill frontmatter contains only `name` and `description`, so the same folder works everywhere.

## Usage

```sh
# What breaks if I move this skill?
python scripts/skill-port.py audit ./my-skill --target openclaw

# Convert and write a report next to the result
python scripts/skill-port.py convert ./my-skill --to portable --out ./out/my-skill

# Check the result (frontmatter, tokens, referenced local files)
python scripts/skill-port.py verify ./out/my-skill --target portable

# Convert + copy into the target harness root
python scripts/skill-port.py install ./my-skill --to claude --root ~/.claude/skills
```

Every command accepts `--json`. `audit` defaults to `--fail-on error`; `convert` defaults to `never` because a successful conversion may still contain documented manual work.

### Exit codes

| Code | Meaning |
|---:|---|
| `0` | No findings at the configured level |
| `1` | Findings at or above `--fail-on` |
| `2` | Tool/input error (bad target, missing `SKILL.md`, existing output without `--force`) |

### What conversion does

- Drops fields the target does not accept and lists each one in `PORT_REPORT.md`.
- Rewrites host tokens: `${CLAUDE_SKILL_DIR}` → `.` or `{baseDir}`, `{baseDir}` → `.` where appropriate.
- Rewrites `.claude/skills/` / `.opencode/skills/` / `skills/` references to the target prefix.
- Normalises the name to kebab-case for OpenClaw; derives a missing name from the folder and a missing description from the first body line.
- Flags `${CLAUDE_PROJECT_DIR}`, `${CLAUDE_SESSION_ID}`, `$ARGUMENTS` and Claude dynamic-context expressions as **manual rewrite** — they have no equivalent.
- Copies all other files (scripts, references, assets) verbatim, excluding `PORT_REPORT.md` and caches.
- Writes UTF-8 without BOM, LF newlines, stable field order. Same input + target = same output.

`verify` checks the converted folder: required frontmatter, target-specific rules, untranslatable tokens, host-specific paths and referenced local files under `scripts/`, `references/`, `assets/`, `templates/`.

## Tests

```sh
python -m unittest discover -s test -v
python -m compileall -q skill_port scripts
python scripts/skill-port.py targets
```

CI runs on Ubuntu 24.04 and Windows 2022 with Python 3.9 and 3.13.

## Scope and limits

- This is a structural portability tool, not a quality or security scanner. It does not judge the skill instructions.
- OpenClaw is not installed on the author's Windows machine; its rules are validated from the official spec and by deterministic tests, not by a live OpenClaw runtime.
- OpenCode V2 treats frontmatter as optional at runtime and derives the skill ID from the folder path; the tool enforces name/folder alignment as a warning there because mismatch is a common source of confusion.
- Claude local skills silently ignore unknown frontmatter keys; `portable` deliberately treats them as errors because upload/API packaging rejects them.

## License

MIT — see [LICENSE](LICENSE).
