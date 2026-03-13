"""
Job Runner: Executes Jobs (sequences of Tasks) using ComputerUseAgent.

Flow:
  JobRunner.run_job(job)
    for each Task in job:
      ComputerUseAgent.run(task.goal)   ← full agentic loop per task
      → result stored in JobRun
    finalize JobRun (completed / failed)

Supports:
  - Sequential task execution
  - Per-task timeout
  - Retry on failure
  - Stop on failure (configurable)
  - Callbacks for live progress
"""
import time
import logging
import threading
import datetime
from typing import Optional, Callable, List

from core.task_manager import (
    TaskManager, Job, Task, JobRun, TaskResult,
)
from core.computer_use_agent import ComputerUseAgent
import config

logger = logging.getLogger(__name__)


class JobRunner:
    """
    Executes a single Job.
    Creates one ComputerUseAgent per Task and blocks until it completes.
    """

    def __init__(
        self,
        task_manager: TaskManager,
        on_job_start: Optional[Callable] = None,      # (job, run)
        on_task_start: Optional[Callable] = None,     # (task, task_result)
        on_task_done: Optional[Callable] = None,      # (task, task_result)
        on_thinking: Optional[Callable] = None,       # (text) — CU thinking
        on_action: Optional[Callable] = None,         # (action, success, msg)
        on_job_done: Optional[Callable] = None,       # (job, run)
        on_status: Optional[Callable] = None,         # (message)
    ):
        self._tm = task_manager
        self.on_job_start = on_job_start
        self.on_task_start = on_task_start
        self.on_task_done = on_task_done
        self.on_thinking = on_thinking
        self.on_action = on_action
        self.on_job_done = on_job_done
        self.on_status = on_status

        self._abort = threading.Event()
        self._current_agent: Optional[ComputerUseAgent] = None
        self._running = False

    def run_job(
        self,
        job: Job,
        triggered_by: str = "manual",
    ) -> JobRun:
        """
        Execute all Tasks in a Job sequentially.
        Blocks until done or aborted.
        Returns the JobRun with results.
        """
        self._abort.clear()
        self._running = True

        run = self._tm.start_run(job, triggered_by=triggered_by)
        self._fire(self.on_job_start, job, run)
        self._status(f"ジョブ開始: {job.name}")

        tasks = self._tm.get_job_tasks(job)

        if not tasks:
            self._status(f"ジョブ '{job.name}': タスクが0件です")
            run.status = "completed"
            self._tm.finish_run(run, "completed", job)
            self._fire(self.on_job_done, job, run)
            self._running = False
            return run

        job_success = True

        for i, task in enumerate(tasks):
            if self._abort.is_set():
                self._status("ジョブ中断（ユーザー指示）")
                job_success = False
                break

            if not task.enabled:
                self._status(f"  スキップ: {task.name} (無効)")
                tr = TaskResult(
                    task_id=task.id,
                    task_name=task.name,
                    started_at=_now(),
                    completed_at=_now(),
                    status="skipped",
                    summary="タスクが無効化されています",
                )
                run.task_results.append(tr)
                continue

            self._status(
                f"  [{i+1}/{len(tasks)}] タスク実行: {task.name}"
            )

            tr = self._run_task(task, run)
            run.task_results.append(tr)

            self._fire(self.on_task_done, task, tr)

            if tr.status == "failed":
                job_success = False
                if job.stop_on_task_failure:
                    self._status(
                        f"  タスク失敗で停止: {task.name} — {tr.summary}"
                    )
                    break
                else:
                    self._status(
                        f"  タスク失敗（継続）: {task.name} — {tr.summary}"
                    )

        final_status = "completed" if (job_success and not self._abort.is_set()) else (
            "aborted" if self._abort.is_set() else "failed"
        )

        self._tm.finish_run(run, final_status, job)
        self._status(
            f"ジョブ完了: {job.name} → {final_status} "
            f"({sum(1 for r in run.task_results if r.status == 'completed')}/"
            f"{len(run.task_results)} タスク成功)"
        )
        self._fire(self.on_job_done, job, run)
        self._running = False
        return run

    def run_job_async(
        self,
        job: Job,
        triggered_by: str = "manual",
    ) -> threading.Thread:
        """Start run_job in a daemon thread. Returns the thread."""
        t = threading.Thread(
            target=self.run_job,
            args=(job, triggered_by),
            daemon=True,
            name=f"job-{job.id}",
        )
        t.start()
        return t

    def abort(self):
        """Abort the current job execution."""
        self._abort.set()
        if self._current_agent:
            self._current_agent.abort()

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Task execution ─────────────────────────────────────────────────────

    def _run_task(self, task: Task, run: JobRun) -> TaskResult:
        """
        Execute a single Task. Returns TaskResult.
        Retries on failure up to task.retry_count times.
        """
        tr = TaskResult(
            task_id=task.id,
            task_name=task.name,
            started_at=_now(),
            status="running",
        )
        self._fire(self.on_task_start, task, tr)

        for attempt in range(1, task.retry_count + 2):  # +2: at least one try
            if self._abort.is_set():
                tr.status = "failed"
                tr.summary = "中断されました"
                tr.completed_at = _now()
                return tr

            if attempt > 1:
                self._status(f"    リトライ {attempt}/{task.retry_count + 1}")
                time.sleep(2)

            tr.attempt = attempt
            summary = self._execute_task_goal(task)

            if summary.startswith("ERROR:"):
                tr.summary = summary
                if attempt <= task.retry_count:
                    continue
                tr.status = "failed"
            else:
                tr.status = "completed"
                tr.summary = summary
            break

        tr.completed_at = _now()
        return tr

    def _execute_task_goal(self, task: Task) -> str:
        """
        Run the task's goal through the appropriate engine.
        Returns summary string. Returns "ERROR: ..." on failure.
        """
        result_holder = {"summary": "", "error": ""}
        done_event = threading.Event()

        def on_complete(summary: str):
            result_holder["summary"] = summary
            done_event.set()

        def on_thinking(text: str):
            if self.on_thinking:
                try:
                    self.on_thinking(text)
                except Exception:
                    pass

        def on_action(action, success, msg):
            if self.on_action:
                try:
                    self.on_action(action, success, msg)
                except Exception:
                    pass

        if task.mode == "computer_use":
            agent = ComputerUseAgent(
                api_key=config.ANTHROPIC_API_KEY,
                on_thinking=on_thinking,
                on_action=on_action,
                on_status=self.on_status,
                on_complete=on_complete,
            )
            self._current_agent = agent
            agent.run(task.goal, background=True)
        else:
            # Standard mode: use the analyzer directly
            # (lightweight, no pyautogui needed for planning)
            from core.ai_analyzer import ScreenAnalyzer
            analyzer = ScreenAnalyzer()
            try:
                result = analyzer.understand_and_execute(
                    instruction=task.goal,
                )
                steps = result.get("steps", [])
                result_holder["summary"] = "完了: " + "; ".join(steps[:3])
                done_event.set()
            except Exception as e:
                result_holder["error"] = str(e)
                done_event.set()

        # Wait for completion (or timeout)
        timeout = task.timeout_seconds
        done_event.wait(timeout=timeout)

        self._current_agent = None

        if not done_event.is_set():
            if self._current_agent:
                self._current_agent.abort()
            return f"ERROR: タイムアウト ({timeout}秒)"

        if result_holder["error"]:
            return f"ERROR: {result_holder['error']}"

        return result_holder["summary"] or "完了"


    # ── Helpers ────────────────────────────────────────────────────────────

    def _fire(self, cb, *args):
        if cb:
            try:
                cb(*args)
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def _status(self, msg: str):
        logger.info(f"[JobRunner] {msg}")
        if self.on_status:
            try:
                self.on_status(msg)
            except Exception:
                pass


def _now() -> str:
    return datetime.datetime.now().isoformat()
