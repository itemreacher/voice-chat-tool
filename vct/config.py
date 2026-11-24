"""Load and validate config.toml (Python 3.11+, uses stdlib tomllib)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .languages import is_valid_code
from .logic import TRANSLATE_MODES
from .updater import is_valid_repo

DEFAULTS: Dict[str, Any] = {
    "hotkey": "f9",
    "translate_hotkey": "f8",         # hold + speak = always translate; "" disables
    "keywords": ["translate", "übersetze"],
    "source_language": "de",          # language you speak (Whisper language code)
    "target_language": "en",          # language of the output text
    "translate_mode": "keyword",      # "keyword" | "always" | "off"
    "vocabulary": [],                 # names / game terms Whisper should recognise
    "replacements": [],               # "wrong = right" lines applied after recognition
    "spellcheck": True,               # fix unknown words with one clear dictionary match
    "whisper_model": "small",
    "whisper_model_gpu": "",          # "" = use whisper_model on the GPU too
    "device": "auto",                 # "auto" | "cpu" | "gpu" (start-up choice)
    "device_toggle_hotkey": "f10",    # switch CPU <-> GPU while running; "" disables
    "microphone_device": "",
    "output_mode": "type",
    "beep": True,
    "desktop_language": "auto",       # language of the desktop audio: "auto" (detect) or a code like "en"
    "desktop_translate_to": "",       # translate the transcript into this language; "" = off
    "desktop_timestamps": True,       # show [hh:mm:ss] in front of each line
    "update_check": True,             # look for a newer release on GitHub at start-up
    "update_repo": "",                # "owner/name"; "" = the repository this build came from
}
OUTPUT_MODES = ("type", "clipboard")
DEVICES = ("auto", "cpu", "gpu")


class ConfigError(Exception):
    pass


def repair_mojibake(text: str) -> str:
    """Undo UTF-8 text that was once read as Windows-1252 ('Ã¼bersetze' -> 'übersetze').

    Only changes text where that round trip works; correct text is returned unchanged.
    """
    if not any(ch in text for ch in "ÃÂâ"):
        return text
    try:
        fixed = text.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    return fixed


def parse_config(data: Dict[str, Any]) -> Dict[str, Any]:
    """Merge user values over defaults and validate. Pure function."""
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in data.items() if k in DEFAULTS})

    hotkey = cfg["hotkey"]
    if not isinstance(hotkey, str) or not hotkey.strip():
        raise ConfigError("hotkey must be a non-empty string, e.g. \"f9\"")
    if "+" in hotkey.strip():
        raise ConfigError("hotkey must be a single key (e.g. \"f9\"); combinations are not supported")
    cfg["hotkey"] = hotkey.strip().lower()

    kws = cfg["keywords"]
    if isinstance(kws, str):
        kws = [kws]
    if not isinstance(kws, list) or not all(isinstance(k, str) for k in kws):
        raise ConfigError("keywords must be a list of strings")
    cfg["keywords"] = [repair_mojibake(k).strip() for k in kws if k.strip()]

    for key in ("source_language", "target_language"):
        code = str(cfg[key]).strip().lower()
        if not is_valid_code(code):
            raise ConfigError(f"{key} must be a language code like \"de\", got {cfg[key]!r}")
        cfg[key] = code
    for key in ("vocabulary", "replacements"):
        items = cfg[key]
        if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
            raise ConfigError(f"{key} must be a list of strings")
        cfg[key] = [repair_mojibake(i).strip() for i in items if i.strip()]
    if not isinstance(cfg["spellcheck"], bool):
        raise ConfigError("spellcheck must be true or false")
    translate_mode = str(cfg["translate_mode"]).strip().lower()
    if translate_mode not in TRANSLATE_MODES:
        raise ConfigError(f"translate_mode must be one of {TRANSLATE_MODES}, got {cfg['translate_mode']!r}")
    cfg["translate_mode"] = translate_mode

    if not isinstance(cfg["whisper_model"], str) or not cfg["whisper_model"].strip():
        raise ConfigError("whisper_model must be a non-empty string, e.g. \"small\"")
    cfg["whisper_model"] = cfg["whisper_model"].strip()

    gpu_model = cfg["whisper_model_gpu"]
    if not isinstance(gpu_model, str):
        raise ConfigError("whisper_model_gpu must be a string (\"\" = same as whisper_model)")
    cfg["whisper_model_gpu"] = gpu_model.strip()

    device = str(cfg["device"]).strip().lower()
    if device == "cuda":
        device = "gpu"
    if device not in DEVICES:
        raise ConfigError(f"device must be one of {DEVICES}, got {cfg['device']!r}")
    cfg["device"] = device

    for key in ("device_toggle_hotkey", "translate_hotkey"):
        value = cfg[key]
        if not isinstance(value, str) or "+" in value:
            raise ConfigError(f"{key} must be a single key like \"f10\", or \"\" to disable")
        cfg[key] = value.strip().lower()
    keys = [cfg[k] for k in ("hotkey", "translate_hotkey", "device_toggle_hotkey") if cfg[k]]
    if len(keys) != len(set(keys)):
        raise ConfigError("hotkey, translate_hotkey and device_toggle_hotkey must be different keys")

    mode = str(cfg["output_mode"]).strip().lower()
    if mode not in OUTPUT_MODES:
        raise ConfigError(f"output_mode must be one of {OUTPUT_MODES}, got {cfg['output_mode']!r}")
    cfg["output_mode"] = mode

    if not isinstance(cfg["beep"], bool):
        raise ConfigError("beep must be true or false")
    if not isinstance(cfg["update_check"], bool):
        raise ConfigError("update_check must be true or false")
    if not isinstance(cfg["desktop_timestamps"], bool):
        raise ConfigError("desktop_timestamps must be true or false")
    lang = str(cfg["desktop_language"]).strip().lower()
    if lang != "auto" and not is_valid_code(lang):
        raise ConfigError(f"desktop_language must be \"auto\" or a language code, got {cfg['desktop_language']!r}")
    cfg["desktop_language"] = lang
    target = str(cfg["desktop_translate_to"]).strip().lower()
    if target and not is_valid_code(target):
        raise ConfigError(f"desktop_translate_to must be empty or a language code, got {cfg['desktop_translate_to']!r}")
    cfg["desktop_translate_to"] = target
    repo = cfg["update_repo"]
    if not isinstance(repo, str) or (repo.strip() and not is_valid_repo(repo.strip())):
        raise ConfigError("update_repo must look like \"owner/name\" (or be empty)")
    cfg["update_repo"] = repo.strip()
    if not isinstance(cfg["microphone_device"], (str, int)) or isinstance(cfg["microphone_device"], bool):
        raise ConfigError("microphone_device must be a string or an integer index")
    if isinstance(cfg["microphone_device"], str):
        cfg["microphone_device"] = repair_mojibake(cfg["microphone_device"]).strip()
    return cfg


def model_for_device(cfg: Dict[str, Any], device: str) -> str:
    """Whisper model name for 'cpu' or 'cuda'. GPU falls back to the CPU model name."""
    if device == "cuda" and cfg["whisper_model_gpu"]:
        return cfg["whisper_model_gpu"]
    return cfg["whisper_model"]


def wants_gpu(preference: str, cuda_available: bool) -> bool:
    """Start-up decision: 'gpu' always tries CUDA, 'auto' only if a GPU exists."""
    return preference == "gpu" or (preference == "auto" and cuda_available)


def next_device(current: Optional[str]) -> str:
    """Target of the toggle key: CUDA -> CPU, anything else -> CUDA."""
    return "cpu" if current == "cuda" else "cuda"


def device_from_config(value: Union[str, int]) -> Optional[Union[str, int]]:
    """'' -> default device; '3' or 3 -> index 3; other text -> name substring."""
    if isinstance(value, int):
        return value
    value = value.strip()
    if not value or value.lower() == "default":
        return None
    return int(value) if value.isdigit() else value


def load_config(path: Path) -> Dict[str, Any]:
    import tomllib  # Python 3.11+

    if not path.exists():
        return parse_config({})
    try:
        # utf-8-sig: Windows editors often add a BOM, which tomllib rejects.
        data = tomllib.loads(path.read_bytes().decode("utf-8-sig"))
    except UnicodeDecodeError as exc:
        raise ConfigError(f"{path} must be saved as UTF-8: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML: {exc}") from exc
    return parse_config(data)


_TEMPLATE = """# voice-chat-tool configuration (UTF-8). The GUI rewrites this file when you save.

