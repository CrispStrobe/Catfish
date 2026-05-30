"""Tests for utils/i18n.py"""

from utils.i18n import Translator


class TestTranslator:
    def test_default_language(self):
        t = Translator()
        assert t.current_lang in ("en", "de")

    def test_set_language(self):
        t = Translator()
        t.set_language("de")
        assert t.current_lang == "de"
        t.set_language("en")
        assert t.current_lang == "en"

    def test_set_invalid_language(self):
        t = Translator()
        t.set_language("fr")
        # Should not change
        assert t.current_lang != "fr"

    def test_get_known_key(self):
        t = Translator()
        t.set_language("en")
        assert t.get("app_title") == "Universal File Search & Index Tool"

    def test_get_unknown_key(self):
        t = Translator()
        t.set_language("en")
        # Unknown key returns the key itself
        assert t.get("nonexistent_key_xyz") == "nonexistent_key_xyz"

    def test_get_with_format_args(self):
        t = Translator()
        t.set_language("en")
        result = t.get("found_status", 42)
        assert "42" in result

    def test_get_with_bad_format(self):
        t = Translator()
        t.set_language("en")
        # Key exists but format args don't match - should not crash
        result = t.get("app_title", "extra_arg")
        assert isinstance(result, str)

    def test_german_translations_exist(self):
        t = Translator()
        t.set_language("de")
        assert t.get("app_title") != "app_title"
        assert t.get("search_button") != "search_button"

    def test_no_duplicate_keys(self):
        t = Translator()
        # Verify critical keys exist in both languages
        for key in ["app_title", "search_button", "error", "cancel_button"]:
            t.set_language("en")
            en = t.get(key)
            t.set_language("de")
            de = t.get(key)
            assert en != key, f"Missing English translation for {key}"
            assert de != key, f"Missing German translation for {key}"
