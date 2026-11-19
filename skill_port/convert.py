"""Deterministic SKILL.md conversion between harness profiles."""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

from .audit import DYNAMIC_CONTEXT_PATTERN, METADATA_HOST_KEYS, PATH_PATTERN, SKILL_FILE, read_doc
from .errors import ToolError
from .findings import Finding
from .frontmatter import SkillDoc, dump
from .profiles import Profile

EXCLUDED_FILES = {SKILL_FILE, "PORT_REPORT.md"}
EXCLUDED_DIRS = {".git", "__pycache__", ".venv", "node_modules", ".DS_Store"}


@dataclass
class ConvertReport:
    """Human-readable trace of everything the converter changed."""

    source: str
    target: str
    dropped_fields: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    token_rewrites: List[str] = field(default_factory=list)
    untranslatable: List[str] = field(default_factory=list)
    copied_files: List[str] = field(default_factory=list)

    def markdown(self) -> str:
        lines = [
            "# skill-port conversion report",
            "",
            "- Source: `%s`" % self.source,
            "- Target: `%s`" % self.target,
            "",
            "## Dropped frontmatter fields",
            "",
        ]
        lines.extend("- `%s`" % item for item in self.dropped_fields or ["none"])
        lines.extend(["", "## Body rewrites", ""])
        lines.extend("- %s" % item for item in self.token_rewrites or ["none"])
        lines.extend(["", "## Notes", ""])
        lines.extend("- %s" % item for item in self.notes or ["none"])
        lines.extend(
            [
                "",
                "## Manual action required",
                "",
            ]
        )
        lines.extend(
            "- **%s** has no equivalent in the target harness. Rewrite the "
            "instruction before publishing." % item
            for item in self.untranslatable
            or ["none — converted skill is self-contained"]
        )
        lines.extend(["", "## Copied files", ""])
        lines.extend("- `%s`" % item for item in self.copied_files or ["none"])
        return "\n".join(lines) + "\n"


def _short_value(value: object) -> str:
    text = repr(value)
    return text if len(text) <= 90 else text[:87] + "..."


def rewrite_body(body: str, profile: Profile, report: ConvertReport) -> str:
    """Rewrite host tokens and skill paths in the Markdown body."""
    for token, replacement in sorted(profile.token_map.items(), key=lambda item: -len(item[0])):
        if token not in body:
            continue
        if replacement is None:
            if token not in report.untranslatable:
                report.untranslatable.append(token)
        elif replacement != token:
            body = body.replace(token, replacement)
            report.token_rewrites.append("%s -> %s" % (token, replacement))

    def replace_path(match: "re.Match[str]") -> str:
        old = match.group(0)
        if old == profile.path_prefix:
            return old
        note = "path %s -> %s" % (old, profile.path_prefix)
        if note not in report.notes:
            report.notes.append(note)
        return profile.path_prefix

    body = PATH_PATTERN.sub(replace_path, body)
    if DYNAMIC_CONTEXT_PATTERN.search(body):
        marker = "Claude !`command` dynamic context"
        if marker not in report.untranslatable:
            report.untranslatable.append(marker)
    return body


def _derive_description(body: str) -> str:
    for line in body.splitlines():
        candidate = line.strip().lstrip("#-*>` ").strip()
        if candidate:
            return candidate
    return ""


