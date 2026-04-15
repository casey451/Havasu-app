from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.activities import SlotInput, replace_time_slots, upsert_activity
from db.database import init_db


def iso_for(days_from_today: int) -> str:
    return (date.today() + timedelta(days=days_from_today)).isoformat()


def main() -> None:
    init_db()

    seeded = [
        (
            "Aquatic Center Open Swim",
            "Lake Havasu Aquatic Center",
            "schedule",
            "kids",
            ["kids", "swim", "family", "water"],
            [
                SlotInput(start_time="12:00:00", end_time="16:00:00", day_of_week=5, recurring=True),
            ],
        ),
        (
            "Altitude Open Jump",
            "Altitude Trampoline Park",
            "schedule",
            "kids",
            ["kids", "indoor", "activity", "family"],
            [
                SlotInput(start_time="11:00:00", end_time="19:00:00", day_of_week=d, recurring=True)
                for d in range(7)
            ],
        ),
        (
            "BJJ Evening Class",
            "Havasu BJJ Academy",
            "schedule",
            "fitness",
            ["fitness", "martial arts", "training"],
            [
                SlotInput(start_time="17:30:00", end_time="19:00:00", day_of_week=d, recurring=True)
                for d in range(0, 5)
            ],
        ),
        (
            "Jet Ski Race Weekend",
            "London Bridge Beach",
            "event",
            "events",
            ["events", "water", "weekend"],
            [SlotInput(start_time="10:00:00", end_time="15:00:00", date=iso_for(4), recurring=False)],
        ),
        (
            "Sunset Boat Party",
            "Bridgewater Channel",
            "event",
            "nightlife",
            ["nightlife", "party", "sunset", "water"],
            [SlotInput(start_time="18:00:00", end_time="21:00:00", date=iso_for(2), recurring=False)],
        ),
        (
            "Downtown Car Meet",
            "Main Street",
            "event",
            "events",
            ["events", "cars", "community"],
            [SlotInput(start_time="19:00:00", end_time="22:00:00", date=iso_for(8), recurring=False)],
        ),
        (
            "Farmers Market",
            "Havasu Community Center",
            "schedule",
            "events",
            ["events", "market", "family", "outdoor"],
            [
                SlotInput(start_time="08:00:00", end_time="12:00:00", day_of_week=5, recurring=True),
                SlotInput(start_time="08:00:00", end_time="12:00:00", day_of_week=6, recurring=True),
            ],
        ),
        (
            "Kids Soccer Camp",
            "Rotary Park",
            "event",
            "kids",
            ["kids", "fitness", "sports", "training"],
            [SlotInput(start_time="09:00:00", end_time="12:00:00", date=iso_for(11), recurring=False)],
        ),
    ]

    created = 0
    for title, location, activity_type, category, tags, slots in seeded:
        activity_id = upsert_activity(
            title=title,
            location=location,
            activity_type=activity_type,
            category=category,
            tags=tags,
            source="seed",
            status="approved",
            description=f"Seeded {activity_type} data for discover realism.",
        )
        replace_time_slots(activity_id, slots)
        created += 1

    print(f"seeded_activities={created}")
    print("approvals_succeeded=yes")


if __name__ == "__main__":
    main()
