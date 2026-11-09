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
    assert statuses("In 2022, May was 0.86.") == [("0.86", "verified", "reading Corn NDVI 2022")]
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


def test_digits_in_the_name_of_a_card_are_not_measurements():
    from engine.numbers import check_numbers

    sources = [("Models 4: what the models lean on", "Orchard: XGBoost leans on LST (63%).")]
    answer = (
        "XGBoost leans on LST for 63% [(Models 4: what the models lean on)], as Models 4 shows."
    )
    found = check_numbers(answer, sources)
    assert [(n.text, n.status) for n in found] == [("63", "verified")]


def test_a_year_is_not_marked_as_a_number():
    assert statuses("In 2022 May was 0.86.") == [("0.86", "verified", "reading Corn NDVI 2022")]


AVERAGE_AND_A_YEAR = [
    (
        "NDVI chart",
        "Orchard, NDVI: in an average year it peaks in Mar (0.70) and is lowest in Jul (0.27).",
    ),
    (
        "reading Orchard NDVI 2002",
        "Orchard, NDVI, monthly means in 2002: Jun 0.24, Jul 0.23, Aug 0.25.",
    ),
    (
        "LST chart",
        "Orchard, Land surface temperature (day): in an average year it peaks in Jul (0.23).",
    ),
]


def test_a_number_must_be_found_where_its_sentence_points():
    # the true low of the average year is 0.27; 0.23 is July of 2002, a year the answer never names
    answer = "NDVI goes as low as 0.23 in July."
    assert statuses(answer, AVERAGE_AND_A_YEAR) == [
        ("0.23", "elsewhere", "reading Orchard NDVI 2002")
    ]
    assert statuses("NDVI is lowest in July, at 0.27.", AVERAGE_AND_A_YEAR) == [
        ("0.27", "verified", "NDVI chart")
    ]
    # the year named in the question counts
    asked = [("your question", "How low did NDVI go in 2002?"), *AVERAGE_AND_A_YEAR]
    assert statuses("It went as low as 0.23 in July.", asked) == [
        ("0.23", "verified", "reading Orchard NDVI 2002")
    ]


def test_a_number_of_another_variable_or_month_does_not_count():
    # 0.23 is also an LST value in the sources: an NDVI sentence cannot borrow it
    assert statuses("In an average year NDVI is 0.23 in July.", AVERAGE_AND_A_YEAR[::2]) == [
        ("0.23", "elsewhere", "LST chart")
    ]
    # the right value, but given for another month than the sentence names
    assert statuses("NDVI is lowest in August, at 0.27.", AVERAGE_AND_A_YEAR) == [
        ("0.27", "elsewhere", "NDVI chart")
    ]
