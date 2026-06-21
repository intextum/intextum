"""Models for admin-driven content item imports."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .items import ContentItemInfo


class EmailAttachmentImportRequest(BaseModel):
    """One attachment entry for an imported email message."""

    relative_path: str
    display_name: str | None = None
    size_bytes: int = 0
    external_id: str | None = None
    content_id_header: str | None = None
    disposition: str | None = None
    is_inline: bool = False
    attachment_index: int | None = None
    modified_time: float = 0.0
    change_time: float = 0.0


class EmailMessageImportRequest(BaseModel):
    """Admin/dev request to seed one email message content item."""

    connector_uuid: str
    relative_path: str
    display_name: str | None = None
    external_id: str | None = None
    message_id_header: str | None = None
    thread_id: str | None = None
    subject: str | None = None
    from_name: str | None = None
    from_address: str | None = None
    to_addresses: list[str] = Field(default_factory=list)
    cc_addresses: list[str] = Field(default_factory=list)
    bcc_addresses: list[str] = Field(default_factory=list)
    reply_to_addresses: list[str] = Field(default_factory=list)
    sent_at: datetime | None = None
    received_at: datetime | None = None
    body_text: str | None = None
    body_html: str | None = None
    snippet: str | None = None
    size_bytes: int = 0
    modified_time: float = 0.0
    change_time: float = 0.0
    attachments: list[EmailAttachmentImportRequest] = Field(default_factory=list)


class EmailMessageImportResponse(BaseModel):
    """Response payload for an imported email message."""

    content_item: ContentItemInfo
    attachment_content_item_ids: list[str]
    task_id: str | None = None
