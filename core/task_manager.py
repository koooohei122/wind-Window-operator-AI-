"""
Task and Job management.

Hierarchy:
  Task  - Single unit of work (one AI goal, e.g. "メールをチェックしてSlackに投稿")
  Job   - Ordered collection of Tasks with a trigger (schedule / interval / manual)
  JobRun - Historical execution record

Persistence: data/jobs/ directory (JSON)
"""
import os
import json
import uuid
import datetime
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

# ── Storage paths ──────────────────────────────────────────────────────────

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
JOBS_DIR = os.path.join(DATA_DIR, "jobs")
TASKS_FILE = os.path.join(JOBS_DIR, "tasks.json")
JOBS_FILE = os.path.join(JOBS_DIR, "jobs.json")
RUNS_FILE = os.path.join(JOBS_DIR, "runs.json")


# ── Data classes ───────────────────────────────────────────────────────────

@dataclass
class Task:
    """
    A single unit of work for the AI to execute.
    goal: natural language instruction passed to ComputerUseAgent or execute_instruction.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    description: str = ""
    goal: str = ""                     # Sent to the AI as the instruction
    mode: str = "computer_use"         # "computer_use" | "standard"
    enabled: bool = True
    timeout_seconds: int = 300
    retry_count: int = 1
    tags: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: _now())
    updated_at: str = field(default_factory=lambda: _now())

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "Task":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Trigger:
    """
    When to run a Job.

    type:
      "manual"   - Only run when explicitly started
      "interval" - Every N minutes (value = "30" means every 30 min)
      "daily"    - Every day at a specific time (value = "09:00")
      "weekday"  - On specified weekdays at a time
                   (value = "09:00", days = ["mon","tue","wed","thu","fri"])
    """
    type: str = "manual"        # manual | interval | daily | weekday
    value: str = ""             # "30" for interval, "09:00" for daily/weekday
    days: List[str] = field(default_factory=list)  # mon,tue,wed,thu,fri,sat,sun

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "Trigger":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Job:
    """
    An ordered collection of Tasks with a trigger.
    All tasks run sequentially by default.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    description: str = ""
    trigger: Trigger = field(default_factory=Trigger)
    task_ids: List[str] = field(default_factory=list)  # ordered
    enabled: bool = True
    stop_on_task_failure: bool = True
    created_at: str = field(default_factory=lambda: _now())
    updated_at: str = field(default_factory=lambda: _now())
    last_run_at: str = ""
    last_run_status: str = ""  # completed | failed | running | ""

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["trigger"] = self.trigger.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: Dict) -> "Job":
        d = dict(d)
        if "trigger" in d and isinstance(d["trigger"], dict):
            d["trigger"] = Trigger.from_dict(d["trigger"])
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class TaskResult:
    task_id: str = ""
    task_name: str = ""
    started_at: str = ""
    completed_at: str = ""
    status: str = "pending"   # pending | running | completed | failed | skipped
    summary: str = ""
    attempt: int = 1

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class JobRun:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    job_id: str = ""
    job_name: str = ""
    started_at: str = field(default_factory=lambda: _now())
    completed_at: str = ""
    status: str = "running"   # running | completed | failed | aborted
    task_results: List[TaskResult] = field(default_factory=list)
    triggered_by: str = "manual"  # manual | schedule

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["task_results"] = [r.to_dict() for r in self.task_results]
        return d

    @classmethod
    def from_dict(cls, d: Dict) -> "JobRun":
        d = dict(d)
        results = d.pop("task_results", [])
        obj = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        obj.task_results = [TaskResult(**r) for r in results]
        return obj


# ── Task Manager ───────────────────────────────────────────────────────────

