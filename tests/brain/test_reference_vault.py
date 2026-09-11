"""
Офлайн-тесты хранилища референсов: без сети, ключей и генерации.

База поднимается во временном файле, «фотографии» пишутся байтами, поэтому
проверяется именно поведение хранилища, а не окружение.
"""
import pytest

from src.brain.engines import visual_identity as vi
from src.brain.engines.reference_vault import ReferenceVault


def _vault(tmp_path):
    return ReferenceVault(db_path=tmp_path / "vault.db")


def _photo(tmp_path, name="face.png", size=200):
    path = tmp_path / name
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * size)
    return path


# -- приём фотографий ---------------------------------------------------
def test_reference_is_stored(tmp_path):
    vault = _vault(tmp_path)
    record = vault.add_reference(_photo(tmp_path), role="лицо")
    assert record["role"] == vi.ROLE_FACE
    assert len(vault.list_references()) == 1


def test_role_is_normalized_from_plain_russian(tmp_path):
    vault = _vault(tmp_path)
    record = vault.add_reference(_photo(tmp_path, "loc.png"), role="фон")
    assert record["role"] == vi.ROLE_LOCATION


def test_unknown_role_becomes_style(tmp_path):
    vault = _vault(tmp_path)
    record = vault.add_reference(_photo(tmp_path, "x.png"), role="непонятно")
    assert record["role"] == vi.DEFAULT_ROLE


def test_same_file_twice_is_not_duplicated(tmp_path):
    vault = _vault(tmp_path)
    photo = _photo(tmp_path)
    first = vault.add_reference(photo, role="стиль")
    second = vault.add_reference(photo, role="лицо")
    assert first["id"] == second["id"]
    stored = vault.list_references()
    assert len(stored) == 1
    assert stored[0]["role"] == vi.ROLE_FACE


def test_missing_file_is_rejected(tmp_path):
    vault = _vault(tmp_path)
    with pytest.raises(ValueError):
        vault.add_reference(tmp_path / "nope.png")


def test_empty_file_is_rejected(tmp_path):
    vault = _vault(tmp_path)
    empty = tmp_path / "empty.png"
    empty.write_bytes(b"")
    with pytest.raises(ValueError):
        vault.add_reference(empty)


def test_html_error_page_is_not_a_photo(tmp_path):
    vault = _vault(tmp_path)
    fake = tmp_path / "fake.png"
    fake.write_bytes(b"<html>error</html>")
    with pytest.raises(ValueError):
        vault.add_reference(fake)


# -- порядок и отбор ----------------------------------------------------
def test_list_is_fresh_first(tmp_path):
    vault = _vault(tmp_path)
    vault.add_reference(_photo(tmp_path, "a.png"), role="стиль", added_at="2026-01-01T00:00:00")
    vault.add_reference(_photo(tmp_path, "b.png"), role="стиль", added_at="2026-09-01T00:00:00")
    assert vault.list_references()[0]["path"].endswith("b.png")


def test_filter_by_role(tmp_path):
    vault = _vault(tmp_path)
    vault.add_reference(_photo(tmp_path, "f.png"), role="лицо")
    vault.add_reference(_photo(tmp_path, "s.png"), role="стиль")
    assert len(vault.list_references(role="лицо")) == 1


def test_active_set_puts_the_face_first(tmp_path):
    vault = _vault(tmp_path)
    vault.add_reference(_photo(tmp_path, "s.png"), role="стиль", added_at="2026-09-09T00:00:00")
    vault.add_reference(_photo(tmp_path, "f.png"), role="лицо", added_at="2026-01-01T00:00:00")
    assert vault.active_references()[0]["path"].endswith("f.png")


def test_active_set_respects_the_model_limit(tmp_path):
    vault = _vault(tmp_path)
    for index in range(20):
        vault.add_reference(_photo(tmp_path, f"p{index}.png"), role="стиль")
    assert len(vault.active_references()) == vi.MAX_REFERENCES


# -- удаление и уборка --------------------------------------------------
def test_reference_can_be_removed(tmp_path):
    vault = _vault(tmp_path)
    record = vault.add_reference(_photo(tmp_path))
    assert vault.remove_reference(record["id"]) is True
    assert vault.list_references() == []


def test_removing_unknown_id_is_false(tmp_path):
    assert _vault(tmp_path).remove_reference("no-such-id") is False


def test_clear_by_role_keeps_the_rest(tmp_path):
    vault = _vault(tmp_path)
    vault.add_reference(_photo(tmp_path, "f.png"), role="лицо")
    vault.add_reference(_photo(tmp_path, "s.png"), role="стиль")
    assert vault.clear_references(role="стиль") == 1
    assert len(vault.list_references()) == 1


def test_vanished_files_are_pruned(tmp_path):
    vault = _vault(tmp_path)
    photo = _photo(tmp_path, "gone.png")
    vault.add_reference(photo)
    photo.unlink()
    assert vault.prune_missing() == 1
    assert vault.list_references() == []


# -- лист героя ---------------------------------------------------------
def test_trait_is_stored_and_read_back(tmp_path):
    vault = _vault(tmp_path)
    vault.set_trait("волосы", "тёмные до плеч")
    assert vault.traits()["волосы"] == "тёмные до плеч"


def test_unknown_trait_is_refused_with_the_allowed_list(tmp_path):
    vault = _vault(tmp_path)
    with pytest.raises(ValueError) as err:
        vault.set_trait("знак зодиака", "весы")
    assert "волосы" in str(err.value)


def test_empty_value_clears_the_trait(tmp_path):
    vault = _vault(tmp_path)
    vault.set_trait("глаза", "серые")
    vault.set_trait("глаза", "   ")
    assert "глаза" not in vault.traits()


def test_traits_follow_the_sheet_order(tmp_path):
    vault = _vault(tmp_path)
    vault.set_trait("глаза", "серые")
    vault.set_trait("герой", "Вика")
    assert list(vault.traits()) == ["герой", "глаза"]


def test_character_sheet_is_built_from_stored_traits(tmp_path):
    vault = _vault(tmp_path)
    vault.set_trait("герой", "Вика")
    sheet = vault.character_sheet()
    assert "Вика" in sheet
    assert sheet.startswith("Лист героя")


# -- сводка -------------------------------------------------------------
def test_summary_is_honest_when_empty(tmp_path):
    summary = _vault(tmp_path).summary()
    assert "пустой" in summary
    assert "Референсов пока нет" in summary


def test_summary_warns_when_there_is_no_face(tmp_path):
    vault = _vault(tmp_path)
    vault.add_reference(_photo(tmp_path, "s.png"), role="стиль")
    assert "Нет ни одного референса лица" in vault.summary()
