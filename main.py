#!/usr/bin/env python3
"""
Wind Window Operator AI - Main Entry Point

起動方法:
  python main.py              # GUIモード
  python main.py --nogui      # CLIモード（テスト用）
  python main.py --apikey YOUR_KEY  # APIキーを直接指定
"""
import os
import sys
import argparse
import logging
import datetime

# ── Setup logging ──────────────────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            os.path.join(
                LOG_DIR,
                f"wind_ai_{datetime.datetime.now().strftime('%Y%m%d')}.log"
            ),
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Wind Window Operator AI - Screen monitoring AI assistant"
    )
    parser.add_argument(
        "--nogui", action="store_true",
        help="Run in CLI mode (no GUI)"
    )
    parser.add_argument(
        "--apikey", type=str, default=None,
        help="Anthropic API key (overrides ANTHROPIC_API_KEY env var)"
    )
    parser.add_argument(
        "--mode", type=str, default="screenshot",
        choices=["screenshot", "recording", "both"],
        help="Capture mode (default: screenshot)"
    )
    parser.add_argument(
        "--interval", type=int, default=None,
        help="Screenshot interval in seconds"
    )
    return parser.parse_args()


def run_gui(args):
    """Launch the GUI application."""
    import config
    if args.apikey:
        config.ANTHROPIC_API_KEY = args.apikey
        os.environ["ANTHROPIC_API_KEY"] = args.apikey

    if args.mode:
        config.CAPTURE_MODE = args.mode

    if args.interval:
        config.SCREENSHOT_INTERVAL_SECONDS = args.interval

    try:
        from ui.main_window import MainWindow
        app = MainWindow()
        logger.info("GUI started")
        app.run()
    except ImportError as e:
        logger.error(f"GUI import error: {e}")
        print(f"\nGUI起動エラー: {e}")
        print("依存パッケージをインストールしてください:")
        print("  pip install -r requirements.txt")
        sys.exit(1)


def run_cli(args):
    """Run in CLI mode for testing without GUI."""
    import config
    import time

    if args.apikey:
        config.ANTHROPIC_API_KEY = args.apikey
        os.environ["ANTHROPIC_API_KEY"] = args.apikey

    if args.mode:
        config.CAPTURE_MODE = args.mode

    if args.interval:
        config.SCREENSHOT_INTERVAL_SECONDS = args.interval

    from core.orchestrator import Orchestrator

    print("Wind Window Operator AI - CLIモード")
    print("=" * 50)
    print(f"キャプチャモード: {config.CAPTURE_MODE}")
    print(f"間隔: {config.SCREENSHOT_INTERVAL_SECONDS}秒")
    print(f"APIキー: {'設定済み' if config.ANTHROPIC_API_KEY else '未設定'}")
    print("=" * 50)
    print("Ctrl+C で終了")
    print()

    def on_status(msg):
        print(f"[STATUS] {msg}")

    def on_rec(text):
        print(f"[RECOMMEND] {text}")

    def on_analysis(a):
        print(f"[ANALYSIS] 状態:{a.get('state','')} 提案:{a.get('suggestion','')}")

    orc = Orchestrator(
        on_status_update=on_status,
        on_recommendation=on_rec,
        on_analysis_done=on_analysis,
        capture_mode=config.CAPTURE_MODE,
    )

    orc.start()

    try:
        while True:
            cmd = input("\n指示を入力 (空白でスキップ、'quit'で終了): ").strip()
            if cmd.lower() in ("quit", "exit", "q"):
                break
            if cmd:
                result = orc.execute_instruction(cmd)
                print(f"\n実行計画:")
                for i, step in enumerate(result.get("steps", []), 1):
                    print(f"  {i}. {step}")
                if result.get("skill_name"):
                    print(f"スキル記録: {result['skill_name']}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n終了中...")
    finally:
        orc.stop()
        print("終了しました")


def main():
    args = parse_args()

    logger.info(
        f"Wind Window Operator AI starting "
        f"(mode={'CLI' if args.nogui else 'GUI'})"
    )

    if args.nogui:
        run_cli(args)
    else:
        run_gui(args)


if __name__ == "__main__":
    main()
