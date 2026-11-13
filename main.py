import sys
import traceback

from vct.app import _report_error, ensure_std_streams, main


def run() -> int:
    ensure_std_streams()
    try:
        return main()
    except KeyboardInterrupt:
        return 0
    except Exception:
        text = traceback.format_exc()
        print(text)
        _report_error("Unerwarteter Fehler:\n\n" + text[-1500:])
        return 1


if __name__ == "__main__":
    sys.exit(run())
