"""
Screen capture module: screenshots and screen recording at regular intervals.
Saves to multiple folders simultaneously.
"""
import os
import time
import threading
import datetime
import logging
from pathlib import Path
from typing import List, Optional, Callable

try:
    from PIL import ImageGrab, Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import mss
    import mss.tools
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

import config

logger = logging.getLogger(__name__)


def capture_screenshot() -> Optional[object]:
    """Capture a single screenshot. Returns PIL Image or numpy array."""
    if MSS_AVAILABLE:
        with mss.mss() as sct:
            monitor = sct.monitors[0]  # Full screen
            screenshot = sct.grab(monitor)
            if PIL_AVAILABLE:
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                return img
            else:
                return np.array(screenshot)
    elif PIL_AVAILABLE:
        return ImageGrab.grab()
    else:
        logger.error("No screen capture library available (mss or PIL required)")
        return None


def save_screenshot(img, folders: List[str], timestamp: str) -> List[str]:
    """Save screenshot to multiple folders. Returns list of saved paths."""
    saved_paths = []
    filename = f"screenshot_{timestamp}.png"

    for folder in folders:
        os.makedirs(folder, exist_ok=True)
        filepath = os.path.join(folder, filename)
        try:
            if PIL_AVAILABLE and hasattr(img, 'save'):
                img.save(filepath, "PNG")
            elif CV2_AVAILABLE and isinstance(img, np.ndarray):
                cv2.imwrite(filepath, cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
            saved_paths.append(filepath)
            logger.debug(f"Screenshot saved: {filepath}")
        except Exception as e:
            logger.error(f"Failed to save screenshot to {filepath}: {e}")

    return saved_paths


class ScreenshotCapture:
    """Periodically captures screenshots and saves to multiple folders."""

    def __init__(self, interval: int = None, on_capture: Callable = None):
        self.interval = interval or config.SCREENSHOT_INTERVAL_SECONDS
        self.on_capture = on_capture  # Callback(filepath_list, timestamp)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.capture_count = 0

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info(f"Screenshot capture started (interval: {self.interval}s)")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Screenshot capture stopped")

    def capture_once(self) -> List[str]:
        """Capture a single screenshot now and return saved paths."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        img = capture_screenshot()
        if img is None:
            return []

        folders = [
            config.SAVE_FOLDERS[0],  # screenshots/primary
            config.SAVE_FOLDERS[1],  # screenshots/backup
        ]
        paths = save_screenshot(img, folders, timestamp)
        self.capture_count += 1
        return paths

    def _capture_loop(self):
        while self._running:
            try:
                paths = self.capture_once()
                if paths and self.on_capture:
                    self.on_capture(paths, datetime.datetime.now())
            except Exception as e:
                logger.error(f"Screenshot capture error: {e}")
            time.sleep(self.interval)


class ScreenRecorder:
    """Records screen in segments and saves to multiple folders."""

    def __init__(self, segment_minutes: int = None, on_segment: Callable = None):
        self.segment_minutes = segment_minutes or config.RECORDING_SEGMENT_MINUTES
        self.on_segment = on_segment  # Callback(filepath_list, timestamp)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.fps = 5  # Low FPS to save space
        self.segment_count = 0

    def start(self):
        if not CV2_AVAILABLE:
            logger.error("OpenCV (cv2) required for screen recording")
            return
        if not MSS_AVAILABLE:
            logger.error("mss required for screen recording")
            return
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()
        logger.info(f"Screen recording started (segment: {self.segment_minutes}min)")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("Screen recording stopped")

    def _record_segment(self) -> List[str]:
        """Record one segment and return saved paths."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"recording_{timestamp}.avi"
        folders = [
            config.SAVE_FOLDERS[2],  # recordings/primary
            config.SAVE_FOLDERS[3],  # recordings/backup
        ]

        # Get screen size
        with mss.mss() as sct:
            monitor = sct.monitors[0]
            width = monitor["width"]
            height = monitor["height"]

        fourcc = cv2.VideoWriter_fourcc(*"XVID")
        writers = []
        paths = []
        for folder in folders:
            os.makedirs(folder, exist_ok=True)
            filepath = os.path.join(folder, filename)
            writer = cv2.VideoWriter(filepath, fourcc, self.fps, (width, height))
            writers.append(writer)
            paths.append(filepath)

        end_time = time.time() + self.segment_minutes * 60
        with mss.mss() as sct:
            monitor = sct.monitors[0]
            while self._running and time.time() < end_time:
                frame_start = time.time()
                screenshot = sct.grab(monitor)
                frame = np.array(screenshot)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                for writer in writers:
                    writer.write(frame)
                elapsed = time.time() - frame_start
                sleep_time = max(0, (1.0 / self.fps) - elapsed)
                time.sleep(sleep_time)

        for writer in writers:
            writer.release()

        self.segment_count += 1
        logger.info(f"Recording segment saved: {paths}")
        return paths

    def _record_loop(self):
        while self._running:
            try:
                paths = self._record_segment()
                if paths and self.on_segment:
                    self.on_segment(paths, datetime.datetime.now())
            except Exception as e:
                logger.error(f"Recording error: {e}")


class CaptureManager:
    """
    Unified manager for both screenshot and recording modes.
    Dispatches to the appropriate capture class based on config.
    """

    def __init__(self, mode: str = None, on_capture: Callable = None):
        self.mode = mode or config.CAPTURE_MODE
        self.on_capture = on_capture
        self._screenshot_capture = ScreenshotCapture(on_capture=on_capture)
        self._recorder = ScreenRecorder(on_segment=on_capture)
        self._running = False

    def start(self):
        self._running = True
        if self.mode == "screenshot":
            self._screenshot_capture.start()
        elif self.mode == "recording":
            self._recorder.start()
        elif self.mode == "both":
            self._screenshot_capture.start()
            self._recorder.start()
        logger.info(f"CaptureManager started in '{self.mode}' mode")

    def stop(self):
        self._running = False
        self._screenshot_capture.stop()
        self._recorder.stop()
        logger.info("CaptureManager stopped")

    def capture_now(self) -> List[str]:
        """Force a single screenshot capture right now."""
        return self._screenshot_capture.capture_once()

    @property
    def is_running(self) -> bool:
        return self._running
