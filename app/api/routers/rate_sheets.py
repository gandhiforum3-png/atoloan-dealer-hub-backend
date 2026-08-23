"""
Rate sheet upload: parse a bank's rate sheet PDF for preview.

Nothing is saved to the bank database here — this returns the parsed
extraction so it can be reviewed before a separate confirm/save step
(not built yet) commits it.
"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.dependencies import get_current_user
from app.models.auth import DealerUserOut
from app.services.rate_sheet_service import RateSheetServiceUnavailableError, parse_rate_sheet

router = APIRouter(prefix="/rate-sheets", tags=["rate-sheets"])


@router.post("/upload")
async def upload_rate_sheet(
    file: UploadFile = File(...),
    _current_user: DealerUserOut = Depends(get_current_user),
) -> dict:
    if file.content_type != "application/pdf" and not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="only PDF rate sheets are supported")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="uploaded file is empty")

    try:
        return await parse_rate_sheet(file.filename, content, file.content_type)
    except RateSheetServiceUnavailableError as exc:
        raise HTTPException(
            status_code=502, detail="rate sheet parsing service is currently unavailable"
        ) from exc
