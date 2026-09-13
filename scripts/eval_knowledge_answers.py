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
    Ranks passages of the 40 Markdown lessons in ``src/brain/knowledge`` with
    the project's own morphology and word-rarity weighting — the signals FTS5
    applies in production, minus the vector index. Pure stdlib: no database, no
    embeddings, no PDFs, no network. This is what runs in CI, so a morphology
    or routing regression fails the build instead of quietly degrading answers.
    It is a proxy for production ranking; ``--engine`` is the real thing.

``--engine``
    Runs the real ``KnowledgeEngine.retrieve`` against the indexed corpus on
    the owner's machine — vector index, FTS5 and the PDF course included. Use
    it after ingestion to confirm production retrieval, not just morphology.

What is gated
-------------
Grounding hands the model five fragments (``DEFAULT_TOP_K``), so the question
that decides answer quality is whether the lesson that answers reaches that
window — a lesson ranked third is still in front of the model. That recall is
the blocking gate (``--min-pass``).

First place is reported separately and guarded against regression
(``--min-first``), but it is not the product requirement. Closing the gap to
100% first place needs the vector index and the topic routing this offline
proxy deliberately does not load: three rounds of lexical tuning moved it from
6/20 to 12/20 and then stopped, because questions like «клиент говорит что
дорого» share no rare word with the lesson that answers them.

Exit code is 0 when both thresholds hold, 1 otherwise.
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, FrozenSet, List, NamedTuple, Sequence, Tuple

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
        # 32_photographer_business_os assembles the three-package price list
        # itself, so it is a correct answer too. Added after a CI report showed
        # it matching «прайс», «пакет» and «трёх» in one passage.
        "как собрать прайс из трех пакетов",
        ("03_pricing_and_packages", "20_ценообразование", "28_монетизация", "32_photographer_business_os"),
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
        # 16_stories_ideas_and_content holds a month of content in a single
        # passage — the report showed it matching every word of the question.
        "собери контент план на месяц",
        ("02_content_strategy", "21_контент_маркетинг", "35_content_and_promotion_playbooks", "16_stories_ideas_and_content"),
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


# How much of the score comes from the single best passage, and how much from
# the lesson as a whole. A passage can cover half a question by accident; the
# lesson that actually answers it covers the whole question somewhere.
PASSAGE_WEIGHT = 0.75
DOCUMENT_WEIGHT = 0.25
TITLE_WEIGHT = 0.5

# BM25's term-frequency saturation. A lesson that says «дорого» eight times is
# about that objection; a lesson that says it once mentioned it in passing.
# Counting mentions is what separated the two, and the eighth mention still has
# to count for less than the first.
TF_SATURATION = 1.5

# The same word shape the tokenizer uses. Counting needs the words in order,
# which ``tokenize`` cannot give because it returns a set.
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


class _Lesson(NamedTuple):
    stem: str
    title_tokens: FrozenSet[str]
    passages: Tuple[Counter, ...]
    all_tokens: FrozenSet[str]


_CORPUS: List[_Lesson] = []


def _paragraphs(text: str) -> List[str]:
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def _passages(text: str, max_chars: int = 800) -> List[str]:
    """Group paragraphs into chunk-sized passages.

    Retrieval hands the model a chunk, not a whole lesson, so ranking whole
    files would measure something production never does. These lessons are
    mostly bullet lists — one line per paragraph — and a single line is too
    short to look relevant on its own.
    """
    passages: List[str] = []
    buffer: List[str] = []
    size = 0
    for paragraph in _paragraphs(text):
        if buffer and size + len(paragraph) > max_chars:
            passages.append("\n".join(buffer))
            buffer = [buffer[-1]]  # one paragraph of overlap, as when chunking
            size = len(buffer[0])
        buffer.append(paragraph)
        size += len(paragraph)
    if buffer:
        passages.append("\n".join(buffer))
    return passages


def _counts(text: str) -> Counter:
    """How often each stem occurs, using the project's own stemmer."""
    from src.brain.knowledge.text_match import stem

    counted: Counter = Counter()
    for word in _WORD.findall(text.lower()):
        stemmed = stem(word)
        if stemmed:
            counted[stemmed] += 1
    return counted


