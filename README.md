# Enter Key Unifier

タスクトレイに常駐し、登録したアプリでだけ **Enter / Shift+Enter = 改行、Ctrl+Enter = 送信** にそろえる Windows アプリ。v0.1.0 の対象は Windows Terminal で動く Claude Code CLI。

## しくみ

アプリの設定ファイルは一切書き換えない。キー入力を横取りして、前面のウィンドウが対象のときだけ別のキーに置き換えて送る。

| 押したキー | Claude Code CLI に届くキー | 結果 |
|---|---|---|
| Enter | Ctrl+J（Claude Code の既定の改行） | 改行 |
| Shift+Enter | Ctrl+J | 改行 |
| Ctrl+Enter | Enter（Ctrl を離した扱い） | 送信 |
| 日本語入力で変換中の Enter | そのまま | 変換の確定 |

- 対象の判定: プロセスが `WindowsTerminal.exe` で、タイトルが Claude Code の記号（待機中 `✳`、処理中 `◐◓◑◒`）で始まるとき
- Alt / Win を押しながらの Enter、対象外のウィンドウ、一時停止中は何もしない
- 止まった・落ちた・判定を外したときは、Claude Code の既定の動き（Enter で送信）に戻る。送信できなくなることはない

## 使い方

1. `pythonw run.py` で起動するか、`build.bat` で `build\enter_key_unifier.exe` を作って起動する。緑のアイコンがトレイに出る
2. トレイメニュー: 一時停止 / 設定ファイルを開く / ログを開く / 終了
3. Windows 起動時に自動で起動するには: `Win + R` → `shell:startup` に exe のショートカットを置く

## 設定

初回起動時に `%APPDATA%\enter_key_unifier\config.json` が作られる。保存すると、次のキー入力から反映される。

```json
{
  "rules": [
    {
      "name": "Claude Code CLI (Windows Terminal)",
      "process": "windowsterminal.exe",
      "title_regex": "^[✳◐◓◑◒]\\s",
      "newline": "ctrl+j",
      "submit": "enter"
    }
  ]
}
```

| キー | 意味 |
|---|---|
| `process` | 実行ファイル名（大文字小文字は区別しない） |
| `title_regex` | ウィンドウタイトルの正規表現（省略するとタイトルは見ない） |
| `newline` / `submit` | 送るキー。`enter` / `j` に `ctrl` `shift` `alt` を `+` でつなぐ |

設定が壊れているときは、直前の正しい設定のまま動く（起動時に壊れていれば何もしない）。

## 既知の制限

- 日本語入力の変換中かどうかは、IME がオンのときに打った文字数から推定している。変換中の文字をマウス操作で確定した直後の Enter は、変換中と判断されてそのまま送られる（Claude Code では送信になる）
- 管理者権限で動いているウィンドウには効かない
- macOS / Linux は未対応（中核部分 `src/engine.py` `src/rules.py` `src/config.py` は OS に依存しない）

## 開発

```
pip install -r requirements.txt
python -m pytest -q
```
