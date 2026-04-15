from __future__ import annotations

"""Havasu Parks & Recreation — discovery URLs."""

# Full weekly pool & exercise schedule (Mon–Sun headers, activity/time pairs).
OPEN_SWIM_SCHEDULE_URL = "https://www.lhcaz.gov/parks-recreation/open-swim-schedule"
PICKLEBALL_URL = "https://www.lhcaz.gov/parks-recreation/pickleball"
COMMUNITY_CENTER_URL = "https://www.lhcaz.gov/parks-recreation/community-center"
YOUTH_ATHLETICS_URL = "https://www.lhcaz.gov/parks-recreation/youth-athletics"
PROGRAMS_ACTIVITIES_URL = "https://www.lhcaz.gov/parks-recreation/programs-activities"


def discover_havasu_parks() -> list[str]:
    """Parks & Recreation pages: schedules (recurring) + program landings (program)."""
    return [
        OPEN_SWIM_SCHEDULE_URL,
        PICKLEBALL_URL,
        COMMUNITY_CENTER_URL,
        YOUTH_ATHLETICS_URL,
        PROGRAMS_ACTIVITIES_URL,
    ]
