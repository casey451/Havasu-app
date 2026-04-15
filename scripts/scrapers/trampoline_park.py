from __future__ import annotations

from db.activities import ActivityInput, SlotInput


def scrape_trampoline_park() -> list[ActivityInput]:
    return [
        ActivityInput(
            title="Altitude Open Jump",
            location="Altitude Trampoline Park",
            activity_type="schedule",
            category="kids",
            tags=["kids", "indoor", "activity", "family"],
            source="scraped",
            status="approved",
            description="General open jump sessions.",
            time_slots=[
                SlotInput(start_time="11:00:00", end_time="19:00:00", day_of_week=d, recurring=True)
                for d in range(7)
            ],
        ),
        ActivityInput(
            title="Toddler Bounce Hour",
            location="Altitude Trampoline Park",
            activity_type="schedule",
            category="kids",
            tags=["kids", "toddler", "family", "indoor"],
            source="scraped",
            status="approved",
            description="Safer low-intensity bounce window for younger kids.",
            time_slots=[
                SlotInput(start_time="09:00:00", end_time="10:00:00", day_of_week=d, recurring=True)
                for d in range(0, 5)
            ],
        ),
        ActivityInput(
            title="Friday Night Jump Jam",
            location="Altitude Trampoline Park",
            activity_type="schedule",
            category="nightlife",
            tags=["nightlife", "music", "activity", "group"],
            source="scraped",
            status="approved",
            description="Late jump session with lights and music.",
            time_slots=[
                SlotInput(start_time="19:00:00", end_time="22:00:00", day_of_week=4, recurring=True),
            ],
        ),
    ]
