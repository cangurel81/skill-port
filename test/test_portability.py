import tempfile
import unittest
from pathlib import Path

from skill_port.audit import audit_doc, audit_path
from skill_port.convert import convert_tree
from skill_port.errors import ToolError
from skill_port.frontmatter import dump, parse
from skill_port.install import install_skill
from skill_port.profiles import get_profile
from skill_port.verify import verify_skill

GOOD_DESCRIPTION = "Audit and port skills between harnesses with a deterministic CLI."


def write_lf(path, text):
    """Path.write_text(newline=...) needs Python 3.10; CI also runs 3.9."""
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def write_skill(root, name="demo", fields=None, body="Instructions.\n", extra=None):
    folder = Path(root) / name
    folder.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = {"name": name, "description": GOOD_DESCRIPTION}
    text = dump(fields, list(fields), body)
    write_lf(folder / "SKILL.md", text)
    for relative, content in (extra or {}).items():
        path = folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        write_lf(path, content)
    return folder


class AuditTests(unittest.TestCase):
    def test_portable_skill_is_clean(self):
        folder = write_skill(tempfile.mkdtemp())
        doc = parse((folder / "SKILL.md").read_text(encoding="utf-8"))
        findings = audit_doc(doc, get_profile("portable"), folder.name)
        self.assertEqual([item.code for item in findings if item.severity == "error"], [])

    def test_claude_only_fields_are_errors_for_portable(self):
        fields = {
            "name": "demo",
            "description": GOOD_DESCRIPTION,
            "allowed-tools": "Read Grep",  # valid in both Claude and portable
            "disable-model-invocation": True,  # Claude/OpenCode/OpenClaw only
            "model": "sonnet",  # Claude local only
        }
        folder = write_skill(tempfile.mkdtemp(), fields=fields)
        doc = parse((folder / "SKILL.md").read_text(encoding="utf-8"))
        portable = audit_doc(doc, get_profile("portable"), folder.name)
        claude = audit_doc(doc, get_profile("claude"), folder.name)
        self.assertIn(
            "non-spec-field",
            [item.code for item in portable if item.severity == "error"],
        )
        self.assertEqual(
            [item.code for item in claude if item.severity == "error"], []
        )

    def test_openclaw_enforces_name_and_description(self):
        fields = {
            "name": "Demo Skill",
            "description": "x" * 200,
        }
        folder = write_skill(tempfile.mkdtemp(), fields=fields)
        doc = parse((folder / "SKILL.md").read_text(encoding="utf-8"))
        codes = [item.code for item in audit_doc(doc, get_profile("openclaw"), folder.name)]
        self.assertIn("name-not-kebab", codes)
        self.assertIn("description-too-long", codes)

    def test_untranslatable_token_is_an_error_outside_claude(self):
        body = "Read $ARGUMENTS then continue.\n"
        folder = write_skill(tempfile.mkdtemp(), body=body)
        doc = parse((folder / "SKILL.md").read_text(encoding="utf-8"))
        portable = audit_doc(doc, get_profile("portable"), folder.name)
        claude = audit_doc(doc, get_profile("claude"), folder.name)
        self.assertIn(
            "untranslatable-token",
            [item.code for item in portable if item.severity == "error"],
        )
        self.assertNotIn(
            "untranslatable-token",
            [item.code for item in claude if item.severity == "error"],
        )

    def test_audit_path_finds_nested_skills(self):
        root = Path(tempfile.mkdtemp())
        write_skill(root, name="alpha")
        write_skill(root / "vendor", name="beta")
        results = audit_path(root, get_profile("portable"))
        self.assertEqual(len(results), 2)
        self.assertEqual(
            sorted(Path(item["path"]).name for item in results), ["alpha", "beta"]
        )


