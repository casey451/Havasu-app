from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from db.accounts import (
    get_business_by_id,
    list_pending_business_accounts,
    update_business_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/pending-businesses")
def list_pending_businesses() -> list[dict]:
    return list_pending_business_accounts()


@router.post("/approve-business/{business_id}", status_code=status.HTTP_204_NO_CONTENT)
def approve_business(
    business_id: int,
) -> None:
    row = get_business_by_id(business_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Business not found")
    if str(row["role"]) != "business":
        raise HTTPException(status_code=400, detail="Not a business account")
    if not update_business_status(business_id, "approved"):
        raise HTTPException(status_code=500, detail="Update failed")
    logger.info("admin approved business_id=%s", business_id)


@router.post("/reject-business/{business_id}", status_code=status.HTTP_204_NO_CONTENT)
def reject_business(
    business_id: int,
) -> None:
    row = get_business_by_id(business_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Business not found")
    if str(row["role"]) != "business":
        raise HTTPException(status_code=400, detail="Not a business account")
    if not update_business_status(business_id, "rejected"):
        raise HTTPException(status_code=500, detail="Update failed")
    logger.info("admin rejected business_id=%s", business_id)
