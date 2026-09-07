"""Isolate before test collection: imports can create databases and indexes."""
import os
import tempfile
from pathlib import Path

_TEST_ROOT = tempfile.TemporaryDirectory(prefix='brain-tests-')
_ROOT = Path(_TEST_ROOT.name)
os.environ['ENV'] = 'test'
os.environ['BRAIN_ENV'] = 'test'
os.environ['BRAIN_DB_PATH'] = str(_ROOT / 'brain.db')
os.environ['BRAIN_API_KEY'] = 'regression-only-not-a-production-key-0001'
os.environ['GEMINI_API_KEY'] = ''
os.environ['TELEGRAM_BOT_TOKEN'] = ''
os.environ['EMBEDDING_PROVIDER_TYPE'] = 'hash_fallback'

import src.brain.config as cfg
cfg.DB_PATH = str(_ROOT / 'brain.db')
cfg.DATA_DIR = _ROOT
cfg.STORAGE_DIR = _ROOT / 'storage'
cfg.ORIGINALS_DIR = cfg.STORAGE_DIR / 'originals'
cfg.DERIVED_DIR = cfg.STORAGE_DIR / 'derived'
cfg.VECTOR_DB_DIR = _ROOT / 'vectors'
for path in (cfg.DATA_DIR, cfg.STORAGE_DIR, cfg.ORIGINALS_DIR, cfg.DERIVED_DIR, cfg.VECTOR_DB_DIR):
    path.mkdir(parents=True, exist_ok=True)
# Some legacy extractors use relative data/ paths. Keep those inside the test root too.
os.chdir(_ROOT)
