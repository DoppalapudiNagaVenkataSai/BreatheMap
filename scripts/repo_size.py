#!/usr/bin/env python3
"""Check repository size against the 9.5 MB threshold."""

import os
import subprocess
import sys
from pathlib import Path

MAX_BYTES = 9.5 * 1024 * 1024  # 9.5 MB


def get_tracked_files_size() -> tuple[int, list[tuple[int, str]]]:
    """Calculate total size of tracked git files."""
    try:
        output = subprocess.check_output(["/usr/bin/git", "ls-files"], text=True)
    except Exception as e:
        print(f"Error running git ls-files: {e}")
        return 0, []

    files = [f.strip() for f in output.splitlines() if f.strip()]
    total_size = 0
    file_sizes = []

    for f in files:
        path = Path(f)
        if path.is_file():
            size = path.stat().st_size
            total_size += size
            file_sizes.append((size, f))

    file_sizes.sort(key=lambda x: x[0], reverse=True)
    return total_size, file_sizes


def get_dir_size(path: Path) -> int:
    """Calculate size of directory recursively."""
    total = 0
    if not path.exists():
        return 0
    for root, _, files in os.walk(path):
        for f in files:
            fp = Path(root) / f
            if fp.is_file():
                total += fp.stat().st_size
    return total


def main() -> int:
    git_dir = Path(".git")
    git_size = get_dir_size(git_dir)
    tracked_size, largest_files = get_tracked_files_size()
    total_size = git_size + tracked_size

    print("=== BreatheMap Repository Size Check ===")
    print(f"Tracked files size: {tracked_size / (1024 * 1024):.2f} MB")
    print(f".git directory size: {git_size / (1024 * 1024):.2f} MB")
    print(f"Total repository size: {total_size / (1024 * 1024):.2f} MB (Limit: 9.5 MB)")

    print("\nTop 10 largest tracked files:")
    for size, name in largest_files[:10]:
        print(f"  {size / 1024:8.2f} KB  {name}")

    if total_size > MAX_BYTES:
        print("\nFAILURE: Repository size exceeds 9.5 MB limit!")
        return 1

    print("\nSUCCESS: Repository size is well within limits.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
