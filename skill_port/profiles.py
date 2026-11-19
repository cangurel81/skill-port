"""Host profiles derived from the official harness documentation.

Sources (checked 2026-11-19):
- OpenCode V2: https://opencode.ai/docs/skills/
- OpenClaw: https://docs.openclaw.ai/tools/creating-skills
- Claude Code: https://docs.claude.com/en/docs/claude-code/skills
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Optional

from .errors import ToolError

# Agent Skills spec: accepted by claude.ai upload, Skills API and packaging
# with a hard error when an extra key is present.
SPEC_FIELDS: FrozenSet[str] = frozenset(
    {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
)

# Claude Code local skills accept every documented field and silently ignore
# fields they do not recognize.
CLAUDE_FIELDS: FrozenSet[str] = SPEC_FIELDS | frozenset(
    {
        "when_to_use",
        "argument-hint",
        "arguments",
        "disable-model-invocation",
        "user-invocable",
        "disallowed-tools",
        "model",
        "effort",
        "context",
        "agent",
        "background",
        "hooks",
        "paths",
        "shell",
    }
)

OPENCODE_FIELDS: FrozenSet[str] = frozenset(
    {"name", "description", "license", "compatibility", "metadata", "disable-model-invocation"}
)

OPENCLAW_FIELDS: FrozenSet[str] = frozenset(
    {
        "name",
        "description",
        "license",
        "compatibility",
        "metadata",
        "user-invocable",
        "disable-model-invocation",
        "command-dispatch",
        "command-tool",
        "command-arg-mode",
        "homepage",
    }
)

ALL_KNOWN_FIELDS: FrozenSet[str] = CLAUDE_FIELDS | OPENCODE_FIELDS | OPENCLAW_FIELDS

NAME_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"

TOKENS: FrozenSet[str] = frozenset(
    {
        "${CLAUDE_SKILL_DIR}",
        "${CLAUDE_PROJECT_DIR}",
        "${CLAUDE_SESSION_ID}",
        "$ARGUMENTS",
        "{baseDir}",
    }
)


@dataclass(frozen=True)
class Profile:
    """Rules for one target harness."""

    id: str
    label: str
    install_path: str
    allowed: FrozenSet[str]
    inert: FrozenSet[str] = frozenset()
    description_max: Optional[int] = None
    description_single_line: bool = False
    require_kebab_name: bool = False
    dir_name_is_id: bool = False
    # token -> replacement; None means the token has no equivalent.
    token_map: Dict[str, Optional[str]] = field(default_factory=dict)
    path_prefix: str = "skills/"


def _tokens(replacements: Dict[str, Optional[str]]) -> Dict[str, Optional[str]]:
    result: Dict[str, Optional[str]] = {}
    for token in TOKENS:
        result[token] = replacements.get(token)
    return result


PROFILES: Dict[str, Profile] = {
    "claude": Profile(
        id="claude",
        label="Claude Code (local ~/.claude/skills)",
        install_path=".claude/skills/<name>/",
        allowed=CLAUDE_FIELDS,
        token_map=_tokens(
            {
                "${CLAUDE_SKILL_DIR}": "${CLAUDE_SKILL_DIR}",
                "${CLAUDE_PROJECT_DIR}": "${CLAUDE_PROJECT_DIR}",
                "${CLAUDE_SESSION_ID}": "${CLAUDE_SESSION_ID}",
                "$ARGUMENTS": "$ARGUMENTS",
                "{baseDir}": ".",
            }
        ),
        path_prefix=".claude/skills/",
    ),
    "portable": Profile(
        id="portable",
        label="Agent Skills spec (claude.ai upload / Skills API)",
        install_path="skills/<name>/",
        allowed=SPEC_FIELDS,
        description_max=1024,
        token_map=_tokens(
            {
                "${CLAUDE_SKILL_DIR}": ".",
                "${CLAUDE_PROJECT_DIR}": None,
                "${CLAUDE_SESSION_ID}": None,
                "$ARGUMENTS": None,
                "{baseDir}": ".",
            }
        ),
        path_prefix="skills/",
    ),
    "opencode": Profile(
        id="opencode",
        label="OpenCode V2 (.opencode/skills or ~/.config/opencode/skills)",
        install_path=".opencode/skills/<name>/",
        allowed=OPENCODE_FIELDS,
        inert=frozenset({"license", "compatibility"}),
        require_kebab_name=False,  # recommended, not enforced by V2
        dir_name_is_id=True,
        token_map=_tokens(
            {
                "${CLAUDE_SKILL_DIR}": ".",
                "${CLAUDE_PROJECT_DIR}": None,
                "${CLAUDE_SESSION_ID}": None,
                "$ARGUMENTS": None,
                "{baseDir}": ".",
            }
        ),
        path_prefix=".opencode/skills/",
    ),
    "openclaw": Profile(
        id="openclaw",
        label="OpenClaw (~/.openclaw/workspace/skills)",
        install_path="skills/<name>/",
        allowed=OPENCLAW_FIELDS,
        inert=frozenset({"license", "compatibility"}),
        description_max=160,
        description_single_line=True,
        require_kebab_name=True,
        token_map=_tokens(
            {
                "${CLAUDE_SKILL_DIR}": "{baseDir}",
                "${CLAUDE_PROJECT_DIR}": None,
                "${CLAUDE_SESSION_ID}": None,
                "$ARGUMENTS": None,
                "{baseDir}": "{baseDir}",
            }
        ),
        path_prefix="skills/",
    ),
}

ALIASES = {
    "claude-portable": "portable",
    "agent-skills": "portable",
    "claude-code": "claude",
}


class UnknownTarget(ToolError):
    """Raised when a target name is not a known profile (exit code 2)."""


def get_profile(name: str) -> Profile:
    key = ALIASES.get(name, name)
    if key not in PROFILES:
        raise UnknownTarget(
            "unknown target %r (choose from: %s)" % (name, ", ".join(sorted(PROFILES)))
        )
    return PROFILES[key]


def all_profiles() -> list:
    return [PROFILES[key] for key in ("claude", "portable", "opencode", "openclaw")]
