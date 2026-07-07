# Copyright (C) 2026 Kristina Quinones
# SPDX-License-Identifier: GPL-2.0-only

"""Per-tenant branding: the product name and an accent color.

The accent color drives a small set of CSS custom properties. One hex does not
fill every token cleanly, so the derivation mirrors the built-in theme: the
button hover is a darkened accent, the ring/border are translucent, and the link
color is nudged until it clears a WCAG-AA contrast floor against the page
background, computed separately for light and dark mode.

Everything the template renders is derived from a *parsed* (r, g, b) triple, so a
malicious ``accent_color`` string can never reach the ``<style>`` block: it
either parses to a color or is dropped entirely.
"""

from __future__ import annotations

import re
from typing import Any

_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

# Page backgrounds the link color is checked against (styles.css --bg-app).
_LIGHT_BG = (247, 248, 250)
_DARK_BG = (15, 17, 21)
_MIN_CONTRAST = 4.5  # WCAG AA for normal text


def parse_hex(value: str | None) -> tuple[int, int, int] | None:
    if not value:
        return None
    candidate = value.strip()
    if not _HEX_RE.match(candidate):
        return None
    digits = candidate[1:]
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    return int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16)


def normalize_hex(value: str | None) -> str | None:
    """Return a canonical ``#rrggbb`` string, or ``None`` if it isn't a valid hex."""
    rgb = parse_hex(value)
    return _to_hex(rgb) if rgb is not None else None


def _to_hex(rgb: tuple[float, float, float]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, round(c))) for c in rgb))


def _mix(rgb, target, t):
    return tuple(rgb[i] + (target[i] - rgb[i]) * t for i in range(3))


def _darken(rgb, t):
    return _mix(rgb, (0, 0, 0), t)


def _lighten(rgb, t):
    return _mix(rgb, (255, 255, 255), t)


def _rgba(rgb, alpha: float) -> str:
    r, g, b = (int(round(c)) for c in rgb)
    return f"rgba({r}, {g}, {b}, {alpha})"


def _channel_luminance(c: float) -> float:
    s = c / 255
    return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4


def _luminance(rgb) -> float:
    r, g, b = (_channel_luminance(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b) -> float:
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _ensure_contrast(fg, background, toward, steps: int = 24):
    """Nudge ``fg`` toward ``toward`` until it clears the contrast floor."""
    current = fg
    for _ in range(steps):
        if _contrast(current, background) >= _MIN_CONTRAST:
            break
        current = _mix(current, toward, 0.08)
    return current


def build_brand_style(accent_color: str | None) -> dict[str, dict[str, str]] | None:
    """Derive the light and dark token overrides, or ``None`` for no/invalid color."""
    rgb = parse_hex(accent_color)
    if rgb is None:
        return None

    light_link = _ensure_contrast(_darken(rgb, 0.14), _LIGHT_BG, (0, 0, 0))
    dark_500 = _lighten(rgb, 0.14)
    dark_link = _ensure_contrast(_lighten(rgb, 0.24), _DARK_BG, (255, 255, 255))

    return {
        "light": {
            "--clay-500": _to_hex(rgb),
            "--clay-600": _to_hex(_darken(rgb, 0.14)),
            "--text-link": _to_hex(light_link),
            "--accent-border": _rgba(rgb, 0.28),
            "--ring": _rgba(rgb, 0.28),
        },
        "dark": {
            "--clay-500": _to_hex(dark_500),
            "--clay-600": _to_hex(_lighten(rgb, 0.04)),
            "--text-link": _to_hex(dark_link),
            "--accent-border": _rgba(dark_500, 0.28),
            "--ring": _rgba(dark_500, 0.28),
        },
    }


def brand_name(user: dict[str, Any] | None) -> str:
    if user and user.get("workspace_name"):
        return user["workspace_name"]
    return "UTM link builder"
