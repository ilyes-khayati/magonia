import pytest

from engine.assistant import SEARCH_TOOL, Scripted, ToolCall, answer, tidy, written_calls
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
    assert [e["type"] for e in events][:3] == ["route", "search", "papers"]
    assert [p["n"] for p in events[2]["papers"]] == [1, 2]
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

    assert [e["type"] for e in events if e["type"] not in ("text", "route")] == ["check"]
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

    assert events[1] == {"type": "search", "query": "olive"}
    assert events[2] == {
        "type": "search_failed",
        "query": "olive",
        "error": "Could not reach OpenAlex: no network",
    }
    assert events[-1]["text"] == "I could not search right now."


def test_the_search_tool_is_offered_to_the_model():
    assert SEARCH_TOOL["function"]["name"] == "search_papers"


def orchard_view():
    from engine.facts import Series, View

    values = [0.3 + 0.01 * (i % 12) for i in range(24)]
    series = [
        {
            "date": f"{2020 + i // 12}-{i % 12 + 1:02d}-01",
            "value": v,
            "masked": False,
            "filled": False,
        }
        for i, v in enumerate(values)
    ]
    return View(
        ["Areas: Orchard (0.64 km²)."],
        [Series("Orchard", "ndvi", "NDVI", "", series)],
        ["ndvi"],
        [],
    )


