import pytest

from vct.config import ConfigError, load_config, parse_config, save_config
from vct.languages import code_from_label, label, needs_translation, required_pairs
from vct.logic import process_transcript

KW = ["translate", "übersetze"]
fake = lambda t: f"<{t}>"


def test_required_pairs_direct_and_pivot():
    assert required_pairs("de", "de") == []
    assert required_pairs("de", "en") == [("de", "en")]
    assert required_pairs("en", "ru") == [("en", "ru")]
    assert required_pairs("ru", "de") == [("ru", "en"), ("en", "de")]


def test_labels_roundtrip():
    assert label("ru") == "Russisch (ru)"
    assert code_from_label("Russisch (ru)") == "ru"
    assert code_from_label("FR") == "fr"
    assert label("xx") == "xx (xx)"


def test_needs_translation():
    assert needs_translation("de", "en") and not needs_translation("ru", "ru")


def test_mode_always_translates_without_keyword():
    out = process_transcript("wir pushen B", KW, fake, "always")
    assert out.text == "<wir pushen B>" and out.translated and not out.keyword_used


def test_mode_always_strips_keyword():
    assert process_transcript("translate hallo", KW, fake, "always").text == "<hallo>"


def test_mode_off_never_translates():
    out = process_transcript("translate hallo", KW, fake, "off")
    assert out.text == "translate hallo" and not out.translated


def test_mode_keyword_is_default():
    assert process_transcript("hallo", KW, fake).text == "hallo"
    assert process_transcript("translate hallo", KW, fake).text == "<hallo>"


def test_always_without_translator_falls_back_with_warning():
    out = process_transcript("hallo", KW, None, "always")
    assert out.text == "hallo" and out.warning and not out.translated


def test_always_empty_is_no_output():
    assert process_transcript("  ", KW, fake, "always").text is None


def test_config_language_defaults_and_validation():
    cfg = parse_config({})
    assert (cfg["source_language"], cfg["target_language"], cfg["translate_mode"]) == ("de", "en", "keyword")
    assert parse_config({"source_language": " RU "})["source_language"] == "ru"
    for bad in ({"source_language": "deutsch"}, {"target_language": ""}, {"translate_mode": "x"}):
        with pytest.raises(ConfigError):
            parse_config(bad)


def test_save_config_roundtrip_without_bom(tmp_path):
    cfg = parse_config({"keywords": ["übersetze", 'a"b'], "microphone_device": "Mikrofon (Fokusrite)",
                        "source_language": "ru", "target_language": "de", "beep": False})
    path = tmp_path / "config.toml"
    save_config(path, cfg)
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert load_config(path) == cfg
