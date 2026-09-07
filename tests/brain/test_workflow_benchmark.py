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
