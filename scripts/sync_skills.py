from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class ConfigError(RuntimeError):
    pass


class DiscoveryError(RuntimeError):
    pass


class ConflictError(RuntimeError):
    pass


class SyncError(RuntimeError):
    pass


@dataclass(frozen=True)
class RepoRule:
    whitelist: list[str]
    blacklist: list[str]


def load_config(config_path: Path) -> dict[str, RepoRule]:
    data = _load_yaml_like(config_path)
    sources = data.get("sources")
    if not isinstance(sources, dict):
        raise ConfigError(f"{config_path}: expected top-level 'sources' mapping")

    rules: dict[str, RepoRule] = {}
    for repo_name, rule_data in sources.items():
        if not isinstance(rule_data, dict):
            raise ConfigError(f"{config_path}: expected mapping for repository '{repo_name}'")
        rules[repo_name] = RepoRule(
            whitelist=_normalize_name_list(config_path, repo_name, "whitelist", rule_data.get("whitelist")),
            blacklist=_normalize_name_list(config_path, repo_name, "blacklist", rule_data.get("blacklist")),
        )
    return rules


def discover_repo_skills(repo_path: Path) -> dict[str, Path]:
    discovered: dict[str, Path] = {}

    for base_dir in (repo_path / "skills", repo_path):
        if not base_dir.is_dir():
            continue
        for child in sorted(base_dir.iterdir()):
            if not child.is_dir() or not (child / "SKILL.md").is_file():
                continue
            existing = discovered.get(child.name)
            resolved = child.resolve()
            if existing is not None and existing != resolved:
                raise DiscoveryError(
                    f"{repo_path}: duplicate skill '{child.name}' found at {existing} and {resolved}"
                )
            discovered[child.name] = resolved

    return discovered


def select_repo_skills(
    repo_name: str,
    discovered: dict[str, Path],
    rule: RepoRule,
) -> dict[str, Path]:
    configured = set(rule.whitelist) | set(rule.blacklist)
    unknown = configured - set(discovered)
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ConfigError(f"{repo_name}: unknown skills in config: {names}")

    selected_names = set(discovered) if not rule.whitelist else set(rule.whitelist)
    selected_names -= set(rule.blacklist)
    return {name: discovered[name] for name in sorted(selected_names)}


def build_desired_skills(repo_skill_map: dict[str, dict[str, Path]]) -> dict[str, Path]:
    desired: dict[str, Path] = {}
    owners: dict[str, str] = {}

    for repo_name, repo_skills in repo_skill_map.items():
        for skill_name, skill_path in repo_skills.items():
            if skill_name in desired:
                raise ConflictError(
                    f"duplicate skill '{skill_name}' found in repositories "
                    f"'{owners[skill_name]}' and '{repo_name}'"
                )
            desired[skill_name] = skill_path
            owners[skill_name] = repo_name

    return desired


def sync_targets(
    desired: dict[str, Path],
    target_roots: list[Path],
    manifest_path: Path,
) -> None:
    manifest = load_manifest(manifest_path)
    previous_managed = manifest.get("managed", {})
    if not isinstance(previous_managed, dict):
        raise SyncError(f"{manifest_path}: manifest 'managed' entry must be a mapping")

    updated_manifest: dict[str, object] = {"version": 1, "managed": {}}
    updated_managed: dict[str, dict[str, dict[str, str]]] = {}
    normalized_previous: dict[str, dict[str, dict[str, str]]] = {}

    for target_root in target_roots:
        target_root.mkdir(parents=True, exist_ok=True)
        target_key = str(target_root.resolve())
        previous_entries = _normalize_manifest_entries(manifest_path, target_key, previous_managed.get(target_key, {}))
        normalized_previous[target_key] = previous_entries
        _validate_sync_plan(target_root, desired, previous_entries)

    for target_root in target_roots:
        target_key = str(target_root.resolve())
        previous_entries = normalized_previous[target_key]
        current_entries: dict[str, dict[str, str]] = {}

        for skill_name, source_path in desired.items():
            link_path = target_root / skill_name
            resolved_source = source_path.resolve()
            _ensure_managed_link(link_path, resolved_source, skill_name, previous_entries)
            current_entries[skill_name] = {
                "link_path": str(link_path),
                "source_path": str(resolved_source),
            }

        _remove_stale_managed_links(previous_entries, current_entries)
        updated_managed[target_key] = current_entries

    updated_manifest["managed"] = updated_managed
    write_manifest(manifest_path, updated_manifest)


def load_manifest(manifest_path: Path) -> dict[str, object]:
    if not manifest_path.is_file():
        return {"version": 1, "managed": {}}

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SyncError(f"{manifest_path}: invalid JSON manifest: {exc}") from exc

    if not isinstance(data, dict):
        raise SyncError(f"{manifest_path}: manifest must be a JSON object")
    return data


