from datetime import date

import pandas as pd

from attbacktrader.data.providers.bigquant import (
    BigQuantIndustryProvider,
    BigQuantIndustryQueryWindow,
    bigquant_classifications_from_frame,
    bigquant_memberships_from_component_frame,
)


def test_bigquant_component_frame_collapses_daily_rows_to_membership_intervals() -> None:
    frame = pd.DataFrame(
        [
            {
                "date": "2024-01-02",
                "instrument": "000001.SZ",
                "industry_level1_code": "801780",
                "industry_level1_name": "银行",
                "industry_level2_code": "801781",
                "industry_level2_name": "银行Ⅱ",
                "industry_level3_code": "851111",
                "industry_level3_name": "银行Ⅲ",
            },
            {
                "date": "2024-01-03",
                "instrument": "000001.SZ",
                "industry_level1_code": "801780",
                "industry_level1_name": "银行",
                "industry_level2_code": "801781",
                "industry_level2_name": "银行Ⅱ",
                "industry_level3_code": "851111",
                "industry_level3_name": "银行Ⅲ",
            },
            {
                "date": "2024-01-04",
                "instrument": "000001.SZ",
                "industry_level1_code": "801120",
                "industry_level1_name": "食品饮料",
                "industry_level2_code": "801121",
                "industry_level2_name": "食品饮料Ⅱ",
                "industry_level3_code": "851211",
                "industry_level3_name": "食品饮料Ⅲ",
            },
        ]
    )

    memberships = bigquant_memberships_from_component_frame(frame, source="SW2014")

    assert len(memberships) == 2
    assert memberships[0].symbol == "000001.SZ"
    assert memberships[0].level1_code == "801780.SI"
    assert memberships[0].in_date == date(2024, 1, 2)
    assert memberships[0].out_date == date(2024, 1, 3)
    assert memberships[0].source == "SW2014"
    assert memberships[1].level1_name == "食品饮料"
    assert memberships[1].out_date is None


def test_bigquant_classification_frame_maps_three_levels_with_parent_codes() -> None:
    frame = pd.DataFrame(
        [
            {
                "industry_level1_name": "银行",
                "industry_level1_code": "801780",
                "industry_level2_name": "银行Ⅱ",
                "industry_level2_code": "801781",
                "industry_level3_name": "银行Ⅲ",
                "industry_level3_code": "851111",
            }
        ]
    )

    classifications = bigquant_classifications_from_frame(frame, source="SW2021")

    assert [(item.level, item.index_code) for item in classifications] == [
        (1, "801780.SI"),
        (2, "801781.SI"),
        (3, "851111.SI"),
    ]
    assert classifications[1].parent_code == "801780.SI"
    assert classifications[2].parent_code == "801781.SI"


def test_bigquant_provider_queries_component_with_date_filter_and_source() -> None:
    class FakeResult:
        def df(self):
            return pd.DataFrame(
                [
                    {
                        "date": "2024-01-02",
                        "industry": "sw2014",
                        "instrument": "000001.SZ",
                        "industry_name": "银行",
                        "industry_instrument": "801780",
                        "industry_level1_code": "801780",
                        "industry_level1_name": "银行",
                        "industry_level2_code": "801781",
                        "industry_level2_name": "银行Ⅱ",
                        "industry_level3_code": "851111",
                        "industry_level3_name": "银行Ⅲ",
                    }
                ]
            )

    class FakeDai:
        def __init__(self):
            self.calls = []

        def query(self, sql, filters=None):
            self.calls.append({"sql": sql, "filters": filters})
            return FakeResult()

    fake_dai = FakeDai()
    provider = BigQuantIndustryProvider(
        dai_module=fake_dai,
        window=BigQuantIndustryQueryWindow(start_date=date(2024, 1, 1), end_date=date(2024, 1, 31)),
    )

    memberships = provider.fetch_stock_industry_memberships_for_symbols(["000001.SZ"], source="SW2014")

    assert memberships["000001.SZ"][0].level1_code == "801780.SI"
    assert fake_dai.calls[0]["filters"] == {"date": ["2024-01-01", "2024-01-31"]}
    assert "industry = 'sw2014'" in fake_dai.calls[0]["sql"]
    assert "instrument IN ('000001.SZ')" in fake_dai.calls[0]["sql"]