def test_the_open_workspace_goes_with_the_question_only():
    model = Scripted("NDVI peaks in Dec (0.41) (NDVI chart).")
    history = [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi."}]
    events = list(
        answer(
            model,
            [*history, {"role": "user", "content": "When does it peak?"}],
            view=orchard_view(),
        )
    )

    assert events[1] == {"type": "view", "cards": ["NDVI chart"]}
    question = model.seen[-1]["content"]
    assert question.startswith("What is open in Magonia now")
    assert question.endswith("\n\n---\nThe researcher asks: When does it peak?")
    assert "[NDVI chart]" in question and "peaks in Dec (0.41)" in question
    assert model.seen[1]["content"] == "Hello"  # earlier turns are not repeated with facts
    assert events[-1]["text"] == "NDVI peaks in Dec (0.41) (NDVI chart)."


def test_the_model_can_read_a_year_of_the_researchers_data():
    model = Scripted(
        ToolCall("read_series", {"area": "Orchard", "variable": "ndvi", "year": 2021}), "Done."
    )
    events = list(answer(model, [{"role": "user", "content": "And 2021?"}], view=orchard_view()))

    assert {"type": "read", "area": "Orchard", "variable": "ndvi", "year": 2021} in events
    reading = model.seen[-1]
    assert reading["role"] == "tool" and reading["content"].startswith(
        "Orchard, NDVI, monthly means in 2021"
    )


WRITTEN = """This will give the NDVI data:

```json
{
  "name": "read_series",
  "arguments": {"area": "Orchard", "variable": "ndvi", "year": 2021}
}
```"""


def test_a_call_written_out_as_json_is_found_and_taken_out_of_the_text():
    [call], rest = written_calls(WRITTEN)
    assert call == ToolCall("read_series", {"area": "Orchard", "variable": "ndvi", "year": 2021})
    assert rest == "This will give the NDVI data:"
    bare = 'Searching. {"name": "search_papers", "parameters": {"query": "olive"}} Done.'
    assert written_calls(bare) == (
        [ToolCall("search_papers", {"query": "olive"})],
        "Searching.  Done.",
    )
    plain = 'NDVI is {"high": 0.8} in spring, see {"name": "Orchard"}.'
    assert written_calls(plain) == ([], plain)


def test_a_call_the_model_wrote_out_is_made_and_its_json_never_shown():
    model = Scripted(WRITTEN, "NDVI peaked in April 2021 at 0.62.")
    events = list(answer(model, [{"role": "user", "content": "And 2021?"}], view=orchard_view()))

    assert {"type": "read", "area": "Orchard", "variable": "ndvi", "year": 2021} in events
    assert {"type": "rewrite", "text": ""} in events  # what it said on the way is taken back
    assert events[-1]["text"] == "NDVI peaked in April 2021 at 0.62."


def test_a_written_call_that_can_no_longer_be_made_is_still_not_shown():
    model = Scripted(WRITTEN)
    events = list(
        answer(model, [{"role": "user", "content": "And 2021?"}], view=orchard_view(), max_reads=0)
    )
    assert not any(e["type"] == "read" for e in events)
    assert events[-1]["text"] == "This will give the NDVI data:"


def test_reads_are_limited_then_the_model_must_answer():
    model = Scripted(ToolCall("read_series", {"area": "Orchard", "variable": "ndvi"}))
    events = list(
        answer(model, [{"role": "user", "content": "q"}], view=orchard_view(), max_reads=2)
    )
    assert sum(e["type"] == "read" for e in events) == 2
    assert events[-1]["type"] == "check"


def test_without_a_workspace_the_read_tool_is_not_offered():
    seen_tools = []

    class Recorder(Scripted):
        def stream(self, messages, tools=None):
            seen_tools.append([t["function"]["name"] for t in tools or []])
            yield from super().stream(messages, tools)

    question = [{"role": "user", "content": "Does NDVI fall in drought?"}]
    list(answer(Recorder("Hi."), question))
    list(answer(Recorder("Hi."), question, view=orchard_view()))
    assert seen_tools == [["search_papers"], ["search_papers", "read_series"]]


def test_numbers_in_a_data_answer_are_checked_against_facts_and_readings():
    model = Scripted(
        ToolCall("read_series", {"area": "Orchard", "variable": "ndvi", "year": 2021}),
        "It peaks in Dec (0.41); in Jan 2021 it was 0.30, in Feb 0.77.",
    )
    events = list(answer(model, [{"role": "user", "content": "And 2021?"}], view=orchard_view()))

    numbers = {n["text"]: (n["status"], n["source"]) for n in events[-1]["numbers"]}
    # a number also in the reading taken for this answer is credited to that reading
    assert numbers == {
        "0.41": ("verified", "reading Orchard NDVI 2021"),
        "0.30": ("verified", "reading Orchard NDVI 2021"),
        "0.77": ("unverified", None),
    }


def test_a_plain_chat_answer_has_no_number_check():
    events = list(
        answer(Scripted("NDVI ranges from -1 to 1."), [{"role": "user", "content": "NDVI?"}])
    )
    assert "numbers" not in events[-1]


def test_rules_for_the_data_go_with_the_facts_not_with_every_question():
    from engine.assistant import DATA_RULES, RULES

    assert "read_series" not in RULES and "read_series" in DATA_RULES
    model = Scripted("Fine.")
    list(answer(model, [{"role": "user", "content": "Peak?"}], view=orchard_view()))
    assert DATA_RULES in model.seen[-1]["content"]


def test_magonia_proposes_an_analysis_and_runs_nothing():
    model = Scripted(
        ToolCall(
            "propose_analysis",
            {
                "kind": "trend",
                "variable": "ndvi",
                "start": "2010",
                "end": "2020",
                "why": "Greening?",
            },
        ),
        "I proposed a trend of NDVI from 2010 to 2020; add it to see it.",
    )
    events = list(
        answer(
            model,
            [{"role": "user", "content": "Can you run a trend for 2010-2020?"}],
            view=orchard_view(),
        )
    )
    proposed = [e["proposal"] for e in events if e["type"] == "proposal"]
    assert proposed == [
        {
            "kind": "trend",
            "label": "Long-term trend",
            "why": "Greening?",
            "variable": "ndvi",
            "period": {"start": "2010-01", "end": "2020-12"},
            "title": "Long-term trend: NDVI, period 2010-01 to 2020-12",
        }
    ]
    told = model.seen[-1]
    assert told["role"] == "tool" and "nothing has run" in told["content"]


def test_a_proposal_that_does_not_fit_is_sent_back_to_the_model():
    model = Scripted(
        ToolCall("propose_analysis", {"kind": "lags", "area": "Tunis", "why": ""}), "Sorry."
    )
    events = list(
        answer(model, [{"role": "user", "content": "Add lags in Tunis"}], view=orchard_view())
    )
    assert not any(e["type"] == "proposal" for e in events)
    assert "no area is called 'Tunis'" in model.seen[-1]["content"]


@pytest.mark.parametrize(
    "question, offered",
    [
        ("Can you run a trend test on NDVI?", True),
        ("Add a season-dates analysis for NDVI.", True),
        ("Please forecast NDVI for 2025", True),
        ("Let's build an experiment with XGBoost only", True),
        # asked for in the words of the analysis, not "run" (measured, a01)
        ("Can you split my orchard's LST into its trend and seasonal parts?", True),
        ("Decompose my LST", True),
        ("I'd like you to correlate NDVI with SPEI-3", True),
        ("Could you do a phenology analysis of my NDVI?", True),
        # from a conversation where proposals drowned the questions
        ("no don't propose anything, just give me a list of hyperparameters", False),
        ("What hyperparameters should I try for Random Forest?", False),
        ("Is there a trend in my orchard's NDVI?", False),
        ("Let's just chat: why would olive and forest differ?", False),
        ("Don't run anything, add it to my notes later", False),
        ("Can you tell me when NDVI peaks?", False),
        ("Was 2024 unusual?", False),
    ],
)
def test_proposing_is_offered_only_when_asked_to_run_something(question, offered):
    seen_tools = []

    class Recorder(Scripted):
        def stream(self, messages, tools=None):
            seen_tools.append([t["function"]["name"] for t in tools or []])
            yield from super().stream(messages, tools)

    list(answer(Recorder("Fine."), [{"role": "user", "content": question}], view=orchard_view()))
    assert ("propose_analysis" in seen_tools[0]) is offered


def test_a_proposal_not_offered_is_not_made():
    model = Scripted(
        ToolCall("propose_analysis", {"kind": "trend", "variable": "ndvi", "why": ""}), "Fine."
    )
    question = "no don't propose anything, just give me a list of hyperparameters"
    events = list(answer(model, [{"role": "user", "content": question}], view=orchard_view()))
    assert not any(e["type"] == "proposal" for e in events)


def test_after_a_proposal_the_question_is_still_answered():
    model = Scripted(
        ToolCall("propose_analysis", {"kind": "trend", "variable": "ndvi", "why": "Greening?"}),
        "Here is the answer.",
    )
    list(
        answer(
            model, [{"role": "user", "content": "Run a trend and tell me why"}], view=orchard_view()
        )
    )
    assert "Now answer their question" in model.seen[-1]["content"]


def tools_seen(question: str) -> tuple:
    seen = []

    class Recorder(Scripted):
        def stream(self, messages, tools=None):
            seen.append([t["function"]["name"] for t in tools or []])
            yield from super().stream(messages, tools)

    model = Recorder("Fine.")
    events = list(answer(model, [{"role": "user", "content": question}], view=orchard_view()))
    return seen, model, events


def test_a_research_question_gets_the_search_and_no_workspace_facts():
    seen, model, events = tools_seen("What do studies say about olive NDVI in drought?")
    assert seen == [["search_papers"]]
    assert "What is open in Magonia" not in model.seen[-1]["content"]
    assert events[0] == {
        "type": "route",
        "kind": "research",
        "source": "Answered from the literature",
    }


def test_a_data_question_gets_the_facts_and_no_search():
    seen, model, _ = tools_seen("When does NDVI peak in my orchard?")
    assert seen == [["read_series"]]
    assert "What is open in Magonia" in model.seen[-1]["content"]
    assert "search_papers" not in model.seen[0]["content"]


def test_a_method_question_gets_the_glossary_and_the_settings_but_no_tools():
    seen, model, _ = tools_seen("What is EVI, and which XGBoost settings can I change?")
    assert seen == [[]]
    assert "keeps responding in dense" in model.seen[-1]["content"]
    assert "learning_rate (0.001 to 1)" in model.seen[0]["content"]


def test_only_the_last_turns_of_a_long_conversation_are_sent():
    history = []
    for n in range(10):
        history += [{"role": "user", "content": f"q{n}"}, {"role": "assistant", "content": f"a{n}"}]
    model = Scripted("Fine.")
    list(answer(model, [*history, {"role": "user", "content": "Hello"}]))
    sent = [m["content"] for m in model.seen[1:]]
    assert sent == ["q7", "a7", "q8", "a8", "q9", "a9", "Hello"]


def test_numbers_from_the_model_settings_are_verified():
    model = Scripted("XGBoost learning_rate goes from 0.001 to 1, and max_depth up to 15.")
    question = [{"role": "user", "content": "Which XGBoost settings can I change?"}]
    events = list(answer(model, question, view=orchard_view()))
    assert {n["status"] for n in events[-1]["numbers"]} == {"verified"}


def test_the_answer_is_shown_without_tool_names_code_or_a_closing_offer():
    said = (
        "NDVI peaks in April.\n\n"
        "- **Answer:** To get the values, you would need to call `read_series` with the area. "
        "The peak is about 0.70.\n"
        "```python\nread_series(area='Orchard', variable='ndvi', year=2020)\n```\n\n"
        "If you have any specific questions or need further analysis, feel free to ask!"
    )
    assert tidy(said) == "NDVI peaks in April.\n\n- **Answer:** The peak is about 0.70."
    kept = "Use a lag of 12 months.\n```python\nmodel.fit(X, y)\n```"
    assert tidy(kept) == kept  # code that is not the machinery stays


def test_detailed_answers_and_papers_per_search_follow_the_settings():
    systems = []

    class Recorder(Scripted):
        def stream(self, messages, tools=None):
            systems.append(messages[0]["content"])
            yield from super().stream(messages, tools)

    question = [{"role": "user", "content": "What is NDVI?"}]
    list(answer(Recorder("Hi."), question))
    list(answer(Recorder("Hi."), question, detail="detailed"))
    assert "Be concise" in systems[0] and "thorough" not in systems[0]
    assert "Be concise" not in systems[1] and "thorough" in systems[1]


def test_the_answer_says_where_its_time_went():
    model = Scripted("NDVI measures greenness.")
    events = list(answer(model, [{"role": "user", "content": "What is NDVI?"}]))
    timings = events[-1]["timings"]
    assert "model" in timings and timings["total"] >= timings["model"] >= 0
