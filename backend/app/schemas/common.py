"""通用响应结构。"""

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """分页响应，对齐设计文档 §7.1。"""

    items: list[T]
    total: int
    page: int
    page_size: int


class ErrorResponse(BaseModel):
    """统一错误体，对齐设计文档 §7.1。"""

    code: str
    message: str
    detail: dict = {}


class HealthResponse(BaseModel):
    status: str
