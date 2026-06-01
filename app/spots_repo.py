"""SpotRepository: single source of truth for Spot row-mapping + ACL.

A Spot is a user-contributed Plekje (parallel to a public Marker). Both the
public-facing router (``app.spots``) and the admin router (``app.admin``) read
the same ``spots`` table joined to ``users``, but historically each duplicated
its own ``_spot_row_to_dict`` and inlined the ACL into raw SQL. This module
holds:

- ``SPOT_SELECT_COLUMNS`` / ``ADMIN_SPOT_SELECT_COLUMNS`` — the two column
  projections (admin additionally exposes ``denial_reason`` and the owner's
  email).
- ``spot_row_to_dict`` — one mapper covering both projections.
- ``ACL_VISIBLE_WHERE`` / ``PENDING_WHERE`` — the ACL/listing predicates that
  were previously hand-written in each router's WHERE clause.
- ``user_can_see`` — the row-level mirror of ``ACL_VISIBLE_WHERE``.

Behaviour is identical to the previous inlined versions; this is a pure
extraction.
"""

from __future__ import annotations

from typing import Optional

# --- Column projections ----------------------------------------------------
# Public listing/detail shape (11 columns).
SPOT_SELECT_COLUMNS = (
    "s.id, s.owner_id, s.lat, s.lon, s.label, s.description, "
    "s.category, s.visibility, s.public_status, s.created_at, u.display_name"
)

# Admin shape (13 columns): adds denial_reason and the owner's email.
ADMIN_SPOT_SELECT_COLUMNS = (
    "s.id, s.owner_id, s.lat, s.lon, s.label, s.description, "
    "s.category, s.visibility, s.public_status, s.denial_reason, "
    "s.created_at, u.display_name, u.email"
)

# --- ACL / listing predicates ----------------------------------------------
# Anonymous see public+approved; authenticated additionally see their own
# spots. Parameters are bound positionally as (user_id, user_id).
ACL_VISIBLE_WHERE = (
    "(s.visibility = 'public' AND s.public_status = 'approved') "
    "OR (? IS NOT NULL AND s.owner_id = ?)"
)

# Admin pending queue: spots awaiting a public-listing decision.
PENDING_WHERE = "s.public_status = 'requested'"


def spot_row_to_dict(row, *, admin: bool = False) -> dict:
    """Map a DB row to the API spot dict.

    With ``admin=False`` the row must match ``SPOT_SELECT_COLUMNS``; with
    ``admin=True`` it must match ``ADMIN_SPOT_SELECT_COLUMNS`` (which carries
    the extra ``denial_reason`` column and ``owner.email``).
    """
    if admin:
        (sid, owner_id, lat, lon, label, description, category,
         visibility, public_status, denial_reason, created_at,
         owner_display_name, owner_email) = row
        owner = {
            "id": owner_id,
            "display_name": owner_display_name,
            "email": owner_email,
        }
        extra = {"denial_reason": denial_reason}
    else:
        (sid, owner_id, lat, lon, label, description, category,
         visibility, public_status, created_at, owner_display_name) = row
        owner = {
            "id": owner_id,
            "display_name": owner_display_name,
        }
        extra = {}

    result = {
        "id": sid,
        "lat": lat,
        "lon": lon,
        "label": label,
        "description": description,
        "category": category,
        "visibility": visibility,
        "public_status": public_status,
        **extra,
        "created_at": created_at,
        "owner": owner,
    }
    return result


def user_can_see(spot: dict, user) -> bool:
    """Row-level ACL check mirroring ``ACL_VISIBLE_WHERE``.

    ``user`` is an ``app.auth.User`` or ``None``.
    """
    if spot["visibility"] == "public" and spot["public_status"] == "approved":
        return True
    if user and spot["owner"]["id"] == user.id:
        return True
    return False
