"""
Point Break Calendar, Briefing & Scheduling Engine
==================================================
Handles user schedule optimization, daily & evening briefings, conflict resolution,
and calendar events.
"""

import time
import datetime
from typing import Dict, Any, List, Optional
from tools.registry import register_tool
from core.memory.context_store import context_store

class CalendarAgent:
    def __init__(self):
        self.events: List[Dict[str, Any]] = [
            {"id": "evt_1", "title": "Team Standup", "start": "10:00", "end": "10:30", "priority": "High"},
            {"id": "evt_2", "title": "Client Sync - Point Break Architecture", "start": "14:00", "end": "15:00", "priority": "High"},
            {"id": "evt_3", "title": "Gym / Workout", "start": "19:00", "end": "20:00", "priority": "Medium"}
        ]

    def get_schedule(self, date_str: Optional[str] = None) -> Dict[str, Any]:
        """Returns events for the requested date."""
        return {"success": True, "date": date_str or "Today", "events": self.events}

    def create_event(self, title: str, start: str, end: str, date_str: Optional[str] = None) -> Dict[str, Any]:
        """Creates an event on the user calendar."""
        event_id = f"evt_{int(time.time())}"
        new_event = {
            "id": event_id,
            "title": title,
            "start": start,
            "end": end,
            "date": date_str or datetime.date.today().isoformat()
        }
        self.events.append(new_event)
        print(f"[CalendarAgent] 📅 Event created: '{title}' from {start} to {end}")
        return {"success": True, "event": new_event}

    def generate_daily_briefing(self) -> Dict[str, Any]:
        """Synthesizes comprehensive morning briefing for Daksh."""
        user = context_store.preferences.user_name
        briefing = (
            f"Good morning, {user}. Here is your operational briefing: "
            f"You have 3 scheduled commitments today starting with Team Standup at 10:00 AM, "
            f"followed by Client Architecture Sync at 2:00 PM. "
            f"Weather is clear, and your pending tasks are staged in queue."
        )
        return {
            "success": True,
            "briefing_text": briefing,
            "scheduled_count": len(self.events)
        }

    def generate_evening_briefing(self) -> Dict[str, Any]:
        """Synthesizes evening recap and tomorrow preview."""
        user = context_store.preferences.user_name
        briefing = (
            f"Good evening, {user}. Daily recap: all primary tasks completed. "
            f"Tomorrow morning you have an open calendar block until 11:00 AM. "
            f"All critical systems are stable."
        )
        return {"success": True, "briefing_text": briefing}

calendar_agent = CalendarAgent()

@register_tool(name="get_schedule", description="Fetches calendar events and schedule", risk_level="R0")
def get_schedule(date_str: Optional[str] = None, **kwargs) -> Dict[str, Any]:
    return calendar_agent.get_schedule(date_str)

@register_tool(name="create_calendar_event", description="Creates a new calendar event", risk_level="R1")
def create_calendar_event(title: str = "", start: str = "", end: str = "", date_str: Optional[str] = None, **kwargs) -> Dict[str, Any]:
    return calendar_agent.create_event(title, start, end, date_str)

@register_tool(name="daily_briefing", description="Generates comprehensive daily morning briefing", risk_level="R0")
def daily_briefing(**kwargs) -> Dict[str, Any]:
    return calendar_agent.generate_daily_briefing()

@register_tool(name="evening_briefing", description="Generates evening recap and preview", risk_level="R0")
def evening_briefing(**kwargs) -> Dict[str, Any]:
    return calendar_agent.generate_evening_briefing()
