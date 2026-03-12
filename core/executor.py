"""
Executor: Actually performs screen operations.
Mouse, keyboard, app launch, window management, file operations.

Action format:
  {"type": "click",       "x": 100, "y": 200}
  {"type": "click",       "target": "OKボタン"}   <- visual search
  {"type": "double_click","x": 100, "y": 200}
  {"type": "right_click", "x": 100, "y": 200}
  {"type": "type",        "text": "hello"}
  {"type": "key",         "keys": "ctrl+c"}
  {"type": "launch",      "app": "notepad"}
  {"type": "move",        "x": 100, "y": 200}
  {"type": "scroll",      "x": 100, "y": 200, "amount": -3}
  {"type": "screenshot",  "save": true}
  {"type": "wait",        "seconds": 1.0}
  {"type": "find_and_click", "target": "検索ボタン"}
"""
import os
import time
import logging
import threading
import datetime
import base64
from typing import List, Dict, Any, Optional, Callable, Tuple

import config

logger = logging.getLogger(__name__)

# ── Optional imports ──────────────────────────────────────────────────────

try:
    import pyautogui
    pyautogui.FAILSAFE = True        # Move mouse to corner to abort
    pyautogui.PAUSE = 0.05           # Small pause between actions
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    logger.warning("pyautogui not installed. Install: pip install pyautogui")

try:
    import pygetwindow as gw
    PYGETWINDOW_AVAILABLE = True
except ImportError:
    PYGETWINDOW_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class ActionResult:
    """Result of a single action execution."""

    def __init__(
        self,
        action: Dict,
        success: bool,
        message: str = "",
        screenshot_path: str = "",
    ):
        self.action = action
        self.success = success
        self.message = message
        self.screenshot_path = screenshot_path
        self.timestamp = datetime.datetime.now().isoformat()

    def to_dict(self) -> Dict:
        return {
            "action": self.action,
            "success": self.success,
            "message": self.message,
            "screenshot_path": self.screenshot_path,
            "timestamp": self.timestamp,
        }


class VisualFinder:
    """
    Uses Claude Vision to find UI elements on screen by description.
    Returns (x, y) coordinates.
    """

    def __init__(self, api_key: str = None):
        self._api_key = api_key or config.ANTHROPIC_API_KEY
        self._client = None
        if self._api_key:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self._api_key)
            except ImportError:
                pass

    def find(self, target_description: str, screenshot_path: str) -> Optional[Tuple[int, int]]:
        """
        Find UI element by description on screenshot.
        Returns (x, y) pixel coordinates or None.
        """
        if not self._client or not os.path.exists(screenshot_path):
            return None

        try:
            with open(screenshot_path, "rb") as f:
                img_data = base64.standard_b64encode(f.read()).decode("utf-8")

            import anthropic
            response = self._client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=256,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": img_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                f"この画面で「{target_description}」を見つけて、"
                                f"その中心のピクセル座標を返してください。\n"
                                f"必ずJSON形式で: {{\"x\": 数値, \"y\": 数値}}\n"
                                f"見つからない場合: {{\"x\": null, \"y\": null}}"
                            ),
                        },
                    ],
                }],
            )

            import json, re
            text = next((b.text for b in response.content if b.type == "text"), "")
            m = re.search(r'\{"x":\s*(\d+|null),\s*"y":\s*(\d+|null)\}', text)
            if m:
                x_str, y_str = m.group(1), m.group(2)
                if x_str != "null" and y_str != "null":
                    return int(x_str), int(y_str)

        except Exception as e:
            logger.error(f"Visual find error: {e}")

        return None


