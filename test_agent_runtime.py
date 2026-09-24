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

def test_office_and_data_forge():
    print("\n--- TEST 4: SPRINT 2 OFFICE & DATA FORGE ---")
    from tools.registry import tool_registry

    # 1. Spreadsheet creation & reading
    ss_res = tool_registry.execute(
        "create_spreadsheet",
        output_path="test_metrics.xlsx",
        data=[{"Quarter": "Q1", "Revenue": 125000}, {"Quarter": "Q2", "Revenue": 180000}, {"Quarter": "Q3", "Revenue": 240000}]
    )
    assert ss_res["success"] is True and os.path.exists("test_metrics.xlsx")
    print("✔ create_spreadsheet -> test_metrics.xlsx created")

    read_res = tool_registry.execute("read_spreadsheet", file_path="test_metrics.xlsx")
    assert read_res["success"] is True and read_res["total_rows"] == 3
    print(f"✔ read_spreadsheet -> verified {read_res['total_rows']} rows")

    # 2. Matplotlib Chart generation
    chart_res = tool_registry.execute(
        "generate_chart",
        file_path="test_metrics.xlsx",
        x_col="Quarter",
        y_col="Revenue",
        chart_type="bar",
        title="Quarterly Growth",
        output_png="test_growth_chart.png"
    )
    assert chart_res["success"] is True and os.path.exists("test_growth_chart.png")
    print("✔ generate_chart -> test_growth_chart.png generated")

    # 3. PowerPoint 16:9 Presentation creation
    ppt_res = tool_registry.execute(
        "create_presentation",
        title="Point Break Architecture Overview",
        subtitle="Sprint 2 Automated Delivery",
        output_path="test_architecture.pptx"
    )
    assert ppt_res["success"] is True and os.path.exists("test_architecture.pptx")
    print(f"✔ create_presentation -> test_architecture.pptx ({ppt_res['total_slides']} slides)")

    # 4. Word (.docx) Document creation
    doc_res = tool_registry.execute(
        "create_document",
        title="Point Break S-Tier Architecture Whitepaper",
        sections=[
            {"heading": "1. Mission Objectives", "body": "Transform Point Break into an autonomous Personal Assistant runtime."},
            {"heading": "2. Security Matrix", "body": "Enforce strict R0-R4 boundaries with tactical human takeover."}
        ],
        output_path="test_whitepaper.docx"
    )
    assert doc_res["success"] is True and os.path.exists("test_whitepaper.docx")
    print(f"✔ create_document -> test_whitepaper.docx ({doc_res['sections_count']} sections)")

    # 5. Deep Research Dossier
    dossier_res = tool_registry.execute("deep_research", topic="Local INT8 LLM Quantization vs Cloud GPU")
    assert dossier_res["success"] is True and len(dossier_res["sections"]) == 4
    print(f"✔ deep_research -> synthesized dossier on '{dossier_res['topic']}'")

    # Cleanup test artifacts
    for f in ["test_metrics.xlsx", "test_growth_chart.png", "test_architecture.pptx", "test_whitepaper.docx"]:
        if os.path.exists(f):
            try: os.remove(f)
            except: pass

def test_commerce_and_meetings():
    print("\n--- TEST 5: SPRINT 2 COMMERCE & MEETINGS ---")
    from tools.registry import tool_registry

    # 1. Product Search
    prod_res = tool_registry.execute("search_products", query="mechanical keyboard", platform="amazon", max_budget=3500)
    assert prod_res["success"] is True and len(prod_res["top_products"]) > 0
    print(f"✔ search_products -> {prod_res['query']} on {prod_res['platform']}")

    # 2. Food Delivery Comparison
    food_res = tool_registry.execute("order_food", query="order sweet lassi from swiggy or zomato whichever is cheaper")
    assert food_res["success"] is True and "swiggy" in food_res["recommended_platform"].lower()
    print(f"✔ order_food -> {food_res['dish']} (Recommended: {food_res['recommended_platform']})")

    # 3. Meeting Intelligence
    m_res = tool_registry.execute("prepare_meeting_briefing", meeting_title="Sprint 2 Review", attendees=["Daksh", "Engineering Lead"])
    assert m_res["success"] is True and "Daksh" in m_res["briefing"]
    print("✔ prepare_meeting_briefing -> briefing generated")

    action_res = tool_registry.execute("extract_action_items", notes_or_transcript="- Deploy agent runtime to staging\n- Review test logs\n- TODO: confirm train ticket")
    assert action_res["success"] is True and action_res["action_items_count"] >= 2
    print(f"✔ extract_action_items -> extracted {action_res['action_items_count']} action items")

if __name__ == "__main__":
    print("==================================================")
    print(" POINT BREAK AUTONOMOUS RUNTIME TEST SUITE")
    print("==================================================")
    test_risk_classification()
    test_state_persistence()
    test_canonical_train_booking()
    test_office_and_data_forge()
    test_commerce_and_meetings()
    print("\n==================================================")
    print(" ALL TESTS PASSED SUCCESSFULLY! ")
    print("==================================================")
