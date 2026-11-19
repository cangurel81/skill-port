import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from skill_port.cli import main
from skill_port.frontmatter import dump

GOOD_DESCRIPTION = "Audit and port skills between harnesses with a deterministic CLI."


def make_source(fields=None, body="Instructions.\n"):
    root = Path(tempfile.mkdtemp()) / "demo"
    root.mkdir(parents=True)
    if fields is None:
        fields = {"name": "demo", "description": GOOD_DESCRIPTION}
    (root / "SKILL.md").write_text(dump(fields, list(fields), body), encoding="utf-8", newline="\n")
    return root


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class CliTests(unittest.TestCase):
    def test_targets_json(self):
        code, out, _ = run(["targets", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(
            [row["id"] for row in payload["targets"]],
            ["claude", "portable", "opencode", "openclaw"],
        )
        self.assertIn("$ARGUMENTS", next(
            row for row in payload["targets"] if row["id"] == "portable"
        )["untranslatable_tokens"])

    def test_no_command_prints_help(self):
        code, out, _ = run([])
        self.assertEqual(code, 0)
        self.assertIn("usage: skill-port", out)

    def test_audit_exit_codes_and_json(self):
        source = make_source({
            "name": "demo",
            "description": GOOD_DESCRIPTION,
            "model": "sonnet",  # Claude-only; portable rejects it
            "allowed-tools": "Read",  # portable accepts this
        })
        code, out, _ = run(["audit", str(source), "--target", "portable", "--json"])
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertEqual(payload["command"], "audit")
        self.assertEqual(payload["skills"], 1)
        self.assertGreater(payload["summary"]["error"], 0)

        code, _, _ = run([
            "audit", str(source), "--target", "claude", "--fail-on", "never"
        ])
        self.assertEqual(code, 0)

    def test_convert_and_verify_json(self):
        source = make_source(body="Run `${CLAUDE_SKILL_DIR}/scripts/run.sh`.\n")
        out_dir = Path(tempfile.mkdtemp()) / "converted"
        code, out, _ = run([
            "convert", str(source), "--to", "portable", "--out", str(out_dir), "--json"
        ])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["output"], str(out_dir.resolve()))
        self.assertIn("${CLAUDE_SKILL_DIR} -> .", payload["token_rewrites"])

        code, verify_out, _ = run([
            "verify", str(out_dir), "--target", "portable", "--json"
        ])
        self.assertEqual(code, 1)  # referenced script was not copied
        self.assertIn("missing-asset", verify_out)

    def test_install_json(self):
        source = make_source()
        root = Path(tempfile.mkdtemp()) / "skills"
        code, out, _ = run([
            "install", str(source), "--to", "opencode", "--root", str(root), "--json"
        ])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["destination"], str((root / "demo").resolve()))

    def test_unknown_target_is_tool_error(self):
        source = make_source()
        code, _, err = run(["audit", str(source), "--target", "nope"])
        self.assertEqual(code, 2)
        self.assertIn("unknown target", err)

    def test_missing_skill_md_is_tool_error(self):
        empty = Path(tempfile.mkdtemp())
        code, _, err = run(["audit", str(empty)])
        self.assertEqual(code, 2)
        self.assertIn("no SKILL.md found", err)

    def test_version(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as caught:
            main(["--version"])
        self.assertEqual(caught.exception.code, 0)
        self.assertIn("skill-port 1.0.0", out.getvalue())


if __name__ == "__main__":
    unittest.main()
