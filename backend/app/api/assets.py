"""Quản lý file dùng chung cho dựng video (logo, intro/outro, nhạc nền).

Hai đường nhập: upload qua HTTP (bản web) và nhập từ đường dẫn có sẵn trên máy
(bản desktop — người dùng chọn file bằng hộp thoại hệ điều hành, không cần đẩy
cả file 500 MB qua HTTP).
"""

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.services import asset_service

router = APIRouter(prefix="/api/assets", tags=["assets"])


class AssetRead(BaseModel):
    id: str
    name: str
    kind: str
    path: str
    size: int


class ImportRequest(BaseModel):
    path: str


def _to_read(asset: asset_service.Asset) -> AssetRead:
    return AssetRead(id=asset.id, name=asset.name, kind=asset.kind, path=asset.path, size=asset.size)


@router.get("", response_model=list[AssetRead])
def list_assets(kind: str | None = None) -> list[AssetRead]:
    return [_to_read(a) for a in asset_service.list_assets(kind)]


@router.post("", response_model=AssetRead, status_code=201)
async def upload_asset(file: UploadFile = File(...)) -> AssetRead:
    try:
        asset = asset_service.save_asset(file.filename or "asset", await file.read())
    except asset_service.AssetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _to_read(asset)


@router.post("/import", response_model=AssetRead, status_code=201)
def import_asset(payload: ImportRequest) -> AssetRead:
    try:
        asset = asset_service.import_from_path(payload.path)
    except asset_service.AssetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _to_read(asset)


@router.get("/{asset_id}/file")
def download_asset(asset_id: str) -> FileResponse:
    """Trả file để frontend xem trước (ảnh logo, nghe thử nhạc nền)."""
    asset = asset_service.get_asset(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy asset")
    return FileResponse(asset.path, filename=asset.name)


@router.delete("/{asset_id}")
def delete_asset(asset_id: str) -> dict[str, bool]:
    if not asset_service.delete_asset(asset_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy asset")
    return {"deleted": True}
