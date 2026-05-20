"""Spots: user-contributed Plekjes parallel to public Markers.

This module exposes a FastAPI router with the /api/spots endpoints.
ACL is applied in-query: anonymous see only public+approved spots;
authenticated users additionally see all their own spots (any
visibility/status). The friends-tier is reserved for Z v2.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request

from app.auth import User, get_current_user

router = APIRouter()


def _spot_row_to_dict(row) -> dict:
    (sid, owner_id, lat, lon, label, description, category,
     visibility, public_status, created_at, owner_display_name) = row
    return {
        "id": sid,
        "lat": lat,
        "lon": lon,
        "label": label,
        "description": description,
        "category": category,
        "visibility": visibility,
        "public_status": public_status,
        "created_at": created_at,
        "owner": {
            "id": owner_id,
            "display_name": owner_display_name,
        },
    }


@router.get("/api/spots")
async def list_spots(
    request: Request,
    user: Optional[User] = Depends(get_current_user),
):
    """Return spots visible to the requester.

    - Anonymous: only spots with visibility='public' AND public_status='approved'.
    - Logged-in: above PLUS all own spots regardless of status.
    - Friends tier: schema-prepared but UI-deferred to Z v2.
    """
    db = request.app.state.db
    user_id = user.id if user else None
    cur = await db.execute(
        """
        SELECT s.id, s.owner_id, s.lat, s.lon, s.label, s.description,
               s.category, s.visibility, s.public_status, s.created_at,
               u.display_name
        FROM spots s
        JOIN users u ON u.id = s.owner_id
        WHERE
          (s.visibility = 'public' AND s.public_status = 'approved')
          OR (? IS NOT NULL AND s.owner_id = ?)
        ORDER BY s.created_at DESC
        """,
        (user_id, user_id),
    )
    rows = await cur.fetchall()
    return {"spots": [_spot_row_to_dict(row) for row in rows]}