class TaskManager:
    """
    CRUD for Tasks and Jobs. Persists to JSON files.
    Thread-safe writes (holds a simple in-memory cache).
    """

    def __init__(self):
        os.makedirs(JOBS_DIR, exist_ok=True)
        self._tasks: Dict[str, Task] = {}
        self._jobs: Dict[str, Job] = {}
        self._runs: List[JobRun] = []
        self._load()

    # ── Tasks ──────────────────────────────────────────────────────────────

    def add_task(self, task: Task) -> Task:
        task.updated_at = _now()
        self._tasks[task.id] = task
        self._save_tasks()
        return task

    def update_task(self, task: Task) -> Task:
        task.updated_at = _now()
        self._tasks[task.id] = task
        self._save_tasks()
        return task

    def delete_task(self, task_id: str):
        self._tasks.pop(task_id, None)
        # Remove from all jobs
        for job in self._jobs.values():
            if task_id in job.task_ids:
                job.task_ids.remove(task_id)
        self._save_tasks()
        self._save_jobs()

    def get_task(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def list_tasks(self) -> List[Task]:
        return sorted(self._tasks.values(), key=lambda t: t.created_at)

    # ── Jobs ───────────────────────────────────────────────────────────────

    def add_job(self, job: Job) -> Job:
        job.updated_at = _now()
        self._jobs[job.id] = job
        self._save_jobs()
        return job

    def update_job(self, job: Job) -> Job:
        job.updated_at = _now()
        self._jobs[job.id] = job
        self._save_jobs()
        return job

    def delete_job(self, job_id: str):
        self._jobs.pop(job_id, None)
        self._save_jobs()

    def get_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def list_jobs(self) -> List[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at)

    def get_job_tasks(self, job: Job) -> List[Task]:
        """Return the Tasks for a Job in order."""
        return [self._tasks[tid] for tid in job.task_ids if tid in self._tasks]

    # ── Runs ───────────────────────────────────────────────────────────────

    def start_run(self, job: Job, triggered_by: str = "manual") -> JobRun:
        run = JobRun(
            job_id=job.id,
            job_name=job.name,
            triggered_by=triggered_by,
        )
        self._runs.append(run)
        # Update job status
        job.last_run_at = run.started_at
        job.last_run_status = "running"
        self._save_jobs()
        self._save_runs()
        return run

    def finish_run(self, run: JobRun, status: str, job: Job):
        run.completed_at = _now()
        run.status = status
        job.last_run_status = status
        self._save_jobs()
        self._save_runs()

    def get_recent_runs(self, job_id: str = None, limit: int = 50) -> List[JobRun]:
        runs = self._runs
        if job_id:
            runs = [r for r in runs if r.job_id == job_id]
        return sorted(runs, key=lambda r: r.started_at, reverse=True)[:limit]

    def get_running_jobs(self) -> List[str]:
        """Return job IDs currently running."""
        return [j.id for j in self._jobs.values() if j.last_run_status == "running"]

    # ── Persistence ────────────────────────────────────────────────────────

    def _load(self):
        try:
            if os.path.exists(TASKS_FILE):
                data = _read_json(TASKS_FILE)
                for d in data:
                    t = Task.from_dict(d)
                    self._tasks[t.id] = t
        except Exception as e:
            logger.error(f"Failed to load tasks: {e}")

        try:
            if os.path.exists(JOBS_FILE):
                data = _read_json(JOBS_FILE)
                for d in data:
                    j = Job.from_dict(d)
                    self._jobs[j.id] = j
        except Exception as e:
            logger.error(f"Failed to load jobs: {e}")

        try:
            if os.path.exists(RUNS_FILE):
                data = _read_json(RUNS_FILE)
                self._runs = [JobRun.from_dict(d) for d in data]
        except Exception as e:
            logger.error(f"Failed to load runs: {e}")

    def _save_tasks(self):
        _write_json(TASKS_FILE, [t.to_dict() for t in self._tasks.values()])

    def _save_jobs(self):
        _write_json(JOBS_FILE, [j.to_dict() for j in self._jobs.values()])

    def _save_runs(self):
        # Keep only last 200 runs
        runs = sorted(self._runs, key=lambda r: r.started_at, reverse=True)[:200]
        _write_json(RUNS_FILE, [r.to_dict() for r in runs])


# ── Helpers ────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.datetime.now().isoformat()


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, data: Any):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
