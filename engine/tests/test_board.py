from engine.assistant import Scripted, answer
from engine.board import Pinned, block, check, given


def test_failed_answers_are_never_given_and_items_are_numbered():
    board = [
        Pinned("Trend 1: NDVI", "NDVI fell 0.02 per year", "computed"),
        Pinned("Magon: drought?", "An answer whose checks failed", "failed"),
        Pinned("Note", "I think the orchard was irrigated in 2019", "note"),
    ]
    shown = given(board, "Did NDVI fall?")
    assert [(b.n, b.trust) for b in shown] == [(1, "computed"), (2, "note")]
    text = block(shown)
    assert "[B2] Note (the researcher's own note: quote it as theirs" in text
    assert "checks failed" not in text


def test_a_large_board_gives_the_items_closest_to_the_question():
    board = [Pinned(f"Card {i}", f"rainfall total {i}", "computed") for i in range(12)]
    board.append(Pinned("Lag", "olive NDVI follows SPEI with a two-month lag", "computed"))
    shown = given(board, "What lag between SPEI and olive NDVI?", limit=3)
    assert len(shown) == 3 and any(b.title == "Lag" for b in shown)


def test_citations_to_items_not_given_are_removed():
    shown = given([Pinned("Trend", "NDVI fell", "computed")], "trend")
    text, cited, removed = check("NDVI fell [B1], as your note said [B4].", shown)
    assert text == "NDVI fell [B1], as your note said." and cited == [1] and removed == [4]


def test_magon_cites_the_board_and_cannot_invent_items():
    model = Scripted("Your trend card shows NDVI falling 0.02 per year [B1][B3].")
    board = [Pinned("Trend 1: NDVI", "NDVI fell 0.02 per year since 2010", "computed")]
    events = list(answer(model, [{"role": "user", "content": "Is NDVI falling?"}], board=board))
    assert any(e["type"] == "board" for e in events)
    final = events[-1]
    assert final["board_cited"] == [1] and final["board_removed"] == [3]
    assert "[B3]" not in final["text"]
    assert "[B1] Trend 1: NDVI (computed in this workspace)" in model.seen[-1]["content"]
