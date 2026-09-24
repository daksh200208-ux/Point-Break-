"""
Point Break Risk Classification Engine (R0 - R4 Risk Matrix)
=============================================================
Enforces security boundaries for autonomous agent actions:
- R0: Read-Only / Information Retrieval (Autonomous)
- R1: Low Impact Local Operations (Auto + Audit Log)
- R2: External Communications (Voice alert + 5s abort or explicit confirmation)
- R3: Consequential Operations (Bookings, purchases, deletions - Tactical Modal Gate)
- R4: Critical Financial / Authentication (Payment execution, OTPs, passkeys - Mandatory Takeover)
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import re

class RiskLevel(Enum):
    R0_READ_ONLY = "R0"
    R1_LOW_IMPACT = "R1"
    R2_EXTERNAL_COMMS = "R2"
    R3_CONSEQUENTIAL = "R3"
    R4_CRITICAL = "R4"

@dataclass
class RiskAssessment:
    level: RiskLevel
    action: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    summary: str = ""
    requires_modal: bool = False
    requires_takeover: bool = False
    auto_executable: bool = True

    @property
    def is_blocking(self) -> bool:
        return self.requires_modal or self.requires_takeover

# Canonical mapping for actions
EXPLICIT_ACTION_MAP: Dict[str, RiskLevel] = {
    # R0 - Harmless Read-Only
    "search_web": RiskLevel.R0_READ_ONLY,
    "read_file": RiskLevel.R0_READ_ONLY,
    "list_directory": RiskLevel.R0_READ_ONLY,
    "get_system_stats": RiskLevel.R0_READ_ONLY,
    "read_inbox": RiskLevel.R0_READ_ONLY,
    "read_calendar": RiskLevel.R0_READ_ONLY,
    "get_schedule": RiskLevel.R0_READ_ONLY,
    "search_trains": RiskLevel.R0_READ_ONLY,
    "search_flights": RiskLevel.R0_READ_ONLY,
    "search_hotels": RiskLevel.R0_READ_ONLY,
    "search_products": RiskLevel.R0_READ_ONLY,
    "open_url": RiskLevel.R0_READ_ONLY,
    "capture_screen": RiskLevel.R0_READ_ONLY,
    "ocr_screen": RiskLevel.R0_READ_ONLY,
    "summarize_thread": RiskLevel.R0_READ_ONLY,

    # R1 - Low Impact / Staging
    "create_draft_email": RiskLevel.R1_LOW_IMPACT,
    "create_note": RiskLevel.R1_LOW_IMPACT,
    "set_timer": RiskLevel.R1_LOW_IMPACT,
    "set_reminder": RiskLevel.R1_LOW_IMPACT,
    "set_volume": RiskLevel.R1_LOW_IMPACT,
    "launch_app": RiskLevel.R1_LOW_IMPACT,
    "type_text": RiskLevel.R1_LOW_IMPACT,
    "fill_form_field": RiskLevel.R1_LOW_IMPACT,
    "click_navigation": RiskLevel.R1_LOW_IMPACT,
    "scroll": RiskLevel.R1_LOW_IMPACT,

    # R2 - External Communications
    "send_email": RiskLevel.R2_EXTERNAL_COMMS,
    "reply_email": RiskLevel.R2_EXTERNAL_COMMS,
    "forward_email": RiskLevel.R2_EXTERNAL_COMMS,
    "send_whatsapp_message": RiskLevel.R2_EXTERNAL_COMMS,
    "send_telegram_message": RiskLevel.R2_EXTERNAL_COMMS,
    "post_social_update": RiskLevel.R2_EXTERNAL_COMMS,
    "send_meeting_invite": RiskLevel.R2_EXTERNAL_COMMS,
    "accept_meeting_invite": RiskLevel.R2_EXTERNAL_COMMS,
    "decline_meeting_invite": RiskLevel.R2_EXTERNAL_COMMS,

    # R3 - Consequential / Irreversible / Bookings
    "book_train_ticket": RiskLevel.R3_CONSEQUENTIAL,
    "book_flight_ticket": RiskLevel.R3_CONSEQUENTIAL,
    "reserve_hotel": RiskLevel.R3_CONSEQUENTIAL,
    "add_to_cart": RiskLevel.R3_CONSEQUENTIAL,
    "checkout_cart": RiskLevel.R3_CONSEQUENTIAL,
    "delete_file": RiskLevel.R3_CONSEQUENTIAL,
    "delete_email": RiskLevel.R3_CONSEQUENTIAL,
    "cancel_event": RiskLevel.R3_CONSEQUENTIAL,
    "cancel_booking": RiskLevel.R3_CONSEQUENTIAL,
    "execute_shell_script": RiskLevel.R3_CONSEQUENTIAL,
    "git_push": RiskLevel.R3_CONSEQUENTIAL,

    # R4 - Critical Financial / Auth / Takeover
    "authorize_payment": RiskLevel.R4_CRITICAL,
    "enter_upi_pin": RiskLevel.R4_CRITICAL,
    "enter_card_cvv": RiskLevel.R4_CRITICAL,
    "submit_otp": RiskLevel.R4_CRITICAL,
    "change_password": RiskLevel.R4_CRITICAL,
    "modify_security_passkey": RiskLevel.R4_CRITICAL,
    "format_drive": RiskLevel.R4_CRITICAL,
    "grant_admin_privileges": RiskLevel.R4_CRITICAL
}

def classify_risk(action_name: str, parameters: Optional[Dict[str, Any]] = None) -> RiskAssessment:
    """
    Evaluates action name and parameters against the Point Break R0-R4 Risk Matrix.
    """
    params = parameters or {}
    act = action_name.lower().strip()

    # 1. Exact match in canonical table
    if act in EXPLICIT_ACTION_MAP:
        level = EXPLICIT_ACTION_MAP[act]
    else:
        # Heuristic pattern matching
        if re.search(r'\b(pay|upi|pin|cvv|otp|card_number|password|passkey|credential|bank|wallet)\b', act):
            level = RiskLevel.R4_CRITICAL
        elif re.search(r'\b(book|reserve|checkout|purchase|buy|delete|remove|drop|format|terminate|kill)\b', act):
            level = RiskLevel.R3_CONSEQUENTIAL
        elif re.search(r'\b(send|email|mail|message|whatsapp|telegram|sms|post|publish|invite)\b', act):
            level = RiskLevel.R2_EXTERNAL_COMMS
        elif re.search(r'\b(draft|create|type|write|click|scroll|navigate|set|update|save)\b', act):
            level = RiskLevel.R1_LOW_IMPACT
        else:
            level = RiskLevel.R0_READ_ONLY

    # 2. Parameter-based risk escalation
    # Escalation: Any payment or transaction amount > 0 is R3 or R4
    amount = params.get("amount") or params.get("fare") or params.get("price") or params.get("total")
    if amount is not None:
        try:
            val = float(str(amount).replace(",", "").replace("₹", "").replace("$", ""))
            if val > 0:
                if "pay" in act or "authorize" in act or "checkout" in act:
                    level = RiskLevel.R4_CRITICAL
                elif level.value < RiskLevel.R3_CONSEQUENTIAL.value:
                    level = RiskLevel.R3_CONSEQUENTIAL
        except (ValueError, TypeError):
            pass

    # Escalation: File deletion checks
    if "delete" in act or "remove" in act:
        target_path = str(params.get("path") or params.get("file") or "").lower()
        if any(crit in target_path for crit in ["system32", "windows", "program files", ".git", ".env", "jarvis"]):
            level = RiskLevel.R4_CRITICAL

    # 3. Build comprehensive assessment
    if level == RiskLevel.R4_CRITICAL:
        reason = "Direct financial payment, authentication credential, or sensitive security boundary."
        requires_modal = False
        requires_takeover = True
        auto_executable = False
    elif level == RiskLevel.R3_CONSEQUENTIAL:
        reason = "Consequential action involving real-world booking, cart purchase, or destructive deletion."
        requires_modal = True
        requires_takeover = False
        auto_executable = False
    elif level == RiskLevel.R2_EXTERNAL_COMMS:
        reason = "External communication to outside contacts or attendees."
        requires_modal = False
        requires_takeover = False
        auto_executable = True # Can execute with voice heads-up or 5s abort window
    elif level == RiskLevel.R1_LOW_IMPACT:
        reason = "Low-impact local workspace or UI staging operation."
        requires_modal = False
        requires_takeover = False
        auto_executable = True
    else:
        reason = "Information lookup, reading, or read-only query."
        requires_modal = False
        requires_takeover = False
        auto_executable = True

    summary = f"[{level.value}] {act.replace('_', ' ').title()}"
    if params:
        key_params = {k: v for k, v in params.items() if not any(s in k.lower() for s in ["token", "key", "password", "secret", "cvv", "pin"])}
        if key_params:
            summary += f" ({', '.join(f'{k}={v}' for k, v in list(key_params.items())[:3])})"

    return RiskAssessment(
        level=level,
        action=act,
        parameters=params,
        reason=reason,
        summary=summary,
        requires_modal=requires_modal,
        requires_takeover=requires_takeover,
        auto_executable=auto_executable
    )
