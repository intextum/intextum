"""Download endpoints for assistant-response exports."""

from fastapi import APIRouter, Depends, Response

from auth.dependencies import require_user
from models.exports import AssistantResponseExportRequest
from models.user import User
from services.exports import (
    DOCX_MEDIA_TYPE,
    build_content_disposition,
    build_docx_export,
    sanitize_export_filename_base,
)

router = APIRouter()


@router.post("/docx")
async def export_assistant_response_docx(
    payload: AssistantResponseExportRequest,
    user: User = Depends(require_user),
):
    """Render one assistant response export payload as a DOCX download."""
    _ = user
    filename = f"{sanitize_export_filename_base(payload.filename_base)}.docx"
    return Response(
        content=build_docx_export(payload),
        media_type=DOCX_MEDIA_TYPE,
        headers={"Content-Disposition": build_content_disposition(filename)},
    )
