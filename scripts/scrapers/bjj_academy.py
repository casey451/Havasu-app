from __future__ import annotations

from db.activities import ActivityInput, SlotInput


def scrape_bjj_academy() -> list[ActivityInput]:
    return [
        ActivityInput(
            title="BJJ Evening Class",
            location="Havasu BJJ Academy",
            activity_type="schedule",
            category="fitness",
            tags=["fitness", "martial arts", "training"],
            source="scraped",
            status="approved",
            description="All-level evening class.",
            time_slots=[
                SlotInput(start_time="17:30:00", end_time="19:00:00", day_of_week=d, recurring=True)
                for d in range(0, 5)
            ],
        ),
        ActivityInput(
            title="No-Gi Fundamentals",
            location="Havasu BJJ Academy",
            activity_type="schedule",
            category="fitness",
            tags=["fitness", "training", "nogi", "beginner"],
            source="scraped",
            status="approved",
            description="Foundations-focused no-gi training.",
            time_slots=[
                SlotInput(start_time="12:00:00", end_time="13:00:00", day_of_week=1, recurring=True),
                SlotInput(start_time="12:00:00", end_time="13:00:00", day_of_week=3, recurring=True),
            ],
        ),
        ActivityInput(
            title="Saturday Open Mat",
            location="Havasu BJJ Academy",
            activity_type="schedule",
            category="fitness",
            tags=["fitness", "open mat", "training", "community"],
            source="scraped",
            status="approved",
            description="Open training mat for all affiliations.",
            time_slots=[
                SlotInput(start_time="10:00:00", end_time="12:00:00", day_of_week=5, recurring=True),
            ],
        ),
    ]
