from __future__ import annotations

from datetime import date

from crawler.sources.riverscene.date_signals import title_implies_seasonal_mismatch


def test_nye_title_with_april_date_is_mismatch() -> None:
    assert title_implies_seasonal_mismatch(
        "Altitude's Noon Year's Eve Balloon Drop",
        date(2026, 4, 14),
    )


def test_nye_title_with_dec31_ok() -> None:
    assert not title_implies_seasonal_mismatch(
        "New Year's Eve Party",
        date(2026, 12, 31),
    )
