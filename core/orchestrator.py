"""
Orchestrator: Coordinates all modules - capture, analysis, memory, cleanup,
recommendations, and skill recording. Runs background analysis loops.
"""
import os
import time
import threading
import datetime
import logging
from typing import List, Optional, Callable, Dict, Any

import config
from core.screen_capture import CaptureManager
from core.ai_analyzer import ScreenAnalyzer
from core.memory_manager import MemoryManager
from core.cleanup_manager import CleanupManager
from core.recommender import Recommender
from core.skill_recorder import SkillRecorder

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Central coordinator for the Wind Window Operator AI system.
    Manages the lifecycle of all components and background analysis.
    """

    def __init__(
        self,
        on_status_update: Optional[Callable] = None,    # (message: str)
        on_recommendation: Optional[Callable] = None,    # (text: str)
        on_analysis_done: Optional[Callable] = None,     # (analysis: dict)
        on_capture: Optional[Callable] = None,           # (paths: list, ts)
        capture_mode: str = None,
    ):
        self.on_status_update = on_status_update
        self.on_recommendation = on_recommendation
        self.on_analysis_done = on_analysis_done

        # Modules
        self.capture = CaptureManager(
            mode=capture_mode or config.CAPTURE_MODE,
            on_capture=self._on_capture,
        )
        self.analyzer = ScreenAnalyzer()
        self.memory = MemoryManager()
        self.cleanup = CleanupManager(on_cleanup=self._on_cleanup)
        self.recommender = Recommender(on_text_recommendation=on_recommendation)
        self.skills = SkillRecorder()

        # State
        self._running = False
        self._recent_screenshots: List[str] = []
        self._analysis_thread: Optional[threading.Thread] = None
        self._recommend_thread: Optional[threading.Thread] = None
        self._screenshots_since_last_analysis = 0
        self._last_recommendation_time = 0

        if on_capture:
            self._external_on_capture = on_capture
        else:
            self._external_on_capture = None

    def start(self):
        """Start all background processes."""
        if self._running:
            return

        self._running = True
        self._status("システム起動中...")

        # Start components
        self.cleanup.start()
        self.recommender.start()
        self.capture.start()

        # Start analysis loop
        self._analysis_thread = threading.Thread(
            target=self._analysis_loop, daemon=True
        )
        self._analysis_thread.start()

        # Start recommendation loop
        self._recommend_thread = threading.Thread(
            target=self._recommendation_loop, daemon=True
        )
        self._recommend_thread.start()

        self._status(
            f"起動完了 - {config.CAPTURE_MODE}モード "
            f"(間隔:{config.SCREENSHOT_INTERVAL_SECONDS}秒)"
        )
        logger.info("Orchestrator started")

    def stop(self):
        """Stop all background processes."""
        if not self._running:
            return

        self._running = False
        self._status("システム停止中...")

        self.capture.stop()
        self.cleanup.stop()
        self.recommender.stop()

        if self._analysis_thread:
            self._analysis_thread.join(timeout=5)
        if self._recommend_thread:
            self._recommend_thread.join(timeout=5)

        self._status("停止完了")
        logger.info("Orchestrator stopped")

    def execute_instruction(self, instruction: str) -> Dict[str, Any]:
        """
        Receive a user instruction, understand it, execute steps,
        and record it as a skill.
        """
        self._status(f"指示を処理中: {instruction[:50]}")

        # Get current screenshot for context
        current_screenshot = None
        if self._recent_screenshots:
            current_screenshot = self._recent_screenshots[-1]

        # Get available skills
        relevant_skills = self.skills.search(instruction, max_results=5)

        # Ask AI to understand and plan execution
        analysis = self.analyzer.understand_and_execute(
            instruction=instruction,
            screenshot_path=current_screenshot,
            skills=relevant_skills,
        )

        # Record the skill
        if analysis.get("skill_name"):
            skill = self.skills.record_from_analysis(instruction, analysis)
            if skill:
                self.memory.add_skill_memo(
                    skill_name=skill.name,
                    description=skill.description,
                )
                self._status(f"スキル記録: {skill.name}")

        # Return the execution plan
        steps = analysis.get("steps", [])
        self._status(f"実行計画: {len(steps)}ステップ")

        return {
            "instruction": instruction,
            "steps": steps,
            "skill_name": analysis.get("skill_name", ""),
            "executable": analysis.get("executable", False),
            "timestamp": datetime.datetime.now().isoformat(),
        }

    def capture_now(self) -> List[str]:
        """Force an immediate screenshot."""
        paths = self.capture.capture_now()
        if paths:
            self._recent_screenshots.extend(paths)
            self._recent_screenshots = self._recent_screenshots[-20:]
        return paths

    # ─── Internal callbacks ───────────────────────────────────────────────

    def _on_capture(self, paths: List[str], timestamp: datetime.datetime):
        """Called when new screenshots/recordings are captured."""
        self._recent_screenshots.extend(paths)
        self._recent_screenshots = self._recent_screenshots[-20:]
        self._screenshots_since_last_analysis += 1

        if self._external_on_capture:
            self._external_on_capture(paths, timestamp)

    def _on_cleanup(self, deleted_count: int, freed_bytes: int):
        freed_mb = freed_bytes / (1024 * 1024)
        self._status(f"クリーンアップ: {deleted_count}件削除、{freed_mb:.1f}MB解放")

    # ─── Background loops ─────────────────────────────────────────────────

    def _analysis_loop(self):
        """Periodically analyze recent screenshots."""
        while self._running:
            # Wait for enough screenshots
            if self._screenshots_since_last_analysis >= config.ANALYSIS_INTERVAL_SECONDS // config.SCREENSHOT_INTERVAL_SECONDS:
                self._screenshots_since_last_analysis = 0
                self._run_analysis()
            time.sleep(5)

    def _run_analysis(self):
        """Run a single analysis cycle."""
        # Get recent unique screenshot paths
        screenshots = []
        seen = set()
        for p in reversed(self._recent_screenshots):
            if p not in seen and os.path.exists(p):
                seen.add(p)
                screenshots.append(p)
            if len(screenshots) >= config.MAX_SCREENSHOTS_PER_ANALYSIS:
                break
        screenshots.reverse()

        if not screenshots:
            return

        context = self.memory.get_context_for_analysis()
        short_term = self.memory.short_term.get_recent(5)

        try:
            analysis = self.analyzer.analyze_screenshots(
                screenshot_paths=screenshots,
                context=context,
                short_term_memory=short_term,
            )
            if analysis:
                # Save to memory
                self.memory.add_operation_memo(analysis)

                if self.on_analysis_done:
                    self.on_analysis_done(analysis)

                logger.debug(
                    f"Analysis done: {analysis.get('state','')[:60]}"
                )
        except Exception as e:
            logger.error(f"Analysis loop error: {e}")

    def _recommendation_loop(self):
        """Periodically generate and deliver recommendations."""
        while self._running:
            time.sleep(config.RECOMMENDATION_INTERVAL_SECONDS)

            if not self._running:
                break

            # Check enough time has passed
            now = time.time()
            if now - self._last_recommendation_time < config.RECOMMENDATION_INTERVAL_SECONDS:
                continue

            self._last_recommendation_time = now
            self._generate_recommendation()

    def _generate_recommendation(self):
        """Generate a new recommendation."""
        recent_analyses = []
        for entry in self.memory.short_term.get_recent(5):
            recent_analyses.append(entry)

        if not recent_analyses:
            return

        long_term = self.memory.long_term.get_recent(5)

        try:
            recommendation = self.analyzer.generate_recommendation(
                recent_analyses=recent_analyses,
                long_term_memory=long_term,
            )
            if recommendation:
                self.memory.add_recommendation(recommendation)
                self.recommender.recommend(recommendation, voice=config.VOICE_ENABLED)
                logger.debug(f"Recommendation: {recommendation[:80]}")
        except Exception as e:
            logger.error(f"Recommendation loop error: {e}")

    def _status(self, message: str):
        """Send a status update."""
        logger.info(message)
        if self.on_status_update:
            try:
                self.on_status_update(message)
            except Exception:
                pass

    # ─── Properties ───────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    def get_stats(self) -> Dict[str, Any]:
        """Get system statistics."""
        return {
            "running": self._running,
            "capture_mode": config.CAPTURE_MODE,
            "screenshots_captured": self.capture._screenshot_capture.capture_count,
            "analyses_done": self.analyzer.analysis_count,
            "recommendations_sent": self.recommender.recommendation_count,
            "skills_recorded": self.skills.count,
            "memory": self.memory.get_summary(),
            "disk": self.cleanup.get_disk_usage(),
        }
