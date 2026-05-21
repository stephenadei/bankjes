"""Spots: user-contributed Plekjes parallel to public Markers.

This module exposes a FastAPI router with the /api/spots endpoints.
ACL is applied in-query: anonymous see only public+approved spots;
authenticated users additionally see all their own spots (any
visibility/status). The friends-tier is reserved for Z v2.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth import User, get_current_user, require_current_user

router = APIRouter()


CATEGORIES = ("bank", "stoel", "picknicktafel", "krukje", "anders")


class SpotCreate(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    label: str = Field(..., min_length=1, max_length=60)
    description: Optional[str] = Field(default=None, max_length=400)
    category: Optional[str] = Field(default="anders")


class SpotPatch(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=60)
    description: Optional[str] = Field(default=None, max_length=400)
    category: Optional[str] = Field(default=None)


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


@router.post("/api/spots")
async def create_spot(
    payload: SpotCreate,
    request: Request,
    user: User = Depends(require_current_user),
):
    """Create a new spot owned by the authenticated user.

    Defaults to private visibility and 'none' public_status.
    Returns the created spot in the same shape as list_spots.
    """
    if payload.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"invalid category; must be one of {CATEGORIES}")

    db = request.app.state.db
    spot_id = str(uuid.uuid4())
    label = payload.label.strip()
    if not label:
        raise HTTPException(status_code=400, detail="label cannot be empty after strip")

    await db.execute(
        "INSERT INTO spots (id, owner_id, lat, lon, label, description, category) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (spot_id, user.id, payload.lat, payload.lon, label,
         payload.description, payload.category),
    )
    await db.commit()

    # Return the created spot using the same shape as list_spots
    cur = await db.execute(
        """
        SELECT s.id, s.owner_id, s.lat, s.lon, s.label, s.description,
               s.category, s.visibility, s.public_status, s.created_at,
               u.display_name
        FROM spots s
        JOIN users u ON u.id = s.owner_id
        WHERE s.id = ?
        """,
        (spot_id,),
    )
    row = await cur.fetchone()
    return _spot_row_to_dict(row)


def _user_can_see(spot: dict, user: Optional[User]) -> bool:
    """ACL check matching the list-query semantics, applied to one row."""
    if spot["visibility"] == "public" and spot["public_status"] == "approved":
        return True
    if user and spot["owner"]["id"] == user.id:
        return True
    return False


async def _fetch_spot(db, spot_id: str) -> Optional[dict]:
    """Fetch a single spot by id with owner info, or None if not found."""
    cur = await db.execute(
        """
        SELECT s.id, s.owner_id, s.lat, s.lon, s.label, s.description,
               s.category, s.visibility, s.public_status, s.created_at,
               u.display_name
        FROM spots s
        JOIN users u ON u.id = s.owner_id
        WHERE s.id = ?
        """,
        (spot_id,),
    )
    row = await cur.fetchone()
    return _spot_row_to_dict(row) if row else None


@router.get("/api/spots/{spot_id}")
async def get_spot(
    spot_id: str,
    request: Request,
    user: Optional[User] = Depends(get_current_user),
):
    """Fetch a single spot by id.

    - Anonymous: only visible if public + approved.
    - Logged-in: above PLUS their own spots regardless of status.
    """
    spot = await _fetch_spot(request.app.state.db, spot_id)
    if spot is None or not _user_can_see(spot, user):
        raise HTTPException(status_code=404, detail="spot not found")
    return spot


@router.patch("/api/spots/{spot_id}")
async def patch_spot(
    spot_id: str,
    payload: SpotPatch,
    request: Request,
    user: User = Depends(require_current_user),
):
    """Update a spot (label, description, category only).

    Owner-only. Visibility cannot be changed via PATCH.
    """
    db = request.app.state.db
    spot = await _fetch_spot(db, spot_id)
    if spot is None:
        raise HTTPException(status_code=404, detail="spot not found")
    if spot["owner"]["id"] != user.id:
        raise HTTPException(status_code=403, detail="not your spot")

    # Build dynamic UPDATE clause from the present fields
    sets = []
    args: list = []
    if payload.label is not None:
        label = payload.label.strip()
        if not label:
            raise HTTPException(status_code=400, detail="label cannot be empty")
        sets.append("label = ?")
        args.append(label)
    if payload.description is not None:
        sets.append("description = ?")
        args.append(payload.description)
    if payload.category is not None:
        if payload.category not in CATEGORIES:
            raise HTTPException(status_code=400, detail=f"invalid category")
        sets.append("category = ?")
        args.append(payload.category)
    if not sets:
        return spot  # no-op

    sets.append("updated_at = CURRENT_TIMESTAMP")
    args.append(spot_id)
    await db.execute(f"UPDATE spots SET {', '.join(sets)} WHERE id = ?", args)
    await db.commit()
    return await _fetch_spot(db, spot_id)


def _tg_notify_request(spot_label: str, owner_name: str) -> None:
    """Fire-and-forget Telegram ping to Stephen when a public-spot is requested.

    Reads TG_NOTIFY_ON_PUBLIC_REQUEST env (set to "1" in prd). Uses the
    /home/stephen/scripts/notify/tg CLI which already exists in this
    workspace. Failures are swallowed: a missed ping must never block
    the user's submit flow.
    """
    if os.environ.get("TG_NOTIFY_ON_PUBLIC_REQUEST") != "1":
        return
    tg = shutil.which("tg") or "/home/stephen/scripts/notify/tg"
    if not os.path.exists(tg):
        return
    msg = (
        f"🆕 <b>Bankjes — nieuw plekje voor approval</b>\n\n"
        f"<b>{spot_label}</b> door {owner_name}\n"
        f"Open /admin om te reviewen."
    )
    try:
        subprocess.Popen(
            [tg, "send", msg],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
    except Exception:
        # Never let a notification failure block a user request
        pass


@router.post("/api/spots/{spot_id}/request-public")
async def request_public(
    spot_id: str,
    request: Request,
    user: User = Depends(require_current_user),
):
    """Request public listing for a spot.

    Transitions a private spot to public with public_status='requested'.
    Owner-only. Calls _tg_notify_request to ping Stephen for approval.
    """
    db = request.app.state.db
    spot = await _fetch_spot(db, spot_id)
    if spot is None:
        raise HTTPException(status_code=404, detail="spot not found")
    if spot["owner"]["id"] != user.id:
        raise HTTPException(status_code=403, detail="not your spot")
    if spot["public_status"] == "approved":
        raise HTTPException(status_code=409, detail="already approved")

    await db.execute(
        "UPDATE spots SET visibility = 'public', public_status = 'requested', "
        "denial_reason = NULL, decided_by = NULL, decided_at = NULL, "
        "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (spot_id,),
    )
    await db.commit()

    _tg_notify_request(spot["label"], user.display_name)
    return await _fetch_spot(db, spot_id)


@router.post("/api/spots/{spot_id}/revoke-public")
async def revoke_public(
    spot_id: str,
    request: Request,
    user: User = Depends(require_current_user),
):
    """Revoke public listing for a spot.

    Transitions a spot back to private with public_status='revoked'.
    Owner-only.
    """
    db = request.app.state.db
    spot = await _fetch_spot(db, spot_id)
    if spot is None:
        raise HTTPException(status_code=404, detail="spot not found")
    if spot["owner"]["id"] != user.id:
        raise HTTPException(status_code=403, detail="not your spot")

    await db.execute(
        "UPDATE spots SET visibility = 'private', public_status = 'revoked', "
        "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (spot_id,),
    )
    await db.commit()
    return await _fetch_spot(db, spot_id)


@router.delete("/api/spots/{spot_id}")
async def delete_spot(
    spot_id: str,
    request: Request,
    user: User = Depends(require_current_user),
):
    """Delete a spot.

    Owner-only, except admins can delete any spot.
    """
    db = request.app.state.db
    spot = await _fetch_spot(db, spot_id)
    if spot is None:
        raise HTTPException(status_code=404, detail="spot not found")
    if spot["owner"]["id"] != user.id and not user.is_admin:
        raise HTTPException(status_code=403, detail="not your spot")
    await db.execute("DELETE FROM spots WHERE id = ?", (spot_id,))
    await db.commit()
    return {"ok": True}
