"""Command line interface for skill-port."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Sequence

from . import __version__
from .audit import audit_path
from .convert import convert_tree, verdict
from .errors import ToolError
from .findings import Finding, count, sort_findings
from .install import default_root, install_skill
from .profiles import all_profiles, get_profile
from .verify import verify_skill

FAIL_CHOICES = ("error", "warning", "never")


def _emit_json(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False))


def _print_findings(findings: Sequence[Finding]) -> None:
    for item in findings:
        location = " %s" % item.path if item.path else ""
        print("[%s] %s %s%s" % (item.severity, item.code, item.message, location))


def _summary(findings: Sequence[Finding]) -> Dict[str, int]:
    return count(list(findings))


def _decide(findings: Sequence[Finding], fail_on: str) -> int:
    counts = count(list(findings))
    if fail_on == "never":
        return 0
    if fail_on == "warning":
        return 1 if counts["error"] + counts["warning"] else 0
    return 1 if counts["error"] else 0


def _base_payload(command: str, target: str, findings: Sequence[Finding]) -> Dict[str, Any]:
    return {
        "tool": "skill-port",
        "version": __version__,
        "command": command,
        "target": target,
        "summary": _summary(findings),
        "findings": [item.as_dict() for item in sort_findings(list(findings))],
    }


def cmd_targets(args: argparse.Namespace) -> int:
    profiles = all_profiles()
    rows = []
    for profile in profiles:
        row = {
            "id": profile.id,
            "label": profile.label,
            "install_path": profile.install_path,
            "allowed_fields": sorted(profile.allowed),
            "inert_fields": sorted(profile.inert),
            "description_max": profile.description_max,
            "description_single_line": profile.description_single_line,
            "require_kebab_name": profile.require_kebab_name,
            "path_prefix": profile.path_prefix,
            "untranslatable_tokens": sorted(
                token for token, replacement in profile.token_map.items() if replacement is None
            ),
        }
        rows.append(row)
    if args.json:
        _emit_json({"tool": "skill-port", "version": __version__, "targets": rows})
        return 0
    print("skill-port targets (%s)" % __version__)
    for row in rows:
        print("")
        print("%s - %s" % (row["id"], row["label"]))
        print("  install: %s" % row["install_path"])
        print("  fields: %s" % ", ".join(row["allowed_fields"]))
        print("  description max: %s" % (row["description_max"] or "unlimited"))
        print("  untranslatable: %s" % (", ".join(row["untranslatable_tokens"]) or "none"))
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    profile = get_profile(args.target)
    results = audit_path(args.path, profile)
    if not results:
        raise ToolError("no SKILL.md found under %s" % args.path)
    findings = [
        Finding(**item["findings"][index])
        for item in results
        for index in range(len(item["findings"]))
    ]
    findings = sort_findings(findings)
    if args.json:
        payload = _base_payload("audit", profile.id, findings)
        payload["skills"] = len(results)
        payload["paths"] = [item["path"] for item in results]
        _emit_json(payload)
    else:
        counts = count(findings)
        print("skill-port audit - %s" % os.path.abspath(args.path))
        print(
            "Target: %s | Skills: %d | errors: %d | warnings: %d | info: %d"
            % (profile.id, len(results), counts["error"], counts["warning"], counts["info"])
        )
        _print_findings(findings)
    return _decide(findings, args.fail_on)


def cmd_convert(args: argparse.Namespace) -> int:
    profile = get_profile(args.to)
    _, report, output = convert_tree(
        args.source,
        args.out,
        profile,
        force=args.force,
        write_report=not args.no_report,
    )
    findings = verdict(report, profile)
    if args.json:
        payload = _base_payload("convert", profile.id, findings)
        payload["output"] = str(output)
        payload["dropped_fields"] = report.dropped_fields
        payload["token_rewrites"] = report.token_rewrites
        payload["untranslatable"] = report.untranslatable
        payload["copied_files"] = report.copied_files
        _emit_json(payload)
    else:
        print("skill-port convert - %s -> %s" % (args.source, profile.id))
        print("Output: %s" % output)
        print("Dropped fields: %d" % len(report.dropped_fields))
        print("Token rewrites: %d" % len(report.token_rewrites))
        print("Manual rewrites needed: %d" % len(report.untranslatable))
        print("Copied files: %d" % len(report.copied_files))
        if not args.no_report:
            print("Report: %s" % (output / "PORT_REPORT.md"))
        _print_findings(findings)
    return _decide(findings, args.fail_on)


def cmd_verify(args: argparse.Namespace) -> int:
    profile = get_profile(args.target)
    findings = sort_findings(verify_skill(args.dir, profile))
    if args.json:
        payload = _base_payload("verify", profile.id, findings)
        payload["path"] = str(args.dir)
        _emit_json(payload)
    else:
        counts = count(findings)
        print("skill-port verify - %s" % os.path.abspath(args.dir))
        print(
            "Target: %s | errors: %d | warnings: %d | info: %d"
            % (profile.id, counts["error"], counts["warning"], counts["info"])
        )
        _print_findings(findings)
    return _decide(findings, args.fail_on)


def cmd_install(args: argparse.Namespace) -> int:
    profile = get_profile(args.to)
    root = args.root or default_root(profile)
    destination, report, findings = install_skill(
        args.source, profile, root=root, force=args.force
    )
    if args.json:
        payload = _base_payload("install", profile.id, findings)
        payload["destination"] = str(destination)
        payload["token_rewrites"] = report.token_rewrites
        payload["untranslatable"] = report.untranslatable
        _emit_json(payload)
    else:
        print("skill-port install - %s -> %s" % (args.source, profile.id))
        print("Destination: %s" % destination)
        print("Token rewrites: %d" % len(report.token_rewrites))
        _print_findings(findings)
    return _decide(findings, args.fail_on)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skill-port",
        description="Port SKILL.md skills between Claude Code, OpenCode and OpenClaw.",
    )
    parser.add_argument("--version", action="version", version="skill-port " + __version__)
    sub = parser.add_subparsers(dest="command")

    targets = sub.add_parser("targets", help="list supported harness profiles")
    targets.add_argument("--json", action="store_true")
    targets.set_defaults(func=cmd_targets)

    audit = sub.add_parser("audit", help="report portability findings for a skill or tree")
    audit.add_argument("path")
    audit.add_argument("--target", default="claude")
    audit.add_argument("--json", action="store_true")
    audit.add_argument("--fail-on", choices=FAIL_CHOICES, default="error")
    audit.set_defaults(func=cmd_audit)

    convert = sub.add_parser("convert", help="convert a skill folder to a target harness")
    convert.add_argument("source")
    convert.add_argument("--to", required=True)
    convert.add_argument("--out", required=True)
    convert.add_argument("--force", action="store_true")
    convert.add_argument("--no-report", action="store_true")
    convert.add_argument("--json", action="store_true")
    convert.add_argument("--fail-on", choices=FAIL_CHOICES, default="never")
    convert.set_defaults(func=cmd_convert)

    verify = sub.add_parser("verify", help="verify a converted or installed skill")
    verify.add_argument("dir")
    verify.add_argument("--target", default="claude")
    verify.add_argument("--json", action="store_true")
    verify.add_argument("--fail-on", choices=FAIL_CHOICES, default="error")
    verify.set_defaults(func=cmd_verify)

    install = sub.add_parser("install", help="convert and install into a harness skills root")
    install.add_argument("source")
    install.add_argument("--to", required=True)
    install.add_argument("--root", help="override the target skills root")
    install.add_argument("--force", action="store_true")
    install.add_argument("--json", action="store_true")
    install.add_argument("--fail-on", choices=FAIL_CHOICES, default="error")
    install.set_defaults(func=cmd_install)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    try:
        return int(args.func(args))
    except ToolError as exc:
        print("skill-port: %s" % exc, file=sys.stderr)
        return 2
