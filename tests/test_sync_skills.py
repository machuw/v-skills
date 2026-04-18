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


class SelectSkillsTests(unittest.TestCase):
    def test_select_repo_skills_applies_blacklist_after_whitelist(self) -> None:
        discovered = {
            "keep-me": Path("/tmp/keep-me"),
            "drop-me": Path("/tmp/drop-me"),
            "also-drop": Path("/tmp/also-drop"),
        }
        rule = sync_skills.RepoRule(
            whitelist=["keep-me", "drop-me"],
            blacklist=["drop-me"],
        )

        selected = sync_skills.select_repo_skills("repo-a", discovered, rule)

        self.assertEqual(selected, {"keep-me": Path("/tmp/keep-me")})

    def test_build_desired_skills_rejects_duplicate_names(self) -> None:
        repo_skill_map = {
            "repo-a": {"shared": Path("/tmp/repo-a/shared")},
            "repo-b": {"shared": Path("/tmp/repo-b/shared")},
        }

        with self.assertRaises(sync_skills.ConflictError):
            sync_skills.build_desired_skills(repo_skill_map)
