"""
Computer Use Agent: The cutting-edge approach.

Uses Anthropic's native Computer Use API (computer_20241022 tool) with:
- Claude Opus 4.6 + adaptive thinking
- True agentic loop: screenshot → think → act → screenshot → ...
- Self-correction: Claude sees the result of each action and adapts
- Streaming with interleaved thinking display

This replaces the "generate plan → blindly execute" approach with
a proper perception-action loop where Claude drives every decision.

Beta header: computer-use-2024-10-22
Tool: {"type": "computer_20241022", "name": "computer", ...}

Actions Claude can request:
  screenshot, left_click, right_click, double_click, middle_click,
  left_click_drag, type, key, cursor_position, scroll
"""
import os
import time
import base64
import logging
import datetime
import threading
from typing import Optional, Callable, List, Dict, Any, Tuple

import anthropic

import config

logger = logging.getLogger(__name__)

# ── Optional pyautogui ─────────────────────────────────────────────────────
try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False


# ── Computer Use Tool definition ───────────────────────────────────────────

def _computer_tool(width: int, height: int) -> Dict:
    return {
        "type": "computer_20241022",
        "name": "computer",
        "display_width_px": width,
        "display_height_px": height,
    }


class ComputerUseAgent:
    """
    Drives the screen using Anthropic's Computer Use API.

    Architecture:
        1. User gives a natural-language goal
        2. Agent takes a screenshot and sends it to Claude Opus 4.6
        3. Claude responds with: thinking (visible) + one action
        4. Agent executes the action via pyautogui
        5. Agent takes a new screenshot to verify
        6. Repeat until Claude says it's done (stop_reason = "end_turn")

    Key difference from Executor:
        - Claude makes ALL decisions, one action at a time
        - Claude sees the screen after every action and self-corrects
        - Adaptive thinking lets Claude reason through complex UIs
    """

    # Maximum iterations to prevent infinite loops
    MAX_TURNS = 50

    def __init__(
        self,
        api_key: str = None,
        on_thinking: Optional[Callable[[str], None]] = None,   # (thinking_text)
        on_action: Optional[Callable[[Dict, bool, str], None]] = None,  # (action, success, msg)
        on_screenshot: Optional[Callable[[str], None]] = None,  # (path)
        on_status: Optional[Callable[[str], None]] = None,      # (message)
        on_complete: Optional[Callable[[str], None]] = None,    # (summary)
    ):
        self._api_key = api_key or config.ANTHROPIC_API_KEY
        self.on_thinking = on_thinking
        self.on_action = on_action
        self.on_screenshot = on_screenshot
        self.on_status = on_status
        self.on_complete = on_complete

        self._client = anthropic.Anthropic(api_key=self._api_key) if self._api_key else None
        self._abort = threading.Event()
        self._running = False

        # Screen dimensions
        if PYAUTOGUI_AVAILABLE:
            self._width, self._height = pyautogui.size()
        else:
            self._width, self._height = 1920, 1080

    # ── Public API ─────────────────────────────────────────────────────────

    def run(self, goal: str, background: bool = False) -> Optional[str]:
        """
        Execute the given goal using Computer Use.

        goal: Natural language instruction, e.g. "メモ帳を開いてHelloと入力して保存する"
        background: If True, run in a daemon thread.
        Returns: Final summary text (or None if aborted / backgrounded)
        """
        if not self._client:
            msg = "APIキーが設定されていません。設定でAnthropicキーを入力してください。"
            self._status(msg)
            return msg

        if not PYAUTOGUI_AVAILABLE:
            msg = "pyautogui がインストールされていません。pip install pyautogui を実行してください。"
            self._status(msg)
            return msg

        if background:
            t = threading.Thread(target=self._run_loop, args=(goal,), daemon=True)
            t.start()
            return None
        else:
            return self._run_loop(goal)

    def abort(self):
        """Stop the running agent loop."""
        self._abort.set()

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Internal agentic loop ──────────────────────────────────────────────

    def _run_loop(self, goal: str) -> str:
        self._abort.clear()
        self._running = True
        messages: List[Dict] = []
        turn = 0

        self._status(f"Computer Use 開始: {goal[:60]}")

        # Build system prompt
        system = self._build_system_prompt()

        # Initial user message with the goal
        messages.append({
            "role": "user",
            "content": goal,
        })

        final_text = ""

        try:
            while turn < self.MAX_TURNS and not self._abort.is_set():
                turn += 1
                self._status(f"ターン {turn}/{self.MAX_TURNS} - Claude が考えています...")

                # Call Claude with streaming + adaptive thinking
                response = self._call_claude(system, messages)
                if response is None:
                    break

                # Parse response: collect thinking, text, tool use
                thinking_text = ""
                response_text = ""
                tool_uses = []

                for block in response.content:
                    if block.type == "thinking":
                        thinking_text += block.thinking
                    elif block.type == "text":
                        response_text += block.text
                    elif block.type == "tool_use" and block.name == "computer":
                        tool_uses.append(block)

                # Emit thinking
                if thinking_text and self.on_thinking:
                    try:
                        self.on_thinking(thinking_text)
                    except Exception:
                        pass

                # Append assistant turn to history
                messages.append({
                    "role": "assistant",
                    "content": response.content,
                })

                # If Claude is done (no tool calls)
                if response.stop_reason == "end_turn" or not tool_uses:
                    final_text = response_text or "タスク完了"
                    self._status(f"完了: {final_text[:60]}")
                    if self.on_complete:
                        try:
                            self.on_complete(final_text)
                        except Exception:
                            pass
                    break

                # Execute each tool call and collect results
                tool_results = []
                for tool_use in tool_uses:
                    action = tool_use.input
                    action_type = action.get("action", "")
                    self._status(f"実行中: {action_type} {self._action_summary(action)}")

                    result_content, success, message = self._execute_action(action)

                    if self.on_action:
                        try:
                            self.on_action(action, success, message)
                        except Exception:
                            pass

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": result_content,
                        "is_error": not success,
                    })

                # Append tool results as next user turn
                messages.append({
                    "role": "user",
                    "content": tool_results,
                })

        except pyautogui.FailSafeException:
            self._status("フェイルセーフ発動（マウスが画面端）- 中断")
            final_text = "フェイルセーフにより中断されました"
        except Exception as e:
            logger.error(f"ComputerUseAgent error: {e}", exc_info=True)
            self._status(f"エラー: {e}")
            final_text = f"エラーが発生しました: {e}"
        finally:
            self._running = False

        if self._abort.is_set():
            final_text = "ユーザーにより中断されました"
            self._status(final_text)

        return final_text

    # ── Claude API call ────────────────────────────────────────────────────

    def _call_claude(
        self,
        system: str,
        messages: List[Dict],
    ) -> Optional[anthropic.types.Message]:
        """Call Claude Opus 4.6 with Computer Use tools + adaptive thinking."""
        try:
            with self._client.messages.stream(
                model="claude-opus-4-6",
                max_tokens=4096,
                thinking={"type": "adaptive"},
                system=system,
                tools=[_computer_tool(self._width, self._height)],
                messages=messages,
                betas=["computer-use-2024-10-22"],
            ) as stream:
                return stream.get_final_message()

        except anthropic.BadRequestError as e:
            logger.error(f"BadRequest: {e}")
            self._status(f"APIエラー (400): {e.message}")
        except anthropic.RateLimitError:
            self._status("レート制限。10秒後にリトライ...")
            time.sleep(10)
            return self._call_claude(system, messages)
        except anthropic.AuthenticationError:
            self._status("APIキーが無効です。設定を確認してください。")
        except Exception as e:
            logger.error(f"Claude API error: {e}", exc_info=True)
            self._status(f"APIエラー: {e}")
        return None

    # ── Action execution ───────────────────────────────────────────────────

    def _execute_action(
        self,
        action: Dict,
    ) -> Tuple[List[Dict], bool, str]:
        """
        Execute a computer use action.
        Returns: (tool_result_content, success, message)
        """
        action_type = action.get("action", "")

        try:
            if action_type == "screenshot":
                return self._do_screenshot()

            elif action_type == "left_click":
                return self._do_click(action, "left")

            elif action_type == "right_click":
                return self._do_click(action, "right")

            elif action_type == "middle_click":
                return self._do_click(action, "middle")

            elif action_type == "double_click":
                x, y = action.get("coordinate", [0, 0])
                pyautogui.doubleClick(x, y)
                time.sleep(0.1)
                return self._do_screenshot(f"ダブルクリック: ({x},{y})")

            elif action_type == "left_click_drag":
                return self._do_drag(action)

            elif action_type == "type":
                text = action.get("text", "")
                pyautogui.typewrite(text, interval=0.03)
                time.sleep(0.05)
                return self._do_screenshot(f"入力: {text[:30]}")

            elif action_type == "key":
                keys = action.get("text", "")
                self._press_key(keys)
                time.sleep(0.15)
                return self._do_screenshot(f"キー: {keys}")

            elif action_type == "scroll":
                x, y = action.get("coordinate", [0, 0])
                direction = action.get("direction", "down")
                amount = action.get("amount", 3)
                scroll_val = -amount if direction == "down" else amount
                pyautogui.scroll(scroll_val, x=x, y=y)
                time.sleep(0.1)
                return self._do_screenshot(f"スクロール{direction}: {amount}")

            elif action_type == "cursor_position":
                pos = pyautogui.position()
                return (
                    [{"type": "text", "text": f'{{"x":{pos.x},"y":{pos.y}}}'}],
                    True,
                    f"カーソル位置: {pos}",
                )

            else:
                return (
                    [{"type": "text", "text": f"未知のアクション: {action_type}"}],
                    False,
                    f"未知のアクション: {action_type}",
                )

        except pyautogui.FailSafeException:
            raise  # Re-raise to abort the loop
        except Exception as e:
            logger.error(f"Action error ({action_type}): {e}")
            return (
                [{"type": "text", "text": f"エラー: {e}"}],
                False,
                f"アクションエラー: {e}",
            )

    def _do_screenshot(self, context: str = "") -> Tuple[List[Dict], bool, str]:
        """Take a screenshot and return as base64 image content."""
        try:
            img = pyautogui.screenshot()

            # Save to disk
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            path = os.path.join(
                config.SAVE_FOLDERS[0],
                f"cu_{ts}.png",
            )
            os.makedirs(os.path.dirname(path), exist_ok=True)
            img.save(path)

            if self.on_screenshot:
                try:
                    self.on_screenshot(path)
                except Exception:
                    pass

            # Encode as base64 for the API
            import io
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            img_b64 = base64.standard_b64encode(buf.getvalue()).decode("utf-8")

            msg = f"スクリーンショット{': ' + context if context else ''}"
            return (
                [{
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": img_b64,
                    },
                }],
                True,
                msg,
            )
        except Exception as e:
            return (
                [{"type": "text", "text": f"スクリーンショット失敗: {e}"}],
                False,
                f"スクリーンショット失敗: {e}",
            )

    def _do_click(
        self,
        action: Dict,
        button: str = "left",
    ) -> Tuple[List[Dict], bool, str]:
        x, y = action.get("coordinate", [0, 0])
        pyautogui.click(x, y, button=button)
        time.sleep(0.1)
        return self._do_screenshot(f"{button}クリック: ({x},{y})")

    def _do_drag(self, action: Dict) -> Tuple[List[Dict], bool, str]:
        start = action.get("start_coordinate", action.get("coordinate", [0, 0]))
        end = action.get("end_coordinate", [0, 0])
        duration = action.get("duration", 0.5)
        pyautogui.moveTo(start[0], start[1])
        time.sleep(0.05)
        pyautogui.dragTo(end[0], end[1], duration=duration)
        return self._do_screenshot(f"ドラッグ: {start}→{end}")

    def _press_key(self, keys: str):
        """Press a key or key combination (e.g. 'ctrl+c', 'Return', 'super')."""
        # Normalize key names
        key_map = {
            "return": "enter",
            "super": "win",
            "ctrl": "ctrl",
            "alt": "alt",
            "shift": "shift",
            "escape": "esc",
            "delete": "delete",
            "backspace": "backspace",
            "tab": "tab",
        }
        parts = [k.strip().lower() for k in keys.split("+")]
        parts = [key_map.get(p, p) for p in parts]

        if len(parts) == 1:
            pyautogui.press(parts[0])
        else:
            pyautogui.hotkey(*parts)

    # ── System prompt ──────────────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        return (
            "あなたは画面操作AIアシスタントです。\n"
            "computerツールを使って、ユーザーのゴールを達成してください。\n\n"
            "## 行動原則\n"
            "1. まず現在の画面をscreenshotで確認してください\n"
            "2. ゴールを達成するために必要な最小限のアクションを実行してください\n"
            "3. 各アクション後にscreenshotで結果を確認し、期待通りか検証してください\n"
            "4. 予期しない画面が表示された場合は柔軟に対応してください\n"
            "5. エラーダイアログや確認ダイアログが出た場合は適切に対処してください\n"
            "6. タスクが完了したら、何をしたかを日本語で簡潔に報告してください\n\n"
            "## 注意事項\n"
            "- 一度に1つのアクションのみ実行する（複数のtool_useを返さない）\n"
            "- テキスト入力前には必ず入力フィールドをクリックしてフォーカスを取得する\n"
            "- ファイル保存などの重要な操作は完了を確認してから報告する\n"
            "- 破壊的な操作（ファイル削除、重要データの変更等）は実行前に一度確認する\n"
            f"- 画面解像度: {self._width}×{self._height}\n"
        )

    # ── Utilities ──────────────────────────────────────────────────────────

    def _action_summary(self, action: Dict) -> str:
        action_type = action.get("action", "")
        coord = action.get("coordinate", "")
        text = action.get("text", "")
        direction = action.get("direction", "")
        parts = []
        if coord:
            parts.append(str(coord))
        if text:
            parts.append(f'"{text[:20]}"')
        if direction:
            parts.append(direction)
        return " ".join(parts)

    def _status(self, message: str):
        logger.info(f"[ComputerUse] {message}")
        if self.on_status:
            try:
                self.on_status(message)
            except Exception:
                pass
