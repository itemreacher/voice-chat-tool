"""Copy the licence texts of the bundled NVIDIA libraries next to the program (GPU build).

Usage: python tools/copy_licenses.py <folder of the built program>
Looks at the NVIDIA wheels installed in the build environment and writes
<program>/licenses/nvidia/<package>/<file>.
"""
import shutil
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python tools/copy_licenses.py <program folder>")
        return 1
    program = Path(sys.argv[1])
    site = next(p for p in map(Path, sys.path) if (p / "nvidia").is_dir()) if any(
        (Path(p) / "nvidia").is_dir() for p in sys.path) else None
    if site is None:
        print("no NVIDIA packages installed: nothing to copy")
        return 0
    count = 0
    for dist_info in sorted(site.glob("nvidia_*.dist-info")):
        for lic in (dist_info / "licenses").glob("*"):
            if lic.is_file():
                target = program / "licenses" / "nvidia" / dist_info.name.replace(".dist-info", "")
                target.mkdir(parents=True, exist_ok=True)
                shutil.copy2(lic, target / lic.name)
                count += 1
    print(f"copied {count} NVIDIA licence files to {program / 'licenses' / 'nvidia'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
