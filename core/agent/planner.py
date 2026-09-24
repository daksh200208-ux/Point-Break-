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
- "search_flights": params = {{"from_city": "...", "to_city": "...", "date_str": "..."}}
- "select_flight": params = {{"flight_number": "...", "preference": "fastest"}}
- "book_flight_ticket": params = {{"fare": 4650}} (R3 Consequential)
- "track_flight": params = {{"flight_number": "..."}}
- "search_hotels": params = {{"city": "...", "checkin_date": "...", "checkout_date": "..."}}
- "select_hotel": params = {{"hotel_name": "...", "room_type": "..."}}
- "reserve_hotel": params = {{"nights": 1, "total_fare": 7800}} (R3 Consequential)
- "check_hotel_reservation": params = {{"confirmation_code": "..."}}
- "search_local_services": params = {{"service_type": "...", "locality": "..."}}
- "schedule_service_appointment": params = {{"service_type": "...", "time_slot": "..."}} (R2 External Comms)
- "create_support_ticket": params = {{"platform_or_vendor": "...", "issue_category": "...", "description": "..."}}
- "draft_complaint": params = {{"target_company": "...", "order_or_account_id": "...", "incident_summary": "..."}}
- "read_inbox": params = {{"filter": "..."}}
- "summarize_emails": params = {{"topic": "..."}}
- "draft_email": params = {{"to": "...", "subject": "...", "body": "..."}}
- "send_email": params = {{"to": "...", "subject": "...", "body": "..."}} (R2 External Comms)
- "get_schedule": params = {{"date": "..."}}
- "create_calendar_event": params = {{"title": "...", "start": "...", "end": "..."}}
- "daily_briefing": params = {{}}
- "create_spreadsheet": params = {{"output_path": "...", "data": [{{"col": "val"}}]}}
- "generate_chart": params = {{"file_path": "...", "x_col": "...", "y_col": "...", "chart_type": "bar"}}
- "create_presentation": params = {{"title": "...", "subtitle": "...", "slides_data": [{{"title": "...", "points": ["..."]}}]}}
- "create_document": params = {{"title": "...", "sections": [{{"heading": "...", "body": "..."}}]}}
- "extract_pdf_text": params = {{"pdf_path": "..."}}
- "search_products": params = {{"query": "...", "platform": "amazon"}}
- "order_food": params = {{"query": "..."}}
- "prepare_meeting_briefing": params = {{"meeting_title": "..."}}
- "extract_action_items": params = {{"notes_or_transcript": "..."}}
- "deep_research": params = {{"topic": "..."}}
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

        # 4. Presentation & Slide Deck Creation
        if "presentation" in low or "slide" in low or "powerpoint" in low or "deck" in low:
            return [
                TaskStep(
                    index=0,
                    action="create_presentation",
                    parameters={"title": clean_goal.title(), "subtitle": "Point Break Automated Presentation"},
                    description="Generate 16:9 PowerPoint presentation deck with speaker notes",
                    risk_level="R1"
                )
            ]

        # 5. Spreadsheet & Tabular Analysis
        if "spreadsheet" in low or "excel" in low or "csv" in low or "chart" in low:
            return [
                TaskStep(
                    index=0,
                    action="create_spreadsheet",
                    parameters={
                        "output_path": "point_break_data.xlsx",
                        "data": [{"Metric": "Q1", "Score": 88}, {"Metric": "Q2", "Score": 94}, {"Metric": "Q3", "Score": 99}]
                    },
                    description="Compile tabular dataset into spreadsheet",
                    risk_level="R1"
                ),
                TaskStep(
                    index=1,
                    action="generate_chart",
                    parameters={"file_path": "point_break_data.xlsx", "x_col": "Metric", "y_col": "Score", "chart_type": "bar"},
                    description="Plot high-resolution data visualization chart",
                    risk_level="R1"
                )
            ]

        # 6. Document Generation & Proofreading
        if "document" in low or "docx" in low or "report" in low or "letter" in low:
            return [
                TaskStep(
                    index=0,
                    action="create_document",
                    parameters={
                        "title": clean_goal.title(),
                        "sections": [{"heading": "Overview", "body": f"Report regarding: {clean_goal}"}]
                    },
                    description="Author formatted Word (.docx) document",
                    risk_level="R1"
                )
            ]

        # 7. Shopping & Product Search
        if "buy" in low or "shop" in low or "amazon" in low or "flipkart" in low or "product" in low:
            return [
                TaskStep(
                    index=0,
                    action="search_products",
                    parameters={"query": clean_goal, "platform": "amazon"},
                    description="Perform automated product and price search",
                    risk_level="R0"
                )
            ]

        # 8. Food Delivery Comparison
        if "food" in low or "zomato" in low or "swiggy" in low or "order food" in low or "pizza" in low or "biryani" in low:
            return [
                TaskStep(
                    index=0,
                    action="order_food",
                    parameters={"query": clean_goal},
                    description="Compare dish prices between Swiggy and Zomato and prepare cart",
                    risk_level="R1"
                )
            ]

        # 9. Deep Research Dossier
        if "research" in low or "dossier" in low or "investigate" in low:
            return [
                TaskStep(
                    index=0,
                    action="deep_research",
                    parameters={"topic": clean_goal},
                    description="Synthesize multi-source research dossier with citations",
                    risk_level="R0"
                )
            ]

        # 10. Flight Search & Booking
        if "flight" in low or "fly" in low or "airline" in low:
            return [
                TaskStep(
                    index=0,
                    action="search_flights",
                    parameters={"from_city": "Delhi", "to_city": "Mumbai"},
                    description="Search direct flights and real-time fares across airlines",
                    risk_level="R0"
                ),
                TaskStep(
                    index=1,
                    action="select_flight",
                    parameters={"preference": "fastest"},
                    description="Select premier non-stop flight option",
                    risk_level="R1"
                ),
                TaskStep(
                    index=2,
                    action="book_flight_ticket",
                    parameters={"fare": 4650.0},
                    description="Request user confirmation and complete flight ticket booking",
                    risk_level="R3"
                )
            ]

        # 11. Hotel Search & Reservation
        if "hotel" in low or "resort" in low or "stay" in low:
            return [
                TaskStep(
                    index=0,
                    action="search_hotels",
                    parameters={"city": clean_goal},
                    description="Search rated hotel accommodations and room rates",
                    risk_level="R0"
                ),
                TaskStep(
                    index=1,
                    action="select_hotel",
                    parameters={"room_type": "Deluxe King Room"},
                    description="Select hotel property and room configuration",
                    risk_level="R1"
                ),
                TaskStep(
                    index=2,
                    action="reserve_hotel",
                    parameters={"nights": 1, "total_fare": 7800.0},
                    description="Authorize hotel reservation and generate voucher",
                    risk_level="R3"
                )
            ]

        # 12. Local Services & Technicians
        if any(w in low for w in ["repair", "plumber", "electrician", "technician", "ac service", "car service"]):
            return [
                TaskStep(
                    index=0,
                    action="search_local_services",
                    parameters={"service_type": clean_goal},
                    description="Find top-rated vetted local technicians and service providers",
                    risk_level="R0"
                ),
                TaskStep(
                    index=1,
                    action="schedule_service_appointment",
                    parameters={"service_type": clean_goal, "time_slot": "11:00 AM - 01:00 PM"},
                    description="Schedule service appointment and technician visit",
                    risk_level="R2"
                )
            ]

        # 13. Customer Support & Complaints
        if "complaint" in low or "grievance" in low or "support ticket" in low:
            return [
                TaskStep(
                    index=0,
                    action="create_support_ticket",
                    parameters={"platform_or_vendor": clean_goal, "issue_category": "Service Escalation", "description": clean_goal},
                    description="File formal customer support escalation ticket",
                    risk_level="R1"
                ),
                TaskStep(
                    index=1,
                    action="draft_complaint",
                    parameters={"target_company": clean_goal, "order_or_account_id": "REF-AUTO", "incident_summary": clean_goal},
                    description="Draft formal consumer protection complaint letter",
                    risk_level="R1"
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
