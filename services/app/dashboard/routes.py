from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(tags=["Dashboard"])

_STATIC_DIR = Path(__file__).resolve().parent / "static"


def _static_file(name: str) -> FileResponse:
    return FileResponse(_STATIC_DIR / name)


@router.get("/dashboard", include_in_schema=False)
def dashboard_page() -> FileResponse:
    return _static_file("index.html")


@router.get("/dashboard/{asset_name}", include_in_schema=False)
def dashboard_asset(asset_name: str) -> FileResponse:
    if asset_name not in {"app.js", "styles.css"}:
        raise HTTPException(status_code=404, detail="Not found")
    return _static_file(asset_name)


@router.get("/wallet/topup/success", include_in_schema=False)
def topup_success() -> FileResponse:
    return _static_file("topup-success.html")


@router.get("/wallet/topup/cancel", include_in_schema=False)
def topup_cancel() -> FileResponse:
    return _static_file("topup-cancel.html")
