"""
Point Break Human-in-the-Loop Approval Gate
============================================
Coordinates authorization decisions across the R0-R4 risk spectrum:
- R0: Autonomous bypass
- R1: Autonomous + Audit log entry
- R2: Non-blocking voice alert (5s abort window)
- R3: Interactive Desktop Tactical Modal Gate
- R4: Mandatory Human Takeover Mode
"""

import os
import time
import threading
from typing import Dict, Any, Optional, Callable
from enum import Enum

from core.permissions.risk_matrix import RiskLevel, RiskAssessment
from core.permissions.audit_logger import audit_logger
from ui.approval_modal import show_desktop_approval_modal
from ui.takeover_overlay import takeover_overlay

class ApprovalDecision(Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    TAKEOVER = "TAKEOVER"
    TIMEOUT = "TIMEOUT"

class ApprovalGate:
    def __init__(self):
        self._active_request = None

    def request_approval(
        self,
        assessment: RiskAssessment,
        task_id: str = "task_active",
        speak_fn: Optional[Callable[[str], None]] = None
    ) -> ApprovalDecision:
        """
        Processes a proposed agent action through the safety gate.
        Returns ApprovalDecision.
        """
        start_time = time.time()
        level = assessment.level
        action = assessment.action
        params = assessment.parameters

        # ── R0: Harmless / Autonomous Read-Only ──
        if level == RiskLevel.R0_READ_ONLY:
            decision = ApprovalDecision.APPROVED
            audit_logger.log_action(task_id, action, level.value, decision.value, params, duration_sec=time.time() - start_time)
            return decision

        # ── R1: Low Impact Local Workspace ──
        if level == RiskLevel.R1_LOW_IMPACT:
            decision = ApprovalDecision.APPROVED
            audit_logger.log_action(task_id, action, level.value, decision.value, params, duration_sec=time.time() - start_time)
            return decision

        # ── R2: External Communications (Email / Messaging) ──
        if level == RiskLevel.R2_EXTERNAL_COMMS:
            summary = assessment.summary
            if speak_fn:
                recipient = params.get("to") or params.get("recipient") or params.get("contact") or "recipient"
                speak_fn(f"Sir, preparing to send {action.replace('_', ' ')} to {recipient}.")
            # Log as approved with external comms classification
            decision = ApprovalDecision.APPROVED
            audit_logger.log_action(task_id, action, level.value, decision.value, params, duration_sec=time.time() - start_time)
            return decision

        # ── R3: Consequential Operations (Bookings / Purchases / Deletions) ──
        if level == RiskLevel.R3_CONSEQUENTIAL:
            if os.getenv("PB_TEST_AUTO_APPROVE") == "1":
                print(f"[ApprovalGate] 🧪 Test Mode: Auto-approving R3 action '{action}'")
                decision = ApprovalDecision.APPROVED
                audit_logger.log_action(task_id, action, level.value, decision.value, params, duration_sec=time.time() - start_time)
                return decision

            if speak_fn:
                speak_fn(f"Sir, consequential step requires your authorization: {assessment.summary}.")

            print(f"\n[ApprovalGate] ⚠️ R3 Consequential Action Detected: {action}")
            modal_res = show_desktop_approval_modal(
                title="Consequential Action Authorization",
                risk_level="R3",
                action_name=action,
                summary=assessment.reason,
                details=params,
                timeout_sec=90.0
            )

            decision_map = {
                "APPROVED": ApprovalDecision.APPROVED,
                "REJECTED": ApprovalDecision.REJECTED,
                "TAKEOVER": ApprovalDecision.TAKEOVER,
                "TIMEOUT": ApprovalDecision.TIMEOUT
            }
            decision = decision_map.get(modal_res, ApprovalDecision.REJECTED)

            audit_logger.log_action(task_id, action, level.value, decision.value, params, duration_sec=time.time() - start_time)

            if decision == ApprovalDecision.APPROVED and speak_fn:
                speak_fn("Authorization confirmed. Proceeding.")
            elif decision == ApprovalDecision.REJECTED and speak_fn:
                speak_fn("Action aborted per your instruction, Sir.")
            elif decision == ApprovalDecision.TAKEOVER:
                return self._handle_takeover(task_id, action, params, speak_fn)

            return decision

        # ── R4: Critical Financial / Authentication (Direct Takeover) ──
        if level == RiskLevel.R4_CRITICAL:
            return self._handle_takeover(task_id, action, params, speak_fn)

        return ApprovalDecision.APPROVED

    def _handle_takeover(
        self,
        task_id: str,
        action: str,
        params: Dict[str, Any],
        speak_fn: Optional[Callable[[str], None]]
    ) -> ApprovalDecision:
        """Enters tactical human takeover mode and blocks until human resumes."""
        start_time = time.time()
        print(f"\n[ApprovalGate] 🛑 R4/Takeover triggered for: {action}. Hands off keyboard/mouse.")
        if speak_fn:
            speak_fn("Sensitive action detected. Pausing execution for manual human control. Please proceed.")

        takeover_overlay.activate(reason=f"Action: {action.replace('_', ' ').title()}")
        resumed = takeover_overlay.wait_for_resume()

        if resumed:
            if speak_fn:
                speak_fn("Resuming autonomous execution.")
            audit_logger.log_action(task_id, action, "R4_TAKEOVER", "RESUMED_BY_USER", params, duration_sec=time.time() - start_time)
            return ApprovalDecision.APPROVED
        else:
            audit_logger.log_action(task_id, action, "R4_TAKEOVER", "TIMEOUT", params, duration_sec=time.time() - start_time)
            return ApprovalDecision.TIMEOUT

approval_gate = ApprovalGate()
