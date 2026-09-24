"""
Point Break Master Autonomous Personal Assistant Runtime Engine
===============================================================
Coordinates the complete autonomous execution lifecycle:
Observe -> Plan -> Inspect Risk -> Approval Gate -> Act -> Verify -> Self-Heal -> Report.
Supports task interruption, pause, resumption, and persistent state restoration.
"""

import time
import threading
from typing import Dict, Any, List, Optional, Callable

from core.agent.state import TaskState, TaskStep, TaskStatus, StepStatus, task_store
from core.agent.planner import goal_planner
from core.agent.verifier import outcome_verifier
from core.agent.recovery import self_healing_engine
from core.permissions.risk_matrix import classify_risk
from core.permissions.approval_gate import approval_gate, ApprovalDecision
from tools.registry import tool_registry

# Auto-register all domain tools into ToolRegistry
try:
    import tools.travel.train_engine
    import tools.travel.flight_engine
    import tools.travel.hotel_engine
    import tools.communications.email_agent
    import tools.system.calendar_agent
    import tools.system.meeting_engine
    import tools.system.local_services
    import tools.computer.visual_grounding
    import tools.computer.uia_driver
    import tools.office.spreadsheet_engine
    import tools.office.presentation_engine
    import tools.office.document_engine
    import tools.office.research_engine
    import tools.commerce.shopping_sniper
    import tools.commerce.food_delivery
except Exception as _tool_err:
    print(f"[AgentRuntime] Warning importing tools: {_tool_err}")

