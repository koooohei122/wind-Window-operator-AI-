"""
AI Analyzer: Uses Claude API (vision) to analyze screenshots and understand
human screen operations. Generates memos about user state, purpose, and intent.
"""
import os
import base64
import logging
import json
import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

import anthropic
import config

logger = logging.getLogger(__name__)


def encode_image_base64(image_path: str) -> Optional[str]:
    """Encode an image file to base64."""
    try:
        with open(image_path, "rb") as f:
            return base64.standard_b64encode(f.read()).decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to encode image {image_path}: {e}")
        return None


def get_image_media_type(path: str) -> str:
    ext = Path(path).suffix.lower()
    return {"png": "image/png", ".png": "image/png",
            "jpg": "image/jpeg", ".jpg": "image/jpeg",
            "jpeg": "image/jpeg", ".jpeg": "image/jpeg"}.get(ext, "image/png")


class ScreenAnalyzer:
    """
    Analyzes screenshots using Claude's vision capabilities to understand
    what the user is doing, why, and what assistance may be helpful.
    """

    SYSTEM_PROMPT = """あなたは画面操作の分析AIアシスタントです。
ユーザーのスクリーンショットを見て、以下を日本語で分析してください：

1. **現在の状態**: ユーザーが今何をしているか（アプリ、ファイル、作業内容）
2. **目的・意図**: なぜその操作をしていると思われるか
3. **次の行動予測**: 次に何をしようとしているか
4. **補助提案**: AIがどのように助けられるか（具体的で実用的なもの）
5. **注目点**: 特筆すべき操作パターンや習慣

分析は簡潔に、各項目50文字以内でまとめてください。
JSONフォーマットで返答してください。"""

    def __init__(self):
        api_key = config.ANTHROPIC_API_KEY or os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set. AI analysis will be disabled.")
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else None
        self.analysis_count = 0

    def analyze_screenshots(
        self,
        screenshot_paths: List[str],
        context: Optional[str] = None,
        short_term_memory: Optional[List[Dict]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze a list of screenshots and return structured analysis.

        Returns dict with keys: state, purpose, next_action, suggestion, pattern, raw_memo
        """
        if not self.client:
            return self._mock_analysis(screenshot_paths)

        # Build image content blocks (most recent N screenshots)
        image_blocks = []
        for path in screenshot_paths[-config.MAX_SCREENSHOTS_PER_ANALYSIS:]:
            encoded = encode_image_base64(path)
            if not encoded:
                continue
            image_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": get_image_media_type(path),
                    "data": encoded,
                },
            })

        if not image_blocks:
            logger.warning("No valid images to analyze")
            return None

        # Build text prompt with context
        context_text = ""
        if context:
            context_text += f"\n過去の操作コンテキスト:\n{context}\n"
        if short_term_memory:
            recent = short_term_memory[-3:]
            mem_text = "\n".join(
                f"- {m.get('timestamp','')}: {m.get('state','')}" for m in recent
            )
            context_text += f"\n直近の短期メモリ:\n{mem_text}\n"

        text_block = {
            "type": "text",
            "text": (
                f"以下の{'複数の' if len(image_blocks) > 1 else ''}スクリーンショット"
                f"（時系列順）を分析してください。{context_text}\n\n"
                "必ず以下のJSON形式で返答してください：\n"
                '{"state": "現在の状態", "purpose": "目的・意図", '
                '"next_action": "次の行動予測", "suggestion": "補助提案", '
                '"pattern": "操作パターン・注目点"}'
            ),
        }

        try:
            with self.client.messages.stream(
                model=config.CLAUDE_MODEL,
                max_tokens=1024,
                thinking={"type": "adaptive"},
                system=self.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": image_blocks + [text_block]}],
            ) as stream:
                response = stream.get_final_message()

            raw_text = next(
                (b.text for b in response.content if b.type == "text"), ""
            )
            self.analysis_count += 1

            # Parse JSON from response
            analysis = self._parse_json_response(raw_text)
            analysis["raw_memo"] = raw_text
            analysis["timestamp"] = datetime.datetime.now().isoformat()
            analysis["screenshot_count"] = len(image_blocks)
            return analysis

        except anthropic.AuthenticationError:
            logger.error("Invalid Anthropic API key")
            return self._mock_analysis(screenshot_paths)
        except Exception as e:
            logger.error(f"Analysis error: {e}")
            return self._mock_analysis(screenshot_paths)

    def generate_recommendation(
        self,
        recent_analyses: List[Dict],
        long_term_memory: Optional[List[Dict]] = None,
    ) -> Optional[str]:
        """
        Generate a recommendation/assistance suggestion based on recent analyses
        and memory. Returns Japanese text recommendation.
        """
        if not self.client or not recent_analyses:
            return "現在の操作を分析中です。しばらくお待ちください。"

        # Build context from recent analyses
        analysis_text = "\n".join(
            f"[{a.get('timestamp','')}] 状態: {a.get('state','')} / "
            f"目的: {a.get('purpose','')} / 提案: {a.get('suggestion','')}"
            for a in recent_analyses[-5:]
        )

        mem_text = ""
        if long_term_memory:
            mem_text = "\n長期メモリ（過去のパターン）:\n" + "\n".join(
                f"- {m.get('content','')}" for m in long_term_memory[-5:]
            )

        try:
            with self.client.messages.stream(
                model=config.CLAUDE_MODEL,
                max_tokens=512,
                thinking={"type": "adaptive"},
                system=(
                    "あなたは画面操作をサポートするAIアシスタントです。"
                    "ユーザーの操作履歴を見て、今すぐ役立つ具体的なアドバイスを"
                    "1〜3文の日本語で提供してください。"
                    "実用的で、ユーザーの作業効率を上げる提案をしてください。"
                ),
                messages=[{
                    "role": "user",
                    "content": (
                        f"以下の操作履歴に基づいて、今すぐ役立つアドバイスをください:\n\n"
                        f"{analysis_text}{mem_text}"
                    ),
                }],
            ) as stream:
                response = stream.get_final_message()

            return next((b.text for b in response.content if b.type == "text"), "")

        except Exception as e:
            logger.error(f"Recommendation generation error: {e}")
            return "操作の分析中にエラーが発生しました。"

    def understand_and_execute(
        self,
        instruction: str,
        screenshot_path: Optional[str] = None,
        skills: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """
        Understand a user instruction and determine how to execute it.
        Returns: {steps: [...], skill_name: str, skill_description: str, executable: bool}
        """
        if not self.client:
            return {
                "steps": ["AIが利用できません。APIキーを設定してください。"],
                "skill_name": "",
                "skill_description": "",
                "executable": False,
            }

        # Build context with current screen and available skills
        content = []
        if screenshot_path:
            encoded = encode_image_base64(screenshot_path)
            if encoded:
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": get_image_media_type(screenshot_path),
                        "data": encoded,
                    },
                })

        skills_text = ""
        if skills:
            skills_text = "\n利用可能なスキル:\n" + "\n".join(
                f"- {s.get('name','')}: {s.get('description','')}" for s in skills[:10]
            )

        content.append({
            "type": "text",
            "text": (
                f"ユーザーの指示: 「{instruction}」\n\n"
                f"{skills_text}\n\n"
                "この指示を実行するための手順を考えてください。\n"
                "以下のJSON形式で返答:\n"
                '{"steps": ["手順1", "手順2", ...], '
                '"skill_name": "このスキルの名前（英語スネークケース）", '
                '"skill_description": "このスキルの説明（日本語100文字以内）", '
                '"executable": true/false}'
            ),
        })

        try:
            with self.client.messages.stream(
                model=config.CLAUDE_MODEL,
                max_tokens=1024,
                thinking={"type": "adaptive"},
                system=(
                    "あなたは画面操作を実行するAIアシスタントです。"
                    "ユーザーの指示を理解し、具体的な実行手順を考えてください。"
                    "現在の画面状態を考慮して、最適な方法を提案してください。"
                ),
                messages=[{"role": "user", "content": content}],
            ) as stream:
                response = stream.get_final_message()

            raw_text = next((b.text for b in response.content if b.type == "text"), "")
            result = self._parse_json_response(raw_text)
            result.setdefault("steps", [raw_text])
            result.setdefault("skill_name", "custom_task")
            result.setdefault("skill_description", instruction[:100])
            result.setdefault("executable", True)
            return result

        except Exception as e:
            logger.error(f"Instruction understanding error: {e}")
            return {
                "steps": [f"エラー: {str(e)}"],
                "skill_name": "",
                "skill_description": "",
                "executable": False,
            }

    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        """Extract JSON from model response text."""
        # Try to find JSON block
        import re
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        # Return empty structure if parsing fails
        return {
            "state": text[:100] if text else "分析中",
            "purpose": "",
            "next_action": "",
            "suggestion": "",
            "pattern": "",
        }

    def _mock_analysis(self, screenshot_paths: List[str]) -> Dict[str, Any]:
        """Return mock analysis when API is unavailable."""
        return {
            "state": "APIキー未設定のためモック分析",
            "purpose": "画面操作の分析（APIキー設定後に有効化）",
            "next_action": "ANTHROPIC_API_KEY環境変数を設定してください",
            "suggestion": "設定ファイルまたは環境変数でAPIキーを設定してください",
            "pattern": "テストモード",
            "raw_memo": "APIキー未設定",
            "timestamp": datetime.datetime.now().isoformat(),
            "screenshot_count": len(screenshot_paths),
        }
