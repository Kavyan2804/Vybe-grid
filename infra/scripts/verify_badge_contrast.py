"""Contrast check for FE_DESIGN badge colors on --surface (#FFFFFF).

Fails the process if any badge color is below WCAG AA 4.5:1 against white.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CSS = ROOT / "dashboard" / "app" / "globals.css"

BADGE_VARS = ("--live", "--forecast", "--simulated", "--baseline")


def _hex_to_rgb(value: str) -> tuple[float, float, float]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def _channel(c: float) -> float:
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(rgb: tuple[float, float, float]) -> float:
    r, g, b = (_channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg: str, bg: str = "#FFFFFF") -> float:
    l1 = _luminance(_hex_to_rgb(fg))
    l2 = _luminance(_hex_to_rgb(bg))
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def main() -> int:
    text = CSS.read_text(encoding="utf-8")
    values = dict(re.findall(r"(--[\w-]+):\s*(#[0-9A-Fa-f]{6})", text))
    failures: list[str] = []
    for var in BADGE_VARS:
        if var not in values:
            failures.append(f"missing {var}")
            continue
        ratio = contrast(values[var], values.get("--surface", "#FFFFFF"))
        print(f"{var} {values[var]} contrast={ratio:.2f}:1")
        if ratio < 4.5:
            failures.append(f"{var} contrast {ratio:.2f} < 4.5")
    if failures:
        print("FAIL:", "; ".join(failures), file=sys.stderr)
        return 1
    print("OK: all badge colors meet 4.5:1 on --surface")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