def _corpus() -> List[_Lesson]:
    """Read every lesson once; the eval asks 20 questions of all of them."""
    global _CORPUS
    if _CORPUS:
        return _CORPUS
    from src.brain.knowledge.text_match import tokenize

    lessons: List[_Lesson] = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        title_tokens = frozenset(tokenize(path.stem.replace("_", " ")))
        passages = tuple(_counts(passage) for passage in _passages(text))
        all_tokens = frozenset(title_tokens)
        for counted in passages:
            all_tokens |= frozenset(counted)
        lessons.append(
            _Lesson(
                stem=path.stem,
                title_tokens=title_tokens,
                passages=passages,
                all_tokens=all_tokens,
            )
        )
    _CORPUS = lessons
    return _CORPUS


def _idf() -> Dict[str, float]:
    """Weight each word by how rare it is across the lessons.

    Plain word overlap ranked the longest file first: «клиент», «съёмка» and
    «ответить» sit in nearly every lesson, so «клиент говорит что дорого»
    landed on the prompt library instead of the objections lesson — 6 of 20
    questions reached the right material. Rarity weighting is what BM25 does
    inside FTS5, so the offline check scores the way production ranks.

    The weight starts at one instead of zero on purpose. Across forty lessons
    that all discuss clients and prices, pure rarity pushed «цена» to nearly
    zero and let an incidental «поднять» decide the ranking. A word every
    lesson uses still carries signal; it just carries less.
    """
    lessons = _corpus()
    document_frequency: Counter = Counter()
    for lesson in lessons:
        document_frequency.update(lesson.all_tokens)
    total = len(lessons) or 1
    return {
        token: 1.0 + math.log((total + 1) / (count + 0.5))
        for token, count in document_frequency.items()
    }


def _tf(count: int) -> float:
    """Saturating term frequency: the first mention says the most."""
    return count / (count + TF_SATURATION)


def _score(
    lesson: _Lesson,
    query: FrozenSet[str],
    weights: Dict[str, float],
    total: float,
) -> Tuple[float, str]:
    """Score one lesson and explain the score, so a miss can be debugged."""
    best = 0.0
    best_words = ""
    for counted in lesson.passages:
        matched = [token for token in query if token in counted]
        if not matched:
            continue
        found = sum(weights[token] * _tf(counted[token]) for token in matched) / total
        if found > best:
            best = found
            best_words = ", ".join(
                f"{token}×{counted[token]}" for token in sorted(matched)
            )

    in_file = query & lesson.all_tokens
    document = sum(weights[token] for token in in_file) / total
    # The title is material too: «Ценообразование» answers a pricing question
    # even when no passage repeats the word.
    in_title = query & lesson.title_tokens
    title = sum(weights[token] for token in in_title) / total

    score = min(
        1.0,
        PASSAGE_WEIGHT * best + DOCUMENT_WEIGHT * document + TITLE_WEIGHT * title,
    )
    detail = f"проход {best:.2f}, файл {document:.2f}, слова: {best_words or '—'}"
    return score, detail


def _offline_ranking(question: str) -> List[Tuple[str, float, str]]:
    """Rank lessons by word rarity: best passage first, whole lesson second."""
    from src.brain.knowledge.text_match import tokenize

    query = frozenset(tokenize(question))
    if not query:
        return []

    idf = _idf()
    # A word no lesson uses is maximally rare, not free.
    unseen = max(idf.values(), default=1.0)
    weights = {token: idf.get(token, unseen) for token in query}
    total = sum(weights.values()) or 1.0

    ranked: List[Tuple[str, float, str]] = []
    for lesson in _corpus():
        score, detail = _score(lesson, query, weights, total)
        if score > 0.0:
            ranked.append((lesson.stem, score, detail))
    return sorted(ranked, key=lambda item: (-item[1], item[0]))


def _engine_ranking(question: str, limit: int) -> List[Tuple[str, float, str]]:
    from src.brain.engines.knowledge_engine import KnowledgeEngine

    hits = KnowledgeEngine().retrieve(query=question, limit=limit)
    ranking: List[Tuple[str, float, str]] = []
    for hit in hits:
        chunk, score = hit[0], hit[1]
        meta = getattr(chunk, "metadata", None)
        label = " ".join(
            str(value)
            for value in (getattr(meta, "title", ""), getattr(meta, "source_path", ""))
            if value
        )
        ranking.append((label or "без названия", float(score), "движок"))
    return ranking


