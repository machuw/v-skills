import tempfile
import textwrap
import unittest
from pathlib import Path

from scripts import sync_skills


class LoadConfigTests(unittest.TestCase):
    def test_load_config_includes_all_when_whitelist_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "skill-sync.yaml"
            config_path.write_text(
                textwrap.dedent(
                    """
                    sources:
                      repo-a:
                        whitelist: []
                        blacklist:
                          - skip-me
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            config = sync_skills.load_config(config_path)

            self.assertEqual(config["repo-a"].whitelist, [])
            self.assertEqual(config["repo-a"].blacklist, ["skip-me"])


class DiscoverSkillsTests(unittest.TestCase):
    def test_discover_skills_supports_repo_root_and_skills_subdir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sources_root = Path(tmp) / "sources"
            (sources_root / "repo-root" / "alpha").mkdir(parents=True)
            (sources_root / "repo-root" / "alpha" / "SKILL.md").write_text(
                "", encoding="utf-8"
            )
            (sources_root / "repo-subdir" / "skills" / "beta").mkdir(parents=True)
            (sources_root / "repo-subdir" / "skills" / "beta" / "SKILL.md").write_text(
                "", encoding="utf-8"
            )

            root_skills = sync_skills.discover_repo_skills(sources_root / "repo-root")
            subdir_skills = sync_skills.discover_repo_skills(sources_root / "repo-subdir")

            self.assertEqual(set(root_skills), {"alpha"})
            self.assertEqual(set(subdir_skills), {"beta"})
