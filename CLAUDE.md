# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

`v-skills` is a **meta repository** that curates Claude / Codex "skills" from external repos and exposes them to the local machine:

1. Upstream skill repos are tracked as Git submodules under `sources/` (read-only mirrors — changes belong upstream).
2. `scripts/sync_skills.py` reads `config/skill-sync.yaml` and **symlinks** each selected skill into `~/.claude/skills` and `~/.codex/skills`, so edits in `sources/` flow through immediately.

The repo owns exactly three things: the submodule pointers, the curation config, and the sync script + its tests. There is no runtime application code beyond that.

## Repo layout

- `sources/*` — upstream skill repos (submodules). Two supported layouts coexist:
  - `sources/<repo>/skills/<skill>/SKILL.md` (e.g. `sources/obsidian-skills`)
  - `sources/<repo>/<skill>/SKILL.md` (e.g. `sources/axton-obsidian-visual-skills`)
- `config/skill-sync.yaml` — per-repo `whitelist` / `blacklist` curation rules.
- `scripts/sync_skills.py` — the sync tool (stdlib-only; uses PyYAML if importable, otherwise a small internal parser restricted to the config shape shown in the spec).
- `tests/test_sync_skills.py` — `unittest` suite covering config, discovery, selection, duplicate detection, symlink create/update/cleanup, and preflight rollback.
- `docs/superpowers/specs/2026-04-19-skill-sync-design.md` — design spec; source of truth for sync behavior.
- `docs/superpowers/plans/2026-04-19-skill-sync-implementation.md` — implementation plan.

## Common commands

```bash
# Initialize / refresh submodules
git submodule update --init --recursive
git submodule update --remote --merge   # pull upstream, then commit updated pointers

# Add a new upstream skill repo
git submodule add <git-url> sources/<repo-name>

# Run the sync (from repo root)
python3 scripts/sync_skills.py

# Run tests (from repo root so `from scripts import sync_skills` resolves)
python3 -m unittest discover -s tests

# Run a single test
python3 -m unittest tests.test_sync_skills.SyncTargetsTests.test_sync_creates_and_cleans_up_only_managed_links
```

## Sync tool invariants (load-bearing)

Any change to `scripts/sync_skills.py` must preserve these — they are what keeps the tool safe to run against a shared skills directory:

- **Symlinks, not copies.** Link the skill **directory** (so `assets/`, `references/` resolve), never just `SKILL.md`.
- **Fixed targets.** Always `~/.claude/skills` and `~/.codex/skills` (derived from `HOME`). Create them if missing.
- **Manifest-gated ownership.** The tool only removes or overwrites entries recorded in the manifest at `$XDG_STATE_HOME/v-skills/skill-sync-manifest.json` (fallback `~/.local/state/v-skills/skill-sync-manifest.json`). Anything else in the target dirs is user-managed and must not be touched. The manifest is machine-local — never commit it.
- **Preflight before mutate.** `sync_targets` validates every target root *before* writing anything, so a conflict in `~/.codex/skills` does not leave `~/.claude/skills` half-synced (see `test_sync_does_not_leave_partial_changes_when_preflight_fails`).
- **Manifest is written last**, only after all mutations succeed.
- **Fail fast** with `ConfigError` / `DiscoveryError` / `ConflictError` / `SyncError` on: malformed/missing config, missing configured repo dir, unknown skill names in whitelist/blacklist, duplicate skill names across repos, or a target path that exists but isn't a managed symlink.
- **Selection semantics:** empty/omitted `whitelist` ⇒ include all discovered; otherwise include only listed; `blacklist` always subtracts last. Unknown names in either list are an error, not a silent no-op.
- **Discovery order:** first `sources/<repo>/skills/*`, then direct children of `sources/<repo>/*`; in both cases a skill requires `SKILL.md`. Non-skill dirs like `.claude-plugin`, `assets`, `references` are implicitly skipped by that rule.

## Things to avoid

- Don't `git add` an upstream repo as a plain directory — always use `git submodule add`. The README has recovery steps if this happens.
- Don't hardcode PyYAML as a dependency; the fallback parser in `_parse_simple_yaml` is intentional so the script runs on a bare Python 3 install.
- Don't edit files under `sources/*` as part of this repo's workflow — submit upstream instead and bump the submodule pointer.
