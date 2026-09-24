"""
Point Break Durable Task State Machine
======================================
Provides crash-resilient task persistence with SQLite and active JSON mirrors.
Allows complex multi-step workflows to pause for approvals, resume after reboots,
and recover from crashes without loss of state.
"""

import os
import json
import time
import sqlite3
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional

class TaskStatus(Enum):
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class StepStatus(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"

@dataclass
class TaskStep:
    index: int
    action: str
    target: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    status: StepStatus = StepStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    retry_count: int = 0
    risk_level: str = "R0"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskStep":
        d = dict(data)
        if isinstance(d.get("status"), str):
            d["status"] = StepStatus(d["status"])
        return cls(**d)

@dataclass
class TaskState:
    task_id: str
    goal: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    current_step_index: int = 0
    steps: List[TaskStep] = field(default_factory=list)
    extracted_data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_finished(self) -> bool:
        return self.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]

    def get_current_step(self) -> Optional[TaskStep]:
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "current_step_index": self.current_step_index,
            "steps": [s.to_dict() for s in self.steps],
            "extracted_data": self.extracted_data,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskState":
        steps = [TaskStep.from_dict(s) for s in data.get("steps", [])]
        status = TaskStatus(data.get("status", TaskStatus.PENDING.value))
        return cls(
            task_id=data["task_id"],
            goal=data["goal"],
            status=status,
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            current_step_index=data.get("current_step_index", 0),
            steps=steps,
            extracted_data=data.get("extracted_data", {}),
            metadata=data.get("metadata", {})
        )

class TaskStore:
    def __init__(self, db_path: Optional[str] = None):
        if not db_path:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            db_path = os.path.join(base_dir, "task_state.db")
        self.db_path = db_path
        self.active_json_path = os.path.join(os.path.dirname(self.db_path), "active_task.json")
        self._init_db()

    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS tasks (
                        task_id TEXT PRIMARY KEY,
                        goal TEXT,
                        status TEXT,
                        created_at REAL,
                        updated_at REAL,
                        current_step_index INTEGER,
                        state_json TEXT
                    )
                """)
                conn.commit()
        except Exception as e:
            print(f"[TaskStore] DB init error: {e}")

    def save_task(self, state: TaskState):
        state.updated_at = time.time()
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO tasks 
                    (task_id, goal, status, created_at, updated_at, current_step_index, state_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    state.task_id,
                    state.goal,
                    state.status.value,
                    state.created_at,
                    state.updated_at,
                    state.current_step_index,
                    json.dumps(state.to_dict())
                ))
                conn.commit()

            # Mirror to active_task.json if active
            if not state.is_finished:
                with open(self.active_json_path, "w", encoding="utf-8") as f:
                    json.dump(state.to_dict(), f, indent=2)
            else:
                if os.path.exists(self.active_json_path):
                    try: os.remove(self.active_json_path)
                    except: pass
        except Exception as e:
            print(f"[TaskStore] Error saving task {state.task_id}: {e}")

    def create_task(self, goal: str, initial_steps: Optional[List[TaskStep]] = None) -> TaskState:
        t_id = f"task_{time.strftime('%Y%m%d_%H%M%S')}_{int(time.time() * 1000) % 1000}"
        state = TaskState(
            task_id=t_id,
            goal=goal,
            status=TaskStatus.PLANNING,
            steps=initial_steps or []
        )
        self.save_task(state)
        return state

    def get_task(self, task_id: str) -> Optional[TaskState]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT state_json FROM tasks WHERE task_id = ?", (task_id,))
                row = cursor.fetchone()
                if row:
                    return TaskState.from_dict(json.loads(row[0]))
        except Exception as e:
            print(f"[TaskStore] Error fetching task {task_id}: {e}")
        return None

    def get_active_task(self) -> Optional[TaskState]:
        """Loads task from active_task.json or newest unfinished in DB."""
        if os.path.exists(self.active_json_path):
            try:
                with open(self.active_json_path, "r", encoding="utf-8") as f:
                    return TaskState.from_dict(json.load(f))
            except Exception:
                pass

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT state_json FROM tasks 
                    WHERE status NOT IN ('COMPLETED', 'FAILED', 'CANCELLED') 
                    ORDER BY updated_at DESC LIMIT 1
                """)
                row = cursor.fetchone()
                if row:
                    return TaskState.from_dict(json.loads(row[0]))
        except Exception as e:
            print(f"[TaskStore] Error getting active task: {e}")
        return None

    def list_interrupted_tasks(self) -> List[TaskState]:
        """Finds any tasks left unfinished due to system reboot or crash."""
        tasks = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT state_json FROM tasks 
                    WHERE status IN ('EXECUTING', 'PLANNING', 'AWAITING_APPROVAL', 'PAUSED')
                    ORDER BY updated_at DESC
                """)
                for row in cursor.fetchall():
                    tasks.append(TaskState.from_dict(json.loads(row[0])))
        except Exception as e:
            print(f"[TaskStore] Error listing interrupted tasks: {e}")
        return tasks

    def update_step(
        self,
        task_id: str,
        step_index: int,
        status: StepStatus,
        result: Optional[Any] = None,
        error: Optional[str] = None
    ):
        state = self.get_task(task_id)
        if state and 0 <= step_index < len(state.steps):
            step = state.steps[step_index]
            step.status = status
            if result is not None: step.result = result
            if error is not None: step.error = error
            self.save_task(state)

    def set_task_status(self, task_id: str, status: TaskStatus):
        state = self.get_task(task_id)
        if state:
            state.status = status
            self.save_task(state)

task_store = TaskStore()
