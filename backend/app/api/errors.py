"""统一错误处理，所有错误响应对齐设计文档 §7.1 的错误体结构。"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# 使用字面量 422，避免不同 Starlette 版本对状态常量命名的差异
HTTP_422_UNPROCESSABLE = 422


class APIError(HTTPException):
    """带业务错误码的 HTTP 异常。"""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        detail: dict | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message
        self.detail = detail or {}


def _body(code: str, message: str, detail: dict | None = None) -> dict:
    return {"code": code, "message": message, "detail": detail or {}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def _handle_api_error(_: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(exc.code, exc.message, exc.detail),
        )

    @app.exception_handler(HTTPException)
    async def _handle_http_error(_: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(f"HTTP_{exc.status_code}", str(exc.detail)),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=HTTP_422_UNPROCESSABLE,
            content=_body(
                "VALIDATION_ERROR",
                "请求参数校验失败",
                {"errors": jsonable_encoder(exc.errors())},
            ),
        )
