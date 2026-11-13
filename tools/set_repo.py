"""Write the GitHub repository ("owner/name") into vct/build_info.py.

Usage: python tools/set_repo.py owner/name      (the release workflow does this automatically)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vct.updater import is_valid_repo  # noqa: E402


def main() -> int:
    repo = sys.argv[1] if len(sys.argv) > 1 else ""
    if not is_valid_repo(repo):
        print("usage: python tools/set_repo.py owner/name")
        return 1
    target = Path(__file__).resolve().parent.parent / "vct" / "build_info.py"
    target.write_text(
        '"""Set at build time by tools/set_repo.py (CI does it from the GitHub repository name)."""\n'
        f'REPO = "{repo}"  # "owner/name" of the GitHub repository that publishes the releases\n',
        encoding="utf-8")
    print(f"update repository set to {repo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
