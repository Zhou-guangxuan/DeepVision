"""拓扑校验接口。"""

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.graph import GraphValidationResult, ModelConfigIn
from app.services.graph_validation import validate_model_config

router = APIRouter(prefix="/graph", tags=["graph"])


@router.post(
    "/validate",
    response_model=GraphValidationResult,
    summary="校验网络拓扑结构",
)
def validate_graph(
    payload: ModelConfigIn,
    current_user: User = Depends(get_current_user),
) -> GraphValidationResult:
    """返回 {valid, errors, warnings}。

    errors 表示结构非法（无法训练），warnings 表示结构合法但当前版本不支持。
    """
    return GraphValidationResult(**validate_model_config(payload))
