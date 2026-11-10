from app.period_order import insertion_index, recency_key


def test_present_outranks_dated_end():
    assert recency_key("Jul 2026 - present") > recency_key("Dec 2008 - Mar 2015")


def test_inserts_newest_at_top():
    periods = ["Mar 2020 - Jan 2024", "Dec 2008 - Mar 2015"]
    assert insertion_index(periods, "Jul 2026 - present") == 0


def test_inserts_in_middle():
    periods = ["2020 - present", "2010 - 2015"]
    assert insertion_index(periods, "2016 - 2019") == 1


def test_oldest_goes_last():
    assert insertion_index(["2020 - present", "2010 - 2015"], "2001 - 2005") == 2


def test_unparseable_appends():
    assert insertion_index(["2020 - present"], "sometime") == 1
    assert insertion_index(["2020 - present"], None) == 1


def test_numeric_months():
    assert recency_key("03/2020 - 06/2021") == ((2021, 6), (2020, 3))