class Executor:
    """
    Executes a sequence of actions on the screen.
    Supports mouse, keyboard, app launch, window management.
    """

    def __init__(
        self,
        on_action: Optional[Callable] = None,    # (result: ActionResult)
        on_status: Optional[Callable] = None,    # (message: str)
        safe_mode: bool = True,                   # Require confirmation for destructive ops
        api_key: str = None,
    ):
        self.on_action = on_action
        self.on_status = on_status
        self.safe_mode = safe_mode
        self._finder = VisualFinder(api_key=api_key or config.ANTHROPIC_API_KEY)
        self._running = False
        self._abort = threading.Event()
        self.history: List[ActionResult] = []

    def execute_plan(
        self,
        actions: List[Dict],
        description: str = "",
        confirm_before: bool = False,
    ) -> List[ActionResult]:
        """
        Execute a list of actions sequentially.
        Returns list of ActionResult.
        """
        if not PYAUTOGUI_AVAILABLE:
            err = ActionResult(
                action={"type": "error"},
                success=False,
                message="pyautogui not installed. Run: pip install pyautogui",
            )
            return [err]

        self._abort.clear()
        self._running = True
        results = []

        self._status(f"実行開始: {description or f'{len(actions)}アクション'}")

        for i, action in enumerate(actions):
            if self._abort.is_set():
                self._status("実行中断されました")
                break

            action_type = action.get("type", "")
            desc = action.get("description", action_type)
            self._status(f"[{i+1}/{len(actions)}] {desc}")

            result = self._execute_one(action)
            results.append(result)
            self.history.append(result)

            if self.on_action:
                try:
                    self.on_action(result)
                except Exception:
                    pass

            if not result.success:
                logger.warning(f"Action failed: {action_type} - {result.message}")
                # Don't abort on failure unless it's critical
                if action.get("abort_on_fail", False):
                    self._status(f"エラーで中断: {result.message}")
                    break

            # Small pause between actions
            pause = action.get("pause_after", 0.1)
            if pause > 0:
                time.sleep(pause)

        self._running = False
        success_count = sum(1 for r in results if r.success)
        self._status(f"実行完了: {success_count}/{len(results)} 成功")
        return results

    def abort(self):
        """Abort the current execution."""
        self._abort.set()

    def _execute_one(self, action: Dict) -> ActionResult:
        """Execute a single action. Returns ActionResult."""
        action_type = action.get("type", "").lower()

        try:
            if action_type == "click":
                return self._click(action)
            elif action_type == "double_click":
                return self._double_click(action)
            elif action_type == "right_click":
                return self._right_click(action)
            elif action_type == "move":
                return self._move(action)
            elif action_type == "type":
                return self._type(action)
            elif action_type == "key":
                return self._key(action)
            elif action_type == "scroll":
                return self._scroll(action)
            elif action_type == "launch":
                return self._launch(action)
            elif action_type == "screenshot":
                return self._take_screenshot(action)
            elif action_type == "wait":
                return self._wait(action)
            elif action_type == "find_and_click":
                return self._find_and_click(action)
            elif action_type == "window_focus":
                return self._window_focus(action)
            elif action_type == "drag":
                return self._drag(action)
            elif action_type == "hotkey":
                return self._hotkey(action)
            else:
                return ActionResult(
                    action=action,
                    success=False,
                    message=f"未知のアクションタイプ: {action_type}",
                )
        except pyautogui.FailSafeException:
            self._abort.set()
            return ActionResult(
                action=action,
                success=False,
                message="フェイルセーフ発動（マウスが画面端に移動）- 実行中断",
            )
        except Exception as e:
            return ActionResult(
                action=action,
                success=False,
                message=f"実行エラー: {str(e)}",
            )

    # ── Action implementations ─────────────────────────────────────────────

    def _resolve_coords(self, action: Dict) -> Optional[Tuple[int, int]]:
        """Resolve x,y from action. May use visual finder for 'target'."""
        x = action.get("x")
        y = action.get("y")

        if x is not None and y is not None:
            return int(x), int(y)

        target = action.get("target")
        if target:
            # Take a screenshot and ask Claude to find the element
            ss_path = self._quick_screenshot()
            if ss_path:
                coords = self._finder.find(target, ss_path)
                if coords:
                    logger.debug(f"Found '{target}' at {coords}")
                    return coords
            # Fallback: try pyautogui image search if image provided
            img = action.get("image")
            if img and os.path.exists(img):
                try:
                    pos = pyautogui.locateCenterOnScreen(img, confidence=0.8)
                    if pos:
                        return pos.x, pos.y
                except Exception:
                    pass

        return None

    def _click(self, action: Dict) -> ActionResult:
        coords = self._resolve_coords(action)
        if not coords:
            return ActionResult(action, False, "クリック位置が見つかりません")
        x, y = coords
        button = action.get("button", "left")
        pyautogui.click(x, y, button=button)
        return ActionResult(action, True, f"クリック: ({x}, {y})")

    def _double_click(self, action: Dict) -> ActionResult:
        coords = self._resolve_coords(action)
        if not coords:
            return ActionResult(action, False, "ダブルクリック位置が見つかりません")
        x, y = coords
        pyautogui.doubleClick(x, y)
        return ActionResult(action, True, f"ダブルクリック: ({x}, {y})")

    def _right_click(self, action: Dict) -> ActionResult:
        coords = self._resolve_coords(action)
        if not coords:
            return ActionResult(action, False, "右クリック位置が見つかりません")
        x, y = coords
        pyautogui.rightClick(x, y)
        return ActionResult(action, True, f"右クリック: ({x}, {y})")

    def _move(self, action: Dict) -> ActionResult:
        coords = self._resolve_coords(action)
        if not coords:
            return ActionResult(action, False, "移動位置が見つかりません")
        x, y = coords
        duration = action.get("duration", 0.2)
        pyautogui.moveTo(x, y, duration=duration)
        return ActionResult(action, True, f"マウス移動: ({x}, {y})")

    def _type(self, action: Dict) -> ActionResult:
        text = action.get("text", "")
        if not text:
            return ActionResult(action, False, "テキストが空です")
        interval = action.get("interval", 0.03)
        # Focus first if target specified
        if action.get("target") or (action.get("x") and action.get("y")):
            click_result = self._click(action)
            if not click_result.success:
                return ActionResult(action, False, "入力フィールドをクリックできません")
            time.sleep(0.1)
        pyautogui.typewrite(text, interval=interval)
        return ActionResult(action, True, f"テキスト入力: {text[:30]}")

    def _key(self, action: Dict) -> ActionResult:
        keys = action.get("keys", "")
        if not keys:
            return ActionResult(action, False, "キーが指定されていません")
        # Support "ctrl+c", "enter", "tab" etc.
        if "+" in keys:
            parts = [k.strip().lower() for k in keys.split("+")]
            pyautogui.hotkey(*parts)
        else:
            pyautogui.press(keys.lower())
        return ActionResult(action, True, f"キー押下: {keys}")

    def _hotkey(self, action: Dict) -> ActionResult:
        keys = action.get("keys", [])
        if isinstance(keys, str):
            keys = [k.strip() for k in keys.split("+")]
        if not keys:
            return ActionResult(action, False, "キーが指定されていません")
        pyautogui.hotkey(*[k.lower() for k in keys])
        return ActionResult(action, True, f"ホットキー: {'+'.join(keys)}")

    def _scroll(self, action: Dict) -> ActionResult:
        x = action.get("x")
        y = action.get("y")
        amount = action.get("amount", -3)  # negative = scroll down
        if x and y:
            pyautogui.scroll(amount, x=int(x), y=int(y))
        else:
            pyautogui.scroll(amount)
        direction = "下" if amount < 0 else "上"
        return ActionResult(action, True, f"スクロール{direction}: {abs(amount)}")

    def _drag(self, action: Dict) -> ActionResult:
        x1 = action.get("from_x", action.get("x", 0))
        y1 = action.get("from_y", action.get("y", 0))
        x2 = action.get("to_x", 0)
        y2 = action.get("to_y", 0)
        duration = action.get("duration", 0.5)
        pyautogui.drag(x2 - x1, y2 - y1, duration=duration, startX=x1, startY=y1)
        return ActionResult(action, True, f"ドラッグ: ({x1},{y1})→({x2},{y2})")

    def _launch(self, action: Dict) -> ActionResult:
        import subprocess
        app = action.get("app", "")
        args = action.get("args", [])
        if not app:
            return ActionResult(action, False, "アプリ名が指定されていません")

        try:
            if isinstance(args, str):
                args = args.split()
            cmd = [app] + args
            subprocess.Popen(cmd)
            wait = action.get("wait_seconds", 1.5)
            time.sleep(wait)
            return ActionResult(action, True, f"起動: {app}")
        except FileNotFoundError:
            # Try with shell on Linux/Mac
            try:
                subprocess.Popen(app, shell=True)
                time.sleep(1.5)
                return ActionResult(action, True, f"起動(shell): {app}")
            except Exception as e:
                return ActionResult(action, False, f"起動失敗: {app} - {e}")
        except Exception as e:
            return ActionResult(action, False, f"起動エラー: {e}")

    def _take_screenshot(self, action: Dict) -> ActionResult:
        path = self._quick_screenshot()
        if path:
            return ActionResult(action, True, f"スクリーンショット: {path}", path)
        return ActionResult(action, False, "スクリーンショット失敗")

    def _wait(self, action: Dict) -> ActionResult:
        seconds = action.get("seconds", 1.0)
        time.sleep(float(seconds))
        return ActionResult(action, True, f"待機: {seconds}秒")

    def _find_and_click(self, action: Dict) -> ActionResult:
        target = action.get("target", "")
        if not target:
            return ActionResult(action, False, "検索対象が指定されていません")

        ss_path = self._quick_screenshot()
        if not ss_path:
            return ActionResult(action, False, "スクリーンショット取得失敗")

        coords = self._finder.find(target, ss_path)
        if not coords:
            return ActionResult(action, False, f"「{target}」が見つかりません")

        x, y = coords
        button = action.get("button", "left")
        pyautogui.click(x, y, button=button)
        return ActionResult(action, True, f"「{target}」をクリック: ({x},{y})")

    def _window_focus(self, action: Dict) -> ActionResult:
        if not PYGETWINDOW_AVAILABLE:
            return ActionResult(action, False, "pygetwindow not installed")
        title = action.get("title", "")
        if not title:
            return ActionResult(action, False, "ウィンドウタイトルが指定されていません")
        try:
            windows = gw.getWindowsWithTitle(title)
            if windows:
                windows[0].activate()
                time.sleep(0.3)
                return ActionResult(action, True, f"ウィンドウフォーカス: {title}")
            return ActionResult(action, False, f"ウィンドウ「{title}」が見つかりません")
        except Exception as e:
            return ActionResult(action, False, f"ウィンドウフォーカスエラー: {e}")

    def _quick_screenshot(self) -> Optional[str]:
        """Take a quick screenshot and return filepath."""
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            path = os.path.join(
                config.SAVE_FOLDERS[0],
                f"exec_ss_{timestamp}.png"
            )
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if PYAUTOGUI_AVAILABLE:
                img = pyautogui.screenshot()
                img.save(path)
                return path
        except Exception as e:
            logger.error(f"Quick screenshot error: {e}")
        return None

    def _status(self, message: str):
        logger.info(f"[Executor] {message}")
        if self.on_status:
            try:
                self.on_status(message)
            except Exception:
                pass

    @property
    def is_running(self) -> bool:
        return self._running

    def get_screen_size(self) -> Tuple[int, int]:
        if PYAUTOGUI_AVAILABLE:
            return pyautogui.size()
        return (1920, 1080)

    def get_mouse_position(self) -> Tuple[int, int]:
        if PYAUTOGUI_AVAILABLE:
            pos = pyautogui.position()
            return pos.x, pos.y
        return (0, 0)