class ConvertTests(unittest.TestCase):
    def test_convert_drops_fields_and_reports_manual_work(self):
        fields = {
            "name": "demo",
            "description": GOOD_DESCRIPTION,
            "allowed-tools": "Read Grep",  # portable keeps this
            "disable-model-invocation": True,
            "model": "sonnet",  # Claude-only, must be dropped
            "metadata": {"opencode/autoinvoke": False, "team": "core"},
        }
        body = (
            "Run `${CLAUDE_SKILL_DIR}/scripts/run.sh` with $ARGUMENTS.\n"
            "See `.claude/skills/other/SKILL.md`.\n"
        )
        source = write_skill(
            tempfile.mkdtemp(), fields=fields, body=body,
            extra={"scripts/run.sh": "echo hi\n"},
        )
        out = Path(tempfile.mkdtemp()) / "out"
        _, report, output = convert_tree(source, out, get_profile("portable"))

        self.assertIn("model (", " ".join(report.dropped_fields))
        self.assertIn("disable-model-invocation (", " ".join(report.dropped_fields))
        self.assertNotIn("allowed-tools (", " ".join(report.dropped_fields))
        self.assertIn("metadata.opencode/autoinvoke", " ".join(report.dropped_fields))
        self.assertIn("$ARGUMENTS", report.untranslatable)
        self.assertIn("${CLAUDE_SKILL_DIR} -> .", report.token_rewrites)
        self.assertIn("scripts/run.sh", report.copied_files)
        self.assertTrue((output / "PORT_REPORT.md").is_file())

        converted = parse((output / "SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(
            set(converted.fields) - {"metadata"},
            {"name", "description", "allowed-tools"},
        )
        self.assertEqual(converted.get("allowed-tools"), "Read Grep")
        self.assertEqual(converted.get("metadata"), {"team": "core"})
        self.assertIn("`./scripts/run.sh`", converted.body)
        self.assertIn("`skills/other/SKILL.md`", converted.body)

    def test_convert_is_deterministic(self):
        fields = {
            "name": "Demo",
            "description": GOOD_DESCRIPTION,
            "allowed-tools": "Read",
        }
        source = write_skill(tempfile.mkdtemp(), fields=fields)
        base = Path(tempfile.mkdtemp())
        _, _, first = convert_tree(source, base / "one", get_profile("openclaw"))
        _, _, second = convert_tree(source, base / "two", get_profile("openclaw"))
        self.assertEqual(
            (first / "SKILL.md").read_bytes(), (second / "SKILL.md").read_bytes()
        )
        converted = parse((first / "SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(converted.get("name"), "demo")

    def test_convert_refuses_existing_output_without_force(self):
        source = write_skill(tempfile.mkdtemp())
        out = Path(tempfile.mkdtemp()) / "out"
        out.mkdir()
        with self.assertRaises(ToolError):
            convert_tree(source, out, get_profile("claude"))
        _, _, output = convert_tree(source, out, get_profile("claude"), force=True)
        self.assertEqual(output, out.resolve())

    def test_convert_rejects_output_inside_source(self):
        source = write_skill(tempfile.mkdtemp())
        with self.assertRaises(ToolError):
            convert_tree(source, source / "nested", get_profile("claude"))


class VerifyAndInstallTests(unittest.TestCase):
    def test_verify_detects_missing_and_present_assets(self):
        body = "Run `scripts/run.sh`.\n"
        source = write_skill(tempfile.mkdtemp(), body=body)
        profile = get_profile("portable")
        codes = [item.code for item in verify_skill(source, profile)]
        self.assertIn("missing-asset", codes)
        write_skill(source.parent, name=source.name, body=body,
                    extra={"scripts/run.sh": "echo hi\n"})
        codes = [item.code for item in verify_skill(source, profile)]
        self.assertNotIn("missing-asset", codes)

    def test_install_uses_target_root_and_force(self):
        source = write_skill(tempfile.mkdtemp())
        root = Path(tempfile.mkdtemp()) / "skills"
        destination, report, findings = install_skill(
            source, get_profile("claude"), root=root
        )
        self.assertEqual(destination, (root / "demo").resolve())
        self.assertTrue((destination / "SKILL.md").is_file())
        self.assertFalse((destination / "PORT_REPORT.md").exists())
        self.assertEqual([item for item in findings if item.severity == "error"], [])
        with self.assertRaises(ToolError):
            install_skill(source, get_profile("claude"), root=root)
        _, _, _ = install_skill(source, get_profile("claude"), root=root, force=True)
        self.assertTrue(destination.is_dir())


if __name__ == "__main__":
    unittest.main()
