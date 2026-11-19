import unittest

from skill_port.frontmatter import dump, parse, parse_yaml_block


class ParseTests(unittest.TestCase):
    def test_no_frontmatter(self):
        doc = parse("# Just markdown\n\nText.\n")
        self.assertFalse(doc.has_frontmatter)
        self.assertEqual(doc.fields, {})
        self.assertIn("# Just markdown", doc.body)

    def test_scalars_and_flow(self):
        doc = parse(
            "---\n"
            "name: demo\n"
            "description: Does a thing\n"
            "enabled: true\n"
            "count: 3\n"
            "ratio: 1.5\n"
            "empty: null\n"
            "tools: [Read, Grep]\n"
            "---\n"
            "body\n"
        )
        self.assertTrue(doc.has_frontmatter)
        self.assertEqual(doc.get("tools"), ["Read", "Grep"])
        self.assertIs(doc.get("enabled"), True)
        self.assertIs(doc.get("empty"), None)
        self.assertEqual(doc.get("count"), 3)
        self.assertEqual(doc.get("ratio"), 1.5)
        self.assertEqual(doc.body, "body\n")

    def test_nested_mapping_and_list(self):
        doc = parse(
            "---\n"
            "name: demo\n"
            "description: x\n"
            "metadata:\n"
            "  opencode/autoinvoke: false\n"
            "  tags:\n"
            "    - one\n"
            "    - two\n"
            "---\n"
        )
        metadata = doc.get("metadata")
        self.assertEqual(metadata["opencode/autoinvoke"], False)
        self.assertEqual(metadata["tags"], ["one", "two"])

    def test_bom_is_recorded(self):
        doc = parse("\ufeff---\nname: demo\n---\n")
        self.assertTrue(doc.bom)
        self.assertEqual(doc.get("name"), "demo")

    def test_unterminated_frontmatter(self):
        doc = parse("---\nname: demo\n")
        self.assertTrue(doc.has_frontmatter)
        self.assertIsNotNone(doc.parse_error)

    def test_quoted_colon(self):
        doc = parse('---\ndescription: "Use: this, now"\n---\n')
        self.assertEqual(doc.get("description"), "Use: this, now")

    def test_parse_yaml_block_rejects_scalar_root(self):
        fields, warnings = parse_yaml_block(["- one", "- two"])
        self.assertEqual(fields, {})
        self.assertTrue(warnings)


class DumpTests(unittest.TestCase):
    def test_round_trip_is_stable(self):
        source = (
            "---\n"
            "name: demo\n"
            "description: Does a thing\n"
            "allowed-tools: [Read, Grep]\n"
            "metadata:\n"
            "  nested: value\n"
            "---\n"
            "Instructions.\n"
        )
        doc = parse(source)
        once = dump(doc.fields, doc.order, doc.body)
        twice = dump(parse(once).fields, parse(once).order, parse(once).body)
        self.assertEqual(once, twice)

    def test_values_requiring_quotes(self):
        text = dump(
            {
                "name": "demo",
                "description": "Use: carefully",
                "flag": True,
                "num": 7,
                "empty": None,
            },
            ["name", "description", "flag", "num", "empty"],
            "",
        )
        self.assertIn('description: "Use: carefully"', text)
        self.assertIn("flag: true", text)
        self.assertIn("empty: null", text)

    def test_unicode_is_not_escaped(self):
        text = dump({"name": "demo", "description": "Türkçe açıklama"}, ["name", "description"])
        self.assertIn("Türkçe açıklama", text)
        self.assertNotIn("\\u", text)


if __name__ == "__main__":
    unittest.main()
