# Skill Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repository-local Python sync tool that symlinks selected skills from `sources/` into `~/.claude/skills` and `~/.codex/skills` using YAML-configured white/blacklists and a machine-local manifest.

**Architecture:** Keep the implementation in a single focused script with pure helper functions for config loading, discovery, selection, manifest handling, and sync application. Cover behavior with stdlib `unittest` tests using temporary directories and explicit environment overrides so the real home directory is never touched during tests.

**Tech Stack:** Python 3.13, `unittest`, `tempfile`, `pathlib`, symlinks, YAML config with dependency-free fallback parsing for the repo's limited config shape.

---

### Task 1: Add failing tests for config loading and skill discovery

**Files:**
- Create: `tests/test_sync_skills.py`
- Test: `tests/test_sync_skills.py`

- [ ] **Step 1: Write the failing tests for config and discovery**

```python
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
            (sources_root / "repo-root" / "alpha" / "SKILL.md").write_text("", encoding="utf-8")
            (sources_root / "repo-subdir" / "skills" / "beta").mkdir(parents=True)
            (sources_root / "repo-subdir" / "skills" / "beta" / "SKILL.md").write_text("", encoding="utf-8")

            root_skills = sync_skills.discover_repo_skills(sources_root / "repo-root")
            subdir_skills = sync_skills.discover_repo_skills(sources_root / "repo-subdir")

            self.assertEqual(set(root_skills), {"alpha"})
            self.assertEqual(set(subdir_skills), {"beta"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_sync_skills.LoadConfigTests tests.test_sync_skills.DiscoverSkillsTests -v`
Expected: FAIL with import or missing attribute errors because `scripts/sync_skills.py` does not exist yet.

- [ ] **Step 3: Write minimal implementation for config loading and discovery**

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RepoRule:
    whitelist: list[str]
    blacklist: list[str]


def load_config(config_path: Path) -> dict[str, RepoRule]:
    data = _load_yaml_like(config_path)
    return {
        repo_name: RepoRule(
            whitelist=list(rule_data.get("whitelist") or []),
            blacklist=list(rule_data.get("blacklist") or []),
        )
        for repo_name, rule_data in data["sources"].items()
    }


def discover_repo_skills(repo_path: Path) -> dict[str, Path]:
    discovered: dict[str, Path] = {}
    for base_dir in [repo_path / "skills", repo_path]:
        if not base_dir.exists():
            continue
        for child in base_dir.iterdir():
            if child.is_dir() and (child / "SKILL.md").is_file():
                discovered[child.name] = child.resolve()
    return discovered
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_sync_skills.LoadConfigTests tests.test_sync_skills.DiscoverSkillsTests -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_sync_skills.py scripts/sync_skills.py
git commit -m "test: add config and discovery coverage for skill sync"
```

### Task 2: Add failing tests for whitelist/blacklist selection and duplicate detection

**Files:**
- Modify: `tests/test_sync_skills.py`
- Modify: `scripts/sync_skills.py`
- Test: `tests/test_sync_skills.py`

- [ ] **Step 1: Write the failing tests for selection rules**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_sync_skills.SelectSkillsTests -v`
Expected: FAIL because `select_repo_skills`, `build_desired_skills`, and `ConflictError` are not implemented yet.

- [ ] **Step 3: Write minimal implementation for selection and duplicate checks**

```python
class ConflictError(RuntimeError):
    pass


def select_repo_skills(
    repo_name: str,
    discovered: dict[str, Path],
    rule: RepoRule,
) -> dict[str, Path]:
    unknown = (set(rule.whitelist) | set(rule.blacklist)) - set(discovered)
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ConfigError(f"{repo_name}: unknown skills in config: {names}")

    selected_names = set(discovered) if not rule.whitelist else set(rule.whitelist)
    selected_names -= set(rule.blacklist)
    return {name: discovered[name] for name in sorted(selected_names)}


def build_desired_skills(repo_skill_map: dict[str, dict[str, Path]]) -> dict[str, Path]:
    desired: dict[str, Path] = {}
    for repo_name, repo_skills in repo_skill_map.items():
        for skill_name, skill_path in repo_skills.items():
            if skill_name in desired:
                raise ConflictError(
                    f"duplicate skill '{skill_name}' discovered while merging {repo_name}"
                )
            desired[skill_name] = skill_path
    return desired
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_sync_skills.SelectSkillsTests -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_sync_skills.py scripts/sync_skills.py
git commit -m "test: cover selection and duplicate handling"
```

### Task 3: Add failing tests for manifest-backed symlink sync

**Files:**
- Modify: `tests/test_sync_skills.py`
- Modify: `scripts/sync_skills.py`
- Test: `tests/test_sync_skills.py`

