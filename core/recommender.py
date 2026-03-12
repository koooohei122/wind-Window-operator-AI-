"""
Recommender: Delivers AI recommendations via voice (TTS) and text.
Supports Japanese text-to-speech with fallback options.
"""
import logging
import threading
import queue
import time
from typing import Optional, Callable

import config

logger = logging.getLogger(__name__)


def _try_import_tts():
    """Try to import available TTS libraries."""
    # Try pyttsx3 (offline, fast)
    try:
        import pyttsx3
        return "pyttsx3", pyttsx3
    except ImportError:
        pass

    # Try gtts (online, better Japanese support)
    try:
        import gtts
        return "gtts", gtts
    except ImportError:
        pass

    return None, None


TTS_ENGINE, TTS_LIB = _try_import_tts()


class VoiceEngine:
    """Text-to-speech engine with Japanese support."""

    def __init__(self):
        self.engine_type = TTS_ENGINE
        self._engine = None
        self._lock = threading.Lock()
        self._initialized = False

        if self.engine_type == "pyttsx3":
            self._init_pyttsx3()
        elif self.engine_type == "gtts":
            logger.info("Using gTTS for voice output (requires internet)")
        else:
            logger.warning(
                "No TTS library found. Install pyttsx3 or gtts for voice support.\n"
                "  pip install pyttsx3  (offline)\n"
                "  pip install gtts playsound  (online, better Japanese)"
            )

    def _init_pyttsx3(self):
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", config.VOICE_RATE)

            # Try to set Japanese voice
            voices = self._engine.getProperty("voices")
            for voice in voices:
                if "ja" in voice.id.lower() or "japanese" in voice.name.lower():
                    self._engine.setProperty("voice", voice.id)
                    break

            self._initialized = True
            logger.info("pyttsx3 TTS initialized")
        except Exception as e:
            logger.error(f"pyttsx3 init error: {e}")
            self._initialized = False

    def speak(self, text: str) -> bool:
        """Speak the given text. Returns True if successful."""
        if not config.VOICE_ENABLED:
            return False

        with self._lock:
            if self.engine_type == "pyttsx3" and self._initialized:
                return self._speak_pyttsx3(text)
            elif self.engine_type == "gtts":
                return self._speak_gtts(text)
            else:
                logger.debug(f"[VOICE] {text}")
                return False

    def _speak_pyttsx3(self, text: str) -> bool:
        try:
            self._engine.say(text)
            self._engine.runAndWait()
            return True
        except Exception as e:
            logger.error(f"pyttsx3 speak error: {e}")
            return False

    def _speak_gtts(self, text: str) -> bool:
        try:
            from gtts import gTTS
            import tempfile
            import os

            tts = gTTS(text=text, lang=config.VOICE_LANGUAGE)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                tts.save(f.name)
                tmp_path = f.name

            # Try to play
            try:
                import playsound
                playsound.playsound(tmp_path)
            except ImportError:
                try:
                    import subprocess
                    subprocess.run(["mpg123", tmp_path], capture_output=True)
                except Exception:
                    try:
                        subprocess.run(["aplay", tmp_path], capture_output=True)
                    except Exception:
                        pass

            os.unlink(tmp_path)
            return True
        except Exception as e:
            logger.error(f"gTTS speak error: {e}")
            return False

    @property
    def available(self) -> bool:
        return self._initialized or self.engine_type == "gtts"


class Recommender:
    """
    Delivers recommendations to the user via voice and text.
    Uses a background queue to avoid blocking the main thread.
    """

    def __init__(self, on_text_recommendation: Optional[Callable] = None):
        self.on_text_recommendation = on_text_recommendation
        self._voice = VoiceEngine()
        self._queue: queue.Queue = queue.Queue()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_recommendation = ""
        self._recommendation_count = 0

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._process_queue, daemon=True)
        self._thread.start()
        logger.info("Recommender started")

    def stop(self):
        self._running = False
        self._queue.put(None)  # Sentinel to unblock
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Recommender stopped")

    def recommend(
        self,
        text: str,
        voice: bool = True,
        priority: int = 0,
    ):
        """
        Queue a recommendation.
        priority: 0=normal, 1=high (high priority recommendations skip queue)
        """
        if not text or text == self._last_recommendation:
            return

        item = {"text": text, "voice": voice, "priority": priority}

        if priority >= 1:
            # High priority: process immediately in background
            threading.Thread(
                target=self._deliver,
                args=(item,),
                daemon=True,
            ).start()
        else:
            self._queue.put(item)

    def _process_queue(self):
        """Process queued recommendations."""
        while self._running:
            try:
                item = self._queue.get(timeout=1)
                if item is None:
                    break
                self._deliver(item)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Recommender queue error: {e}")

    def _deliver(self, item: dict):
        """Deliver a recommendation via text and optionally voice."""
        text = item.get("text", "")
        if not text:
            return

        self._last_recommendation = text
        self._recommendation_count += 1

        # Text delivery via callback
        if self.on_text_recommendation:
            try:
                self.on_text_recommendation(text)
            except Exception as e:
                logger.error(f"Text recommendation callback error: {e}")

        # Voice delivery
        if item.get("voice", True) and config.VOICE_ENABLED:
            self._voice.speak(text)

    @property
    def voice_available(self) -> bool:
        return self._voice.available

    @property
    def recommendation_count(self) -> int:
        return self._recommendation_count
