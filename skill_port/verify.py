"""Deterministic post-conversion / post-install verification."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List

from .audit import SKILL_FILE, audit_doc, read_doc
from .findings import Finding
from .profiles import Profile

ASSET_PREFIXES = ("scripts/", "references/", "assets/", "templates/")
BACKTICK_PATH = re.compile(r"`([^`\n]+)`")
LINK_PATH = re.compile(r"\]\(([^)\n]+)\)")


def _candidate_paths(body: str) -> List[str]:
    found: List[str] = []
    for pattern in (BACKTICK_PATH, LINK_PATH):
        for match in pattern.finditer(body):
            found.append(match.group(1).strip())
    return found


def _local_asset(candidate: str) -> str:
    value = candidate.strip().strip("<>").split("#", 1)[0].split("?", 1)[0]
    for prefix in ("{baseDir}/", "./", "/"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
    if value.startswith(".") and "/" in value:
        value = value.split("/", 1)[1]
    if value.startswith(ASSET_PREFIXES):
        return value
    return ""


def verify_skill(skill_dir: os.PathLike, profile: Profile) -> List[Finding]:
    """Audit a skill folder and check that referenced local files exist."""
    folder = Path(skill_dir).expanduser()
    skill_file = folder / SKILL_FILE
    if not skill_file.is_file():
        return [
            Finding(
                "error",
                "skill-md-missing",
                "%s not found" % SKILL_FILE,
                profile.id,
                str(folder),
            )
        ]

    doc = read_doc(skill_file)
    findings = audit_doc(doc, profile, folder.name, str(skill_file))

    if not doc.has_frontmatter:
        findings.append(
            Finding(
                "error",
                "frontmatter-not-first",
                "frontmatter must start on the first line",
                profile.id,
                str(skill_file),
            )
        )

    for candidate in _candidate_paths(doc.body):
        asset = _local_asset(candidate)
        if asset and not (folder / asset).is_file():
            findings.append(
                Finding(
                    "error",
                    "missing-asset",
                    "referenced file %r does not exist" % asset,
                    profile.id,
                    str(skill_file),
                )
            )

    return findings
