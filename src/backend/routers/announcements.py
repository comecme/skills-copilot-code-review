"""
Announcement endpoints for the High School Management System API
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementPayload(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    expiration_date: date
    start_date: Optional[date] = None

    @field_validator("message")
    @classmethod
    def sanitize_message(cls, value: str) -> str:
        sanitized = " ".join(value.strip().split())
        if not sanitized:
            raise ValueError("Message cannot be empty")
        return sanitized

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_date and self.start_date > self.expiration_date:
            raise ValueError("Start date must be on or before expiration date")
        return self


class AnnouncementResponse(BaseModel):
    id: str
    message: str
    expiration_date: str
    start_date: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[str] = None


class AnnouncementListResponse(BaseModel):
    announcements: List[AnnouncementResponse]


def _require_signed_in(teacher_username: Optional[str]) -> Dict[str, Any]:
    if not teacher_username:
        raise HTTPException(status_code=401, detail="Authentication required")

    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")

    return teacher


def _to_response_model(document: Dict[str, Any]) -> AnnouncementResponse:
    return AnnouncementResponse(
        id=document["_id"],
        message=document["message"],
        expiration_date=document["expiration_date"],
        start_date=document.get("start_date"),
        created_by=document.get("created_by"),
        created_at=document.get("created_at")
    )


@router.get("", response_model=AnnouncementListResponse)
@router.get("/", response_model=AnnouncementListResponse)
def list_announcements(
    include_inactive: bool = False,
    teacher_username: Optional[str] = Query(None)
) -> AnnouncementListResponse:
    """List announcements. By default, returns only currently active announcements."""
    query: Dict[str, Any] = {}

    if include_inactive:
        _require_signed_in(teacher_username)
    else:
        today = date.today().isoformat()
        query = {
            "expiration_date": {"$gte": today},
            "$or": [
                {"start_date": {"$exists": False}},
                {"start_date": None},
                {"start_date": {"$lte": today}}
            ]
        }

    results = []
    for announcement in announcements_collection.find(query).sort("expiration_date", 1):
        results.append(_to_response_model(announcement))

    return AnnouncementListResponse(announcements=results)


@router.post("", response_model=AnnouncementResponse)
@router.post("/", response_model=AnnouncementResponse)
def create_announcement(
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None)
) -> AnnouncementResponse:
    """Create a new announcement. Requires authentication."""
    teacher = _require_signed_in(teacher_username)

    document = {
        "_id": str(uuid4()),
        "message": payload.message,
        "expiration_date": payload.expiration_date.isoformat(),
        "start_date": payload.start_date.isoformat() if payload.start_date else None,
        "created_by": teacher["_id"],
        "created_at": datetime.utcnow().isoformat()
    }

    announcements_collection.insert_one(document)
    return _to_response_model(document)


@router.put("/{announcement_id}", response_model=AnnouncementResponse)
def update_announcement(
    announcement_id: str,
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None)
) -> AnnouncementResponse:
    """Update an existing announcement. Requires authentication."""
    _require_signed_in(teacher_username)

    existing = announcements_collection.find_one({"_id": announcement_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Announcement not found")

    update_document = {
        "message": payload.message,
        "expiration_date": payload.expiration_date.isoformat(),
        "start_date": payload.start_date.isoformat() if payload.start_date else None,
    }

    announcements_collection.update_one(
        {"_id": announcement_id},
        {"$set": update_document}
    )

    updated = announcements_collection.find_one({"_id": announcement_id})
    return _to_response_model(updated)


@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, str]:
    """Delete an announcement. Requires authentication."""
    _require_signed_in(teacher_username)

    result = announcements_collection.delete_one({"_id": announcement_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
