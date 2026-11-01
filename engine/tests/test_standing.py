from engine.assistant import Scripted, answer
from engine.standing import merged, standing_instruction


def test_standing_instructions_are_found_in_the_researchers_words():
    assert standing_instruction("From now on, answer in French") == "Answer in French."
    assert standing_instruction("from now on cite the page of every passage.") == (
        "Cite the page of every passage."
    )
    assert standing_instruction("Make yourself more concise please") == "Be more concise please."
    assert standing_instruction("Always give the period of each study") == (
        "Always give the period of each study."
    )
    assert standing_instruction("never use bullet points") == "Never use bullet points."
    assert standing_instruction("I want you to keep answers under 150 words") == (
        "Keep answers under 150 words."
    )
    assert standing_instruction("Remember to mention the sensor") == "Mention the sensor."
    assert standing_instruction("Thanks, that helps. From now on, compare with Sfax.") == (
        "Compare with Sfax."
    )
    assert standing_instruction("Answer in English only") == "Answer in English only."
    assert standing_instruction("Make yourself more concise, I'm busy") == "Be more concise."
    assert standing_instruction("always cite pages, thanks!") == "Always cite pages."


def test_questions_and_ordinary_requests_are_not_instructions():
    for message in (
        "Can you always cite pages?",
        "What does drought do to olive NDVI?",
        "Add a trend analysis",
        "From now on",
        "always",
        "Is NDVI always lower in July?",
    ):
        assert standing_instruction(message) is None, message


def test_an_instruction_is_added_once():
    assert merged("", "Answer in French.") == "- Answer in French."
    assert merged("- Answer in French.", "answer in french.") == "- Answer in French."
    assert merged("Be brief.", "Cite pages.") == "Be brief.\n- Cite pages."


def test_mago_proposes_the_instruction_and_does_not_claim_to_save_it():
    model = Scripted("Understood: save it below and I will answer in French.")
    events = list(answer(model, [{"role": "user", "content": "From now on, answer in French"}]))
    [proposal] = [e["proposal"] for e in events if e["type"] == "proposal"]
    assert proposal == {
        "kind": "instruction",
        "label": "instruction",
        "title": "Answer in French.",
        "why": "Kept for every question in this workspace; edit it on the Library page.",
        "text": "Answer in French.",
    }
    assert "a button to save it" in model.seen[-1]["content"]
