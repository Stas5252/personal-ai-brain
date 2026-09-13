#!/usr/bin/env python3
"""Does a real photographer question reach the lesson that answers it?

The knowledge base was "working" for weeks in the sense that ingestion
reported success. Nothing checked the only thing that matters: ask the question
a photographer would actually type, and see whether the material that answers
it comes back. This script is that check, and it is cheap enough to run in CI
on every push.

Two modes
---------
``--offline`` (default)
    Scores the 40 Markdown lessons in ``src/brain/knowledge`` with the same
    lexical matcher retrieval uses. Pure stdlib: no database, no embeddings, no
    PDFs, no network. This is what runs in CI, so a morphology or routing
    regression fails the build instead of quietly degrading answers.

``--engine``
    Runs the real ``KnowledgeEngine.retrieve`` against the indexed corpus on
    the owner's machine — vector index, FTS5 and the PDF course included. Use
    it after ingestion to confirm production retrieval, not just morphology.

Exit code is 0 when the pass rate reaches ``--min-pass``, 1 otherwise.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

KNOWLEDGE_DIR = REPO_ROOT / "src" / "brain" / "knowledge"

# Questions are written the way the owner types them — lowercase, no keywords
# lifted from the lesson titles. Each expectation lists every lesson that may
# legitimately answer first, because "возражение дорого" is covered in four
# files and any of them is a correct hit.
EVAL_SET: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        "клиент говорит что дорого, что ему ответить",
        ("01_objections_and_sales", "08_sales_phrases", "15_objections_handling_deep", "19_продажи_возражения"),
    ),
    (
        "напиши ответ на возражение я подумаю и напишу позже",
        ("01_objections_and_sales", "05_client_communication", "08_sales_phrases", "15_objections_handling_deep", "19_продажи_возражения"),
    ),
    (
        "как собрать прайс из трех пакетов",
        ("03_pricing_and_packages", "20_ценообразование", "28_монетизация"),
    ),
    (
        "как поднять цены и не потерять клиентов",
        ("03_pricing_and_packages", "20_ценообразование", "28_монетизация", "09_psychology_and_mindset"),
    ),
    (
        "идеи для сторис на неделю",
        ("10_reels_and_stories_ideas", "16_stories_ideas_and_content", "23_сторис_хайлайты"),
    ),
    (
        "сценарий рилс про закулисье съёмки",
        ("10_reels_and_stories_ideas", "16_stories_ideas_and_content", "21_контент_маркетинг", "35_content_and_promotion_playbooks"),
    ),
    (
        "как упаковать профиль в инстаграме",
        ("12_profile_packaging_instagram", "04_personal_brand", "22_личный_бренд"),
    ),
    (
        "что написать в шапке профиля и закрепить в хайлайтах",
        ("12_profile_packaging_instagram", "23_сторис_хайлайты", "04_personal_brand", "22_личный_бренд"),
    ),
    (
        "собери контент план на месяц",
        ("02_content_strategy", "21_контент_маркетинг", "35_content_and_promotion_playbooks"),
    ),
    (
        "как вести базу клиентов и возвращать их на повторные съёмки",
        ("13_client_base_management", "24_клиенты_сервис", "06_promotion_and_clients"),
    ),
    (
        "как организовать фотодень",
        ("30_фотодень_организация", "32_photographer_business_os", "07_photo_session_prep"),
    ),
    (
        "как подготовить клиента к съёмке и что ему написать заранее",
        ("07_photo_session_prep", "05_client_communication", "34_client_experience_and_ethics"),
    ),
    (
        "где искать новых клиентов",
        ("06_promotion_and_clients", "29_аудитория", "13_client_base_management", "35_content_and_promotion_playbooks"),
    ),
    (
        "как определить целевую аудиторию",
        ("29_аудитория", "02_content_strategy", "22_личный_бренд"),
    ),
    (
        "личный бренд с чего начать и как рассказать о себе",
        ("04_personal_brand", "22_личный_бренд", "12_profile_packaging_instagram"),
    ),
    (
        "боюсь называть свою цену и стесняюсь продавать",
        ("09_psychology_and_mindset", "27_психология_бизнеса", "20_ценообразование"),
    ),
    (
        "промпты для chatgpt чтобы писать посты",
        ("11_ai_prompts_for_photographer", "25_обучение_chatgpt", "26_инструменты"),
    ),
    (
        "какие сервисы и приложения взять в работу",
        ("26_инструменты", "11_ai_prompts_for_photographer", "14_telegram_content_and_apps", "25_обучение_chatgpt"),
    ),
    (
        "как развивать телеграм канал",
        ("14_telegram_content_and_apps", "35_content_and_promotion_playbooks", "06_promotion_and_clients"),
    ),
    (
        "как зарабатывать больше кроме съёмок",
        ("28_монетизация", "32_photographer_business_os", "03_pricing_and_packages"),
    ),
)


def _paragraphs(text: str) -> List[str]:
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def _offline_ranking(question: str) -> List[Tuple[str, float]]:
    """Best-scoring paragraph per lesson, lessons ranked by that score."""
    from src.brain.knowledge.text_match import lexical_score

    ranked: Dict[str, float] = {}
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        best = 0.0
        for paragraph in _paragraphs(text):
            best = max(best, lexical_score(question, paragraph))
        # The title is part of the material: a lesson called «Ценообразование»
        # answers a pricing question even when no paragraph repeats the word.
        best = max(best, lexical_score(question, path.stem.replace("_", " ")))
        if best > 0.0:
            ranked[path.stem] = best
    return sorted(ranked.items(), key=lambda item: item[1], reverse=True)


def _engine_ranking(question: str, limit: int) -> List[Tuple[str, float]]:
    from src.brain.engines.knowledge_engine import KnowledgeEngine

    hits = KnowledgeEngine().retrieve(query=question, limit=limit)
    ranking: List[Tuple[str, float]] = []
    for hit in hits:
        chunk, score = hit[0], hit[1]
        meta = getattr(chunk, "metadata", None)
        label = " ".join(
            str(value)
            for value in (getattr(meta, "title", ""), getattr(meta, "source_path", ""))
            if value
        )
        ranking.append((label or "без названия", float(score)))
    return ranking


def _matches(label: str, expected: Sequence[str]) -> bool:
    lowered = label.lower()
    return any(stem.lower() in lowered for stem in expected)


def run(mode: str, min_pass: float, verbose: bool, limit: int) -> int:
    if mode == "offline" and not KNOWLEDGE_DIR.is_dir():
        print(f"FAIL: нет каталога с материалами: {KNOWLEDGE_DIR}")
        return 1

    passed = 0
    misses: List[str] = []
    print(f"Проверка знаний: {len(EVAL_SET)} вопросов, режим {mode}\n")

    for question, expected in EVAL_SET:
        ranking = _offline_ranking(question) if mode == "offline" else _engine_ranking(question, limit)
        top = ranking[0] if ranking else ("— ничего не нашлось —", 0.0)
        hit = bool(ranking) and _matches(top[0], expected)
        rank = next(
            (index + 1 for index, item in enumerate(ranking) if _matches(item[0], expected)),
            None,
        )
        if hit:
            passed += 1
        else:
            misses.append(question)
        if verbose or not hit:
            status = "OK  " if hit else "MISS"
            print(f"{status} {question}")
            print(f"     найдено: {top[0]} ({top[1]:.2f})")
            if not hit:
                print(f"     ожидалось: {', '.join(expected)}")
                print(f"     ожидаемый материал на позиции: {rank if rank else 'не нашёлся'}")

    rate = passed / len(EVAL_SET)
    print(f"\nИтог: {passed}/{len(EVAL_SET)} ({rate:.0%}), порог {min_pass:.0%}")
    if rate < min_pass:
        print("Не прошло. Вопросы без попадания:")
        for question in misses:
            print(f"  - {question}")
        return 1
    print("Прошло.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--offline", action="store_true", help="только Markdown-материалы, без БД (по умолчанию)")
    group.add_argument("--engine", action="store_true", help="настоящий KnowledgeEngine.retrieve по проиндексированному корпусу")
    parser.add_argument("--min-pass", type=float, default=0.7, help="минимальная доля попаданий (0–1)")
    parser.add_argument("--limit", type=int, default=5, help="сколько фрагментов запрашивать в режиме --engine")
    parser.add_argument("--verbose", action="store_true", help="печатать каждый вопрос, а не только промахи")
    args = parser.parse_args(argv)

    mode = "engine" if args.engine else "offline"
    try:
        return run(mode=mode, min_pass=args.min_pass, verbose=args.verbose, limit=args.limit)
    except Exception as exc:  # pragma: no cover - operator feedback path
        print(f"FAIL: проверка не запустилась: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
