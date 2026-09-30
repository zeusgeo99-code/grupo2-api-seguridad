#Formato de rrores. se espera la coneccion a la base de datos. 
#400 → BAD_REQUEST
# 401 → UNAUTHORIZED
#403 → FORBIDDEN
#404 → NOT_FOUND
#409 → CONFLICT
#422 → VALIDATION_ERROR
#500 → INTERNAL_ERROR



from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException



# Catálogo de códigos de error (string, no numérico)
class ErrorCode:
    BAD_REQUEST         = "BAD_REQUEST"
    UNAUTHORIZED        = "UNAUTHORIZED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    TOKEN_EXPIRED       = "TOKEN_EXPIRED"
    FORBIDDEN           = "FORBIDDEN"
    NOT_FOUND           = "NOT_FOUND"
    CONFLICT            = "CONFLICT"
    VALIDATION_ERROR    = "VALIDATION_ERROR"
    EMPTY_UPDATE        = "EMPTY_UPDATE"
    INTERNAL_ERROR      = "INTERNAL_ERROR"


DEFAULT_CODES: dict[int, str] = {
    400: ErrorCode.BAD_REQUEST,
    401: ErrorCode.UNAUTHORIZED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND,
    409: ErrorCode.CONFLICT,
    422: ErrorCode.VALIDATION_ERROR,
    500: ErrorCode.INTERNAL_ERROR,
}



#  rutas para lanzar errores con formato uniforme

def api_error(
    status_code: int,
    code: str,
    message: str,
    details: Iterable[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> HTTPException:
   
    return HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": message,
            "details": list(details) if details else [],
        },
        headers=headers,
    )



# Constructor del payload de error--------------------------

def _request_id(request: Request) -> str:
    return (
        request.headers.get("X-Request-ID")
        or request.headers.get("X-Correlation-ID")
        or "desconocido"
    )


def _build_error_payload(
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]],
    request: Request,
) -> dict[str, Any]:
    return {
        "status": status_code,
        "error": {
            "code": code,
            "message": message,
            "details": details,
        },
        "meta": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "path": request.url.path,
            "request_id": _request_id(request),
        },
    }


# ---------------------------------------------------------------------------
# Registro de handlers en la app FastAPI
# ---------------------------------------------------------------------------
def register_error_handlers(app: FastAPI) -> None:
    """ Llamar una sola vez en main"""

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
        detail = exc.detail

        # Caso 1: venimos de api_error() → detail ya es estructurado
        if isinstance(detail, dict) and "code" in detail:
            code    = detail.get("code", DEFAULT_CODES.get(exc.status_code, "HTTP_ERROR"))
            message = detail.get("message", "Error")
            details = detail.get("details", []) or []
        # Caso 2: HTTPException genérica lanzada por FastAPI (p. ej. 404 de rutas)
        else:
            code    = DEFAULT_CODES.get(exc.status_code, "HTTP_ERROR")
            message = str(detail) if detail else "Error"
            details = []

        payload = _build_error_payload(exc.status_code, code, message, details, request)
        return JSONResponse(
            status_code=exc.status_code,
            content=payload,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(request: Request, exc: RequestValidationError):
        details: list[dict[str, Any]] = []
        for err in exc.errors():
            loc = err.get("loc", ())
           
            partes = [str(p) for p in loc if p not in ("body", "query", "path", "header")]
            campo = ".".join(partes) if partes else "body"
            details.append({
                "field": campo,
                "code": str(err.get("type", "invalid")).upper(),
                "message": err.get("msg", "Valor inválido"),
            })

        payload = _build_error_payload(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code=ErrorCode.VALIDATION_ERROR,
            message="Los datos enviados no son válidos",
            details=details,
            request=request,
        )
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=payload)

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception):
        # NO EXPONE INFORMACION ANTE EL USUARIO .
        payload = _build_error_payload(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code=ErrorCode.INTERNAL_ERROR,
            message="Ocurrió un error interno en el servidor",
            details=[],
            request=request,
        )
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=payload)
