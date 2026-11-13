import pytest

from vct.logic import clean_text, detect_keyword, process_transcript

KW = ["translate", "übersetze"]


def fake_translate(text):
    return {"wie spät ist es": "what time is it",
            "ich brauche Hilfe": "I need help"}.get(text, "EN:" + text)


def test_keyword_translate():
    assert detect_keyword("translate wie spät ist es", KW) == (True, "wie spät ist es")


def test_keyword_uebersetze_with_comma_and_case():
    assert detect_keyword("Übersetze, ich brauche Hilfe", KW) == (True, "ich brauche Hilfe")


def test_keyword_uppercase_and_trailing_punctuation():
    assert detect_keyword("TRANSLATE: wir pushen B.", KW) == (True, "wir pushen B.")
    assert detect_keyword("Translate. Hallo", KW) == (True, "Hallo")


def test_no_keyword():
    assert detect_keyword("wir pushen B", KW) == (False, "wir pushen B")


def test_keyword_must_be_whole_first_word():
    assert detect_keyword("translated wir pushen", KW)[0] is False
    assert detect_keyword("bitte translate das", KW)[0] is False


@pytest.mark.parametrize("empty", ["", "   ", "\n\t ", None])
def test_empty_transcript_gives_no_output(empty):
    assert process_transcript(empty, KW, fake_translate).text is None


def test_keyword_only_gives_no_output():
    out = process_transcript("Translate.", KW, fake_translate)
    assert out.text is None and out.keyword_used


def test_translation_applied():
    out = process_transcript("translate wie spät ist es", KW, fake_translate)
    assert out.text == "what time is it" and out.translated


def test_german_passthrough_without_keyword():
    out = process_transcript("  wir pushen   B ", KW, fake_translate)
    assert out.text == "wir pushen B" and not out.translated


def test_translation_failure_falls_back_to_german():
    def boom(_):
        raise RuntimeError("model missing")

    out = process_transcript("translate hallo", KW, boom)
    assert out.text == "hallo" and not out.translated and "failed" in out.warning


def test_translator_unavailable_falls_back():
    out = process_transcript("übersetze hallo", KW, None)
    assert out.text == "hallo" and out.warning


def test_clean_text_collapses_whitespace():
    assert clean_text("  a \n b\t c ") == "a b c"
    assert clean_text(None) == ""
