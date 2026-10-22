"""工作台草稿接口：同一账号在任意设备恢复画布拓扑。"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import APIError
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.workspace import WorkspaceDraft
from app.schemas.workspace import DraftResponse, DraftSaveRequest

router = APIRouter(prefix="/workspace", tags=["workspace"])

MAX_NODES = 200
MAX_EDGES = 400


@router.get("/draft", response_model=DraftResponse, summary="读取画布草稿")
def get_draft(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DraftResponse:
    draft = db.scalar(
        select(WorkspaceDraft).where(WorkspaceDraft.user_id == current_user.id)
    )
    if draft is None:
        return DraftResponse()
    return DraftResponse(graph=draft.graph, updated_at=draft.updated_at)


@router.put("/draft", response_model=DraftResponse, summary="保存画布草稿")
def save_draft(
    payload: DraftSaveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DraftResponse:
    if len(payload.nodes) > MAX_NODES or len(payload.edges) > MAX_EDGES:
        raise APIError(
            status.HTTP_400_BAD_REQUEST,
            "DRAFT_TOO_LARGE",
            "草稿节点或连线数量超出限制",
        )

    graph = {
        "nodes": payload.nodes,
        "edges": payload.edges,
        "savedAt": payload.saved_at or datetime.now(UTC).isoformat(),
    }

    draft = db.scalar(
        select(WorkspaceDraft).where(WorkspaceDraft.user_id == current_user.id)
    )
    if draft is None:
        draft = WorkspaceDraft(user_id=current_user.id, graph=graph)
        db.add(draft)
    else:
        draft.graph = graph

    db.commit()
    db.refresh(draft)
    return DraftResponse(graph=draft.graph, updated_at=draft.updated_at)
