"""Pick input devices from a name (pure; works on the list sounddevice returns).

Windows lists the same microphone once per audio interface (MME, DirectSound, WASAPI, ...), and MME cuts
device names to 31 characters. A bare name is therefore ambiguous. The matching devices are ranked so that
the interface Windows itself uses by default comes first; the recorder tries them in that order.
"""
from __future__ import annotations

from typing import List, Mapping, Optional, Sequence

MME_NAME_LIMIT = 31          # MME truncates device names to this length
_TRUNCATED_MIN = 28          # shorter names are not treated as truncated copies of a longer one


def input_indices(devices: Sequence[Mapping]) -> List[int]:
    return [i for i, d in enumerate(devices) if d.get("max_input_channels", 0) > 0]


def _is_same_device_name(device_name: str, needle: str) -> bool:
    """Equal, or a truncated MME copy of the full name ('Analogue 1 + 2 (Focusrite USB A')."""
    name = device_name.strip().lower()
    return name == needle or (len(name) >= _TRUNCATED_MIN and needle.startswith(name))


def candidate_input_devices(query: str, devices: Sequence[Mapping],
                            default_hostapi: Optional[int] = None) -> List[int]:
    """All input devices that match `query`, best first.

    Same name (including truncated copies) beats a partial match; then the system's default audio
    interface; then the lowest index.
    """
    needle = query.strip().lower()
    found = []
    for i in input_indices(devices):
        name = str(devices[i]["name"])
        if needle in name.lower() or _is_same_device_name(name, needle):
            found.append(i)

    def rank(i: int):
        d = devices[i]
        return (not _is_same_device_name(str(d["name"]), needle), d.get("hostapi") != default_hostapi, i)

    return sorted(found, key=rank)


def resolve_input_device(query: str, devices: Sequence[Mapping],
                         default_hostapi: Optional[int] = None) -> Optional[int]:
    """Index of the best matching input device, or None if nothing matches."""
    candidates = candidate_input_devices(query, devices, default_hostapi)
    return candidates[0] if candidates else None


def unique_input_names(devices: Sequence[Mapping], default_hostapi: Optional[int] = None) -> List[str]:
    """Each microphone name once, in a stable order (default interface first). Truncated MME names are
    left out when the full name is also listed."""
    names: List[str] = []
    ordered = sorted(input_indices(devices), key=lambda i: (devices[i].get("hostapi") != default_hostapi, i))
    all_names = [str(devices[i]["name"]) for i in ordered]
    for name in all_names:
        if name in names:
            continue
        if any(other != name and other.lower().startswith(name.strip().lower()) and len(name) >= _TRUNCATED_MIN
               for other in all_names):
            continue  # a truncated MME copy; the full name is in the list
        names.append(name)
    return names
