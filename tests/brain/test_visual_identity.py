"""
Офлайн-тесты визуальной личности: без ключей, сети и генерации.

Проверяем то, из-за чего лента рассыпается на практике: плывущую внешность,
беспорядок в референсах и тихие отказы модели вместо фото.
"""
from src.brain.engines import visual_identity as vi


# -- роли референсов ---------------------------------------------
def test_role_aliases_are_understood():
    assert vi.normalize_role("Лицо") == vi.ROLE_FACE
    assert vi.normalize_role("face") == vi.ROLE_FACE
    assert vi.normalize_role("локация") == vi.ROLE_LOCATION


def test_unknown_role_falls_back_to_style():
    assert vi.normalize_role("что-то свое") == vi.DEFAULT_ROLE
    assert vi.normalize_role(None) == vi.DEFAULT_ROLE


# -- лист героя -----------------------------------------------------
def test_character_sheet_uses_only_given_traits():
    sheet = vi.character_sheet({"герой": "Вика", "волосы": "темные до плеч"})
    assert "Вика" in sheet
    assert "темные до плеч" in sheet
    assert "глаза" not in sheet.lower()


def test_character_sheet_ignores_unknown_and_empty_fields():
    sheet = vi.character_sheet({"герой": "Вика", "знак зодиака": "весы", "глаза": "   "})
    assert "весы" not in sheet
    assert "глаза" not in sheet.lower()


def test_empty_traits_give_empty_sheet():
    assert vi.character_sheet(None) == ""
    assert vi.character_sheet({}) == ""
    assert vi.character_sheet({"герой": "  "}) == ""


def test_character_sheet_is_capped():
    sheet = vi.character_sheet({"приметы": "родинка " * 300})
    assert len(sheet) <= vi.MAX_SHEET_CHARS


# -- фиксация внешности -------------------------------------------
def test_identity_lock_contains_marker_and_sheet():
    lock = vi.identity_lock("Лист героя: кто в кадре — Вика.", roles=[vi.ROLE_FACE])
    assert vi.IDENTITY_MARKER in lock
    assert "Вика" in lock
    assert "лицо" in lock


def test_identity_lock_is_empty_without_anything_to_lock():
    assert vi.identity_lock("", roles=[]) == ""
    assert vi.identity_lock("", roles=None) == ""


def test_identity_lock_says_references_are_not_the_plot():
    lock = vi.identity_lock("", roles=[vi.ROLE_STYLE])
    assert "брифа" in lock


# -- отбор референсов ---------------------------------------------
def test_face_reference_goes_first():
    picked = vi.select_references([
        {"path": "/a/loc.jpg", "role": "локация", "added_at": "2026-09-09"},
        {"path": "/a/face.jpg", "role": "лицо", "added_at": "2026-01-01"},
    ])
    assert [p["path"] for p in picked] == ["/a/face.jpg", "/a/loc.jpg"]


def test_fresh_reference_wins_inside_one_role():
    picked = vi.select_references([
        {"path": "/a/old.jpg", "role": "лицо", "added_at": "2026-01-01"},
        {"path": "/a/new.jpg", "role": "лицо", "added_at": "2026-09-09"},
    ])
    assert picked[0]["path"] == "/a/new.jpg"


def test_duplicate_paths_are_dropped():
    picked = vi.select_references([
        {"path": "/a/face.jpg", "role": "лицо"},
        {"path": "/a/face.jpg", "role": "стиль"},
    ])
    assert len(picked) == 1


def test_reference_list_is_capped_at_the_model_limit():
    items = [{"path": f"/a/{i}.jpg", "role": "стиль"} for i in range(30)]
    assert len(vi.select_references(items)) == vi.MAX_REFERENCES


def test_explicit_smaller_limit_is_respected():
    items = [{"path": f"/a/{i}.jpg", "role": "стиль"} for i in range(10)]
    assert len(vi.select_references(items, limit=3)) == 3


