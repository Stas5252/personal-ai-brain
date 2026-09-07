"""Isolate before test collection: imports can create databases and indexes."""
import os
import sys
import shutil
import tempfile
from pathlib import Path

_REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPOSITORY))
_TEST_ROOT = tempfile.TemporaryDirectory(prefix='brain-tests-', ignore_cleanup_errors=True)
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
for name in ('fixtures', 'pilot_corpus'):
    source = _REPOSITORY / 'tests' / name
    if source.is_dir():
        shutil.copytree(source, _ROOT / 'tests' / name)
# Relative data/ paths cannot reach production storage; imports still use the checkout.
os.chdir(_ROOT)
