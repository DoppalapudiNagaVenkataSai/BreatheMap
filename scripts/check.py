#!/usr/bin/env python3
"""Run all quality checks: format, lint, mypy, pytest with coverage, repo size."""

import subprocess
import sys


def run_step(name: str, cmd: list[str]) -> bool:
    print(f"\n--- Running: {name} ---")
    res = subprocess.run(cmd, check=False)  # noqa: S603
    if res.returncode != 0:
        print(f"FAILED: {name}")
        return False
    print(f"PASSED: {name}")
    return True


def main() -> int:
    steps = [
        ("Ruff Format Check", [sys.executable, "-m", "ruff", "format", "--check", "."]),
        ("Ruff Lint", [sys.executable, "-m", "ruff", "check", "."]),
        ("Mypy Type Check", [sys.executable, "-m", "mypy", "app"]),
        (
            "Pytest with Coverage",
            [
                sys.executable,
                "-m",
                "pytest",
                "--cov=app",
                "--cov-report=term-missing",
                "--cov-fail-under=85",
            ],
        ),
        ("Repo Size Check", [sys.executable, "scripts/repo_size.py"]),
    ]

    failed = []
    for name, cmd in steps:
        if not run_step(name, cmd):
            failed.append(name)

    print("\n===============================")
    print("Quality Gates Summary:")
    if failed:
        print(f"Failed steps: {', '.join(failed)}")
        return 1

    print("All checks passed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
