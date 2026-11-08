from engine.assistant import RULES, asks_to_run


def test_asking_to_go_ahead_with_an_analysis_offers_cards():
    # these came back as made-up buttons ("click the Seasonal Plot button") instead of cards
    assert asks_to_run("yes, lets start with seasonal patterns")
    assert asks_to_run("I'd like to proceed, you can give me buttons I can click")
    assert asks_to_run("go with the trend analysis")


def test_questions_and_refusals_offer_none():
    assert not asks_to_run("give me some research about vines in tunisia")
    assert not asks_to_run("what is the trend here?")
    assert not asks_to_run("dont run any analysis, just tell me")


def test_magon_is_told_what_the_interface_has():
    for name in ("Season dates", "Memory and lags", "Pixel purity", "Add analysis", "Board"):
        assert name in RULES
