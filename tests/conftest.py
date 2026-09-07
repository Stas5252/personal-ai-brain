"""
Pytest configuration for Personal AI Brain.
Ensures tests run against an isolated test database and NEVER pollute production data/brain.db.
"""
import os
import shutil
import tempfile
import pytest
from pathlib import Path

os.environ["ENV"] = "test"
os.environ["BRAIN_ENV"] = "test"

@pytest.fixture(scope="session", autouse=True)
def isolate_test_environment(tmp_path_factory):
    temp_dir = tmp_path_factory.mktemp("test_brain_data")
    test_db = temp_dir / "test_brain.db"
    
    prod_db = Path("data/brain.db")
    if prod_db.exists():
        shutil.copy(prod_db, test_db)
        
    os.environ["BRAIN_DB_PATH"] = str(test_db)
    
    import src.brain.config as cfg
    cfg.DB_PATH = str(test_db)
    
    yield
