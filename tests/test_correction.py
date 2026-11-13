import pytest

from vct.config import ConfigError, parse_config
from vct.correction import apply_replacements, correct_text, parse_replacements, spell_fix


class FakeSpell:
    """known words + explicit fixes; anything else has no fix."""

    def __init__(self, known, fixes):
        self.known, self.fixes = set(known), dict(fixes)

    def is_known(self, word):
        return word.lower() in self.known

    def best_fix(self, word):
        return self.fixes.get(word.lower())


SPELL = FakeSpell({"ich", "brauche", "hilfe", "wir", "gehen"}, {"hilfee": "hilfe", "brauchee": "brauche"})


def test_parse_replacements_formats_and_junk():
    assert parse_replacements(["wiedora = Valorant", "a -> b", "c → d", "kein trenner", " = x"]) == [
        ("wiedora", "Valorant"), ("a", "b"), ("c", "d")]


def test_replacements_whole_word_case_insensitive():
    out = apply_replacements("Wiedora ist gut, wiedoras nicht", [("wiedora", "Valorant")])
    assert out.text == "Valorant ist gut, wiedoras nicht"
    assert out.changes == [("Wiedora", "Valorant")]


def test_replacements_multi_word_and_longest_first():
    pairs = [("gold", "Gold"), ("gold eins", "Gold 1")]
    assert apply_replacements("ich bin gold eins", pairs).text == "ich bin Gold 1"


def test_replacement_with_special_characters_is_literal():
    assert apply_replacements("a.b geht", [("a.b", "X")]).text == "X geht"
    assert apply_replacements("axb geht", [("a.b", "X")]).text == "axb geht"


def test_spell_fix_corrects_and_keeps_case():
    out = spell_fix("Ich brauchee Hilfee", SPELL)
    assert out.text == "Ich brauche Hilfe"
    assert out.changes == [("brauchee", "brauche"), ("Hilfee", "Hilfe")]


def test_spell_fix_leaves_unclear_unknown_words_alone():
    assert spell_fix("Raketenwerfer ischt da", SPELL).text == "Raketenwerfer ischt da"


def test_spell_fix_skips_protected_short_acronym_digits():
    s = FakeSpell(set(), {"hilfee": "hilfe", "abc": "xyz", "gg1": "ok", "hilf": "hilfe"})
    assert spell_fix("hilfee", s, protected=["Hilfee"]).text == "hilfee"
    assert spell_fix("abc HILFEE gg1", s).text == "abc HILFEE gg1"  # short / ACRONYM / digit


def test_correct_text_runs_replacements_then_spell():
    out = correct_text("wiedora brauchee hilfe", [("wiedora", "Valorant")], SPELL, protected=["Valorant"])
    assert out.text == "Valorant brauche hilfe"
    assert [c[1] for c in out.changes] == ["Valorant", "brauche"]


def test_correct_text_without_backend_only_replaces():
    assert correct_text("hilfee", [("hilfee", "Hilfe")], None).text == "Hilfe"


def test_config_new_keys_defaults_and_validation():
    cfg = parse_config({})
    assert cfg["vocabulary"] == [] and cfg["replacements"] == [] and cfg["spellcheck"] is True
    assert parse_config({"vocabulary": [" Jett ", ""]})["vocabulary"] == ["Jett"]
    for bad in ({"vocabulary": "Jett"}, {"replacements": [1]}, {"spellcheck": "yes"}):
        with pytest.raises(ConfigError):
            parse_config(bad)


def test_real_german_dictionary_end_to_end():
    pytest.importorskip("spellchecker")
    from vct.correction import PySpellBackend

    backend = PySpellBackend("de")
    out = correct_text("Ich brauche Hilfe Raketenwerfer Valorant", [], backend, protected=["Valorant"])
    assert out.text == "Ich brauche Hilfe Raketenwerfer Valorant"  # nothing valid gets changed
    assert correct_text("ich brauche Hilfee", [], backend).text == "ich brauche Hilfe"
    assert not PySpellBackend.supported("xx")
