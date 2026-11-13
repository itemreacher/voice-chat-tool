"""Pick one input device from a name (pure; works on the list sounddevice returns).

Windows lists the same microphone once per audio interface (MME, DirectSound, WASAPI, ...).
A bare name is therefore ambiguous and sounddevice refuses it, so the choice is made here.
"""
from __future__ import annotations

from typing import List, Mapping, Optional, Sequence


def input_indices(devices: Sequence[Mapping]) -> List[int]:
    return [i for i, d in enumerate(devices) if d.get("max_input_channels", 0) > 0]


def resolve_input_device(query: str, devices: Sequence[Mapping],
                         default_hostapi: Optional[int] = None) -> Optional[int]:
    """Index of the input device that matches `query`, or None if nothing matches.

    Exact names beat partial ones; among equals the device on the system's default audio
    interface wins, then the lowest index.
    """
    needle = query.strip().lower()
    candidates = [i for i in input_indices(devices) if needle in str(devices[i]["name"]).lower()]
    if not candidates:
        return None

    def rank(i: int):
        d = devices[i]
        exact = str(d["name"]).strip().lower() == needle
        return (not exact, d.get("hostapi") != default_hostapi, i)

    return min(candidates, key=rank)


def unique_input_names(devices: Sequence[Mapping], default_hostapi: Optional[int] = None) -> List[str]:
    """Each microphone name once, in a stable order (default interface first)."""
    names: List[str] = []
    ordered = sorted(input_indices(devices), key=lambda i: (devices[i].get("hostapi") != default_hostapi, i))
    for i in ordered:
        name = str(devices[i]["name"])
        if name not in names:
            names.append(name)
    return names
