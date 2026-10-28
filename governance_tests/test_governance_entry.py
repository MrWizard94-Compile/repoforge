"""Source onboarding checks, separate from customer product tests."""

import ast
import os
import re
import unittest
from pathlib import Path

ROOT = Path(os.environ.get("REPOFORGE_GOV_ROOT", Path(__file__).resolve().parents[1]))
SOURCE = "https://github.com/MrWizard94-Compile/Agents-Constitution"


class GovernanceTests(unittest.TestCase):
    def test_root_entry_loads_one_canonical_revision(self):
        entry = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        for required in (
            SOURCE,
            "accepted `main`",
            "wpai-constitution",
            "SOURCE",
            "always-load",
            "same revision",
            "not authority",
        ):
            with self.subTest(required=required):
                self.assertIn(required, entry)
        self.assertNotRegex(entry, r"(?i)binding\s+pack|pack\s+path")

    def test_product_stack_and_unpublished_authority_are_preserved(self):
        entry = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        for required in (
            "stdlib-only",
            "Python >=3.10",
            "Windows, macOS and Linux",
            "unpublished 1.1.0",
            "existing index",
            "director-controlled",
            "baseline/local-source-20260728",
            "Dry-run",
        ):
            with self.subTest(required=required):
                self.assertIn(required, entry)

    def test_retired_prepack_is_not_discoverable(self):
        self.assertFalse((ROOT / "AGENTS.md.legacy-pre-pack-20260727-205752").exists())

    def test_instruction_local_links_resolve(self):
        entry = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        links = re.findall(r"\[[^\]]*\]\(([^)]+)\)", entry)
        self.assertGreaterEqual(len(links), 5)
        for target in links:
            if not target.startswith("https://"):
                with self.subTest(target=target):
                    self.assertTrue((ROOT / target).is_file())

    def test_approved_product_contract_is_documented(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        adoption = ROOT / "docs/GOVERNANCE-ADOPTION.md"
        self.assertTrue(adoption.is_file())
        for required in (
            SOURCE,
            "pointer only",
            "retired",
            "before any",
            "--no-constitution",
            "not installed",
            "not download",
            "never recursively deletes",
        ):
            with self.subTest(required=required):
                self.assertIn(required, readme)

    def test_generator_has_no_pack_discovery_or_vendoring_implementation(self):
        source = (ROOT / "repoforge.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
        self.assertIn("validate_constitution_options", names)
        self.assertIn("agents_pointer_content", names)
        self.assertNotIn("discover_constitution_pack", names)
        self.assertNotIn("copy_constitution_pack", names)
        self.assertNotIn("shutil.rmtree", source)

    def test_source_ci_keeps_platforms_and_accepted_pin(self):
        path = ROOT / ".github/workflows/constitution.yml"
        self.assertTrue(path.is_file())
        workflow = path.read_text(encoding="utf-8")
        for required in (
            "ubuntu-24.04",
            "windows-2025",
            "macos-15",
            "'3.10'",
            "'3.14'",
            "'3.12'",
            "requirements-dev.txt",
            "-W error",
            "0010a8353b00754fad31a30ed24327d3b6d05425",
            "tools/check-adoption.py",
            "persist-credentials: false",
        ):
            with self.subTest(required=required):
                self.assertIn(required, workflow)
        for uses in re.findall(r"uses:\s+([^\s]+)", workflow):
            self.assertRegex(uses, r"@[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()
