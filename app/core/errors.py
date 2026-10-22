from fastapi import Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code, self.message, self.status_code = code, message, status_code


async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}}
    )
