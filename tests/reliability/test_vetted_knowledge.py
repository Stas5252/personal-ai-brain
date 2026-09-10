from pathlib import Path

from scripts.seed_vetted_knowledge import KNOWLEDGE_DIR, CORE_FILES as VETTED_FILES, core_paths as validate_corpus


def test_vetted_corpus_is_complete_and_original():
    paths = validate_corpus()
    assert len(paths) == 5
    corpus = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert len(corpus) > 15_000
    for topic in ("Ценообразование", "CRM", "Мудборд", "Возражения", "Reels", "договор"):
        assert topic.lower() in corpus.lower()
    assert "Яишка" not in corpus


def test_vetted_corpus_rejects_fabricated_commercial_claims():
    corpus = "\n".join((KNOWLEDGE_DIR / name).read_text(encoding="utf-8").lower() for name in VETTED_FILES)
    banned = ("осталось всего 2", "жду ответа ещё от 3", "бронь без предоплаты", "100% моих", "гарантирую — фото")
    assert not any(phrase in corpus for phrase in banned)


def test_only_manifested_files_are_seeded_by_default():
    assert "yaishka_knowledge.md" not in VETTED_FILES
    assert not any("prodazhi" in name or "cenoobrazovanie" in name for name in VETTED_FILES)
    assert all((KNOWLEDGE_DIR / name).suffix == ".md" for name in VETTED_FILES)
