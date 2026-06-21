"""Bearer token authentication dependency for worker API endpoints."""

from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from services.worker import WorkerService
from database import get_db
from auth.helpers import unauthorized
from rls import set_rls_context, worker_claim_context

_bearer_scheme = HTTPBearer()


async def require_worker_token(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> str:
    """Validate Bearer token and return worker_id.

    Raises HTTP 401 if the token is missing or invalid.
    Updates last_seen on success.
    """
    service = WorkerService(db=db)
    worker_id = await service.validate_token(credentials.credentials)

    if worker_id is None:
        raise unauthorized("Invalid or revoked worker token")

    await set_rls_context(db, worker_claim_context(worker_id))
    await service.update_last_seen(worker_id)
    return worker_id
