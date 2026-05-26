"""
Firebase Auth middleware for FastAPI.

Extracts and verifies Firebase ID tokens from the Authorization header.
Provides a FastAPI Depends() injectable that returns the authenticated uid.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from firebase_admin import auth

from app.core.firebase import get_firebase_app

logger = logging.getLogger(__name__)


class AuthenticatedUser:
    """Value object carrying verified user info from Firebase token."""

    __slots__ = ("uid", "email", "name", "picture")

    def __init__(self, uid: str, email: Optional[str], name: Optional[str], picture: Optional[str]):
        self.uid = uid
        self.email = email
        self.name = name
        self.picture = picture

    def __repr__(self) -> str:
        return f"AuthenticatedUser(uid={self.uid!r}, email={self.email!r})"


def _extract_token(request: Request) -> str:
    """Extract Bearer token from Authorization header."""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header. Expected: Bearer <token>",
        )
    return header[7:]


async def get_current_user(request: Request) -> AuthenticatedUser:
    """
    FastAPI dependency that verifies the Firebase ID token and returns
    an AuthenticatedUser.

    Usage in routes:
        @router.get("/example")
        async def example(user: AuthenticatedUser = Depends(get_current_user)):
            uid = user.uid
    """
    # Ensure Firebase app is initialized
    get_firebase_app()

    token = _extract_token(request)
    try:
        decoded = auth.verify_id_token(token)
    except auth.InvalidIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Firebase ID token.",
        )
    except auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firebase ID token has expired. Please re-authenticate.",
        )
    except auth.RevokedIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firebase ID token has been revoked.",
        )
    except Exception as exc:
        logger.exception("Unexpected error verifying Firebase token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token verification failed: {exc}",
        )

    uid = decoded.get("uid", "")
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token does not contain a uid.",
        )

    return AuthenticatedUser(
        uid=uid,
        email=decoded.get("email"),
        name=decoded.get("name"),
        picture=decoded.get("picture"),
    )
