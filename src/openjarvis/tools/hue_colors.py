"""Colour maths of the Hue tools: names, #rrggbb <-> CIE xy, kelvin <-> mired.

Pure functions, no bridge access (hue_light uses them to set and show lamps).
"""

from __future__ import annotations

COLORS = {
    "red": "#ff2a1a",
    "orange": "#ff8a1a",
    "yellow": "#ffd21a",
    "green": "#2aff4a",
    "cyan": "#1affe8",
    "blue": "#1a4aff",
    "purple": "#8a2aff",
    "violet": "#8a2aff",
    "pink": "#ff4ab4",
    "magenta": "#ff1aff",
    "white": "#ffffff",
    "warm": "#ffd6a0",
    "warm white": "#ffd6a0",
}
MIRED_PER_KELVIN = 1_000_000  # colour temperature: mired = 1,000,000 / kelvin
CT_RANGE = (153, 500)  # mired range of Hue white lamps (about 6500 K to 2000 K)
WARM_WHITE_BELOW_K = 3200  # HUD colour of a white lamp: warm below, neutral up to
NEUTRAL_WHITE_BELOW_K = 4800  # this, cool above


def _srgb_to_linear(c: float) -> float:
    return ((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92


def _linear_to_srgb(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def hex_to_xy(h: str) -> list[float]:
    """#rrggbb -> CIE xy as the Hue bridge expects it (black gives neutral white)."""
    h = h.lstrip("#")
    r, g, b = (_srgb_to_linear(int(h[i : i + 2], 16) / 255) for i in (0, 2, 4))
    x = r * 0.664511 + g * 0.154324 + b * 0.162028
    y = r * 0.283881 + g * 0.668433 + b * 0.047685
    z = r * 0.000088 + g * 0.072310 + b * 0.986039
    s = x + y + z
    return [round(x / s, 4), round(y / s, 4)] if s > 0 else [0.3227, 0.329]


def xy_to_hex(xy: list[float]) -> str:
    """CIE xy -> #rrggbb at full brightness, for showing a lamp's colour."""
    x, y = xy
    if y <= 0:
        return "#ffffff"
    big_y = 1.0
    big_x, big_z = big_y / y * x, big_y / y * (1 - x - y)
    r = big_x * 1.656492 - big_y * 0.354851 - big_z * 0.255038
    g = -big_x * 0.707196 + big_y * 1.655397 + big_z * 0.036152
    b = big_x * 0.051713 - big_y * 0.121364 + big_z * 1.011530
    m = max(r, g, b, 1e-6)
    return "#" + "".join(
        "%02x" % int(max(0.0, min(1.0, _linear_to_srgb(max(0.0, c / m)))) * 255)
        for c in (r, g, b)
    )


def kelvin_to_mired(kelvin: float) -> int:
    """Colour temperature for the bridge, clamped to what Hue white lamps can do."""
    return max(CT_RANGE[0], min(CT_RANGE[1], round(MIRED_PER_KELVIN / kelvin)))


def white_hex(mired: float) -> str:
    """Approximate display colour of a white lamp at this colour temperature."""
    kelvin = MIRED_PER_KELVIN / max(CT_RANGE[0], mired)
    if kelvin < WARM_WHITE_BELOW_K:
        return "#ffd6a0"
    return "#fff1dc" if kelvin < NEUTRAL_WHITE_BELOW_K else "#e8f0ff"