def convert_doc(doc: SkillDoc, profile: Profile, dir_name: str) -> Tuple[SkillDoc, ConvertReport]:
    """Convert a parsed skill to a target profile (no filesystem access)."""
    report = ConvertReport(
        source=doc.path or "<memory>",
        target=profile.id,
    )
    fields = dict(doc.fields)
    order = list(doc.order)

    for key in list(order):
        if key in profile.allowed:
            continue
        if key not in fields:
            continue
        report.dropped_fields.append("%s (%s)" % (key, _short_value(fields[key])))
        fields.pop(key)
        order.remove(key)

    metadata = fields.get("metadata")
    if isinstance(metadata, dict):
        cleaned = {
            key: value
            for key, value in metadata.items()
            if not (
                isinstance(key, str)
                and any(key.startswith(prefix) for prefix in METADATA_HOST_KEYS)
                and not key.startswith("%s/" % profile.id)
            )
        }
        removed = sorted(set(metadata) - set(cleaned))
        for key in removed:
            report.dropped_fields.append("metadata.%s (other host)" % key)
        if cleaned:
            fields["metadata"] = cleaned
        else:
            fields.pop("metadata", None)
            order = [key for key in order if key != "metadata"]

    name = fields.get("name")
    if not isinstance(name, str) or not name.strip():
        name = dir_name
        report.notes.append("name derived from directory: %s" % dir_name)
    if profile.require_kebab_name:
        normalised = re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")
        if normalised != name:
            report.notes.append("name normalised to kebab-case: %s -> %s" % (name, normalised))
            name = normalised
    fields["name"] = name
    if "name" not in order:
        order.insert(0, "name")

    description = fields.get("description")
    if not isinstance(description, str) or not description.strip():
        description = _derive_description(doc.body)
        report.notes.append("description derived from first body line")
    description = str(description)
    if profile.description_single_line:
        flattened = " ".join(description.split())
        if flattened != description:
            report.notes.append("description flattened to one line")
            description = flattened
    fields["description"] = description
    if "description" not in order:
        order.insert(1 if order and order[0] == "name" else 0, "description")

    body = rewrite_body(doc.body, profile, report)
    converted = SkillDoc(
        path=doc.path,
        fields=fields,
        order=order,
        body=body,
        has_frontmatter=True,
        raw="",
    )
    converted.raw = dump(fields, order, body)
    return converted, report


def _should_skip_dir(name: str) -> bool:
    return name in EXCLUDED_DIRS


def convert_tree(
    source_dir: os.PathLike,
    out_dir: os.PathLike,
    profile: Profile,
    force: bool = False,
    write_report: bool = True,
) -> Tuple[SkillDoc, ConvertReport, Path]:
    """Convert a skill folder into a ready-to-install folder."""
    source = Path(source_dir).expanduser().resolve()
    output = Path(out_dir).expanduser().resolve()
    skill_file = source / SKILL_FILE
    if not skill_file.is_file():
        raise ToolError("no SKILL.md in %s" % source)
    if source == output or source in output.parents:
        raise ToolError("output directory must not be inside the source directory")
    if output.exists() and not force:
        raise ToolError("output directory already exists: %s (use --force)" % output)

    doc = read_doc(skill_file)
    converted, report = convert_doc(doc, profile, source.name)
    output.mkdir(parents=True, exist_ok=True)

    copied: List[str] = []
    for root, dirs, files in os.walk(str(source)):
        dirs[:] = sorted(name for name in dirs if not _should_skip_dir(name))
        rel_root = Path(root).relative_to(source)
        for name in sorted(files):
            if name in EXCLUDED_FILES:
                continue
            rel = rel_root / name
            if rel == Path("."):
                continue
            dest = output / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(root) / name, dest, follow_symlinks=False)
            copied.append(rel.as_posix())

    _write_utf8(output / SKILL_FILE, converted.raw)
    report.copied_files = copied
    if write_report:
        _write_utf8(output / "PORT_REPORT.md", report.markdown())
    return converted, report, output


def _write_utf8(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def verdict(report: ConvertReport, profile: Profile) -> List[Finding]:
    """Turn a conversion report into deterministic findings."""
    findings: List[Finding] = []
    for item in report.untranslatable:
        findings.append(
            Finding("error", "manual-rewrite", item, profile.id, report.source)
        )
    for item in report.dropped_fields:
        findings.append(
            Finding("info", "field-dropped", item, profile.id, report.source)
        )
    return findings