- [ ] **Step 1: Write the failing sync tests**

```python
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

            sync_skills.sync_targets(
                {"skill-two": source_two},
                [claude_dir, codex_dir],
                state_path,
            )

            self.assertFalse((claude_dir / "skill-one").exists())
            self.assertTrue((claude_dir / "skill-two").is_symlink())
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_sync_skills.SyncTargetsTests -v`
Expected: FAIL because manifest and sync helpers are not implemented yet.

- [ ] **Step 3: Write minimal implementation for manifest-backed sync**

```python
import json


def sync_targets(desired: dict[str, Path], target_roots: list[Path], manifest_path: Path) -> None:
    manifest = load_manifest(manifest_path)
    updated = {"version": 1, "managed": {}}

    for target_root in target_roots:
        target_root.mkdir(parents=True, exist_ok=True)
        target_key = str(target_root.resolve())
        previous = manifest["managed"].get(target_key, {})
        updated["managed"][target_key] = {}

        for skill_name, source_path in desired.items():
            link_path = target_root / skill_name
            ensure_managed_link(link_path, source_path.resolve(), previous)
            updated["managed"][target_key][skill_name] = {
                "link_path": str(link_path.resolve(strict=False)),
                "source_path": str(source_path.resolve()),
            }

        remove_stale_managed_links(previous, desired, manifest_path)

    write_manifest(manifest_path, updated)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_sync_skills.SyncTargetsTests -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_sync_skills.py scripts/sync_skills.py
git commit -m "feat: sync managed skill symlinks with manifest"
```

### Task 4: Add the CLI entrypoint and default config file

**Files:**
- Modify: `scripts/sync_skills.py`
- Create: `config/skill-sync.yaml`
- Test: `tests/test_sync_skills.py`

- [ ] **Step 1: Write the failing CLI test**

```python
class MainTests(unittest.TestCase):
    def test_main_uses_repo_config_and_default_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            config_dir = repo_root / "config"
            config_dir.mkdir()
            (config_dir / "skill-sync.yaml").write_text(
                textwrap.dedent(
                    """
                    sources:
                      repo-a:
                        whitelist: []
                        blacklist: []
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )
            skill_dir = repo_root / "sources" / "repo-a" / "skill-one"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("", encoding="utf-8")

            env = {
                "HOME": str(repo_root),
                "XDG_STATE_HOME": str(repo_root / ".state"),
            }

            exit_code = sync_skills.main(repo_root=repo_root, env=env)

            self.assertEqual(exit_code, 0)
            self.assertTrue((repo_root / ".claude" / "skills" / "skill-one").is_symlink())
            self.assertTrue((repo_root / ".codex" / "skills" / "skill-one").is_symlink())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_sync_skills.MainTests -v`
Expected: FAIL because `main` and default path resolution are incomplete.

- [ ] **Step 3: Write minimal CLI implementation and config seed**

```python
def main(repo_root: Path | None = None, env: dict[str, str] | None = None) -> int:
    repo_root = (repo_root or Path(__file__).resolve().parent.parent).resolve()
    env = dict(os.environ if env is None else env)
    config = load_config(repo_root / "config" / "skill-sync.yaml")
    desired = collect_desired_skills(repo_root / "sources", config)
    target_roots = [
        Path(env["HOME"]) / ".claude" / "skills",
        Path(env["HOME"]) / ".codex" / "skills",
    ]
    manifest_path = resolve_manifest_path(env)
    sync_targets(desired, target_roots, manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

```yaml
sources:
  obsidian-skills:
    whitelist: []
    blacklist: []

  axton-obsidian-visual-skills:
    whitelist: []
    blacklist: []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_sync_skills.MainTests -v`
Expected: PASS

- [ ] **Step 5: Run the full test suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS

- [ ] **Step 6: Run the real repository smoke test**

Run: `python3 scripts/sync_skills.py`
Expected: exit code 0 and symlinks created under `~/.claude/skills` and `~/.codex/skills`

- [ ] **Step 7: Commit**

```bash
git add scripts/sync_skills.py config/skill-sync.yaml tests/test_sync_skills.py
git commit -m "feat: add skill sync tool"
```

## Self-Review

- Spec coverage: the plan covers repository discovery, YAML-configured selection, duplicate detection, managed-manifest cleanup, default target directories, and a real smoke test.
- Placeholder scan: no `TODO`/`TBD` markers remain; each task has concrete files, commands, and code to start from.
- Type consistency: the plan uses `RepoRule`, `ConfigError`, `ConflictError`, `SyncError`, `load_config`, `discover_repo_skills`, `select_repo_skills`, `build_desired_skills`, `sync_targets`, and `main` consistently across tasks.
