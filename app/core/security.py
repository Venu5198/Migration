import hmac
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException

from app.core.config import settings


@dataclass(frozen=True)
class Actor:
    subject: str
    roles: frozenset[str]


def current_actor(authorization: str | None = Header(default=None)) -> Actor:
    if not settings.require_auth():
        return Actor("development", frozenset({"admin", "approver", "executor", "viewer"}))
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            401, detail={"code": "UNAUTHENTICATED", "message": "Bearer token required."}
        )
    token = authorization.removeprefix("Bearer ")
    for entry in filter(None, settings.auth_tokens.split(",")):
        try:
            configured_token, subject, roles = entry.split(":", 2)
        except ValueError:
            continue
        if hmac.compare_digest(token, configured_token):
            return Actor(subject, frozenset(filter(None, roles.split("|"))))
    raise HTTPException(401, detail={"code": "UNAUTHENTICATED", "message": "Invalid bearer token."})


def require_roles(*required: str):
    def check(actor: Actor = Depends(current_actor)) -> Actor:
        if not set(required).intersection(actor.roles):
            raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "Insufficient role."})
        return actor

    return check