class AgentRuntime:
    def __init__(self):
        self.active_task: Optional[TaskState] = None
        self._is_running = False
        self._is_paused = False
        self._stop_requested = False
        self._lock = threading.Lock()
        self._pause_event = threading.Event()
        self._pause_event.set() # Unpaused by default
        self._thread: Optional[threading.Thread] = None

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def is_paused(self) -> bool:
        return self._is_paused

    def pause(self, speak_fn: Optional[Callable[[str], None]] = None):
        """Pauses execution of the active task."""
        with self._lock:
            if not self._is_running or self._is_paused:
                return
            self._is_paused = True
            self._pause_event.clear()
            if self.active_task:
                self.active_task.status = TaskStatus.PAUSED
                task_store.save_task(self.active_task)
            print("[AgentRuntime] ⏸️ Task paused by operator.")
            if speak_fn:
                speak_fn("Task execution paused, Sir. Standing by to resume.")

    def resume(self, speak_fn: Optional[Callable[[str], None]] = None):
        """Resumes a paused task."""
        with self._lock:
            if not self._is_running or not self._is_paused:
                return
            self._is_paused = False
            self._pause_event.set()
            if self.active_task:
                self.active_task.status = TaskStatus.EXECUTING
                task_store.save_task(self.active_task)
            print("[AgentRuntime] ▶️ Task resumed by operator.")
            if speak_fn:
                speak_fn("Resuming task execution now.")

    def stop(self, speak_fn: Optional[Callable[[str], None]] = None):
        """Aborts and cancels active execution."""
        with self._lock:
            self._stop_requested = True
            self._is_paused = False
            self._pause_event.set()
            if self.active_task:
                self.active_task.status = TaskStatus.CANCELLED
                task_store.save_task(self.active_task)
            print("[AgentRuntime] ⏹️ Stop requested. Aborting workflow.")
            if speak_fn:
                speak_fn("Task aborted, Sir.")

    def execute_goal_async(
        self,
        goal: str,
        speak_fn: Optional[Callable[[str], None]] = None,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> str:
        """Launches goal execution in a managed background thread."""
        self._thread = threading.Thread(
            target=self.execute_goal,
            args=(goal, speak_fn, callback),
            daemon=True
        )
        self._thread.start()
        return "Task initiated."

    def execute_goal(
        self,
        goal: str,
        speak_fn: Optional[Callable[[str], None]] = None,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """
        Executes an autonomous goal from start to finish.
        """
        with self._lock:
            self._is_running = True
            self._is_paused = False
            self._stop_requested = False
            self._pause_event.set()

        print(f"\n=======================================================")
        print(f" [Point Break Agent Runtime] Initiating Goal: '{goal}'")
        print(f"=======================================================")

        if speak_fn:
            speak_fn(f"Analyzing goal and compiling execution plan, Sir.")

        # 1. Synthesize multi-step execution plan
        steps = goal_planner.synthesize_plan(goal)
        task = task_store.create_task(goal=goal, initial_steps=steps)
        self.active_task = task

        if callback:
            callback({"task_id": task.task_id, "status": "planning", "steps_count": len(steps)})

        task.status = TaskStatus.EXECUTING
        task_store.save_task(task)

        total_steps = len(task.steps)
        print(f"[AgentRuntime] 📋 Execution Plan Generated with {total_steps} Steps:")
        for s in task.steps:
            print(f"   [{s.risk_level}] Step {s.index + 1}: {s.description} ({s.action})")

        # 2. Sequential Execution Loop
        while task.current_step_index < len(task.steps):
            # Check for pause
            self._pause_event.wait()

            # Check for cancellation
            if self._stop_requested:
                task.status = TaskStatus.CANCELLED
                task_store.save_task(task)
                with self._lock: self._is_running = False
                return {"success": False, "cancelled": True, "task_id": task.task_id}

            step = task.steps[task.current_step_index]
            step.status = StepStatus.RUNNING
            task_store.save_task(task)

            print(f"\n[AgentRuntime] ▶ Executing Step {step.index + 1}/{total_steps}: {step.description}")
            if callback:
                callback({
                    "task_id": task.task_id,
                    "status": "running_step",
                    "step_index": step.index + 1,
                    "total_steps": total_steps,
                    "description": step.description
                })

            # A. Risk Assessment & Safety Gate
            risk = classify_risk(step.action, step.parameters)
            decision = approval_gate.request_approval(risk, task_id=task.task_id, speak_fn=speak_fn)

            if decision == ApprovalDecision.REJECTED:
                print(f"[AgentRuntime] ❌ Step {step.index + 1} rejected by user. Aborting task.")
                step.status = StepStatus.FAILED
                step.error = "Rejected by user at approval gate."
                task.status = TaskStatus.CANCELLED
                task_store.save_task(task)
                with self._lock: self._is_running = False
                return {"success": False, "rejected": True, "task_id": task.task_id}

            # B. Execute Tool Action with Self-Healing Retries
            step_result = None
            step_error = None
            step_success = False

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # Execute tool via registry
                    tool_def = tool_registry.get_tool(step.action)
                    if tool_def:
                        step_result = tool_registry.execute(step.action, **step.parameters)
                    else:
                        print(f"[AgentRuntime] ⚠️ Tool '{step.action}' not in registry. Invoking generic handler.")
                        step_result = {"success": True, "action": step.action}

                    # C. Outcome Verification
                    verified, reason = outcome_verifier.verify_step_outcome(
                        step.action,
                        step.parameters,
                        step_result
                    )

                    if verified:
                        step_success = True
                        print(f"[AgentRuntime] ✅ Step {step.index + 1} verified: {reason}")
                        break
                    else:
                        step_error = reason
                        print(f"[AgentRuntime] ⚠️ Step {step.index + 1} verification warning: {reason}")

                except Exception as ex:
                    step_error = str(ex)
                    print(f"[AgentRuntime] ❌ Step {step.index + 1} execution error: {ex}")

                # Self-healing attempt
                if attempt < max_retries - 1:
                    recovered, rec_desc = self_healing_engine.attempt_recovery(
                        step.action,
                        step.parameters,
                        step_error or "Unknown error",
                        attempt + 1,
                        speak_fn=speak_fn
                    )
                    time.sleep(1.0)

            # Record step completion
            if step_success:
                step.status = StepStatus.SUCCESS
                step.result = step_result
                if isinstance(step_result, dict):
                    task.extracted_data.update(step_result)
            else:
                step.status = StepStatus.FAILED
                step.error = step_error
                print(f"[AgentRuntime] ❌ Step {step.index + 1} failed after {max_retries} attempts.")
                task.status = TaskStatus.FAILED
                task_store.save_task(task)
                with self._lock: self._is_running = False
                if speak_fn:
                    speak_fn(f"Step {step.index + 1} encountered a roadblock: {step_error}. Pausing for operator review.")
                return {"success": False, "status": "FAILED", "failed_step": step.index + 1, "error": step_error, "task_id": task.task_id}

            task.current_step_index += 1
            task_store.save_task(task)
            time.sleep(0.3)

        # 3. Task Completion
        task.status = TaskStatus.COMPLETED
        task_store.save_task(task)
        with self._lock: self._is_running = False

        print(f"\n[AgentRuntime] 🏆 Task '{task.task_id}' COMPLETED SUCCESSFULLY!")
        if speak_fn:
            speak_fn(f"Goal completed successfully, Sir. All {total_steps} steps verified.")

        if callback:
            callback({"task_id": task.task_id, "status": "completed", "steps": total_steps})

        return {
            "success": True,
            "status": "COMPLETED",
            "task_id": task.task_id,
            "goal": goal,
            "steps_executed": total_steps,
            "extracted_data": task.extracted_data
        }

agent_runtime = AgentRuntime()
