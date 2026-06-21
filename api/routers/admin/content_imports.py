"""Admin-only routes for seeding non-file content items during development."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_admin
from database import get_db
from models.content.imports import (
    EmailMessageImportRequest,
    EmailMessageImportResponse,
)
from models.user import User
from services.connector import ConnectorRuntimeService
from services.content import EmailAttachmentInput, ContentService, ingest_email_message

router = APIRouter()


@router.post("/admin/content/import-email", response_model=EmailMessageImportResponse)
async def import_email_message(
    request: EmailMessageImportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Seed one email message and attachment set without a real mail connector."""
    connector = ConnectorRuntimeService(db).get_connector(request.connector_uuid)
    if connector is None:
        raise HTTPException(status_code=400, detail="Unknown data connector")

    result = await ingest_email_message(
        db,
        folder_uuid=connector.uuid,
        relative_path=request.relative_path,
        display_name=request.display_name,
        external_id=request.external_id,
        message_id_header=request.message_id_header,
        thread_id=request.thread_id,
        subject=request.subject,
        from_name=request.from_name,
        from_address=request.from_address,
        to_addresses=request.to_addresses,
        cc_addresses=request.cc_addresses,
        bcc_addresses=request.bcc_addresses,
        reply_to_addresses=request.reply_to_addresses,
        sent_at=request.sent_at,
        received_at=request.received_at,
        body_text=request.body_text,
        body_html=request.body_html,
        snippet=request.snippet,
        size_bytes=request.size_bytes,
        modified_time=request.modified_time,
        change_time=request.change_time,
        attachments=[
            EmailAttachmentInput(
                relative_path=attachment.relative_path,
                display_name=attachment.display_name,
                size_bytes=attachment.size_bytes,
                external_id=attachment.external_id,
                content_id_header=attachment.content_id_header,
                disposition=attachment.disposition,
                is_inline=attachment.is_inline,
                attachment_index=attachment.attachment_index,
                modified_time=attachment.modified_time,
                change_time=attachment.change_time,
            )
            for attachment in request.attachments
        ],
        requested_by_sub=user.sub,
    )

    details = await ContentService(db).get_file_details(
        f"{connector.name}/{request.relative_path}",
        user=user,
    )
    return EmailMessageImportResponse(
        content_item=details,
        attachment_content_item_ids=result.attachment_content_item_ids,
        task_id=result.task_id,
    )
