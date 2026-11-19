"""Discover skill directories and audit their portability to a target host."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Optional, Sequence

from .findings import Finding
from .frontmatter import SkillDoc, parse
from .profiles import ALL_KNOWN_FIELDS, NAME_PATTERN, Profile, TOKENS, all_profiles

SKILL_FILE = "SKILL.md"
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
}

PATH_PATTERN = re.compile(r"\.claude/skills/|\.opencode/skills/|(?<![.\w/-])skills/")
DYNAMIC_CONTEXT_PATTERN = re.compile(r"!`[^`\n]+`|```!")
METADATA_HOST_KEYS = ("opencode/", "openclaw/", "claude/")


def read_doc(path: os.PathLike) -> SkillDoc:
    """Read a SKILL.md, tolerating BOM and undecodable bytes."""
    file_path = Path(path)
    data = file_path.read_bytes()
    doc = parse(data.decode("utf-8-sig", errors="replace"), str(file_path))
    doc.bom = data.startswith(b"\xef\xbb\xbf")
    return doc


def find_skill_dirs(path: os.PathLike) -> List[Path]:
    """Accept a skill dir, a SKILL.md file, or a tree of skill dirs."""
    target = Path(path).expanduser()
    if target.is_file():
        return [target.parent] if target.name == SKILL_FILE else []
    if not target.is_dir():
        return []
    if (target / SKILL_FILE).is_file():
        return [target]

    found: List[Path] = []
    for root, dirs, files in os.walk(str(target)):
        dirs[:] = sorted(name for name in dirs if name not in SKIP_DIRS)
        if SKILL_FILE in files:
            found.append(Path(root))
    return sorted(set(found))


def _short_path(path: Path) -> str:
    return path.as_posix()


def audit_doc(
    doc: SkillDoc,
    profile: Profile,
    dir_name: str,
    path: Optional[str] = None,
) -> List[Finding]:
    """Return portability findings for one parsed skill."""
    location = path or doc.path or ""
    findings: List[Finding] = []

    def add(severity: str, code: str, message: str) -> None:
        findings.append(Finding(severity, code, message, profile.id, location))

    if doc.bom:
        add("error", "utf8-bom", "SKILL.md starts with a UTF-8 BOM")
    if not doc.has_frontmatter:
        add("warning", "no-frontmatter", "No frontmatter block; host derives name from folder")
    if doc.parse_error:
        add("warning", "frontmatter-parse", doc.parse_error)

    fields = doc.fields
    name = fields.get("name")
    description = fields.get("description")

    if not isinstance(name, str) or not name.strip():
        severity = "error" if profile.require_kebab_name else "warning"
        add(severity, "name-missing", "Frontmatter 'name' is missing or empty")
    else:
        if profile.require_kebab_name and not re.fullmatch(NAME_PATTERN, name):
            add(
                "error",
                "name-not-kebab",
                "%r is not lowercase kebab-case (required by OpenClaw)" % name,
            )
        if name != dir_name:
            severity = "error" if profile.dir_name_is_id and name.lower() != dir_name.lower() else "warning"
            add(
                severity,
                "name-dir-mismatch",
                "frontmatter name %r differs from directory %r" % (name, dir_name),
            )

    if not isinstance(description, str) or not description.strip():
        add("error", "description-missing", "Frontmatter 'description' is required for discovery")
    else:
        if "\n" in description.strip() and profile.description_single_line:
            add("error", "description-multiline", "OpenClaw requires a one-line description")
        if profile.description_max and len(description) > profile.description_max:
            add(
                "error",
                "description-too-long",
                "description is %d characters, limit is %d"
                % (len(description), profile.description_max),
            )
        if len(description.strip()) < 25:
            add(
                "warning",
                "description-weak",
                "description is under 25 characters and may not trigger reliably",
            )

    for key in doc.order:
        if key in profile.allowed:
            continue
        if profile.id in ("portable",) or key not in ALL_KNOWN_FIELDS:
            add(
                "error" if profile.id == "portable" else "warning",
                "non-spec-field" if profile.id == "portable" else "unknown-field",
                "frontmatter field %r is not valid for %s" % (key, profile.id),
            )
        else:
            hosts = sorted(other.id for other in all_profiles() if key in other.allowed)
            add(
                "warning",
                "host-specific-field",
                "frontmatter field %r is host-specific (supported by: %s)"
                % (key, ", ".join(hosts)),
            )

    metadata = fields.get("metadata")
    if isinstance(metadata, dict):
        for key in metadata:
            if not isinstance(key, str):
                continue
            for prefix in METADATA_HOST_KEYS:
                if key.startswith(prefix):
                    owner = prefix.rstrip("/")
                    if profile.id != owner:
                        add(
                            "warning",
                            "host-specific-metadata",
                            "metadata.%s targets %s, not %s" % (key, owner, profile.id),
                        )

    body = doc.body or ""
    for token in sorted(TOKENS):
        if token not in body:
            continue
        replacement = profile.token_map.get(token)
        if replacement is None:
            add(
                "error",
                "untranslatable-token",
                "%s has no equivalent in %s; rewrite the instruction manually"
                % (token, profile.id),
            )
        elif replacement != token:
            add(
                "info",
                "token-rewritten",
                "%s becomes %s in %s" % (token, replacement, profile.id),
            )

    if DYNAMIC_CONTEXT_PATTERN.search(body) and profile.id != "claude":
        add(
            "error",
            "untranslatable-dynamic-context",
            "Claude '!`command`' dynamic context is not supported in %s" % profile.id,
        )

    for match in PATH_PATTERN.finditer(body):
        if match.group(0) != profile.path_prefix:
            add(
                "warning",
                "host-specific-path",
                "path %r should be %r for %s"
                % (match.group(0), profile.path_prefix, profile.id),
            )

    return findings


def audit_path(path: os.PathLike, profile: Profile) -> List[dict]:
    """Audit one path (skill dir, file or tree). Returns JSON-ready records."""
    results: List[dict] = []
    for skill_dir in find_skill_dirs(path):
        skill_file = skill_dir / SKILL_FILE
        doc = read_doc(skill_file)
        findings = audit_doc(doc, profile, skill_dir.name, _short_path(skill_file))
        results.append(
            {
                "path": _short_path(skill_dir),
                "skill_file": _short_path(skill_file),
                "name": doc.get("name"),
                "findings": [item.as_dict() for item in findings],
            }
        )
    return results


def hosts_supporting(field: str, profiles: Sequence[Profile]) -> List[str]:
    return [profile.id for profile in profiles if field in profile.allowed]
