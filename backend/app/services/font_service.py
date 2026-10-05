"""Catalog of bundled fonts for subtitles/watermark text (drawtext + burn_subtitles).

Uses fonts packaged WITH the source (downloaded from Google Fonts, the OFL license allows
redistribution) instead of probing fonts installed on the OS — behaves the same on
every machine, independent of the user's machine (especially important for the desktop package,
Phase 12: a clean Windows install may lack fonts). All 4 families have the official
"vietnamese" subset on Google Fonts (checked METADATA.pb), meaning the
Vietnamese diacritic glyphs are verified — we do not pick just any basic Latin font because
many fonts lack Vietnamese diacritics entirely even though they seem to support Unicode.
"""

from dataclasses import dataclass
from pathlib import Path

from app.core.config import resource_dir


@dataclass(frozen=True)
class FontOption:
    id: str
    label: str
    # The REAL family name inside the .ttf file (name table) — used for the `FontName` of
    # `force_style` (burn_subtitles/libass), it MUST match exactly so libass recognizes
    # the right font when scanning `fontsdir`, unlike `label` which is the UI display name (may include
    # extra description).
    family_name: str
    regular_file: str
    # None = the font has no separate bold file (e.g. a display font that is already bold) —
    # `resolve_fontfile(bold=True)` will fall back to the regular file.
    bold_file: str | None


_FONTS: list[FontOption] = [
    FontOption("be-vietnam-pro", "Be Vietnam Pro", "Be Vietnam Pro", "BeVietnamPro-Regular.ttf", "BeVietnamPro-Bold.ttf"),
    FontOption("barlow", "Barlow", "Barlow", "Barlow-Regular.ttf", "Barlow-Bold.ttf"),
    FontOption("fira-sans", "Fira Sans", "Fira Sans", "FiraSans-Regular.ttf", "FiraSans-Bold.ttf"),
    FontOption("anton", "Anton (đậm sẵn, kiểu caption)", "Anton", "Anton-Regular.ttf", None),
]

_FONTS_BY_ID = {f.id: f for f in _FONTS}

DEFAULT_FONT_ID = "be-vietnam-pro"


class FontNotFoundError(ValueError):
    pass


def list_fonts() -> list[FontOption]:
    return list(_FONTS)


def get_font(font_id: str) -> FontOption:
    font = _FONTS_BY_ID.get(font_id)
    if font is None:
        raise FontNotFoundError(f"Không có font id {font_id!r}")
    return font


def get_font_or_default(font_id: str | None) -> FontOption:
    """Like `get_font` but does not fail on an empty/unknown id — falls back to the default font.
    Used in the render path (burn_subtitles/drawtext): timelines saved before this
    feature existed have no `font_family` field, and should not break a whole render
    just for lacking 1 optional field."""
    return _FONTS_BY_ID.get(font_id or "", _FONTS_BY_ID[DEFAULT_FONT_ID])


def resolve_fontfile(font_id: str | None, *, bold: bool = False) -> Path:
    """Real .ttf file path on disk for 1 font id + weight. `font_id=None`
    or an id not found falls back to the default font instead of erroring — old timelines
    saved before this feature existed have no `font_family` field."""
    font = get_font_or_default(font_id)
    filename = (font.bold_file if bold else None) or font.regular_file
    return resource_dir() / "fonts" / filename


def fonts_dir() -> Path:
    """Directory containing all font files — used for the `fontsdir` parameter of the
    `subtitles` filter (ffmpeg/libass), so libass finds the bundled fonts without
    probing system fontconfig (avoiding the 'Cannot load default config file' error
    seen with `drawtext`, see the Phase 13 notes)."""
    return resource_dir() / "fonts"
