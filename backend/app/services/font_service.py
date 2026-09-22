"""Danh mục font kèm sẵn cho phụ đề/watermark text (drawtext + burn_subtitles).

Dùng font đóng gói CÙNG mã nguồn (tải từ Google Fonts, giấy phép OFL cho phép
đóng gói lại) thay vì dò font cài trên máy hệ điều hành — chạy giống nhau trên
mọi máy, không phụ thuộc máy user (đặc biệt quan trọng cho bản đóng gói desktop,
Phase 12: máy user cài Windows sạch có thể thiếu font). Cả 4 family đều có
subset "vietnamese" chính thức trên Google Fonts (đã kiểm tra METADATA.pb), tức
glyph dấu tiếng Việt đã được kiểm định — không chọn đại font Latin cơ bản vì
nhiều font thiếu hẳn dấu tiếng Việt dù có vẻ hỗ trợ Unicode.
"""

from dataclasses import dataclass
from pathlib import Path

from app.core.config import resource_dir


@dataclass(frozen=True)
class FontOption:
    id: str
    label: str
    # Tên family THẬT bên trong file .ttf (name table) — dùng cho `FontName` của
    # `force_style` (burn_subtitles/libass), PHẢI khớp chữ để libass nhận diện
    # đúng font khi quét `fontsdir`, khác `label` là tên hiển thị UI (có thể có
    # thêm mô tả).
    family_name: str
    regular_file: str
    # None = font không có file đậm riêng (vd font display vốn đã đậm sẵn) —
    # `resolve_fontfile(bold=True)` sẽ tự rơi về file thường.
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
    """Như `get_font` nhưng không lỗi khi id trống/lạ — rơi về font mặc định.
    Dùng ở đường render (burn_subtitles/drawtext): timeline lưu trước khi có
    tính năng này không có field `font_family`, không nên làm hỏng cả lần render
    chỉ vì thiếu 1 field tuỳ chọn."""
    return _FONTS_BY_ID.get(font_id or "", _FONTS_BY_ID[DEFAULT_FONT_ID])


def resolve_fontfile(font_id: str | None, *, bold: bool = False) -> Path:
    """Đường dẫn file .ttf thật trên đĩa cho 1 font id + độ đậm. `font_id=None`
    hoặc không tìm thấy id thì rơi về font mặc định thay vì lỗi — timeline cũ
    lưu trước khi có tính năng này không có field `font_family`."""
    font = get_font_or_default(font_id)
    filename = (font.bold_file if bold else None) or font.regular_file
    return resource_dir() / "fonts" / filename


def fonts_dir() -> Path:
    """Thư mục chứa mọi file font — dùng cho tham số `fontsdir` của filter
    `subtitles` (ffmpeg/libass), để libass tìm đúng font đã đóng gói mà không
    cần dò qua fontconfig hệ thống (tránh lỗi 'Cannot load default config file'
    đã gặp với `drawtext`, xem ghi chú Phase 13)."""
    return resource_dir() / "fonts"
