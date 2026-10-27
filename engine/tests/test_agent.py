from engine.assistant import SEARCH_TOOL, Scripted, ToolCall, answer
from engine.literature import LiteratureError, Paper


def paper(surname, year, title="A study"):
    return Paper(
        id="W1",
        title=title,
        authors=[f"A. {surname}"],
        year=year,
        venue="Journal",
        doi=None,
        abstract="An abstract.",
        open_access_url=None,
        cited_by=0,
        countries=["TN"],
    )


class Library:
    """Stands in for OpenAlex and remembers the queries."""

    def __init__(self, *results):
        self.results = list(results)
        self.queries = []

    def __call__(self, query):
        self.queries.append(query)
        return self.results.pop(0) if self.results else []


def ask(provider, question, search):
    return list(answer(provider, [{"role": "user", "content": question}], search=search))


def test_model_searches_then_answers_with_checked_citations():
    model = Scripted(
        ToolCall("search_papers", {"query": "olive drought NDVI"}),
        "Drought lowers olive NDVI [1], mainly in rainfed groves [2].",
    )
    library = Library([paper("Sghaier", 2022), paper("Crespo", 2025)])

    events = ask(model, "What does drought do to olive NDVI?", library)

    assert library.queries == ["olive drought NDVI"]
    assert [e["type"] for e in events][:2] == ["search", "papers"]
    assert [p["n"] for p in events[1]["papers"]] == [1, 2]
    final = events[-1]
    assert final["type"] == "check"
    assert final["cited"] == [1, 2] and final["removed"] == []
    # the model read the numbered papers before answering
    tool_message = model.seen[-1]
    assert tool_message["role"] == "tool" and "[1] Sghaier, 2022" in tool_message["content"]


def test_invented_reference_never_reaches_the_researcher():
    model = Scripted(
        ToolCall("search_papers", {"query": "olive"}),
        "Olive NDVI lags drought by two months [1], as also shown in [5].",
    )
    events = ask(model, "Lag of olive NDVI?", Library([paper("Crespo", 2025)]))

    final = events[-1]
    assert final["removed"] == [5]
    assert "[5]" not in final["text"]
    assert final["text"].endswith("as also shown in.")


def test_answer_from_memory_has_its_citations_removed():
    model = Scripted("Studies show NDVI falls in drought [1][2].")
    events = ask(model, "Does NDVI fall in drought?", Library())

    assert [e["type"] for e in events if e["type"] != "text"] == ["check"]
    assert events[-1]["removed"] == [1, 2]
    assert "[" not in events[-1]["text"]


def test_numbers_continue_across_searches():
    model = Scripted(
        ToolCall("search_papers", {"query": "olive drought"}),
        ToolCall("search_papers", {"query": "olive SPEI lag"}),
        "Both [1] and [3] agree.",
    )
    library = Library([paper("A", 2020), paper("B", 2021)], [paper("C", 2022)])
    events = ask(model, "q", library)

    papers = [e for e in events if e["type"] == "papers"]
    assert [p["n"] for p in papers[1]["papers"]] == [3]
    assert events[-1]["cited"] == [1, 3]


def test_searches_are_limited_then_the_model_must_answer():
    model = Scripted(ToolCall("search_papers", {"query": "again"}))  # would search forever
    library = Library()
    list(answer(model, [{"role": "user", "content": "q"}], search=library, max_searches=2))
    assert len(library.queries) == 2


def test_failed_search_is_reported_and_the_model_still_answers():
    def offline(query):
        raise LiteratureError("Could not reach OpenAlex: no network")

    model = Scripted(ToolCall("search_papers", {"query": "olive"}), "I could not search right now.")
    events = ask(model, "q", offline)

    assert events[0] == {"type": "search", "query": "olive"}
    assert events[1] == {
        "type": "search_failed",
        "query": "olive",
        "error": "Could not reach OpenAlex: no network",
    }
    assert events[-1]["text"] == "I could not search right now."


def test_the_search_tool_is_offered_to_the_model():
    assert SEARCH_TOOL["function"]["name"] == "search_papers"
