"""Admin endpoints for the public-register lifecycle.

Two equally-valid auth paths:
1. Logged-in session whose email matches ADMIN_EMAIL env.
2. X-Admin-Token header matching ADMIN_TOKEN env (curl-friendly).
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth import User, get_current_user

router = APIRouter()


async def require_admin(
    request: Request,
    user: Optional[User] = Depends(get_current_user),
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
) -> None:
    """Pass-through dependency that 401/403s when caller is not admin."""
    # Token-path
    expected_token = os.environ.get("ADMIN_TOKEN", "").strip()
    if x_admin_token is not None:
        if expected_token and x_admin_token == expected_token:
            return
        raise HTTPException(status_code=403, detail="invalid admin token")
    # Session-path
    if user is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="not admin")


class DenyRequest(BaseModel):
    reason: str = Field(..., min_length=10)


class DemoteRequest(BaseModel):
    reason: str = Field(..., min_length=5)


class ApproveRequest(BaseModel):
    comment: Optional[str] = None


def _spot_row_to_dict(row) -> dict:
    (sid, owner_id, lat, lon, label, description, category,
     visibility, public_status, denial_reason, created_at,
     owner_display_name, owner_email) = row
    return {
        "id": sid,
        "lat": lat,
        "lon": lon,
        "label": label,
        "description": description,
        "category": category,
        "visibility": visibility,
        "public_status": public_status,
        "denial_reason": denial_reason,
        "created_at": created_at,
        "owner": {
            "id": owner_id,
            "display_name": owner_display_name,
            "email": owner_email,
        },
    }


@router.get("/api/admin/spots/pending", dependencies=[Depends(require_admin)])
async def list_pending(request: Request):
    db = request.app.state.db
    cur = await db.execute(
        """
        SELECT s.id, s.owner_id, s.lat, s.lon, s.label, s.description,
               s.category, s.visibility, s.public_status, s.denial_reason,
               s.created_at, u.display_name, u.email
        FROM spots s
        JOIN users u ON u.id = s.owner_id
        WHERE s.public_status = 'requested'
        ORDER BY s.created_at ASC
        """
    )
    rows = await cur.fetchall()
    return {"spots": [_spot_row_to_dict(row) for row in rows]}


async def _decider_id(user: Optional[User]) -> Optional[str]:
    return user.id if user else None


@router.post("/api/admin/spots/{spot_id}/approve",
             dependencies=[Depends(require_admin)])
async def approve(
    spot_id: str,
    payload: ApproveRequest,
    request: Request,
    user: Optional[User] = Depends(get_current_user),
):
    db = request.app.state.db
    cur = await db.execute(
        "SELECT public_status FROM spots WHERE id = ?", (spot_id,),
    )
    row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="spot not found")
    if row[0] != "requested":
        raise HTTPException(status_code=409, detail="spot is not pending")
    await db.execute(
        "UPDATE spots SET public_status = 'approved', denial_reason = NULL, "
        "decided_by = ?, decided_at = CURRENT_TIMESTAMP, "
        "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (await _decider_id(user), spot_id),
    )
    await db.commit()
    return {"ok": True}


@router.post("/api/admin/spots/{spot_id}/deny",
             dependencies=[Depends(require_admin)])
async def deny(
    spot_id: str,
    payload: DenyRequest,
    request: Request,
    user: Optional[User] = Depends(get_current_user),
):
    db = request.app.state.db
    cur = await db.execute(
        "SELECT public_status FROM spots WHERE id = ?", (spot_id,),
    )
    row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="spot not found")
    if row[0] != "requested":
        raise HTTPException(status_code=409, detail="spot is not pending")
    await db.execute(
        "UPDATE spots SET visibility = 'private', public_status = 'denied', "
        "denial_reason = ?, decided_by = ?, decided_at = CURRENT_TIMESTAMP, "
        "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (payload.reason, await _decider_id(user), spot_id),
    )
    await db.commit()
    return {"ok": True}


@router.post("/api/admin/spots/{spot_id}/demote",
             dependencies=[Depends(require_admin)])
async def demote(
    spot_id: str,
    payload: DemoteRequest,
    request: Request,
    user: Optional[User] = Depends(get_current_user),
):
    db = request.app.state.db
    cur = await db.execute(
        "SELECT public_status FROM spots WHERE id = ?", (spot_id,),
    )
    row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="spot not found")
    if row[0] != "approved":
        raise HTTPException(status_code=409, detail="spot is not approved")
    await db.execute(
        "UPDATE spots SET visibility = 'private', public_status = 'revoked', "
        "denial_reason = ?, decided_by = ?, decided_at = CURRENT_TIMESTAMP, "
        "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (payload.reason, await _decider_id(user), spot_id),
    )
    await db.commit()
    return {"ok": True}
