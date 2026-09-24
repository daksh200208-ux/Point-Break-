"""
Point Break Cryptographic & Structured Audit Logger
===================================================
Maintains an append-only JSONL log of every agent action, risk assessment,
user authorization decision, and execution status.
"""

import os
import json
import time
import hashlib
from typing import Dict, Any, Optional

class AuditLogger:
    def __init__(self, log_path: Optional[str] = None):
        if not log_path:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            log_path = os.path.join(base_dir, "audit_log.jsonl")
        self.log_path = log_path
        self._ensure_file()

    def _ensure_file(self):
        try:
            parent = os.path.dirname(self.log_path)
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)
            if not os.path.exists(self.log_path):
                with open(self.log_path, "a", encoding="utf-8") as f:
                    pass
        except Exception as e:
            print(f"[AuditLogger] Init warning: {e}")

    def log_action(
        self,
        task_id: str,
        action: str,
        risk_level: str,
        decision: str,
        parameters: Optional[Dict[str, Any]] = None,
        result: Optional[Dict[str, Any]] = None,
        duration_sec: float = 0.0
    ) -> str:
        """
        Appends an action entry to the audit log.
        Returns a SHA-256 hash of the record.
        """
        now = time.time()
        # Redact sensitive parameters
        safe_params = {}
        if parameters:
            for k, v in parameters.items():
                if any(sec in k.lower() for sec in ["pin", "password", "token", "secret", "cvv", "key"]):
                    safe_params[k] = "********"
                else:
                    safe_params[k] = v

        record = {
            "timestamp": now,
            "time_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
            "task_id": task_id,
            "action": action,
            "risk_level": risk_level,
            "decision": decision,
            "parameters": safe_params,
            "result_status": "SUCCESS" if (result and result.get("success", True)) else "FAILED",
            "duration_sec": round(duration_sec, 3)
        }

        record_str = json.dumps(record, sort_keys=True)
        rec_hash = hashlib.sha256(record_str.encode("utf-8")).hexdigest()
        record["hash"] = rec_hash

        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            print(f"[AuditLogger] Write error: {e}")

        return rec_hash

audit_logger = AuditLogger()
