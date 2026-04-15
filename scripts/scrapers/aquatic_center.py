from __future__ import annotations

from db.activities import ActivityInput, SlotInput


def scrape_aquatic_center() -> list[ActivityInput]:
    """Example scraper output (hardcoded simulation for ingestion pipeline)."""
    return [
        ActivityInput(
            title="Aquatic Center Open Swim",
            location="Lake Havasu Aquatic Center",
            activity_type="schedule",
            category="kids",
            tags=["kids", "swim", "family", "water"],
            source="scraped",
            status="approved",
            description="Community open swim block.",
            time_slots=[
                SlotInput(start_time="12:00:00", end_time="16:00:00", day_of_week=5, recurring=True),
            ],
        ),
        ActivityInput(
            title="Aquatic Center Lap Swim",
            location="Lake Havasu Aquatic Center",
            activity_type="schedule",
            category="fitness",
            tags=["fitness", "swim", "training", "water"],
            source="scraped",
            status="approved",
            description="Lap swim lanes available.",
            time_slots=[
                SlotInput(start_time="06:00:00", end_time="09:00:00", day_of_week=d, recurring=True)
                for d in range(0, 5)
            ],
        ),
    ]
