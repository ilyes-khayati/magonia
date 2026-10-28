from engine.numbers import check_numbers

FACTS = [
    (
        "NDVI chart",
        "Corn, NDVI: in an average year it peaks in Aug (0.89) and is lowest in Mar (0.35).",
    ),
    ("Correlation 1: NDVI and LST", "Corn: r = -0.15, 312 months, chance band ±0.11."),
    ("reading Corn NDVI 2022", "Corn, NDVI, monthly means in 2022: Mar 0.37, Apr 0.44, May 0.863."),
]


def statuses(answer, sources=FACTS):
    return [(n.text, n.status, n.source) for n in check_numbers(answer, sources)]


def test_numbers_copied_from_the_facts_are_verified_and_linked():
    assert statuses("Corn peaks in August at 0.89 (NDVI chart), lowest 0.35 in March.") == [
        ("0.89", "verified", "NDVI chart"),
        ("0.35", "verified", "NDVI chart"),
    ]


def test_a_number_may_be_rounded_but_not_made_more_precise():
    assert statuses("May was 0.86.") == [("0.86", "verified", "reading Corn NDVI 2022")]
    # 0.9 rounds both 0.89 and 0.863; the closer one is taken as its source
    assert statuses("Around 0.9.") == [("0.9", "verified", "NDVI chart")]
    assert statuses("It peaked at 0.890.") == [("0.890", "unverified", None)]


def test_invented_values_are_flagged():
    # what the model once wrote instead of reading the series
    answer = "2022-01: 0.73\n2022-02: 0.75\n2022-03: 0.37"
    assert statuses(answer) == [
        ("0.73", "unverified", None),
        ("0.75", "unverified", None),
        ("0.37", "verified", "reading Corn NDVI 2022"),
    ]


def test_a_flipped_sign_is_flagged_apart():
    assert statuses("Heat goes with greener crops (r = 0.15).") == [
        ("0.15", "sign", "Correlation 1: NDVI and LST")
    ]
    assert statuses("r = −0.15, inside ±0.11?") == [
        ("−0.15", "verified", "Correlation 1: NDVI and LST"),
        ("0.11", "verified", "Correlation 1: NDVI and LST"),
    ]


def test_dates_citations_and_list_numbers_are_not_measurements():
    answer = "1. In 2022-07 [2] the value was 0.89.\n2. See [1, 3]."
    assert statuses(answer) == [("0.89", "verified", "NDVI chart")]


def test_numbers_inside_names_are_left_alone():
    assert statuses("MOD13Q1 and SPEI-12 agree.", [("ctx", "SPEI-12")]) == [
        ("12", "verified", "ctx")
    ]


def test_positions_point_at_the_number_in_the_answer():
    answer = "Peak 0.89."
    [n] = check_numbers(answer, FACTS)
    assert answer[n.start : n.end] == "0.89"
