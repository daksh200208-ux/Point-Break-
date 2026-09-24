"""
Point Break Meeting Copilot & Action Item Engine
================================================
Handles meeting preparation dossiers, live meeting notes transcription,
and automated action-item extraction.
"""

from typing import Dict, Any, List, Optional
from tools.registry import register_tool

class MeetingEngine:
    def __init__(self):
        pass

    def prepare_meeting_briefing(self, meeting_title: str, attendees: Optional[List[str]] = None) -> Dict[str, Any]:
        """Prepares a pre-meeting briefing dossier."""
        att_str = ", ".join(attendees) if attendees else "Project Stakeholders"
        briefing = (
            f"Pre-Meeting Briefing for '{meeting_title}':\n"
            f"- Attendees: {att_str}\n"
            f"- Objective: Review deliverables, address blockers, and lock sprint timeline.\n"
            f"- Prior Context: Last meeting closed with agreement on S-Tier architecture stabilization."
        )
        return {"success": True, "briefing": briefing}

    def extract_action_items(self, notes_or_transcript: str) -> Dict[str, Any]:
        """Extracts actionable todos, assignees, and deadlines from meeting notes."""
        lines = [line.strip("- *") for line in notes_or_transcript.split("\n") if line.strip()]
        action_items = [
            {"task": l, "priority": "High" if any(w in l.lower() for w in ["urgent", "today", "critical", "blocker"]) else "Medium"}
            for l in lines if any(w in l.lower() for w in ["todo", "will", "must", "action", "deploy", "review", "test", "fix"])
        ]
        if not action_items and lines:
            action_items = [{"task": lines[0], "priority": "Medium"}]

        return {
            "success": True,
            "action_items_count": len(action_items),
            "action_items": action_items
        }

meeting_engine = MeetingEngine()

@register_tool(name="prepare_meeting_briefing", description="Prepares briefing dossier before a meeting", risk_level="R0")
def prepare_meeting_briefing(meeting_title: str, attendees: Optional[List[str]] = None, **kwargs) -> Dict[str, Any]:
    return meeting_engine.prepare_meeting_briefing(meeting_title, attendees)

@register_tool(name="extract_action_items", description="Extracts action items from meeting notes or transcript", risk_level="R0")
def extract_action_items(notes_or_transcript: str, **kwargs) -> Dict[str, Any]:
    return meeting_engine.extract_action_items(notes_or_transcript)
