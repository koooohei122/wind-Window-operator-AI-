# Wind Window Operator AI

画面監視・操作補助AIシステム。スクリーンショット/録画からユーザーの操作を分析し、
AIが記憶・学習して音声＋テキストでサポートする。

## 機能

| 機能 | 説明 |
|------|------|
| 📷 画面キャプチャ | スクリーンショット or 録画を定期実行（複数フォルダに保存） |
| 🧠 AI分析 | Claude Vision APIでユーザーの状態・目的・意図を分析 |
| 📝 メモリ管理 | 短期・長期メモリファイル（各最大100件、500文字/件） |
| 🗑 自動クリーンアップ | 設定時間後にメディアファイル削除（メモリは保持） |
| 💡 レコメンド | 音声＋テキストで操作補助を提案 |
| ⌨️ AI操作実行 | テキスト指示でAIが操作手順を計画・実行 |
| 🛠 スキル記録 | 実行した操作をスキルフォルダに自動記録・再利用 |

## セットアップ

### 1. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 2. APIキーの設定

```bash
# 環境変数で設定（推奨）
export ANTHROPIC_API_KEY="your-api-key-here"   # Linux/Mac
set ANTHROPIC_API_KEY=your-api-key-here         # Windows

# またはコマンドライン引数で
python main.py --apikey YOUR_KEY
```

### 3. 起動

```bash
# GUIモード（通常）
python main.py

# スクリーンショットモード（デフォルト）
python main.py --mode screenshot

# 録画モード
python main.py --mode recording

# 両方
python main.py --mode both

# 間隔指定（秒）
python main.py --interval 15

# CLIモード（GUIなし）
python main.py --nogui
```

## ディレクトリ構成

```
wind-Window-operator-AI-/
├── main.py                    # エントリーポイント
├── config.py                  # 設定
├── requirements.txt
├── core/
│   ├── screen_capture.py      # スクリーンキャプチャ・録画
│   ├── ai_analyzer.py         # Claude API分析
│   ├── memory_manager.py      # 短期・長期メモリ管理
│   ├── cleanup_manager.py     # ファイル自動削除
│   ├── recommender.py         # 音声・テキスト推薦
│   ├── skill_recorder.py      # スキル記録
│   └── orchestrator.py        # 全モジュール統合
├── ui/
│   └── main_window.py         # tkinter GUI
└── data/
    ├── screenshots/
    │   ├── primary/           # スクリーンショット（メイン）
    │   └── backup/            # スクリーンショット（バックアップ）
    ├── recordings/
    │   ├── primary/           # 録画（メイン）
    │   └── backup/            # 録画（バックアップ）
    ├── memory/
    │   ├── short_term.json    # 短期メモリ
    │   └── long_term.json     # 長期メモリ
    └── skills/
        ├── index.json         # スキルインデックス
        └── *.json             # 各スキルの詳細
```

## 設定 (config.py)

| パラメータ | デフォルト | 説明 |
|-----------|-----------|------|
| `SCREENSHOT_INTERVAL_SECONDS` | 10 | スクリーンショット間隔（秒） |
| `SCREENSHOT_RETENTION_HOURS` | 3 | スクリーンショット保持時間 |
| `RECORDING_RETENTION_HOURS` | 6 | 録画保持時間 |
| `MAX_MEMORY_ENTRIES` | 100 | メモリ最大件数 |
| `MAX_MEMORY_CHARS` | 500 | メモリ1件の最大文字数 |
| `VOICE_ENABLED` | True | 音声レコメンドの有効/無効 |
| `ANALYSIS_INTERVAL_SECONDS` | 30 | AI分析間隔（秒） |
| `RECOMMENDATION_INTERVAL_SECONDS` | 60 | レコメンド間隔（秒） |

## メモリシステム

### 短期メモリ (`data/memory/short_term.json`)
- 直近の操作分析メモを最大100件保持
- 各エントリ最大500文字
- 同じパターンが5回以上現れると長期メモリに昇格

### 長期メモリ (`data/memory/long_term.json`)
- 繰り返しパターン・重要な知見を最大100件保持
- スキル記録、操作パターン等を永続化

## スキルシステム

ユーザーがAIに指示を出すと、その実行方法を `data/skills/` に自動記録。

```json
{
  "name": "open_browser_and_search",
  "description": "ブラウザを開いてGoogle検索する",
  "steps": ["ブラウザを起動", "検索窓をクリック", "キーワードを入力"],
  "category": "browser",
  "keywords": ["ブラウザ", "検索", "Google"],
  "use_count": 3
}
```

## 音声サポート

- **pyttsx3** (デフォルト): オフラインTTS、Windows/Mac/Linuxで動作
- **gTTS** (オプション): より自然な日本語音声（インターネット必要）

```bash
# gTTSを使う場合
pip install gtts playsound
```

## システム要件

- Python 3.9+
- `ANTHROPIC_API_KEY` (分析機能に必要)
- 画面キャプチャ: Linux では追加設定が必要な場合あり
