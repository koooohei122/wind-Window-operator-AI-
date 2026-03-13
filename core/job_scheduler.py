"""
Job Scheduler: Background thread that fires Jobs when their trigger conditions are met.

Supported trigger types:
  manual   — Never fires automatically
  interval — Every N minutes
  daily    — Every day at HH:MM
  weekday  — On specified weekdays (mon/tue/..) at HH:MM
"""
import time
import logging
import threading
import datetime
from typing import Optional, Callable, List, Dict

from core.task_manager import TaskManager, Job, Trigger

logger = logging.getLogger(__name__)

WEEKDAY_MAP = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3,
    "fri": 4, "sat": 5, "sun": 6,
}


class JobScheduler:
    """
    Polls every 30 seconds to check whether any enabled Job is due to run.
    Fires on_trigger(job) when a job should be executed.
    """

    POLL_INTERVAL = 30  # seconds

    def __init__(
        self,
        task_manager: TaskManager,
        on_trigger: Optional[Callable] = None,  # (job: Job, triggered_by: str)
        on_status: Optional[Callable] = None,   # (message: str)
    ):
        self._tm = task_manager
        self.on_trigger = on_trigger
        self.on_status = on_status

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False

        # Track last fired time to avoid double-trigger within same minute
        # job_id -> last_fired datetime (local)
        self._last_fired: Dict[str, datetime.datetime] = {}

    def start(self):
        if self._running:
            return
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="job-scheduler",
        )
        self._thread.start()
        logger.info("[Scheduler] 起動しました")

    def stop(self):
        self._stop_event.set()
        self._running = False
        logger.info("[Scheduler] 停止しました")

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Scheduler loop ─────────────────────────────────────────────────────

    def _loop(self):
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception as e:
                logger.error(f"[Scheduler] エラー: {e}")
            self._stop_event.wait(timeout=self.POLL_INTERVAL)

    def _tick(self):
        now = datetime.datetime.now()
        for job in self._tm.list_jobs():
            if not job.enabled:
                continue
            if job.last_run_status == "running":
                continue  # already running
            if self._should_fire(job, now):
                self._last_fired[job.id] = now
                logger.info(f"[Scheduler] ジョブ発火: {job.name}")
                if self.on_trigger:
                    try:
                        self.on_trigger(job, "schedule")
                    except Exception as e:
                        logger.error(f"[Scheduler] trigger callback error: {e}")

    def _should_fire(self, job: Job, now: datetime.datetime) -> bool:
        t = job.trigger
        if t.type == "manual":
            return False

        # Avoid firing more than once per minute for the same job
        last = self._last_fired.get(job.id)
        if last and (now - last).total_seconds() < 60:
            return False

        if t.type == "interval":
            return self._check_interval(job, t, now)
        elif t.type in ("daily", "weekday"):
            return self._check_time_trigger(job, t, now)

        return False

    def _check_interval(self, job: Job, t: Trigger, now: datetime.datetime) -> bool:
        """Fire every N minutes."""
        try:
            interval_minutes = int(t.value)
        except ValueError:
            return False

        if not job.last_run_at:
            return True  # Never run before → fire immediately

        try:
            last_run = datetime.datetime.fromisoformat(job.last_run_at)
        except ValueError:
            return True

        elapsed_minutes = (now - last_run).total_seconds() / 60
        return elapsed_minutes >= interval_minutes

    def _check_time_trigger(self, job: Job, t: Trigger, now: datetime.datetime) -> bool:
        """Fire at a specific time (HH:MM), optionally on specific weekdays."""
        try:
            h, m = map(int, t.value.split(":"))
        except (ValueError, AttributeError):
            return False

        # Check weekday constraint
        if t.type == "weekday" and t.days:
            today_name = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][now.weekday()]
            if today_name not in t.days:
                return False

        # Check if current time matches HH:MM (within the polling window)
        if now.hour != h or now.minute != m:
            return False

        # Make sure we haven't already fired today at this time
        last = self._last_fired.get(job.id)
        if last:
            if last.date() == now.date() and last.hour == h and last.minute == m:
                return False

        return True

    # ── Utilities ──────────────────────────────────────────────────────────

    def next_run_str(self, job: Job) -> str:
        """Human-readable string for when the job will next run."""
        t = job.trigger
        if t.type == "manual":
            return "手動のみ"
        if t.type == "interval":
            try:
                mins = int(t.value)
                return f"{mins}分ごと"
            except ValueError:
                return "不明"
        if t.type in ("daily", "weekday"):
            base = f"{t.value} に実行"
            if t.type == "weekday" and t.days:
                day_str = "/".join(t.days)
                return f"{day_str} {base}"
            return f"毎日 {base}"
        return "不明"