def test_empty_and_broken_items_are_skipped():
    picked = vi.select_references([{"path": "   "}, {}, {"path": "/a/ok.jpg"}])
    assert [p["path"] for p in picked] == ["/a/ok.jpg"]


def test_references_summary_is_human_readable():
    summary = vi.references_summary([
        {"path": "/a/1.jpg", "role": "лицо"},
        {"path": "/a/2.jpg", "role": "лицо"},
        {"path": "/a/3.jpg", "role": "стиль"},
    ])
    assert summary.startswith("лицо — 2")
    assert "стиль и цвет — 1" in summary


# -- проверка готового кадра ------------------------------------
def _ok_result(**overrides):
    payload = {
        "status": "AVAILABLE",
        "image_path": "/data/generated/gen-1.png",
        "bytes": 400 * 1024,
        "notes": "",
        "prompt": "бриф",
    }
    payload.update(overrides)
    return payload


def test_good_result_has_no_findings():
    assert vi.qa_findings(_ok_result(), prompt="бриф") == []


def test_missing_image_is_reported():
    assert vi.qa_findings({"status": "UNAVAILABLE"}) == [vi.FINDING_NO_IMAGE]
    assert vi.qa_findings(None) == [vi.FINDING_NO_IMAGE]


def test_tiny_file_is_suspicious():
    findings = vi.qa_findings(_ok_result(bytes=2048), prompt="бриф")
    assert vi.FINDING_TOO_SMALL in findings


def test_polite_refusal_in_text_is_caught():
    findings = vi.qa_findings(
        _ok_result(notes="К сожалению, я не могу создать такое изображение"),
        prompt="бриф",
    )
    assert vi.FINDING_REFUSAL_TEXT in findings


def test_references_without_identity_lock_are_flagged():
    findings = vi.qa_findings(_ok_result(), prompt="просто бриф", references=3)
    assert vi.FINDING_IDENTITY_MISSING in findings


def test_identity_lock_present_means_no_flag():
    prompt = vi.identity_lock("Лист героя: кто в кадре — Вика.", roles=[vi.ROLE_FACE])
    findings = vi.qa_findings(_ok_result(), prompt=prompt, references=3)
    assert vi.FINDING_IDENTITY_MISSING not in findings


def test_lost_aspect_ratio_is_flagged():
    findings = vi.qa_findings(_ok_result(), prompt="бриф", aspect_ratio="4:5")
    assert vi.FINDING_ASPECT_MISSING in findings


# -- повтор --------------------------------------------------------
def test_retry_is_worth_it_for_fixable_findings():
    assert vi.should_retry([vi.FINDING_TOO_SMALL])
    assert vi.should_retry([vi.FINDING_IDENTITY_MISSING])
    assert not vi.should_retry([])
    assert not vi.should_retry([vi.FINDING_NO_IMAGE])


def test_strengthened_prompt_adds_exactly_what_was_missing():
    stronger = vi.strengthen_prompt(
        "Бриф: портрет у окна",
        [vi.FINDING_IDENTITY_MISSING, vi.FINDING_ASPECT_MISSING],
        sheet="Лист героя: кто в кадре — Вика.",
        aspect_ratio="4:5",
    )
    assert vi.IDENTITY_MARKER in stronger
    assert "4:5" in stronger
    assert "Бриф: портрет у окна" in stronger


def test_strengthened_prompt_does_not_repeat_itself():
    once = vi.strengthen_prompt("Бриф", [vi.FINDING_TOO_SMALL])
    twice = vi.strengthen_prompt(once, [vi.FINDING_TOO_SMALL])
    assert once == twice


def test_nothing_to_fix_leaves_the_prompt_alone():
    assert vi.strengthen_prompt("Бриф", []) == "Бриф"


def test_findings_are_explained_in_words():
    text = vi.explain_findings([vi.FINDING_TOO_SMALL, vi.FINDING_REFUSAL_TEXT])
    assert "маленький" in text
    assert "отказом" in text
