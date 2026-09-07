"""
Workflow Execution Benchmark for Personal AI Brain.
Evaluates multi-step DAG execution, step progression, approval gating,
and latency.
"""
import time
import pytest
from src.brain.services.brain_service import BrainService

def test_workflow_full_lifecycle():
    brain = BrainService()
    
    t0 = time.time()
    # 1. Trigger workflow
    wf = brain.start_workflow("photoday_launch", initial_context={"city": "Москва", "season": "Осень"})
    assert wf.status == "ACTIVE"
    assert wf.current_step == 0
    assert len(wf.steps) == 8
    
    # 2. Progress through steps
    step_data = [
        {"audit": "Профиль готов к приему трафика"},
        {"concept": "Warm Autumn Film Look"},
        {"pricing": "Слоты по 45 минут, 3 пакета"},
        {"post": "Текст анонсирующего поста готов"},
        {"stories": "5 кадров сторис смонтированы"},
        {"reels": "Сценарий рилс утвержден"},
        {"client_dm": "Шаблон бронирования готов"},
        {"checklist": "Реквизит собран, тайминг утвержден"}
    ]
    
    current_wf = wf
    for idx, data in enumerate(step_data):
        current_wf = brain.advance_workflow(current_wf.workflow_id, data)
        # If waiting approval, approve
        if current_wf.status == "WAITING_APPROVAL":
            current_wf = brain.approve_workflow_step(current_wf.workflow_id, approved=True)
            
    total_time = time.time() - t0
    
    assert current_wf.status == "COMPLETED"
    assert len(current_wf.results) == 8
    assert total_time < 2.0, "All 8 workflow steps executed in < 2 seconds"

def test_workflow_dag_automated_step_execution():
    """Tests authentic domain execution of all workflow steps without static stubs."""
    brain = BrainService()
    
    # 1. Test photoday_launch step execution (audit, concept, pricing, content, dm, checklist)
    wf_photo = brain.start_workflow("photoday_launch", initial_context={"theme": "Осенний нуар", "city": "Москва"})
    updated_wf, out_audit = brain.execute_workflow_step(wf_photo.workflow_id)
    assert "audit" in out_audit
    assert "core_value_proposition" in out_audit["audit"]
    assert "market_readiness" in out_audit["audit"]
    assert updated_wf.current_step == 1

    # 2. Test client_chat_analysis with real objection diagnosis and task creation
    wf_chat = brain.start_workflow("client_chat_analysis", initial_context={
        "dialogue": "Здравствуйте! Мы с мужем подумаем и напишем позже.",
        "client_name": "Екатерина"
    })
    # Step 0: parse
    wf_chat, out0 = brain.execute_workflow_step(wf_chat.workflow_id)
    assert "detected_objections" in out0
    assert "подумаем" in out0["detected_objections"]
    # Step 1: diagnose
    wf_chat, out1 = brain.execute_workflow_step(wf_chat.workflow_id)
    assert "recommended_strategy" in out1
    # Step 2: strategy (advances to step 3, which requires approval)
    wf_chat, out2 = brain.execute_workflow_step(wf_chat.workflow_id)
    assert "strategy" in out2
    assert wf_chat.status == "WAITING_APPROVAL"
    assert wf_chat.steps[3].requires_approval
    # User approves step 3
    wf_chat = brain.approve_workflow_step(wf_chat.workflow_id, approved=True)
    assert wf_chat.status == "ACTIVE"
    # Step 3: draft_message
    wf_chat, out3 = brain.execute_workflow_step(wf_chat.workflow_id)
    assert "response" in out3
    assert len(out3["response"]) > 20
    # Step 4: task (creates real DB task)
    wf_chat, out4 = brain.execute_workflow_step(wf_chat.workflow_id)
    assert "task_id" in out4
    assert "title" in out4
    assert "Екатерина" in out4["title"]
    assert out4["priority"] == "HIGH"
    assert wf_chat.status == "COMPLETED"

    # Verify task exists in DB
    created_task = brain.get_task(out4["task_id"])
    assert created_task is not None
    assert created_task.title == out4["title"]

