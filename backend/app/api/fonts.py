"""Catalog of bundled fonts for subtitles/watermark text — shared by the
Timeline Editor (overlay track) and the burned-in subtitle flow (burn_subtitles).
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
    """Return the .ttf file so the frontend can preview the font via `@font-face` before rendering."""
    try:
        font = font_service.get_font(font_id)
    except font_service.FontNotFoundError:
        raise HTTPException(status_code=404, detail="Không tìm thấy font") from None
    return FileResponse(font_service.resolve_fontfile(font_id), filename=font.regular_file)
