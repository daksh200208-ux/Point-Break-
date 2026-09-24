"""
Point Break Agent Runtime Verification Test
============================================
Tests end-to-end planning, state persistence, risk classification,
and execution verification for the canonical Kanpur-to-Delhi train booking workflow.
"""

import os
import sys

# Windows console encoding safeguard
try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

os.environ["PB_TEST_AUTO_APPROVE"] = "1"

# Ensure scratch/jarvis is in PYTHONPATH
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from core.agent.runtime import agent_runtime
from core.agent.state import task_store, TaskStatus
from core.permissions.risk_matrix import classify_risk, RiskLevel
from core.memory.context_store import context_store

def mock_speaker(msg: str):
    print(f"🔊 [TARS VOICE]: {msg}")

def test_risk_classification():
    print("\n--- TEST 1: RISK CLASSIFICATION ---")
    r0 = classify_risk("search_trains", {"from": "Kanpur", "to": "Delhi"})
    assert r0.level == RiskLevel.R0_READ_ONLY, f"Expected R0, got {r0.level}"
    print(f"✔ search_trains -> {r0.level.value}")

    r2 = classify_risk("send_email", {"to": "test@example.com", "subject": "Hello"})
    assert r2.level == RiskLevel.R2_EXTERNAL_COMMS, f"Expected R2, got {r2.level}"
    print(f"✔ send_email -> {r2.level.value}")

    r3 = classify_risk("book_train_ticket", {"train": "22435", "fare": 2420})
    assert r3.level == RiskLevel.R3_CONSEQUENTIAL, f"Expected R3, got {r3.level}"
    print(f"✔ book_train_ticket -> {r3.level.value}")

    r4 = classify_risk("authorize_payment", {"amount": 2420})
    assert r4.level == RiskLevel.R4_CRITICAL, f"Expected R4, got {r4.level}"
    print(f"✔ authorize_payment -> {r4.level.value}")

def test_state_persistence():
    print("\n--- TEST 2: TASK STATE PERSISTENCE ---")
    task = task_store.create_task("Test synthetic goal")
    assert task.task_id.startswith("task_")
    assert task.status == TaskStatus.PLANNING

    loaded = task_store.get_task(task.task_id)
    assert loaded is not None
    assert loaded.goal == "Test synthetic goal"
    print(f"✔ Created and verified task {task.task_id} in SQLite")

def test_canonical_train_booking():
    print("\n--- TEST 3: CANONICAL KANPUR-TO-DELHI TRAIN BOOKING WORKFLOW ---")
    goal = "Book train from Kanpur to Delhi tomorrow morning"
    
    # Run goal execution
    result = agent_runtime.execute_goal(goal, speak_fn=mock_speaker)
    print(f"Result: {result}")
    assert result["success"] is True
    assert "extracted_data" in result
    print(f"✔ Canonical workflow succeeded! PNR: {result['extracted_data'].get('pnr')}")

if __name__ == "__main__":
    print("==================================================")
    print(" POINT BREAK AUTONOMOUS RUNTIME TEST SUITE")
    print("==================================================")
    test_risk_classification()
    test_state_persistence()
    test_canonical_train_booking()
    print("\n==================================================")
    print(" ALL TESTS PASSED SUCCESSFULLY! ")
    print("==================================================")
