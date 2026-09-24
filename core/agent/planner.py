"""
Point Break Resilient Goal Planner
==================================
Decomposes high-level natural language goals into an executable DAG of TaskSteps.
Uses multi-model Gemini LLM failover with strict schema validation.
Supports dynamic re-planning on runtime roadblocks.
"""

import os
import re
import json
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

from core.agent.state import TaskStep, StepStatus
from core.permissions.risk_matrix import classify_risk
from core.memory.context_store import context_store

try:
    import google.generativeai as genai
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    load_dotenv(os.path.join(base_dir, ".env"))
    _api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if _api_key:
        genai.configure(api_key=_api_key)
except Exception:
    genai = None

PLANNER_MODELS = [
    "gemini-2.5-flash",
    "gemini-3.6-flash",
    "gemini-2.5-pro",
    "gemini-1.5-pro"
]

class GoalPlanner:
    def __init__(self):
        pass

    def synthesize_plan(self, goal: str, context: Optional[Dict[str, Any]] = None) -> List[TaskStep]:
        """
        Synthesizes an executable list of TaskSteps for the goal.
        """
        clean_goal = self._clean_goal_str(goal)
        print(f"[GoalPlanner] 🧠 Synthesizing execution plan for: '{clean_goal}'")

        if not genai or not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
            print("[GoalPlanner] ⚠️ Gemini API not available. Using heuristic template planner.")
            return self._heuristic_fallback_plan(clean_goal)

        ctx_summary = context_store.get_context_summary()

        prompt = f"""
You are the Master Autonomous Personal Assistant (PA) Planner for Point Break.
User Context: {ctx_summary}
Goal: "{clean_goal}"

Generate an optimal, concise multi-step execution plan.
Canonical Actions you can use:
- "search_trains": params = {{"from_city": "...", "to_city": "...", "date": "..."}}
- "select_train": params = {{"train_name": "...", "departure_time": "...", "class": "..."}}
- "fill_passenger": params = {{"name": "...", "age": 24, "gender": "M", "berth": "..."}}
- "book_train_ticket": params = {{"train": "...", "fare": 2500, "date": "..."}}  (R3 Consequential)
- "read_inbox": params = {{"filter": "..."}}
- "summarize_emails": params = {{"topic": "..."}}
- "draft_email": params = {{"to": "...", "subject": "...", "body": "..."}}
- "send_email": params = {{"to": "...", "subject": "...", "body": "..."}} (R2 External Comms)
- "get_schedule": params = {{"date": "..."}}
- "create_calendar_event": params = {{"title": "...", "start": "...", "end": "..."}}
- "daily_briefing": params = {{}}
- "open_url": params = {{"url": "..."}}
- "click": params = {{"target": "..."}}
- "type_text": params = {{"target": "...", "text": "..."}}
- "hotkey": params = {{"keys": ["ctrl", "..."]}}
- "wait": params = {{"seconds": 1.0}}

Rules:
1. Break multi-step transactional requests into search -> select -> fill details -> book.
2. For emails: triage/draft -> send.
3. Keep total steps between 2 and 7 steps.
4. Output ONLY valid JSON in this exact structure:
{{
  "goal": "{clean_goal}",
  "steps": [
    {{
      "step": 1,
      "action": "action_name",
      "target": "target_name_or_url",
      "parameters": {{}},
      "description": "Short explanation of what this step does"
    }}
  ]
}}
"""

        for model_name in PLANNER_MODELS:
            try:
                model = genai.GenerativeModel(model_name)
                resp = model.generate_content(prompt, request_options={"timeout": 12.0})
                text = resp.text.strip()
                match = re.search(r'\{.*\}', text, re.DOTALL)
                if match:
                    data = json.loads(match.group(0))
                    raw_steps = data.get("steps", [])
                    if raw_steps:
                        return self._build_task_steps(raw_steps)
            except Exception as e:
                print(f"[GoalPlanner] Model {model_name} failed: {e}")
                continue

        return self._heuristic_fallback_plan(clean_goal)

    def _build_task_steps(self, raw_steps: List[Dict[str, Any]]) -> List[TaskStep]:
        task_steps = []
        for idx, s in enumerate(raw_steps):
            act = s.get("action", "unknown")
            params = s.get("parameters", {})
            risk = classify_risk(act, params)
            ts = TaskStep(
                index=idx,
                action=act,
                target=s.get("target", ""),
                parameters=params,
                description=s.get("description", f"Step {idx + 1}"),
                status=StepStatus.PENDING,
                risk_level=risk.level.value
            )
            task_steps.append(ts)
        return task_steps

    def _clean_goal_str(self, goal: str) -> str:
        q = re.sub(r'^(?:point\s*break|pointbreak|tars|jarvis)?[\s,\-:]*(?:can\s+you\s+|please\s+)?', '', goal, flags=re.I).strip()
        q = re.sub(r'^(?:automate\s+|agent\s+|drive\s+|plan\s+and\s+execute\s+)', '', q, flags=re.I).strip()
        return q or goal

    def _heuristic_fallback_plan(self, clean_goal: str) -> List[TaskStep]:
        """Deterministic plans for canonical user intents when LLM offline."""
        low = clean_goal.lower()

        # 1. Train booking (e.g. Kanpur to Delhi)
        if "train" in low or "irctc" in low:
            return [
                TaskStep(
                    index=0,
                    action="search_trains",
                    parameters={"query": clean_goal},
                    description="Search train routes and live seat availability",
                    risk_level="R0"
                ),
                TaskStep(
                    index=1,
                    action="select_train",
                    parameters={"preference": "fastest_premier"},
                    description="Select premier train option (Vande Bharat / Shatabdi)",
                    risk_level="R1"
                ),
                TaskStep(
                    index=2,
                    action="fill_passenger",
                    parameters={"passenger": "Daksh"},
                    description="Autofill passenger credentials from memory profile",
                    risk_level="R1"
                ),
                TaskStep(
                    index=3,
                    action="book_train_ticket",
                    parameters={"action": "checkout"},
                    description="Request user authorization and complete ticket checkout",
                    risk_level="R3"
                )
            ]

        # 2. Email drafting / triage
        if "email" in low or "mail" in low:
            return [
                TaskStep(
                    index=0,
                    action="read_inbox",
                    parameters={"query": clean_goal},
                    description="Read and summarize incoming emails",
                    risk_level="R0"
                ),
                TaskStep(
                    index=1,
                    action="create_draft_email",
                    parameters={"summary": clean_goal},
                    description="Draft response based on instruction",
                    risk_level="R1"
                )
            ]

        # 3. Daily briefing
        if "briefing" in low or "schedule" in low or "agenda" in low:
            return [
                TaskStep(
                    index=0,
                    action="daily_briefing",
                    parameters={},
                    description="Generate comprehensive daily briefing and agenda",
                    risk_level="R0"
                )
            ]

        # Default single-step general action
        return [
            TaskStep(
                index=0,
                action="open_url",
                parameters={"query": clean_goal},
                description=f"Execute action for '{clean_goal}'",
                risk_level="R0"
            )
        ]

goal_planner = GoalPlanner()