def write_manifest(manifest_path: Path, manifest: dict[str, object]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _normalize_manifest_entries(
    manifest_path: Path,
    target_key: str,
    value: object,
) -> dict[str, dict[str, str]]:
    if value in ({}, None):
        return {}
    if not isinstance(value, dict):
        raise SyncError(f"{manifest_path}: manifest entries for {target_key} must be a mapping")

    normalized: dict[str, dict[str, str]] = {}
    for skill_name, entry in value.items():
        if not isinstance(entry, dict):
            raise SyncError(f"{manifest_path}: manifest entry for {skill_name} must be an object")
        link_path = entry.get("link_path")
        source_path = entry.get("source_path")
        if not isinstance(link_path, str) or not isinstance(source_path, str):
            raise SyncError(
                f"{manifest_path}: manifest entry for {skill_name} must include string link_path and source_path"
            )
        normalized[skill_name] = {"link_path": link_path, "source_path": source_path}
    return normalized


def _ensure_managed_link(
    link_path: Path,
    source_path: Path,
    skill_name: str,
    previous_entries: dict[str, dict[str, str]],
) -> None:
    previous_entry = previous_entries.get(skill_name)
    path_exists = link_path.exists() or link_path.is_symlink()

    if previous_entry is None:
        if path_exists:
            raise SyncError(
                f"{link_path}: existing path for '{skill_name}' is not managed by this tool"
            )
        link_path.symlink_to(source_path)
        return

    if not path_exists:
        link_path.symlink_to(source_path)
        return

    if not link_path.is_symlink():
        raise SyncError(f"{link_path}: managed path for '{skill_name}' was replaced by a non-symlink")

    if link_path.resolve() == source_path:
        return

    link_path.unlink()
    link_path.symlink_to(source_path)


def _validate_sync_plan(
    target_root: Path,
    desired: dict[str, Path],
    previous_entries: dict[str, dict[str, str]],
) -> None:
    for skill_name in desired:
        link_path = target_root / skill_name
        previous_entry = previous_entries.get(skill_name)
        path_exists = link_path.exists() or link_path.is_symlink()
        if previous_entry is None:
            if path_exists:
                raise SyncError(
                    f"{link_path}: existing path for '{skill_name}' is not managed by this tool"
                )
            continue
        if path_exists and not link_path.is_symlink():
            raise SyncError(f"{link_path}: managed path for '{skill_name}' was replaced by a non-symlink")

    stale_names = set(previous_entries) - set(desired)
    for skill_name in sorted(stale_names):
        link_path = Path(previous_entries[skill_name]["link_path"])
        if link_path.exists() and not link_path.is_symlink():
            raise SyncError(f"{link_path}: stale managed path for '{skill_name}' is no longer a symlink")


def _remove_stale_managed_links(
    previous_entries: dict[str, dict[str, str]],
    current_entries: dict[str, dict[str, str]],
) -> None:
    stale_names = set(previous_entries) - set(current_entries)
    for skill_name in sorted(stale_names):
        link_path = Path(previous_entries[skill_name]["link_path"])
        if link_path.is_symlink():
            link_path.unlink()
            continue
        if link_path.exists():
            raise SyncError(f"{link_path}: stale managed path for '{skill_name}' is no longer a symlink")


def _normalize_name_list(
    config_path: Path,
    repo_name: str,
    field_name: str,
    value: object,
) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(
            f"{config_path}: expected {field_name} for '{repo_name}' to be a list of skill names"
        )
    return list(value)


def _load_yaml_like(config_path: Path) -> dict[str, object]:
    text = config_path.read_text(encoding="utf-8")

    try:
        import yaml  # type: ignore
    except ModuleNotFoundError:
        return _parse_simple_yaml(text, config_path)

    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ConfigError(f"{config_path}: expected YAML document to be a mapping")
    return data


def _parse_simple_yaml(text: str, config_path: Path) -> dict[str, object]:
    lines = text.splitlines()
    index = 0

    def next_meaningful(start: int) -> int:
        while start < len(lines):
            stripped = lines[start].strip()
            if stripped and not stripped.startswith("#"):
                break
            start += 1
        return start

    index = next_meaningful(index)
    if index >= len(lines) or lines[index].strip() != "sources:":
        raise ConfigError(f"{config_path}: expected top-level 'sources:' entry")
    index += 1

    sources: dict[str, dict[str, list[str]]] = {}
    while True:
        index = next_meaningful(index)
        if index >= len(lines):
            break

        repo_line = lines[index]
        if _indent(repo_line) != 2 or not repo_line.strip().endswith(":"):
            raise ConfigError(f"{config_path}: expected repository key at line {index + 1}")
        repo_name = repo_line.strip()[:-1]
        index += 1
        repo_data: dict[str, list[str]] = {}

        while True:
            index = next_meaningful(index)
            if index >= len(lines):
                break

            field_line = lines[index]
            field_indent = _indent(field_line)
            if field_indent <= 2:
                break
            if field_indent != 4:
                raise ConfigError(f"{config_path}: expected field for '{repo_name}' at line {index + 1}")

            stripped = field_line.strip()
            field_name, separator, raw_value = stripped.partition(":")
            if separator != ":":
                raise ConfigError(f"{config_path}: malformed field at line {index + 1}")
            raw_value = raw_value.strip()

            if raw_value == "[]":
                repo_data[field_name] = []
                index += 1
                continue

            if raw_value:
                raise ConfigError(
                    f"{config_path}: unsupported inline value for '{field_name}' at line {index + 1}"
                )

            index += 1
            items: list[str] = []
            while True:
                index = next_meaningful(index)
                if index >= len(lines):
                    break

                item_line = lines[index]
                item_indent = _indent(item_line)
                if item_indent <= 4:
                    break
                if item_indent != 6 or not item_line.strip().startswith("- "):
                    raise ConfigError(
                        f"{config_path}: expected list item for '{field_name}' at line {index + 1}"
                    )
                items.append(item_line.strip()[2:].strip())
                index += 1

            repo_data[field_name] = items

        sources[repo_name] = repo_data

    return {"sources": sources}


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))
