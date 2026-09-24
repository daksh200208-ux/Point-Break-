"""
Point Break Context & Preference Memory Store
=============================================
Manages sliding conversational history, recent desktop telemetry, and long-term
user preferences (frequent destinations, passenger profiles, dietary preferences).
Persists to `user_profile.json` and supports dynamic preference learning.
"""

import os
import json
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict

@dataclass
class UserPassengerProfile:
    name: str = "Daksh"
    age: int = 24
    gender: str = "M"
    berth_preference: str = "LOWER"
    food_preference: str = "VEG"

@dataclass
class UserPreferences:
    user_name: str = "Daksh"
    primary_city: str = "Kanpur"
    preferred_train_class: str = "3AC" # 3AC, 2AC, CC, EC
    preferred_train_departure_window: str = "morning" # morning, evening, night
    frequent_routes: List[Dict[str, str]] = field(default_factory=lambda: [
        {"from": "Kanpur", "to": "Delhi", "from_code": "CNB", "to_code": "NDLS"},
        {"from": "Delhi", "to": "Kanpur", "from_code": "NDLS", "to_code": "CNB"}
    ])
    default_passengers: List[Dict[str, Any]] = field(default_factory=lambda: [
        {"name": "Daksh", "age": 24, "gender": "M", "berth": "LOWER"}
    ])
    email_signature: str = "Best regards,\nDaksh"
    work_hours: Dict[str, str] = field(default_factory=lambda: {"start": "09:00", "end": "19:00"})

class ContextStore:
    def __init__(self, profile_path: Optional[str] = None):
        if not profile_path:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            profile_path = os.path.join(base_dir, "user_profile.json")
        self.profile_path = profile_path
        self.preferences = self._load_preferences()
        self.recent_events: List[Dict[str, Any]] = []
        self._max_recent_events = 50

    def _load_preferences(self) -> UserPreferences:
        if os.path.exists(self.profile_path):
            try:
                with open(self.profile_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return UserPreferences(**data)
            except Exception as e:
                print(f"[ContextStore] Error reading user profile: {e}")
        # Default profile
        default_pref = UserPreferences()
        self.save_preferences(default_pref)
        return default_pref

    def save_preferences(self, prefs: Optional[UserPreferences] = None):
        if prefs:
            self.preferences = prefs
        try:
            with open(self.profile_path, "w", encoding="utf-8") as f:
                json.dump(asdict(self.preferences), f, indent=2)
        except Exception as e:
            print(f"[ContextStore] Error saving user profile: {e}")

    def update_preference(self, key: str, value: Any):
        if hasattr(self.preferences, key):
            setattr(self.preferences, key, value)
            self.save_preferences()

    def record_event(self, event_type: str, details: Dict[str, Any]):
        entry = {
            "timestamp": time.time(),
            "iso_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "type": event_type,
            "details": details
        }
        self.recent_events.append(entry)
        if len(self.recent_events) > self._max_recent_events:
            self.recent_events.pop(0)

    def get_context_summary(self) -> str:
        """Returns a compact context string for LLM prompts."""
        p = self.preferences
        return (
            f"User: {p.user_name} | City: {p.primary_city} | "
            f"Train Preference: {p.preferred_train_class}, Departure: {p.preferred_train_departure_window} | "
            f"Primary Passenger: {p.default_passengers[0]['name'] if p.default_passengers else 'User'}"
        )

context_store = ContextStore()