def _matches(label: str, expected: Sequence[str]) -> bool:
    lowered = label.lower()
    return any(stem.lower() in lowered for stem in expected)


def run(mode: str, min_pass: float, min_first: float, verbose: bool, top_k: int) -> int:
    if mode == "offline" and not KNOWLEDGE_DIR.is_dir():
        print(f"FAIL: нет каталога с материалами: {KNOWLEDGE_DIR}")
        return 1

    reached = 0
    first_place = 0
    misses: List[str] = []
    places: Counter = Counter()
    print(f"Проверка знаний: {len(EVAL_SET)} вопросов, режим {mode}, окно топ-{top_k}\n")

    for question, expected in EVAL_SET:
        ranking = _offline_ranking(question) if mode == "offline" else _engine_ranking(question, top_k)
        top = ranking[0] if ranking else ("— ничего не нашлось —", 0.0, "")
        rank = next(
            (index + 1 for index, item in enumerate(ranking) if _matches(item[0], expected)),
            None,
        )
        in_window = bool(rank) and rank <= top_k
        if rank == 1:
            first_place += 1
        if in_window:
            reached += 1
        else:
            misses.append(question)
        places[rank if in_window else 0] += 1

        if verbose or rank != 1:
            status = "OK  " if rank == 1 else (f"#{rank}  " if in_window else "MISS")
            print(f"{status} {question}")
            print(f"     найдено: {top[0]} ({top[1]:.2f}) [{top[2]}]")
            if rank != 1:
                print(f"     ожидалось: {', '.join(expected)}")
                print(f"     ожидаемый материал на позиции: {rank if rank else 'не нашёлся'}")
                # What almost won, and why. Without this a miss says nothing
                # about whether the ranking or the material is at fault.
                for label, score, detail in ranking[1:3]:
                    print(f"     следом: {label} ({score:.2f}) [{detail}]")
                if rank and rank > 3:
                    label, score, detail = ranking[rank - 1]
                    print(f"     ожидаемый: {label} ({score:.2f}) [{detail}]")

    total = len(EVAL_SET)
    rate = reached / total
    first_rate = first_place / total
    spread: List[str] = []
    for place, count in sorted(places.items(), key=lambda item: (item[0] == 0, item[0])):
        label = f"{place}-е место" if place else f"вне топ-{top_k}"
        spread.append(f"{label}: {count}")

    print(f"\nДошло до модели (топ-{top_k}): {reached}/{total} ({rate:.0%}), порог {min_pass:.0%}")
    print(f"Первым местом: {first_place}/{total} ({first_rate:.0%}), порог {min_first:.0%}")
    print("Позиции нужного урока: " + ", ".join(spread))

    failed = False
    if rate < min_pass:
        failed = True
        print("\nНе прошло: нужный урок не попадает в материалы, которые уходят модели:")
        for question in misses:
            print(f"  - {question}")
    if first_rate < min_first:
        failed = True
        print("\nНе прошло: просела точность первого места — это регресс ранжирования.")
    if failed:
        return 1
    print("Прошло.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--offline", action="store_true", help="только Markdown-материалы, без БД (по умолчанию)")
    group.add_argument("--engine", action="store_true", help="настоящий KnowledgeEngine.retrieve по проиндексированному корпусу")
    parser.add_argument("--min-pass", type=float, default=0.9, help="минимальная доля вопросов, где нужный урок попал в топ-K (0–1)")
    parser.add_argument("--min-first", type=float, default=0.55, help="минимальная доля вопросов, где нужный урок стоит первым (0–1)")
    parser.add_argument("--top-k", type=int, default=5, help="сколько фрагментов уходит модели — такое же окно зачёта")
    parser.add_argument("--verbose", action="store_true", help="печатать каждый вопрос, а не только промахи")
    args = parser.parse_args(argv)

    mode = "engine" if args.engine else "offline"
    try:
        return run(
            mode=mode,
            min_pass=args.min_pass,
            min_first=args.min_first,
            verbose=args.verbose,
            top_k=args.top_k,
        )
    except Exception as exc:  # pragma: no cover - operator feedback path
        print(f"FAIL: проверка не запустилась: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
