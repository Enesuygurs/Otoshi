import string

import pytest

from otoshi import i18n


def _placeholders(text):
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


@pytest.mark.parametrize("code", sorted(set(i18n.LANGUAGES) - {"en"}))
def test_locale_matches_english(code):
    english, other = i18n.table("en"), i18n.table(code)
    assert other, f"{code}.json is missing or invalid"
    assert set(other) == set(english), f"{code}: missing {set(english) - set(other)}, extra {set(other) - set(english)}"
    for key, text in english.items():
        assert _placeholders(other[key]) == _placeholders(text), f"{code}:{key} placeholders differ"
        assert other[key].strip(), f"{code}:{key} is empty"


def test_translation_and_fallback():
    try:
        i18n.set_language("tr")
        assert i18n.t("btn_save") == "Kaydet"
        assert i18n.t("msg_recorded", count=i18n.number(1234)) == "1.234 olay kaydedildi."
        assert i18n.upper("Kaydedici") == "KAYDEDİCİ"
        assert i18n.t("no_such_key") == "no_such_key"
        assert i18n.set_language("xx") == "en"
    finally:
        i18n.set_language("en")


def test_font_family_for_cjk():
    assert i18n.font_family("ja") != i18n.font_family("en")
    assert i18n.font_family("zh") != i18n.font_family("en")
