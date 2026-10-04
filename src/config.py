"""Load the rule list from config.json (created with defaults on first run)."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from src.keys import parse_combo
from src.rules import Rule

log = logging.getLogger(__name__)

APP_DIR_NAME = "enter_key_unifier"

# Claude Code titles its terminal tab "<glyph> <session name>": "✳" when idle,
# a "◐◓◑◒" spinner while working (measured 2026-10-04).
# Only the CLI is targeted; Claude Code keeps its default keys, so Enter is sent
# on as Ctrl+J (its built-in newline) and Ctrl+Enter as a plain Enter (submit).
DEFAULT_RULES = [
    {
        "name": "Claude Code CLI (Windows Terminal)",
        "process": "windowsterminal.exe",
        "title_regex": "^[✳◐◓◑◒]\\s",
        "newline": "ctrl+j",
        "submit": "enter",
    },
]


class ConfigError(ValueError):
    """Invalid settings. Callers keep the last good rules (or none)."""


def app_dir() -> Path:
    return Path(os.environ.get("APPDATA", Path.home())) / APP_DIR_NAME


def default_settings() -> dict:
    return {"rules": DEFAULT_RULES}


def load_rules(path: Path) -> tuple[Rule, ...]:
    data = _read_or_create(path)
    raw_rules = data.get("rules", DEFAULT_RULES)
    if not isinstance(raw_rules, list):
        raise ConfigError("rules must be a list")
    return tuple(_parse_rule(i, raw) for i, raw in enumerate(raw_rules))


def _parse_rule(index: int, raw: object) -> Rule:
    if not isinstance(raw, dict):
        raise ConfigError(f"rules[{index}] must be an object")
    try:
        process = _required_str(raw, "process").lower()
        title = raw.get("title_regex")
        if title is not None and not isinstance(title, str):
            raise ConfigError("title_regex must be a string")
        return Rule(
            name=str(raw.get("name", process)),
            process=process,
            title_pattern=re.compile(title) if title else None,
            newline=parse_combo(_required_str(raw, "newline")),
            submit=parse_combo(_required_str(raw, "submit")),
        )
    except (ValueError, re.error) as error:
        raise ConfigError(f"rules[{index}]: {error}") from error


def _required_str(raw: dict, key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{key} must be a non-empty string")
    return value


def _read_or_create(path: Path) -> dict:
    if not path.exists():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(default_settings(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as error:
            log.warning("config: cannot create %s: %s", path, error)
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ConfigError(f"cannot read {path}: {error}") from error
    if not isinstance(data, dict):
        raise ConfigError("the settings file must be a JSON object")
    return data
