from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class ConfigError(RuntimeError):
    pass


class DiscoveryError(RuntimeError):
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
