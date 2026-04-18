# Skill Sync Design

## Goal

Add a repository-local sync tool that links selected skills from `sources/` into:

- `~/.claude/skills`
- `~/.codex/skills`

The sync must use symbolic links instead of copying files, so updates in `sources/` are reflected immediately through the linked directories.

## Scope

This design covers:

- A Python 3 sync script
- A YAML configuration file for per-repository allow/deny rules
- Safe cleanup of links previously created by the script
- Conflict detection for duplicate skill names across repositories

This design does not include:

- Installing Git submodules
- Downloading dependencies automatically
- Syncing anything outside `~/.claude/skills` and `~/.codex/skills`

## Requirements

### Functional

1. The tool must scan `sources/` for skill directories.
2. The tool must support both repository layouts currently present in this repo:
   - `sources/<repo>/skills/<skill-name>/SKILL.md`
   - `sources/<repo>/<skill-name>/SKILL.md`
3. The tool must read a YAML config file that configures repositories independently.
4. Each repository config must support `whitelist` and `blacklist`.
5. If `whitelist` is missing or empty for a configured repository, all discovered skills from that repository are eligible.
6. If `whitelist` is present and non-empty, only listed skills are eligible.
7. `blacklist` must always exclude listed skills, even if they also appear in `whitelist`.
8. The tool must create symlinks for eligible skills in both target directories.
9. If two repositories produce the same final skill name, the tool must fail with an error before changing target directories.
10. The tool must remove links that are no longer selected only if those links were created by this tool earlier.
11. The tool must not remove or overwrite manually managed files or symlinks in the target directories.

### Operational

1. The tool should run as:

```bash
python3 scripts/sync_skills.py
```

2. The tool should use a repository-local config file:

```text
config/skill-sync.yaml
```

3. The tool should create target directories if they do not exist.
4. The tool should fail fast with clear errors for invalid config, missing sources, duplicate names, or unmanaged path conflicts.

## Configuration

### File

```text
config/skill-sync.yaml
```

### Shape

```yaml
sources:
  obsidian-skills:
    whitelist: []
    blacklist:
      - defuddle

  axton-obsidian-visual-skills:
    whitelist:
      - excalidraw-diagram
      - mermaid-visualizer
    blacklist: []
```

### Semantics

- `sources` maps repository directory names under `sources/` to sync rules.
- Repositories not listed in `sources` are skipped.
- `whitelist` omitted or empty means "include every discovered skill from that repository".
- `whitelist` non-empty means "include only these skill names".
- `blacklist` omitted or empty means "exclude nothing".
- Final repository selection is:

```text
(all discovered skills or whitelist result) - blacklist
```

- Listing a skill in `whitelist` or `blacklist` that does not exist should be treated as an error. This keeps the config honest and avoids silent mistakes.

## Discovery Rules

For each configured repository under `sources/`, the tool should discover skills using this order:

1. If `sources/<repo>/skills/` exists, treat each direct child directory containing `SKILL.md` as a skill.
2. Also inspect direct child directories under `sources/<repo>/` and treat any directory containing `SKILL.md` as a skill.
3. Ignore non-skill directories such as `.claude-plugin`, `assets`, `references`, and any directory that does not contain `SKILL.md`.

This allows the current repositories to work without special-case configuration:

- `sources/obsidian-skills/skills/*`
- `sources/axton-obsidian-visual-skills/*`

## Output Targets

The sync output is always written to:

- `~/.claude/skills`
- `~/.codex/skills`

For each selected skill `<name>`, the tool creates:

- `~/.claude/skills/<name>` -> absolute path to the source skill directory
- `~/.codex/skills/<name>` -> absolute path to the source skill directory

The symlink target should be the skill directory, not just `SKILL.md`, so references and assets remain available.

## Managed State

The tool needs a manifest so it can distinguish its own links from manually managed entries.

### Manifest Location

```text
$XDG_STATE_HOME/v-skills/skill-sync-manifest.json
```

If `XDG_STATE_HOME` is not set, the tool should fall back to:

```text
~/.local/state/v-skills/skill-sync-manifest.json
```

If the parent directory does not exist, the tool creates it.

### Manifest Contents

The manifest should record, at minimum:

- Tool version or schema version
- Managed targets for each destination root
- Skill name
- Absolute symlink path
- Absolute source path the link should point to

Example shape:

```json
{
  "version": 1,
  "managed": {
    "/Users/example/.claude/skills": {
      "mermaid-visualizer": {
        "link_path": "/Users/example/.claude/skills/mermaid-visualizer",
        "source_path": "/Users/example/workspaces/v-skills/sources/axton-obsidian-visual-skills/mermaid-visualizer"
      }
    },
    "/Users/example/.codex/skills": {
      "mermaid-visualizer": {
        "link_path": "/Users/example/.codex/skills/mermaid-visualizer",
        "source_path": "/Users/example/workspaces/v-skills/sources/axton-obsidian-visual-skills/mermaid-visualizer"
      }
    }
  }
}
```

The manifest is machine-local state and must not be stored in the repository, because sync output targets are also machine-local.

## Sync Algorithm

1. Load and validate `config/skill-sync.yaml`.
2. Discover skills for each configured repository.
3. Apply `whitelist` and `blacklist` rules.
4. Build the final desired mapping:
   - key: skill name
   - value: absolute source directory
5. Detect duplicate final skill names across repositories.
6. Load the previous manifest, if present.
7. Create destination directories if needed.
8. For each destination root:
   - create missing managed symlinks
   - update managed symlinks that point to the wrong source
   - leave already-correct managed symlinks untouched
   - fail if a desired target path exists but is not a managed symlink owned by this tool
9. Remove previously managed symlinks that are no longer part of the desired set.
10. Write the updated manifest only after a successful sync.

## Conflict Handling

The tool should stop with a non-zero exit status for:

- duplicate skill names across repositories after filtering
- missing configured repository directories
- missing or malformed YAML config
- unknown skills referenced in `whitelist` or `blacklist`
- an existing destination path that is not a managed symlink created by the tool
- a managed destination path that has been replaced with a regular file or directory

This keeps the operation explicit and prevents silent overwrites.

## Error Handling

The script should raise human-readable errors that name:

- the repository
- the skill name when relevant
- the conflicting or missing path
- the action the user needs to take

Example categories:

- `ConfigError`
- `DiscoveryError`
- `ConflictError`
- `SyncError`

Exact exception classes are flexible, but the final CLI output should be short and actionable.

## Testing

Implementation verification should cover:

1. Discovery from both supported repository layouts.
2. `whitelist` omitted, empty, and populated.
3. `blacklist` exclusion precedence.
4. Skipping repositories not listed in config.
5. Duplicate skill detection across repositories.
6. Creation of both destination roots.
7. Creation and update of managed symlinks.
8. Cleanup of stale managed symlinks.
9. Preservation of unmanaged destination entries.
10. Failure on invalid config references.

The most practical approach is a small automated test suite using temporary directories and overridden home/state paths, plus one real smoke test run against the repository layout.

## File Plan

The implementation should add:

- `scripts/sync_skills.py`
- `config/skill-sync.yaml`

Optional follow-up documentation updates can be added later if needed, but they are not required to complete the first version.
