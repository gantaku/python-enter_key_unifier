import json

import pytest

from src.config import ConfigError, load_rules
from src.keys import parse_combo
from src.rules import WindowInfo, find_rule


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.mark.parametrize("glyph", ["✳", "◐", "◓", "◑", "◒"])
def test_first_run_creates_defaults_matching_claude_code(tmp_path, glyph):
    path = tmp_path / "config.json"
    rules = load_rules(path)
    assert path.exists()
    window = WindowInfo("windowsterminal.exe", f"{glyph} 1955 macからのドキュメント確認")
    assert find_rule(rules, window).newline == parse_combo("ctrl+j")


@pytest.mark.parametrize(
    "title",
    [
        "Windows PowerShell",
        "C:\\WINDOWS\\system32\\cmd.exe",
        "gpt-6.1-sol | project",
        "",
    ],
)
def test_default_rule_ignores_other_tabs(tmp_path, title):
    rules = load_rules(tmp_path / "config.json")
    assert find_rule(rules, WindowInfo("windowsterminal.exe", title)) is None


def test_default_rule_ignores_other_processes(tmp_path):
    rules = load_rules(tmp_path / "config.json")
    assert find_rule(rules, WindowInfo("notepad.exe", "✳ x")) is None


def test_process_name_is_case_insensitive(tmp_path):
    path = tmp_path / "config.json"
    write(
        path,
        {
            "rules": [
                {"process": "Claude.EXE", "newline": "shift+enter", "submit": "enter"}
            ]
        },
    )
    assert find_rule(load_rules(path), WindowInfo("claude.exe", "Claude")) is not None


@pytest.mark.parametrize(
    "rule",
    [
        {"newline": "ctrl+j", "submit": "enter"},
        {"process": "a.exe", "newline": "ctrl+k", "submit": "enter"},
        {"process": "a.exe", "newline": "hyper+j", "submit": "enter"},
        {
            "process": "a.exe",
            "newline": "ctrl+j",
            "submit": "enter",
            "title_regex": "(",
        },
        {"process": "a.exe", "newline": "ctrl+ctrl+j", "submit": "enter"},
    ],
)
def test_invalid_rules_raise(tmp_path, rule):
    path = tmp_path / "config.json"
    write(path, {"rules": [rule]})
    with pytest.raises(ConfigError):
        load_rules(path)


def test_broken_json_raises(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_rules(path)


def test_find_rule_without_window():
    assert find_rule((), None) is None
