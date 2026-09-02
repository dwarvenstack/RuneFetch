#!/usr/bin/env python3
"""
Smoke-test the update system.

Version comparison is the part that must not be wrong: a bad comparison either
hides a release from every user or puts the whole install base into an update
loop. The offline checks below are the important ones and always run. The live
GitHub check is best-effort, so CI does not fail because of rate limiting or a
network blip on the runner.
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def check_version_source() -> list:
    """VERSION file must exist and match what the app reports."""
    failures = []
    from core.version import __version__, parse

    version_file = ROOT / "VERSION"
    if not version_file.exists():
        print("FAIL  VERSION file is missing")
        return ["version_file"]

    on_disk = version_file.read_text(encoding="utf-8").strip()
    if on_disk != __version__:
        print(f"FAIL  VERSION says {on_disk!r} but core.version reports {__version__!r}")
        failures.append("version_mismatch")
    else:
        print(f"OK    VERSION = {__version__}")

    if parse(__version__) == (0, 0, 0):
        print(f"FAIL  version {__version__!r} does not parse to a real version")
        failures.append("version_parse")

    return failures


def check_no_hardcoded_versions() -> list:
    """
    Guard against the drift that already happened once: the version was pasted
    into four files and bridge.py silently kept reporting 1.0.0 through the
    entire v2 migration.
    """
    import re

    failures = []
    pattern = re.compile(r'["\'](\d+\.\d+\.\d+)["\']')
    targets = [
        ROOT / "app.py",
        ROOT / "core" / "ui_server.py",
        ROOT / "core" / "bridge.py",
    ]

    for path in targets:
        if not path.exists():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "version" not in line.lower():
                continue
            # core/version.py's _FALLBACK is the one legitimate literal.
            if "_FALLBACK" in line:
                continue
            match = pattern.search(line)
            if match:
                rel = path.relative_to(ROOT)
                print(f"FAIL  hardcoded version {match.group(1)} at {rel}:{lineno}")
                failures.append(f"{rel}:{lineno}")

    if not failures:
        print("OK    no hardcoded version strings")
    return failures


def check_comparison() -> list:
    """The comparison table that decides whether users are offered an update."""
    from core.version import is_newer

    cases = [
        # (candidate, current, expected)
        ("2.0.1",        "2.0.0", True),
        ("2.1.0",        "2.0.0", True),
        ("3.0.0",        "2.0.0", True),
        ("2.0.0",        "2.0.0", False),   # same version: never re-offer
        ("1.9.9",        "2.0.0", False),   # older: never downgrade
        ("v2.0.1",       "2.0.0", True),    # tags carry a leading v
        ("2.0.1-beta.1", "2.0.0", True),    # pre-release suffix
        ("2.10.0",       "2.9.0", True),    # 10 > 9 numerically, not as a string
        ("2.0",          "2.0.0", False),   # short form pads to 2.0.0
        ("garbage",      "2.0.0", False),   # malformed upstream tag must not offer
        ("",             "2.0.0", False),
    ]

    failures = []
    for candidate, current, expected in cases:
        actual = is_newer(candidate, current)
        if actual == expected:
            print(f"OK    is_newer({candidate!r}, {current!r}) = {actual}")
        else:
            print(f"FAIL  is_newer({candidate!r}, {current!r}) = {actual}, want {expected}")
            failures.append(f"{candidate}>{current}")
    return failures


def check_throttle() -> list:
    """The startup check must not hit the API on every launch."""
    import time
    from core import updater

    failures = []
    now = int(time.time())
    cases = [
        ({},                                   True,  "no prior check"),
        ({"last_update_check": now},           False, "checked just now"),
        ({"last_update_check": now - 2*86400}, True,  "checked 2 days ago"),
        ({"last_update_check": "garbage"},     True,  "corrupt value"),
    ]
    for cfg, expected, label in cases:
        actual = updater._due_for_check(cfg)
        if actual == expected:
            print(f"OK    throttle: {label} -> {actual}")
        else:
            print(f"FAIL  throttle: {label} -> {actual}, want {expected}")
            failures.append(label)
    return failures


def check_live_api():
    """Best-effort: confirm the Releases API is reachable and parses."""
    from core import updater
    try:
        info = updater.check_for_update(force=True, cfg={})
    except Exception as exc:
        print(f"WARN  live check raised {type(exc).__name__}: {exc}")
        return

    if info.get("error") in ("network", "http_403", "http_429"):
        print(f"WARN  live check unavailable ({info['error']}) — skipping")
        return

    print(f"OK    live check: latest={info.get('version') or 'none'} "
          f"current={info.get('current')} available={info.get('available')}")


def main() -> int:
    failures = []
    print("── Version source ──")
    failures += check_version_source()
    print("\n── Hardcoded versions ──")
    failures += check_no_hardcoded_versions()
    print("\n── Version comparison ──")
    failures += check_comparison()
    print("\n── Check throttling ──")
    failures += check_throttle()
    print("\n── Live GitHub API (best effort) ──")
    check_live_api()

    if failures:
        print(f"\nUpdate system check failed: {', '.join(failures)}")
        return 1

    print("\nUpdate system OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
