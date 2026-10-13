"""How the interface writes lengths of time and moments (kept from the tests of the older Start an RCA page)."""

from datetime import datetime, timezone

import pytest

from rca.ui import formatting
from rca.ui.strings import t


@pytest.mark.parametrize(
    "value, written",
    [(45, "45 min"), (95, "1 h 35 min"), (120, "2 h"), (None, t("common.unknown"))],
)
def test_a_length_of_time_is_written_the_way_people_say_it(value, written):
    assert formatting.minutes(value) == written


def test_a_moment_is_always_written_in_utc():
    moment = datetime(2026, 7, 14, 14, 32, tzinfo=timezone.utc)
    assert formatting.date_time(moment) == "14 Jul 2026, 14:32 UTC"
