# Contributing

Thanks for helping. Short version:

1. Fork, create a branch, make your change.
2. Run the tests: `python -m pytest -q` (needs `pip install -r requirements-test.txt`).
3. Keep OS-specific code (hotkeys, typing, clipboard, sounds) separate from pure logic, so the logic
   stays testable everywhere. New logic needs a test.
4. Open a pull request and describe what changed and how you checked it.

Project rules: offline-first, no accounts or telemetry, only permissively licensed dependencies
(see `THIRD_PARTY_LICENSES.md`), and please do not add a dependency for something the standard
library does well. Never commit personal `config.toml` files or logs (they are ignored by `.gitignore`).

How the code is organised: `docs/ARCHITECTURE.md`. How releases work: `docs/RELEASING.md`.