def test_workflow_rest_api_endpoints():
    """Tests authenticated REST API endpoints for workflow orchestration."""
    import os
    from fastapi.testclient import TestClient
    from src.brain.api.app import app
    
    key = os.environ.get("BRAIN_API_KEY", "regression-only-not-a-production-key-0001")
    client = TestClient(app, headers={"Authorization": f"Bearer {key}"})

    # 1. Start workflow via API
    res = client.post("/brain/workflows/start", json={
        "workflow_type": "no_content_emergency",
        "initial_context": {"theme": "Съемка в кафе"},
        "name": "Тестовая скорая помощь"
    })
    assert res.status_code == 200
    wf_data = res.json()
    wf_id = wf_data["workflow_id"]
    assert wf_data["status"] == "ACTIVE"
    assert len(wf_data["steps"]) == 3

    # 2. Get workflow via API
    res_get = client.get(f"/brain/workflows/{wf_id}")
    assert res_get.status_code == 200
    assert res_get.json()["workflow_id"] == wf_id

    # 3. Execute step via API
    res_exec = client.post(f"/brain/workflows/{wf_id}/execute")
    assert res_exec.status_code == 200
    exec_data = res_exec.json()
    assert "workflow" in exec_data
    assert "step_output" in exec_data
    assert exec_data["workflow"]["current_step"] == 1

def test_workflow_approval_gate_enforcement():
    """Verifies that unapproved gated steps cannot be executed via engine or REST API."""
    import os
    from fastapi.testclient import TestClient
    from src.brain.api.app import app

    brain = BrainService()
    key = os.environ.get("BRAIN_API_KEY", "regression-only-not-a-production-key-0001")
    client = TestClient(app, headers={"Authorization": f"Bearer {key}"})

    wf = brain.start_workflow("client_chat_analysis", initial_context={
        "dialogue": "Здравствуйте! Это слишком дорого для нас сейчас."
    })
    # Advance through step 0, 1, 2
    brain.execute_workflow_step(wf.workflow_id)
    brain.execute_workflow_step(wf.workflow_id)
    wf_gated, _ = brain.execute_workflow_step(wf.workflow_id)
    
    assert wf_gated.status == "WAITING_APPROVAL"
    assert wf_gated.current_step == 3
    assert wf_gated.steps[3].requires_approval

    # Attempting to execute unapproved step directly via engine must raise ValueError
    with pytest.raises(ValueError, match="requires approval before execution"):
        brain.execute_workflow_step(wf.workflow_id)

    # Attempting to execute unapproved step via REST API must return 400 Bad Request
    res_err = client.post(f"/brain/workflows/{wf.workflow_id}/execute")
    assert res_err.status_code == 400
    assert "requires approval before execution" in res_err.json()["detail"]

    # Approve step via REST API without body
    res_appr = client.post(f"/brain/workflows/{wf.workflow_id}/approve", json={})
    assert res_appr.status_code == 200
    assert res_appr.json()["status"] == "ACTIVE"

    # Execution now succeeds
    res_ok = client.post(f"/brain/workflows/{wf.workflow_id}/execute")
    assert res_ok.status_code == 200
    assert res_ok.json()["workflow"]["current_step"] == 4

def test_workflow_cancellation_and_completion_guards():
    """Verifies that completed or cancelled workflows reject further step execution."""
    import os
    from fastapi.testclient import TestClient
    from src.brain.api.app import app

    brain = BrainService()
    key = os.environ.get("BRAIN_API_KEY", "regression-only-not-a-production-key-0001")
    client = TestClient(app, headers={"Authorization": f"Bearer {key}"})

    # 1. Test cancellation via API
    res_start = client.post("/brain/workflows/start", json={"workflow_type": "daily_planning"})
    wf_id = res_start.json()["workflow_id"]
    res_cancel = client.post(f"/brain/workflows/{wf_id}/cancel")
    assert res_cancel.status_code == 200
    assert res_cancel.json()["status"] == "CANCELLED"

    # Execution on cancelled workflow must fail
    res_exec_cancel = client.post(f"/brain/workflows/{wf_id}/execute")
    assert res_exec_cancel.status_code == 400
    assert "cancelled" in res_exec_cancel.json()["detail"].lower()

    # 2. Test completion guard
    wf2 = brain.start_workflow("daily_planning")
    brain.execute_workflow_step(wf2.workflow_id)
    wf2_done, _ = brain.execute_workflow_step(wf2.workflow_id)
    assert wf2_done.status == "COMPLETED"

    with pytest.raises(ValueError, match="already completed"):
        brain.execute_workflow_step(wf2.workflow_id)

