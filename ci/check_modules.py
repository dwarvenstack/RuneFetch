#!/usr/bin/env python3
"""
Import every RuneFetch module.

There is no test suite, so this is the cheapest available guard against syntax
errors, bad imports, and import-time exceptions reaching a release. app.py is
excluded on purpose: importing it is safe, but it is the module whose __main__
opens a window, so we only compile-check it.
"""

import importlib
import pathlib
import py_compile
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PACKAGES = ["core", "downloaders", "utils"]


def main() -> int:
    failures = []

    for package in PACKAGES:
        pkg_dir = ROOT / package
        if not pkg_dir.is_dir():
            print(f"FAIL  package directory missing: {package}")
            failures.append(package)
            continue

        for path in sorted(pkg_dir.glob("*.py")):
            module = f"{package}.{path.stem}"
            try:
                importlib.import_module(module)
                print(f"OK    {module}")
            except Exception as exc:
                print(f"FAIL  {module} -> {type(exc).__name__}: {exc}")
                failures.append(module)

    # app.py: compile only — importing it is fine, but keep CI away from the
    # module that owns window creation.
    try:
        py_compile.compile(str(ROOT / "app.py"), doraise=True)
        print("OK    app.py (compiled)")
    except Exception as exc:
        print(f"FAIL  app.py -> {exc}")
        failures.append("app.py")

    if failures:
        print(f"\n{len(failures)} module(s) failed: {', '.join(failures)}")
        return 1

    print("\nAll project modules import cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
