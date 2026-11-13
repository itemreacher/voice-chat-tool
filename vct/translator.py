"""Offline translation between any installed language pair via Argos Translate (lazy imports).

Packs are language<->English; Argos chains two of them (X -> en -> Y) on its own.
"""
from __future__ import annotations

from typing import Callable, List, Optional, Set, Tuple

from .languages import required_pairs

Log = Callable[[str], None]


def installed_pairs() -> Set[Tuple[str, str]]:
    """Directly installed packs as (from_code, to_code)."""
    import argostranslate.package as pkg

    return {(p.from_code, p.to_code) for p in pkg.get_installed_packages()}


def missing_pairs(source: str, target: str) -> List[Tuple[str, str]]:
    have = installed_pairs()
    return [p for p in required_pairs(source, target) if p not in have]


def can_translate(source: str, target: str) -> bool:
    return source == target or not missing_pairs(source, target)


def available_packages(log: Log):
    """Refresh the Argos index (needs internet) and return all downloadable packages."""
    import argostranslate.package as pkg

    log("Loading the Argos language index...")
    pkg.update_package_index()
    return pkg.get_available_packages()


def install_pair(from_code: str, to_code: str, log: Log, packages=None) -> bool:
    import argostranslate.package as pkg

    try:
        packages = packages if packages is not None else available_packages(log)
        found = next((p for p in packages
                      if p.from_code == from_code and p.to_code == to_code), None)
        if found is None:
            log(f"No Argos pack for {from_code} -> {to_code} in the index.")
            return False
        log(f"Downloading language pack {from_code} -> {to_code}...")
        path = found.download()
        log(f"Installing {from_code} -> {to_code}...")
        pkg.install_from_path(path)
        return True
    except Exception as exc:
        log(f"Could not install {from_code} -> {to_code}: {exc}")
        return False


def uninstall_pair(from_code: str, to_code: str, log: Log) -> bool:
    import argostranslate.package as pkg

    try:
        for p in pkg.get_installed_packages():
            if p.from_code == from_code and p.to_code == to_code:
                pkg.uninstall(p)
                log(f"Removed language pack {from_code} -> {to_code}.")
                return True
        return False
    except Exception as exc:
        log(f"Could not remove {from_code} -> {to_code}: {exc}")
        return False


def ensure(source: str, target: str, log: Log) -> bool:
    """Make source -> target translatable, downloading missing packs. True if usable."""
    try:
        missing = missing_pairs(source, target)
    except Exception as exc:
        log(f"WARNING: translation unavailable ({exc}).")
        return False
    if not missing:
        return True
    try:
        packages = available_packages(log)
    except Exception as exc:
        log(f"WARNING: cannot reach the language index ({exc}). Text will not be translated.")
        return False
    ok = all(install_pair(f, t, log, packages) for f, t in missing)
    if ok:
        log(f"Translation {source} -> {target} ready.")
    return ok


def translate(text: str, source: str, target: str) -> str:
    """Translate text. Raises if the packs are not installed."""
    if source == target:
        return text
    import argostranslate.translate as at

    return at.translate(text, source, target)


def make_translate_fn(source: str, target: str) -> Optional[Callable[[str], str]]:
    """A text -> text function for the current pair, or None if packs are missing."""
    if source == target or not can_translate(source, target):
        return None
    return lambda text: translate(text, source, target)
