"""Приём фото-референсов и связь кнопок съёмки с хранилищем.

Всё офлайн: сеть не нужна, генератор подменён, база живёт во временной
папке. Проверяется то, что ломается в бою: роль из подписи, выживание файла
после уборки раннера и то, что набор действительно доезжает до генерации.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.brain.engines import visual_identity as vi
from src.brain.engines.reference_vault import ReferenceVault
from src.brain.services import reference_intake as intake
from src.brain.services.guided_actions import (
    ACTION_BY_ID,
    ACTION_BY_LABEL,
    VAULT_ACTIONS,
    GuidedActionService,
    MissingActionInput,
)

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 96
_OTHER_PNG = b"\x89PNG\r\n\x1a\n" + b"\x01" * 96


class _FakeImages:
    """Генератор-дублёр: запоминает, что ему реально передали."""

    def __init__(self):
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "status": "AVAILABLE",
            "image_path": "/tmp/gen-test.png",
            "file_name": "gen-test.png",
            "model": "test-model",
            "bytes": 120000,
            "notes": "",
            "reference_used": bool(kwargs.get("reference_image_path")),
            "references_used": len(kwargs.get("references") or []),
            "references_skipped": [],
            "character_sheet": vi.character_sheet(kwargs.get("character_traits")),
        }


class _BrokenVault:
    """Закрытая база: генерация всё равно должна состояться."""

    def active_references(self):
        raise RuntimeError("database is locked")

    def traits(self):
        raise RuntimeError("database is locked")


@pytest.fixture
def brain():
    return SimpleNamespace(profile_engine=SimpleNamespace(get_profile=lambda: None))


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN_REFERENCES_DIR", str(tmp_path / "refs"))
    built = GuidedActionService.__new__(GuidedActionService)
    built._vault = ReferenceVault(db_path=tmp_path / "brain.db")
    built.images = _FakeImages()
    return built


def _photo(tmp_path, name="shot.png", raw=_PNG):
    path = tmp_path / name
    path.write_bytes(raw)
    return str(path)


def test_role_words_agree_with_the_identity_engine():
    # Два словаря разъедутся при первой же правке, если их не сверять:
    # тогда кнопка будет понимать слово, а движок положит его в другую роль.
    for word, role in intake._ROLE_BASES.items():
        assert vi.normalize_role(word) == role


@pytest.mark.parametrize(
    "caption,role",
    [
        ("вот моё лицо", vi.ROLE_FACE),
        ("снято на фоне окна", vi.ROLE_LOCATION),
        ("это для стиля", vi.ROLE_STYLE),
        ("Фигуру возьми отсюда", vi.ROLE_BODY),
        ("любимый предмет", vi.ROLE_PROP),
    ],
)
def test_caption_names_the_role(caption, role):
    assert intake.detect_role(caption) == role


@pytest.mark.parametrize("caption", ["", "просто красиво", "тут красивый фонарь"])
def test_caption_without_a_role_word_is_not_guessed(caption):
    # «фонарь» — главная ловушка стеммера: он бы стал «фоном» и уехал в локации.
    assert intake.detect_role(caption) is None


def test_note_keeps_the_words_of_the_author():
    assert intake.reference_note("лицо, без макияжа") == "без макияжа"
    assert intake.reference_note("лицо") == ""
    assert intake.reference_note("") == ""


def test_traits_are_parsed_and_foreign_fields_are_named():
    accepted, unknown = intake.parse_traits("волосы: русые до плеч; глаза — серые; настроение: доброе")
    assert accepted == {"волосы": "русые до плеч", "глаза": "серые"}
    assert unknown == ["настроение"]
    # Дефис внутри значения не должен разрывать пару.
    assert intake.parse_traits("волосы: русые до-плеч")[0] == {"волосы": "русые до-плеч"}
    assert intake.parse_traits("волосы русые") == ({}, [])


def test_stored_photo_survives_the_runner_cleanup(tmp_path):
    # Раннер удаляет временный файл в finally — если не скопировать, в базе
    # останется путь в никуда.
    temp = Path(_photo(tmp_path, "from-telegram.png"))
    stored = intake.store_reference_file(temp, target_dir=tmp_path / "refs")
    temp.unlink()
    assert stored.is_file()
    assert stored.read_bytes() == _PNG
    assert stored.name.startswith("ref-")
    # Имя — по содержимому: те же байты не плодят копий.
    again = intake.store_reference_file(_photo(tmp_path, "same.png"), target_dir=tmp_path / "refs")
    other = intake.store_reference_file(
        _photo(tmp_path, "other.png", _OTHER_PNG), target_dir=tmp_path / "refs"
    )
    assert again == stored
    assert other != stored


def test_missing_file_is_reported_by_name(tmp_path):
    with pytest.raises(ValueError, match="не найден"):
        intake.store_reference_file(tmp_path / "ghost.png", target_dir=tmp_path / "refs")


def test_vault_buttons_are_declared_and_reachable():
    assert VAULT_ACTIONS == {"shoot.reference", "shoot.character", "shoot.refset"}
    for action_id in sorted(VAULT_ACTIONS):
        action = ACTION_BY_ID[action_id]
        assert ACTION_BY_LABEL[action.label].action_id == action_id


def test_reference_button_asks_for_the_role_instead_of_guessing(service, brain, tmp_path):
    photo = _photo(tmp_path)
    with pytest.raises(MissingActionInput) as excinfo:
        service.execute("shoot.reference", brain, text="просто красиво", image_path=photo)
    assert "«лицо»" in str(excinfo.value)
    assert service.vault.list_references() == []
    assert list((tmp_path / "refs").glob("*")) == []


def test_reference_button_without_a_photo_says_so(service, brain):
    with pytest.raises(MissingActionInput, match="фото"):
        service.execute("shoot.reference", brain, text="лицо")


def test_reference_is_stored_under_the_named_role_and_counted(service, brain, tmp_path):
    photo = _photo(tmp_path)
    data = service.execute("shoot.reference", brain, text="лицо, без макияжа", image_path=photo)["data"]
    assert data["role"] == vi.ROLE_LABELS[vi.ROLE_FACE]
    assert data["note"] == "без макияжа"
    assert data["count"] == f"1 из {vi.MAX_REFERENCES}"
    # Повторная присылка того же кадра меняет роль, а не плодит дубли.
    again = service.execute("shoot.reference", brain, text="фон", image_path=photo)["data"]
    assert again["role"] == vi.ROLE_LABELS[vi.ROLE_LOCATION]
    assert again["count"] == f"1 из {vi.MAX_REFERENCES}"


def test_an_error_page_instead_of_a_photo_leaves_nothing_behind(service, brain, tmp_path):
    junk = tmp_path / "page.png"
    junk.write_bytes(b"<html><body>404</body></html>")
    with pytest.raises(MissingActionInput, match="фотография"):
        service.execute("shoot.reference", brain, text="лицо", image_path=str(junk))
    assert service.vault.list_references() == []
    assert list((tmp_path / "refs").glob("*")) == []


def test_character_sheet_button_writes_only_known_fields(service, brain):
    data = service.execute(
        "shoot.character", brain, text="волосы: русые до плеч\nглаза: серые\nнастроение: доброе"
    )["data"]
    assert data["fields"] == {"волосы": "русые до плеч", "глаза": "серые"}
    assert "настроение" in " ".join(data["rejected"])
    assert "русые до плеч" in data["sheet"]
    # Незаполненное поле просто отсутствует — примет никто не выдумывает.
    assert "особые приметы" not in data["sheet"]


def test_character_sheet_button_lists_the_allowed_fields(service, brain):
    with pytest.raises(MissingActionInput, match="волосы"):
        service.execute("shoot.character", brain, text="настроение: доброе")


def test_set_button_shows_what_generation_will_receive(service, brain, tmp_path):
    empty = service.execute("shoot.refset", brain)["data"]
    assert empty["status"] == "empty"
    assert "Лист героя" in empty["sheet"]

    service.execute("shoot.reference", brain, text="лицо", image_path=_photo(tmp_path))
    ready = service.execute("shoot.refset", brain)["data"]
    assert ready["status"] == "ready"
    assert ready["count"] == f"1 из {vi.MAX_REFERENCES}"
    assert "cleaned" not in ready

    # Файл исчез с диска — набор обязан убрать мёртвый путь сам.
    for leftover in (tmp_path / "refs").glob("*"):
        leftover.unlink()
    cleaned = service.execute("shoot.refset", brain)["data"]
    assert cleaned["count"] == f"0 из {vi.MAX_REFERENCES}"
    assert "cleaned" in cleaned


def test_generation_receives_the_stored_set_and_the_sheet(service, brain, tmp_path):
    service.execute("shoot.reference", brain, text="лицо", image_path=_photo(tmp_path))
    service.execute("shoot.character", brain, text="глаза: серые")

    result = service.execute("shoot.generate", brain, text="портрет у окна", use_llm=False)
    call = service.images.calls[-1]
    assert [Path(item["path"]).name.startswith("ref-") for item in call["references"]] == [True]
    assert call["references"][0]["role"] == vi.ROLE_FACE
    assert call["character_traits"]["глаза"] == "серые"
    assert "референсов набора: 1" in result["markdown"]
    assert "Лист героя" in result["markdown"]


def test_a_locked_database_does_not_block_generation(service, brain):
    service._vault = _BrokenVault()
    result = service.execute("shoot.generate", brain, text="портрет у окна", use_llm=False)
    assert result["data"]["status"] == "AVAILABLE"
    assert result["data"]["vault_error"] == "database is locked"
    assert "Набор референсов не прочитан: database is locked" in result["markdown"]
