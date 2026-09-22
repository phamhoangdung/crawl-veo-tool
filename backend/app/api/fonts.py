"""Danh mục font đóng gói sẵn cho phụ đề/watermark text — dùng chung cho
Timeline Editor (track overlay) và luồng ghép phụ đề cứng (burn_subtitles).
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.services import font_service

router = APIRouter(prefix="/api/fonts", tags=["fonts"])


class FontRead(BaseModel):
    id: str
    label: str


@router.get("", response_model=list[FontRead])
def list_fonts() -> list[FontRead]:
    return [FontRead(id=f.id, label=f.label) for f in font_service.list_fonts()]


@router.get("/{font_id}/file")
def download_font_file(font_id: str) -> FileResponse:
    """Trả file .ttf để frontend xem trước font bằng `@font-face` trước khi render."""
    try:
        font = font_service.get_font(font_id)
    except font_service.FontNotFoundError:
        raise HTTPException(status_code=404, detail="Không tìm thấy font") from None
    return FileResponse(font_service.resolve_fontfile(font_id), filename=font.regular_file)
