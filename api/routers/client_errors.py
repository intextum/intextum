"""Routes for client-side error reporting."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from auth.dependencies import require_user
from logging_config import get_logger
from models.client_errors import ClientErrorReport, ClientErrorReportResponse
from models.user import User

router = APIRouter(prefix="/client-errors")
logger = get_logger(__name__)


@router.post("", response_model=ClientErrorReportResponse)
async def report_client_error(
    report: ClientErrorReport,
    user: User = Depends(require_user),
) -> ClientErrorReportResponse:
    """Accept and log a browser-side error report for operational visibility."""
    logger.error(
        "Client error reported",
        extra={
            "user_sub": user.sub,
            "username": user.username,
            "route_name": report.route_name,
            "href": report.href,
            "error_name": report.name,
            "error_message": report.message,
            "component_stack": report.component_stack,
            "stack": report.stack,
            "user_agent": report.user_agent,
        },
    )
    return ClientErrorReportResponse()