# Push-to-talk key: hold to record, release to process. A single key only.
hotkey = {hotkey}
# Hold this key instead and speak: the text is ALWAYS translated into target_language,
# no keyword needed. A soft tone confirms it. "" disables it.
translate_hotkey = {translate_hotkey}

# Language you speak (Whisper language code) and language of the output text.
# Any pair works once the language packs are installed (tab "Sprachen & Modelle").
source_language = {source_language}
target_language = {target_language}

# "keyword" = translate only if you start with a keyword below
# "always"  = translate everything
# "off"     = output exactly what you said
translate_mode = {translate_mode}
keywords = {keywords}

# Words Whisper should get right (names, game terms), e.g. ["Valorant", "Jett", "Spike"].
vocabulary = {vocabulary}
# Fixed replacements after recognition, one "wrong = right" per entry,
# e.g. ["wiedora = Valorant"]. Whole words, case-insensitive.
replacements = {replacements}
# Fix unknown words that have one clear dictionary match (source language, before translation).
spellcheck = {spellcheck}

# faster-whisper model: tiny, base, small, medium, large-v3 ...
whisper_model = {whisper_model}
# Optional bigger model used only on the GPU. "" = same as whisper_model.
whisper_model_gpu = {whisper_model_gpu}

# Where Whisper runs at start-up: "auto", "cpu" or "gpu". F10-style key switches live.
device = {device}
device_toggle_hotkey = {device_toggle_hotkey}

# "" = Windows default microphone, a device index (e.g. 2) or part of a device name.
microphone_device = {microphone_device}

# "type" = type into the focused window AND copy; "clipboard" = copy only (safest with anti-cheat).
output_mode = {output_mode}

# Soft tones (no sound for normal push-to-talk): a short rising tone when translation is
# active, a tone when switching CPU/GPU. false = completely silent.
beep = {beep}

# Desktop audio tab: transcribe what the PC plays. Language "auto" detects it; translate_to "" = no translation.
desktop_language = {desktop_language}
desktop_translate_to = {desktop_translate_to}
desktop_timestamps = {desktop_timestamps}

# Updates: look for a newer release on GitHub when the program starts (a plain HTTPS request,
# nothing about you is sent). update_repo "" = the repository this program was built from.
update_check = {update_check}
update_repo = {update_repo}
"""


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    return json.dumps(str(value), ensure_ascii=False)  # JSON string escapes are valid TOML


def render_config(cfg: Dict[str, Any]) -> str:
    return _TEMPLATE.format(**{k: _toml_value(cfg[k]) for k in DEFAULTS})


def save_config(path: Path, cfg: Dict[str, Any]) -> None:
    """Validate, then write cfg as UTF-8 without BOM."""
    cfg = parse_config(cfg)
    path.write_text(render_config(cfg), encoding="utf-8", newline="\n")
