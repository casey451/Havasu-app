from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ItemType = Literal["event", "recurring", "program"]


class ItemPayload(BaseModel):
    """
    Normalized row stored in `items.payload_json`.

    * **event** — dated calendar items (RiverScene, GoLakeHavasu); may use start_date / end_date.
    * **recurring** — facility schedules (lap swim, open gym): time blocks, often no single start_date;
      use weekday + times; do not coerce a fake calendar date.
    * **program** — long-running or external registration (camps, youth sports); often link-out only.
    """

    model_config = ConfigDict(extra="allow")

    source: str = Field(
        min_length=1,
        description="Crawler source id, e.g. golakehavasu | riverscene | havasu_parks",
    )
    type: ItemType = "event"
    title: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    date_text: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    has_time: bool = False
    has_location: bool = False
    venue_name: str | None = None
    address: str | None = None
    description: str | None = None
    short_description: str | None = None
    source_url: str | None = None
    high_confidence: bool | None = None
    # Recurring schedules: match local "today" without inventing start_date
    weekday: str | None = Field(
        None,
        description="For type=recurring: day name e.g. Monday (any case); used with /schedule/today",
    )
    location_label: str | None = Field(
        None,
        description="Short place name e.g. Aquatic Center (schedules)",
    )
    # Programs: external registration
    external_url: str | None = Field(
        None,
        description="For type=program: primary outlink to RecDesk/CivicRec/etc.",
    )
    item_key: str | None = Field(
        None,
        description="Logical identity; set at storage from compute_item_key(payload).",
    )
    tags: list[str] = Field(default_factory=list)
    category: str | None = None
    trust_score: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Optional persisted trust; usually computed in normalize_item.",
    )

    @field_validator("tags", mode="before")
    @classmethod
    def _default_tags(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        return []

    @field_validator("trust_score", mode="before")
    @classmethod
    def _trust_optional(cls, v: Any) -> float | None:
        if v is None or v == "":
            return None
        return float(v)


# Backward-compatible alias
Event = ItemPayload


def validate_item_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Validate and return JSON-serializable dict; raises on invalid source/type."""
    return ItemPayload.model_validate(data).model_dump(mode="json")


def validate_event_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Same as validate_item_payload; kept for existing crawler imports."""
    return validate_item_payload(data)
