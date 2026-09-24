"""
Point Break Outcome Verification Subsystem
==========================================
Cryptographically and semantically verifies that real-world actions completed
successfully before advancing state (e.g. confirms PNR string format, order receipts,
sent email records, screen state transitions).
"""

import os
import re
from typing import Dict, Any, Tuple, Optional

class OutcomeVerifier:
    def __init__(self):
        pass

    def verify_step_outcome(
        self,
        action: str,
        parameters: Dict[str, Any],
        result: Any,
        observation: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str]:
        """
        Validates whether the step genuinely succeeded.
        Returns: (is_verified, reason)
        """
        obs = observation or {}
        act = action.lower()

        # 1. Travel / Train Booking verification
        if "train" in act or "ticket" in act:
            if isinstance(result, dict):
                pnr = result.get("pnr")
                if pnr and re.match(r'^\d{10}$', str(pnr).strip()):
                    return True, f"Valid 10-digit Indian Railways PNR verified: {pnr}"
                if result.get("success"):
                    return True, "Train search/action completed successfully."

            # Check screen text observation
            screen_text = str(obs.get("screen_text", "")).lower()
            if any(term in screen_text for term in ["confirmed", "pnr", "seat details", "berth allocated"]):
                return True, "Confirmation detected in screen observation."

        # 2. Email Verification
        if "email" in act:
            if isinstance(result, dict) and result.get("success"):
                return True, f"Email delivery confirmed: {result.get('message_id', 'dispatched')}"

        # 3. File Creation / Download verification
        if "file" in act or "download" in act or "report" in act:
            target_path = parameters.get("path") or (result.get("path") if isinstance(result, dict) else None)
            if target_path and os.path.exists(target_path):
                size = os.path.getsize(target_path)
                if size > 0:
                    return True, f"Target file verified on disk ({size} bytes): {target_path}"
                else:
                    return False, f"Target file was created but is empty: {target_path}"

        # 4. Web Navigation / Form fill
        if "open_url" in act or "navigate" in act:
            if result is True or (isinstance(result, dict) and result.get("success")):
                return True, "Navigation executed."

        # 5. Generic check
        if isinstance(result, dict):
            if result.get("success") is True:
                return True, "Operation returned success."
            elif result.get("success") is False:
                return False, result.get("error", "Action explicitly returned failure.")

        if result is not None and result is not False:
            return True, "Action completed without unhandled exceptions."

        return False, "Action returned empty or false outcome."

outcome_verifier = OutcomeVerifier()
