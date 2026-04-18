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


class SyncTargetsTests(unittest.TestCase):
    def test_sync_creates_and_cleans_up_only_managed_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            source_one = repo_root / "sources" / "repo-a" / "skill-one"
            source_two = repo_root / "sources" / "repo-a" / "skill-two"
            source_one.mkdir(parents=True)
            source_two.mkdir(parents=True)
            (source_one / "SKILL.md").write_text("", encoding="utf-8")
            (source_two / "SKILL.md").write_text("", encoding="utf-8")

            claude_dir = repo_root / ".claude" / "skills"
            codex_dir = repo_root / ".codex" / "skills"
            state_path = repo_root / ".state" / "skill-sync-manifest.json"

            sync_skills.sync_targets(
                {"skill-one": source_one, "skill-two": source_two},
                [claude_dir, codex_dir],
                state_path,
            )

            self.assertTrue((claude_dir / "skill-one").is_symlink())
            self.assertEqual((claude_dir / "skill-one").resolve(), source_one.resolve())

            sync_skills.sync_targets(
                {"skill-two": source_two},
                [claude_dir, codex_dir],
                state_path,
            )

            self.assertFalse((claude_dir / "skill-one").exists())
            self.assertTrue((claude_dir / "skill-two").is_symlink())
            self.assertEqual((claude_dir / "skill-two").resolve(), source_two.resolve())
            self.assertTrue((codex_dir / "skill-two").is_symlink())

    def test_sync_rejects_unmanaged_existing_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            source_skill = repo_root / "sources" / "repo-a" / "skill-one"
            source_skill.mkdir(parents=True)
            (source_skill / "SKILL.md").write_text("", encoding="utf-8")

            claude_dir = repo_root / ".claude" / "skills"
            claude_dir.mkdir(parents=True)
            (claude_dir / "skill-one").write_text("manual", encoding="utf-8")

            with self.assertRaises(sync_skills.SyncError):
                sync_skills.sync_targets(
                    {"skill-one": source_skill},
                    [claude_dir],
                    repo_root / ".state" / "skill-sync-manifest.json",
                )

    def test_sync_does_not_leave_partial_changes_when_preflight_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            source_skill = repo_root / "sources" / "repo-a" / "skill-one"
            source_skill.mkdir(parents=True)
            (source_skill / "SKILL.md").write_text("", encoding="utf-8")

            claude_dir = repo_root / ".claude" / "skills"
            codex_dir = repo_root / ".codex" / "skills"
            codex_dir.mkdir(parents=True)
            (codex_dir / "skill-one").write_text("manual", encoding="utf-8")

            with self.assertRaises(sync_skills.SyncError):
                sync_skills.sync_targets(
                    {"skill-one": source_skill},
                    [claude_dir, codex_dir],
                    repo_root / ".state" / "skill-sync-manifest.json",
                )

            self.assertFalse((claude_dir / "skill-one").exists())