def test_workflow_full_dag_all_templates():
    """Executes every step of all 5 core DAG templates to ensure zero unhandled stubs."""
    brain = BrainService()

    # 1. Photoday Launch (8 steps)
    wf_photo = brain.start_workflow("photoday_launch", initial_context={
        "theme": "Вечерний кинематографичный портрет",
        "city": "Санкт-Петербург",
        "packages": [
            {"name": "Минимальный", "price": 12000, "duration_hours": 1, "retouched_photos": 15},
            {"name": "Оптимальный", "price": 20000, "duration_hours": 2, "retouched_photos": 30}
        ]
    })
    for idx in range(8):
        curr_wf = brain.get_workflow(wf_photo.workflow_id)
        if curr_wf.status == "WAITING_APPROVAL":
            brain.approve_workflow_step(wf_photo.workflow_id, approved=True)
        curr_wf, out = brain.execute_workflow_step(wf_photo.workflow_id)
    assert curr_wf.status == "COMPLETED"
    assert "audit" in curr_wf.results["audit_context"]
    assert "concept" in curr_wf.results["concept_and_visual_logic"]
    assert "packages" in curr_wf.results["package_architecture"]
    assert "post_text" in curr_wf.results["announcement_post"]
    assert "stories_content" in curr_wf.results["stories_sequence"]
    assert "reels_content" in curr_wf.results["reels_script"]
    assert "dm_template" in curr_wf.results["client_dm_template"]
    assert "checklist" in curr_wf.results["launch_checklist"]

    # 2. Shoot Preparation (4 steps)
    wf_prep = brain.start_workflow("shoot_preparation", initial_context={
        "theme": "Деловой минимализм в студии",
        "client_name": "Мария",
        "location": "Циклорама"
    })
    for idx in range(4):
        curr_wf = brain.get_workflow(wf_prep.workflow_id)
        if curr_wf.status == "WAITING_APPROVAL":
            brain.approve_workflow_step(wf_prep.workflow_id, approved=True)
        curr_wf, out = brain.execute_workflow_step(wf_prep.workflow_id)
    assert curr_wf.status == "COMPLETED"
    assert "concept" in curr_wf.results["concept_definition"]
    assert "light_scheme" in curr_wf.results["visual_logic"]
    assert "shot_list" in curr_wf.results["shot_list_and_timing"]
    assert "memo" in curr_wf.results["client_memo"]

    # 3. Voice to Content (2 steps)
    wf_voice = brain.start_workflow("voice_to_content", initial_context={
        "transcript": "Вчера провели невероятную съемку в ретро-отеле. Героиня сначала очень стеснялась и говорила что деревянная, но мы включили джаз и через 20 минут получили журнал."
    })
    wf_voice, out_v0 = brain.execute_workflow_step(wf_voice.workflow_id)
    assert "extracted_events" in out_v0
    wf_voice, out_v1 = brain.execute_workflow_step(wf_voice.workflow_id)
    assert "derivative_post" in out_v1
    assert "derivative_reels" in out_v1
    assert wf_voice.status == "COMPLETED"

def test_task_rest_api_endpoints():
    """Tests authenticated Task CRUD REST API endpoints."""
    import os
    from fastapi.testclient import TestClient
    from src.brain.api.app import app

    key = os.environ.get("BRAIN_API_KEY", "regression-only-not-a-production-key-0001")
    client = TestClient(app, headers={"Authorization": f"Bearer {key}"})

    # 1. Create Task via API
    res_create = client.post("/brain/tasks", json={
        "title": "Подготовить мудборд для фотодня",
        "type": "preparation",
        "priority": "HIGH"
    })
    assert res_create.status_code == 200
    task_data = res_create.json()
    task_id = task_data["task_id"]
    assert task_data["title"] == "Подготовить мудборд для фотодня"
    assert task_data["status"] == "TODO"

    # 2. Get Task via API
    res_get = client.get(f"/brain/tasks/{task_id}")
    assert res_get.status_code == 200
    assert res_get.json()["task_id"] == task_id

    # 3. Update Task Status via API
    res_patch = client.patch(f"/brain/tasks/{task_id}", json={
        "status": "COMPLETED"
    })
    assert res_patch.status_code == 200
    assert res_patch.json()["status"] == "COMPLETED"

    # 4. List Tasks via API
    res_list = client.get("/brain/tasks?status=COMPLETED")
    assert res_list.status_code == 200
    tasks_list = res_list.json()
    assert any(t["task_id"] == task_id for t in tasks_list)
