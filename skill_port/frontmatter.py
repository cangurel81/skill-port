"""Small YAML frontmatter reader/writer for SKILL.md files.

Only the subset used by skill frontmatter is implemented: mappings, sequences,
scalars and flow lists/maps. Standard library only, no PyYAML dependency.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

DELIMITER = "---"

_BOOL_TRUE = {"true", "yes", "on"}
_BOOL_FALSE = {"false", "no", "off"}
_NULL = {"null", "~"}
_QUOTE_START = set("-?:,[]{}#&*!|>'\"%@`")


@dataclass
class SkillDoc:
    """Parsed SKILL.md: frontmatter fields, body and source metadata."""

    path: Optional[str]
    fields: Dict[str, Any]
    order: List[str]
    body: str
    has_frontmatter: bool
    raw: str
    bom: bool = False
    parse_error: Optional[str] = None

    def get(self, key: str, default: Any = None) -> Any:
        return self.fields.get(key, default)


def parse(text: str, path: Optional[str] = None) -> SkillDoc:
    """Parse a SKILL.md string. Never raises on malformed YAML."""
    bom = text.startswith("\ufeff")
    if bom:
        text = text[1:]
    lines = text.split("\n")
    if not lines or lines[0].strip() != DELIMITER:
        return SkillDoc(path, {}, [], text, False, text, bom)

    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() in (DELIMITER, "..."):
            end = index
            break
    if end is None:
        return SkillDoc(
            path,
            {},
            [],
            text,
            True,
            text,
            bom,
            "frontmatter opening has no closing delimiter",
        )

    fields, warnings = parse_yaml_block(lines[1:end])
    body = "\n".join(lines[end + 1 :])
    error = "; ".join(warnings) if warnings else None
    return SkillDoc(path, fields, list(fields.keys()), body, True, text, bom, error)


def parse_yaml_block(block: List[str]) -> Tuple[Dict[str, Any], List[str]]:
    """Parse a YAML mapping block into an insertion-ordered dict."""
    lines = [
        line
        for line in block
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not lines:
        return {}, []
    value, _, warnings = _parse_block(lines, 0, _indent(lines[0]))
    if not isinstance(value, dict):
        return {}, warnings + ["frontmatter root is not a mapping"]
    return value, warnings


def dump(fields: Dict[str, Any], order: Optional[List[str]] = None, body: str = "") -> str:
    """Serialize fields and body back to SKILL.md text."""
    keys: List[str] = []
    for key in order or []:
        if key in fields and key not in keys:
            keys.append(key)
    for key in fields:
        if key not in keys:
            keys.append(key)

    out = [DELIMITER]
    for key in keys:
        out.extend(_emit_pair(key, fields[key], 0))
    out.append(DELIMITER)
    text = "\n".join(out) + "\n"
    return text + body


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _split_key(line: str) -> Optional[Tuple[str, str]]:
    index = line.find(":")
    if index <= 0:
        return None
    return line[:index].strip(), line[index + 1 :].strip()


def _split_flow(text: str) -> List[str]:
    parts: List[str] = []
    current: List[str] = []
    depth = 0
    quote = ""
    for char in text:
        if quote:
            current.append(char)
            if char == quote:
                quote = ""
            continue
        if char in "\"'":
            quote = char
            current.append(char)
        elif char in "[{":
            depth += 1
            current.append(char)
        elif char in "]}":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if current:
        parts.append("".join(current).strip())
    return parts


def _parse_scalar(raw: str) -> Any:
    raw = raw.strip()
    if not raw:
        return ""
    if raw[0] == "[" and raw[-1] == "]":
        inner = raw[1:-1].strip()
        return [_parse_scalar(part) for part in _split_flow(inner)] if inner else []
    if raw[0] == "{" and raw[-1] == "}":
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return raw  # keep unsupported flow maps verbatim
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        if raw[0] == '"':
            try:
                return json.loads(raw)
            except ValueError:
                return raw[1:-1]
        return raw[1:-1].replace("''", "'")
    low = raw.lower()
    if low in _BOOL_TRUE:
        return True
    if low in _BOOL_FALSE:
        return False
    if low in _NULL:
        return None
    if re.fullmatch(r"[-+]?\d+", raw):
        return int(raw)
    if re.fullmatch(r"[-+]?\d*\.\d+", raw):
        return float(raw)
    return raw


def _child_indent(lines: List[str], index: int, parent: int) -> int:
    if index >= len(lines):
        return parent + 2
    found = _indent(lines[index])
    if found > parent:
        return found
    if found == parent and lines[index].lstrip().startswith("- "):
        return found
    return parent + 2


def _parse_block(lines: List[str], start: int, indent: int) -> Tuple[Any, int, List[str]]:
    warnings: List[str] = []
    index = start
    if index >= len(lines) or _indent(lines[index]) < indent:
        return None, index, warnings

    if lines[index].lstrip().startswith("- "):
        items: List[Any] = []
        while index < len(lines):
            current = lines[index]
            if _indent(current) != indent or not current.lstrip().startswith("- "):
                break
            item = current.strip()[2:].strip()
            index += 1
            if not item:
                child_indent = _child_indent(lines, index, indent)
                if child_indent > indent:
                    child, index, notes = _parse_block(lines, index, child_indent)
                    warnings.extend(notes)
                    items.append(child)
                else:
                    items.append(None)
                continue
            pair = _split_key(item)
            if pair and not item.startswith(("{", "[")):
                key, value = pair
                if value:
                    items.append({key: _parse_scalar(value)})
                else:
                    child_indent = _child_indent(lines, index, indent)
                    if child_indent > indent:
                        child, index, notes = _parse_block(lines, index, child_indent)
                        warnings.extend(notes)
                        items.append({key: child})
                    else:
                        items.append({key: None})
            else:
                items.append(_parse_scalar(item))
        return items, index, warnings

    mapping: Dict[str, Any] = {}
    while index < len(lines):
        current = lines[index]
        if _indent(current) != indent or current.lstrip().startswith("- "):
            break
        pair = _split_key(current.strip())
        if pair is None:
            warnings.append("skipped unparsed line: %s" % current.strip())
            index += 1
            continue
        key, value = pair
        index += 1
        if value:
            mapping[key] = _parse_scalar(value)
            continue
        child_indent = _child_indent(lines, index, indent)
        if child_indent > indent or (
            child_indent == indent
            and index < len(lines)
            and lines[index].lstrip().startswith("- ")
        ):
            child, index, notes = _parse_block(lines, index, child_indent)
            warnings.extend(notes)
            mapping[key] = child
        else:
            mapping[key] = None
    return mapping, index, warnings


def _needs_quote(value: str) -> bool:
    if not value or value.strip() != value:
        return True
    if value[0] in _QUOTE_START:
        return True
    if ": " in value or " #" in value:
        return True
    low = value.lower()
    if low in _BOOL_TRUE or low in _BOOL_FALSE or low in _NULL:
        return True
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", value):
        return True
    return False


def _emit_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    return json.dumps(text, ensure_ascii=False) if _needs_quote(text) else text


def _emit_pair(key: str, value: Any, indent: int) -> List[str]:
    pad = " " * indent
    if isinstance(value, str) and "\n" in value:
        lines = ["%s%s: |" % (pad, key)]
        lines.extend("  " + pad + part for part in value.split("\n"))
        return lines
    if isinstance(value, dict) and value:
        lines = ["%s%s:" % (pad, key)]
        for sub_key, sub_value in value.items():
            lines.extend(_emit_pair(sub_key, sub_value, indent + 2))
        return lines
    if isinstance(value, list):
        if not value:
            return ["%s%s: []" % (pad, key)]
        lines = ["%s%s:" % (pad, key)]
        for item in value:
            if isinstance(item, dict) and item:
                sub_lines: List[str] = []
                for sub_key, sub_value in item.items():
                    sub_lines.extend(_emit_pair(sub_key, sub_value, indent + 2))
                sub_lines[0] = "%s- %s" % (pad, sub_lines[0][indent + 2 :])
                lines.extend(sub_lines)
            else:
                lines.append("%s- %s" % (pad, _emit_scalar(item)))
        return lines
    return ["%s%s: %s" % (pad, key, _emit_scalar(value))]
