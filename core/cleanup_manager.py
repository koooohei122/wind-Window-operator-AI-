"""
Cleanup Manager: Periodically deletes old screenshots and recordings
based on configured retention hours, while preserving memory files.
"""
import os
import time
import threading
import datetime
import logging
from pathlib import Path
from typing import Callable, Optional

import config

logger = logging.getLogger(__name__)


class CleanupManager:
    """
    Background cleanup manager that removes old media files
    while preserving analysis memories.
    """

    def __init__(self, on_cleanup: Optional[Callable] = None):
        self.on_cleanup = on_cleanup  # Callback(deleted_count, freed_bytes)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.total_deleted = 0
        self.total_freed_bytes = 0

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._thread.start()
        logger.info(
            f"Cleanup manager started "
            f"(screenshots: {config.SCREENSHOT_RETENTION_HOURS}h, "
            f"recordings: {config.RECORDING_RETENTION_HOURS}h)"
        )

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Cleanup manager stopped")

    def run_now(self) -> dict:
        """Run cleanup immediately and return stats."""
        return self._do_cleanup()

    def _cleanup_loop(self):
        interval = config.CLEANUP_CHECK_INTERVAL_MINUTES * 60
        while self._running:
            try:
                stats = self._do_cleanup()
                if stats["deleted"] > 0:
                    logger.info(
                        f"Cleanup: deleted {stats['deleted']} files, "
                        f"freed {stats['freed_mb']:.1f} MB"
                    )
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
            time.sleep(interval)

    def _do_cleanup(self) -> dict:
        """Delete old files based on retention policy. Returns stats."""
        deleted = 0
        freed_bytes = 0
        now = datetime.datetime.now()

        # Screenshot folders (primary + backup)
        screenshot_folders = [
            config.SAVE_FOLDERS[0],
            config.SAVE_FOLDERS[1],
        ]
        screenshot_cutoff = now - datetime.timedelta(
            hours=config.SCREENSHOT_RETENTION_HOURS
        )

        for folder in screenshot_folders:
            d, b = self._delete_old_files(
                folder,
                cutoff=screenshot_cutoff,
                extensions={".png", ".jpg", ".jpeg"},
            )
            deleted += d
            freed_bytes += b

        # Recording folders (primary + backup)
        recording_folders = [
            config.SAVE_FOLDERS[2],
            config.SAVE_FOLDERS[3],
        ]
        recording_cutoff = now - datetime.timedelta(
            hours=config.RECORDING_RETENTION_HOURS
        )

        for folder in recording_folders:
            d, b = self._delete_old_files(
                folder,
                cutoff=recording_cutoff,
                extensions={".avi", ".mp4", ".mkv"},
            )
            deleted += d
            freed_bytes += b

        self.total_deleted += deleted
        self.total_freed_bytes += freed_bytes

        stats = {
            "deleted": deleted,
            "freed_bytes": freed_bytes,
            "freed_mb": freed_bytes / (1024 * 1024),
            "timestamp": now.isoformat(),
        }

        if self.on_cleanup and deleted > 0:
            self.on_cleanup(deleted, freed_bytes)

        return stats

    def _delete_old_files(
        self,
        folder: str,
        cutoff: datetime.datetime,
        extensions: set,
    ) -> tuple:
        """Delete files older than cutoff with matching extensions. Returns (count, bytes)."""
        deleted = 0
        freed = 0

        if not os.path.exists(folder):
            return 0, 0

        for filepath in Path(folder).iterdir():
            if not filepath.is_file():
                continue
            if filepath.suffix.lower() not in extensions:
                continue

            try:
                mtime = datetime.datetime.fromtimestamp(filepath.stat().st_mtime)
                if mtime < cutoff:
                    size = filepath.stat().st_size
                    filepath.unlink()
                    deleted += 1
                    freed += size
                    logger.debug(f"Deleted old file: {filepath}")
            except Exception as e:
                logger.warning(f"Could not delete {filepath}: {e}")

        return deleted, freed

    def get_disk_usage(self) -> dict:
        """Get current disk usage for all managed folders."""
        usage = {}
        for i, folder in enumerate(config.SAVE_FOLDERS):
            folder_name = ["screenshots/primary", "screenshots/backup",
                           "recordings/primary", "recordings/backup"][i]
            total_size = 0
            file_count = 0
            if os.path.exists(folder):
                for f in Path(folder).iterdir():
                    if f.is_file():
                        total_size += f.stat().st_size
                        file_count += 1
            usage[folder_name] = {
                "files": file_count,
                "size_mb": total_size / (1024 * 1024),
            }

        usage["total_deleted"] = self.total_deleted
        usage["total_freed_mb"] = self.total_freed_bytes / (1024 * 1024)
        return usage
