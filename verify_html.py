"""
verify_html.py — Integrity checker for Algorithm185History.html
===============================================================
Run after any write to Algorithm185History.html to ensure the file
was not silently truncated (a known issue with the Claude Edit tool
on files >~1,200 lines).

Usage:
    python verify_html.py                          # checks Algorithm185History.html
    python verify_html.py path/to/file.html        # checks a specific file

Exit code 0 = OK, 1 = truncation or missing critical section detected.

Called automatically by update_accuracy.py and update_performance.py.
"""

import sys
from pathlib import Path

# ── Required markers — all must be present for the file to be intact ──────
REQUIRED_MARKERS = [
    ("Allocation data array",    "const ALLOC_DATA = ["),
    ("Strategy classifier",      "function classify(r)"),
    ("Accuracy stats function",  "function computeAccuracyStats()"),
    ("Performance renderer",     "function renderPerformance()"),
    ("Table render function",    "function render()"),
    ("Pagination: gotoPage",     "function gotoPage(p)"),
    ("Growth chart init",        "growthChart"),
    ("Initial paint call",       "applyFilter();"),
    ("HTML closing tag",         "</html>"),
]

# ── Minimum line count ─────────────────────────────────────────────────────
# The file had ~1,307 lines when truncated; full version is ~1,444+.
# Set floor conservatively at 1,350 to catch future truncations early.
MIN_LINES = 1350

def verify(path: Path) -> bool:
    """Return True if file is intact, False if truncated/broken."""
    if not path.exists():
        print(f"❌ File not found: {path}")
        return False

    text = path.read_text(encoding="utf-8")
    lines = text.count("\n")

    ok = True

    # Line count check
    if lines < MIN_LINES:
        print(f"❌ TRUNCATION DETECTED: {path.name} has only {lines} lines "
              f"(expected ≥ {MIN_LINES})")
        ok = False
    else:
        print(f"✅ Line count OK: {lines} lines (≥ {MIN_LINES})")

    # Marker checks
    for label, marker in REQUIRED_MARKERS:
        if marker not in text:
            print(f"❌ MISSING: {label!r}  →  expected to find: {marker!r}")
            ok = False
        else:
            print(f"✅ Found: {label}")

    return ok


def main():
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "Algorithm185History.html"

    print(f"\n🔍 Verifying {target.name} ...")
    print("─" * 60)

    if verify(target):
        print("─" * 60)
        print("✅ All checks passed — file is intact.\n")
        sys.exit(0)
    else:
        print("─" * 60)
        print("❌ INTEGRITY CHECK FAILED")
        print("   The file appears to be truncated or corrupted.")
        print("   Restore from git:  git checkout HEAD -- " + target.name)
        print()
        sys.exit(1)


if __name__ == "__main__":
    main()
