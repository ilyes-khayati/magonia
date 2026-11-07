import pytest

from engine.route import glossary, route

AREAS = ["Orchard", "olive-jendouba-polygon"]


@pytest.mark.parametrize(
    "question, kind",
    [
        ("Hello, who are you?", "chat"),
        ("thanks!", "chat"),
        ("What is known about drought and olive NDVI in the Mediterranean?", "research"),
        ("Which studies forecast NDVI with machine learning?", "research"),
        ("What did Smith and Jones (2023) find about SAVI?", "research"),
        ("When does NDVI peak in my orchard, and how low does it go?", "data"),
        ("What were the monthly NDVI values of my orchard in 2012?", "data"),
        ("Is the Orchard drier than usual?", "data"),
        ("What is SAVI?", "method"),
        ("Explain the difference between NDVI and EVI", "method"),
        ("What hyperparameters should I try for Random Forest and XGBoost?", "method"),
        ("no don't propose anything, just give me a list of hyperparameters", "method"),
        # two kinds at once, or none: everything, as before routing
        ("Do studies agree with what my orchard shows?", "general"),
        ("Does NDVI fall in drought?", "general"),
        ("What does drought do to olive NDVI?", "general"),
    ],
)
def test_questions_are_routed_by_kind(question, kind):
    assert route(question, AREAS, has_view=True) == kind


def test_without_a_workspace_nothing_is_about_the_data():
    assert route("When does NDVI peak in my orchard?", [], has_view=False) == "general"


def test_the_glossary_comes_from_the_catalogue():
    said = glossary("what is ndmi, and how is it different from rainfall?")
    assert "NDMI (MODIS Terra MOD09A1" in said and "Rainfall (ERA5-Land" in said
    assert "Random Forest:" in glossary("how deep should a random forest be?")
    assert glossary("hello") == ""


def test_how_well_a_product_works_is_a_literature_question():
    assert route("What are the limits of MODIS NDVI at 250 m for small fields?") == "research"
    assert route("How accurate is SPEI for olive drought?") == "research"


def test_short_follow_ups_are_recognised():
    from engine.route import follows

    assert follows("And in Tunisia?")
    assert follows("What about forests?")
    assert not follows("What do studies say about drought and olive NDVI in Tunisia since 2010?")
