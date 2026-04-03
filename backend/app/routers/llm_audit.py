import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_password_changed
from app.models.llm_log import LLMLog
from app.models.user import User

router = APIRouter(prefix="/llm-audit", tags=["llm-audit"])


class LLMLogOut(BaseModel):
    id: uuid.UUID
    sync_run_id: uuid.UUID | None
    model: str
    stage: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    duration_ms: int
    created_at: datetime

    model_config = {"from_attributes": True}


class LLMLogDetailOut(LLMLogOut):
    request: dict
    response: dict


@router.get("/logs", response_model=list[LLMLogOut])
def list_llm_logs(
    sync_run_id: uuid.UUID | None = Query(None),
    limit: int = Query(50, le=200),
    current_user: User = Depends(require_password_changed),  # noqa: ARG001
    db: Session = Depends(get_db),
):
    """List LLM call logs, optionally filtered by sync run."""
    q = db.query(LLMLog).order_by(LLMLog.created_at.desc())
    if sync_run_id:
        q = q.filter(LLMLog.sync_run_id == sync_run_id)
    return q.limit(limit).all()


@router.get("/logs/{log_id}", response_model=LLMLogDetailOut)
def get_llm_log(
    log_id: uuid.UUID,
    current_user: User = Depends(require_password_changed),  # noqa: ARG001
    db: Session = Depends(get_db),
):
    """Return a single LLM call log with full request/response payloads."""
    log = db.get(LLMLog, log_id)
    if not log:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Log not found")
    return log
