from app.cv_locales import SECTION_TITLES_EN, SECTION_TITLES_RU, section_titles_for


def test_section_titles_for_returns_the_matching_locale():
    assert section_titles_for("ru") == SECTION_TITLES_RU
    assert section_titles_for("en") == SECTION_TITLES_EN


def test_section_titles_for_falls_back_to_english_for_an_unknown_language():
    assert section_titles_for("fr") == SECTION_TITLES_EN
    assert section_titles_for("") == SECTION_TITLES_EN


def test_every_locale_has_the_same_key_set_and_order():
    # A locale dict missing a key would KeyError wherever a renderer looks
    # it up for that language (app/cv_locales.py's own module docstring).
    assert list(SECTION_TITLES_RU.keys()) == list(SECTION_TITLES_EN.keys())


def test_no_locale_has_a_blank_title():
    for locale in (SECTION_TITLES_EN, SECTION_TITLES_RU):
        for title in locale.values():
            assert title.strip() != ""
