"""Collective tide mood for waystation care and room actions."""

from __future__ import annotations

MOOD_RISING = "rising"
MOOD_FALLING = "falling"
MOOD_STILL = "still"


def mood_for_tide(tide: int) -> str:
    if tide >= 40:
        return MOOD_RISING
    if tide <= -40:
        return MOOD_FALLING
    return MOOD_STILL
