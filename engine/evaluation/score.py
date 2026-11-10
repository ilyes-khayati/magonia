"""Score every answer of a run, the same way for every system.

    uv run python evaluation/score.py RESULTS_DIR

Reads RESULTS_DIR/raw.jsonl and writes RESULTS_DIR/scored.jsonl, one line per answer. What
needs the network or the model (does a reference exist, does a passage support a statement,
does a paper answer the question) is remembered in RESULTS_DIR/cache.json, so scoring again
is quick and gives the same verdicts.

What is measured:

- expectations: each check written in the case (cases.py), passed or failed
- references: every author–year mention and every quoted title in the answer, looked up in
  OpenAlex. A mention counts as found when the author published, that year, a work whose
  title shares a word with the question; a title, when a work has nearly the same title.
  Lenient on purpose: what is not found was made up
- statements (research questions): the answer's sentences, and for each whether a paper
  found for the question supports it. Every system is checked against the same pool, all
  the abstracts and passages any system was given for that question, so a statement of the
  bare model is judged by the same literature as Magonia's. Magonia's own support check,
  against only the papers it cites, is kept as it reported it
- retrieval: each paper found, judged by the model on its title and abstract: does it help
  answer the question?
- numbers (data questions): every number in the answer, looked for in the true data of the
  orchard; a number not found there was made up
- the consensus rule: phrases that count studies or give an overall verdict
"""

import hashlib
import json
import os
import re
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
from cases import CASES, jendouba_view

from engine.assistant import Ollama
from engine.citations import GROUP
from engine.literature import CERTIFICATES
from engine.numbers import check_numbers
from engine.rank import words
from engine.support import NOT_AN_END, OFF_TOPIC, SENTENCE, judge_with

BY_ID = {c.id: c for c in CASES}

# Sentences that count studies or weigh them into a verdict, against Magonia's rules
CONSENSUS = re.compile(
    r"\b(most|many|several|the majority of|few|all) (of the )?(studies|papers|"
    r"research(ers)?|authors)\b|\bthe (literature|evidence|research) "
    r"(agrees|suggests overall|is clear|consistently)|\boverall,? (the )?(studies|evidence|"
    r"research|literature)|\b(\d+|two|three|four|five) (of|out of) (the )?(\d+|six|five|four) "
    r"(studies|papers)|\bconsensus\b",
    re.IGNORECASE,
)
DENIES = re.compile(
    r"\b(could ?n[o']t|cannot|can'?t|unable to|did not|didn'?t|was not able to|were unable to)"
    r" (find|locate|identify|verify|confirm)|\bno (such |matching |relevant )?(paper|study|"
    r"report|record|publication|evidence)s?\b|\bnot (aware|find|found)\b|\bdoes not (appear|seem)"
    r" to exist|\b(do|does) not have (any )?(information|access|record)|\bnot (able|possible) "
    r"to (find|verify|confirm)|\bno (information|record) (on|about|of)\b|\bne (trouve|peux)"
    r"|\bnone of the (papers|studies|results)|\b(do|does|did) not (include|contain|mention|"
    r"address|match)|\bnot among the papers",
    re.IGNORECASE,
)
DECLINES = re.compile(
    r"\b(I'?m|I am) (sorry|afraid|here to help|designed|focused|specialized|not able)|\b(can'?t|"
    r"cannot|unable to) (help|assist|write|provide|answer|predict)|\boutside (my|the) "
    r"(scope|field|area|expertise)|\bonly (help|assist|answer)|\bfocus(es|ed)? on\b|\bnot "
    r"(within|related to|in) (my|the)",
    re.IGNORECASE,
)
# Common French words; a text where they are frequent is in French
FRENCH = {
    *("le", "la", "les", "des", "est", "et", "une", "un", "du", "pour", "dans", "que", "qui"),
    *("sur", "pas", "avec", "sont", "plus", "au", "aux", "ce", "cette", "vous", "je", "être"),
    *("ou", "mais", "par", "leur"),
}

# A reference: Name et al. (2019), Name and Other (2019), (Name et al., 2019), Name et al., 2019,
# or a line of a reference list: Name, J., ... (2019)
MENTION = re.compile(
    r"\b([A-Z][a-zà-ÿ'\-]+)(?: et al\.?| (?:and|&) [A-Z][a-zà-ÿ'\-]+)? \((\d{4})[a-z]?\)"
    r"|\(([A-Z][a-zà-ÿ'\-]+)(?: et al\.?| (?:and|&) [A-Z][a-zà-ÿ'\-]+)?,? (\d{4})[a-z]?[;)]"
    r"|\b([A-Z][a-zà-ÿ'\-]+) et al\.?,? (\d{4})\b"
    r"|^\s*(?:\d+\.|[-*])?\s*\**([A-Z][a-zà-ÿ'\-]+), [A-Z]\.[^\n]{0,120}?\((\d{4})\)",
    re.MULTILINE,
)
NOT_NAMES = {"In", "From", "During", "Since", "The", "By", "Until", "Between", "After", "Before"}
TITLE = re.compile(r"[\"“]([A-Z][^\"”\n]{25,200}?)[\"”]")


class Cache:
    """Results of slow lookups, kept on disk; safe to use from several threads (a lookup may
    then run twice, which costs time but not correctness)."""

    def __init__(self, path: Path):
        self.path = path
        self.data = json.loads(path.read_text()) if path.exists() else {}
        self.unsaved = 0
        self.lock = threading.Lock()

    def get(self, key: str, compute: Callable[[], object]):
        with self.lock:
            if key in self.data:
                return self.data[key]
        value = compute()
        with self.lock:
            self.data[key] = value
            self.unsaved += 1
            if self.unsaved >= 20:
                self.save()
        return value

    def save(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False))
        self.unsaved = 0


class BudgetSpent(Exception):
    """OpenAlex's daily budget is used up: references cannot be checked until it resets."""


SPENT = False  # once spent, references are left unchecked instead of asking again


def openalex(params: dict) -> dict:
    global SPENT
    if SPENT:
        raise BudgetSpent
    if key := os.environ.get("OPENALEX_API_KEY"):
        params = {**params, "api_key": key}
    request = Request(
        f"https://api.openalex.org/works?{urlencode(params)}", headers={"User-Agent": "Magonia"}
    )
    for attempt in range(4):
        try:
            with urlopen(request, timeout=30, context=CERTIFICATES) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code == 429:  # waiting does not help: the daily budget is spent
                SPENT = True
                print(
                    "OpenAlex's daily budget is used up: references are left unchecked. Set "
                    "OPENALEX_API_KEY or wait until midnight UTC, and score again to check them."
                )
                raise BudgetSpent from exc
            time.sleep(2 + 4 * attempt)
        except (URLError, TimeoutError):
            time.sleep(2 + 4 * attempt)
    raise RuntimeError("OpenAlex could not be reached")


def mentions(text: str) -> list[tuple[str, int]]:
    found = []
    for m in MENTION.finditer(text):
        groups = [g for g in m.groups() if g]
        name, year = groups[0], int(groups[1])
        if name not in NOT_NAMES and 1950 <= year <= 2026:
            found.append((name, year))
    return list(dict.fromkeys(found))


def titles(text: str) -> list[str]:
    return list(dict.fromkeys(t.strip(" .,") for t in TITLE.findall(text)))


def unless_spent(look):
    """True or False when OpenAlex could answer, None when its budget was spent."""
    try:
        return look()
    except BudgetSpent:
        return None


def mention_exists(cache: Cache, name: str, year: int, topic: set[str]) -> bool | None:
    def look() -> bool:
        found = openalex(
            {
                "filter": f"raw_author_name.search:{name},publication_year:{year}",
                "search": " ".join(sorted(topic)[:6]),
                "per_page": 50,
                "select": "title",
            }
        )
        return any(topic & words(w.get("title") or "") for w in found.get("results", []))

    return unless_spent(lambda: cache.get(f"mention|{name}|{year}|{' '.join(sorted(topic))}", look))


def title_exists(cache: Cache, title: str) -> bool | None:
    def look() -> bool:
        asked = words(title)
        clean = re.sub(r"[^\w\s-]", " ", title)
        found = openalex({"filter": f"title.search:{clean}", "per_page": 10, "select": "title"})
        for w in found.get("results", []):
            got = words(w.get("title") or "")
            if asked and len(asked & got) / len(asked | got) >= 0.7:
                return True
        return False

    return unless_spent(lambda: cache.get(f"title|{title}", look))


def sentences(text: str) -> list[str]:
    """The answer's statements: sentences with a few content words, not headings, without
    their citations."""
    masked = NOT_AN_END.sub(lambda m: m.group(0).replace(".", "\x00"), text)
    found = []
    for match in SENTENCE.finditer(masked):
        sentence = text[match.start() : match.end()]
        claim = " ".join(GROUP.sub("", sentence).split()).strip(" -*#:")
        claim = re.sub(r"\*\*", "", claim)
        heading = not claim.endswith((".", "!", "?")) and len(claim.split()) <= 10
        if not heading and len(words(claim)) >= 3:
            found.append(claim)
    return found


def french(text: str) -> bool:
    tokens = re.findall(r"[a-zà-ÿ]+", text.lower())
    return bool(tokens) and sum(t in FRENCH for t in tokens) / len(tokens) > 0.08


def value_given(text: str, value: float, decimals: int) -> bool:
    """The value appears in the text, written with at least its decimals (0.70 also as 0.7)."""
    for found in re.findall(r"[−-]?\d+(?:\.\d+)?", text.replace("−", "-")):
        try:
            if round(float(found), decimals) == round(value, decimals) and (
                "." in found or decimals == 0
            ):
                return True
        except ValueError:
            continue
    return False


def expectations(r: dict, case) -> dict[str, bool]:
    text = r.get("answer") or ""
    e = case.expect
    out = {}
    if "search" in e:
        out["search"] = bool(r["searches"]) == e["search"]
    if "query_has" in e:
        out["query_has"] = any(e["query_has"] in q.lower() for q in r["searches"])
    if "denies" in e:
        out["denies"] = bool(DENIES.search(text))
    if "declines" in e:
        out["declines"] = bool(DECLINES.search(text))
    for pattern in e.get("has", []):
        out[f"has {pattern}"] = bool(re.search(pattern, text, re.IGNORECASE))
    if "has_any" in e:
        out["has any"] = any(re.search(p, text, re.IGNORECASE) for p in e["has_any"])
    for value, decimals in e.get("values", []):
        out[f"value {value}"] = value_given(text, value, decimals)
    for pattern in e.get("lacks", []):
        out[f"lacks {pattern}"] = not re.search(pattern, text, re.IGNORECASE)
    if e.get("language") == "fr":
        out["french"] = french(text)
    if "max_words" in e:
        out["short"] = len(text.split()) <= e["max_words"]
    if "proposal" in e:
        out["proposal"] = bool(r["proposals"]) == e["proposal"]
    if e.get("recalls_cited"):
        first = r["earlier_cited"][:1]
        paper = next((p for p in r["earlier_papers"] if first and p["n"] == first[0]), None)
        if paper is None:
            out["recalls cited"] = False
        else:
            surname = (paper["authors"][0].split()[-1] if paper["authors"] else "") or "§"
            title = words(paper["title"])
            out["recalls cited"] = surname.lower() in text.lower() or (
                len(title & words(text)) / max(len(title), 1) >= 0.5
            )
    return out


class Pool:
    """Everything any system was given from the literature for one question, embedded once."""

    def __init__(self, chunks: list[str], embed):
        self.chunks = chunks
        self.vectors = None
        if chunks and embed is not None:
            vectors = []
            for i in range(0, len(chunks), 32):
                vectors += embed([f"search_document: {c}" for c in chunks[i : i + 32]])
            self.vectors = np.asarray(vectors, dtype=np.float32)
            self.vectors /= np.linalg.norm(self.vectors, axis=1, keepdims=True)

    def closest(self, claim: str, embed, keep: int = 2) -> list[tuple[float, str]]:
        if self.vectors is None:
            return []
        v = np.asarray(embed([f"search_query: {claim}"])[0], dtype=np.float32)
        scores = self.vectors @ (v / np.linalg.norm(v))
        best = np.argsort(-scores)[:keep]
        return [(float(scores[i]), self.chunks[i]) for i in best]


def evidence(pool: Pool, claim: str, embed) -> list[str]:
    """The passages a statement is judged against: the closest ones that are on its subject."""
    return [t for s, t in pool.closest(claim, embed) if s >= OFF_TOPIC]


def pool_support(cache: Cache, pool: Pool, claim: str, embed, judge) -> str:
    """supported, partly, unsupported or off-topic: what the literature found says of it."""

    def look() -> str:
        near = evidence(pool, claim, embed)
        if not near:
            return "off-topic"
        verdicts = [judge(claim, text) for text in near]
        if "yes" in verdicts:
            return "supported"
        return "partly" if "partly" in verdicts else "unsupported"

    return cache.get(f"pool|{claim}|{len(pool.chunks)}|{hash_of(pool.chunks)}", look)


def hash_of(chunks: list[str]) -> str:
    return hashlib.sha1("\n".join(chunks).encode()).hexdigest()[:12]


def relevance(cache: Cache, question: str, paper: dict, stream) -> str:
    def look() -> str:
        asked = (
            "Would this paper help a researcher answer the question? Answer with one word: "
            f"yes, partly or no.\n\nQuestion: {question}\n\nPaper: {paper['title']}. "
            f"{(paper.get('abstract') or 'No abstract.')[:1200]}"
        )
        said = "".join(
            p for p in stream([{"role": "user", "content": asked}], None) if isinstance(p, str)
        )
        first = (re.findall(r"[a-z]+", said.lower()) or ["no"])[0]
        return first if first in ("yes", "partly", "no") else "no"

    return cache.get(f"relevance|{question}|{paper['title']}", look)


# A judge's question needs a word, not Magon's rules: a short system message, a few tokens and
# no randomness make each verdict about forty times cheaper than an assistant turn
JUDGE_SYSTEM = "You are a careful, strict judge. Answer with one word only."
WORKERS = 4  # answers scored at once; Ollama serves parallel requests when it has the memory


def judge_stream(url: str, model: str):
    def stream(messages: list[dict], tools=None):
        body = {
            "model": model,
            "messages": [{"role": "system", "content": JUDGE_SYSTEM}, *messages],
            "stream": False,
            "options": {"num_predict": 4, "num_ctx": 4096, "temperature": 0},
        }
        request = Request(
            f"{url.rstrip('/')}/api/chat",
            json.dumps(body).encode(),
            {"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=300) as response:
            yield json.load(response)["message"]["content"]

    return stream


def main() -> None:
    folder = Path(sys.argv[1])
    raw = [json.loads(line) for line in (folder / "raw.jsonl").read_text().splitlines()]
    cache = Cache(folder / "cache.json")
    provider = Ollama(
        os.environ.get("MAGONIA_MODEL_URL", "http://localhost:11434"),
        os.environ.get("MAGONIA_MODEL", "qwen2.5:7b"),
    )
    lean = judge_stream(provider.url, provider.model)
    judge = judge_with(lean)
    embed = provider.embed
    view = jendouba_view()
    # the true data of the orchard: its facts and every reading Magonia could give
    truth = [("facts", view.sheet())] + [
        (f"{v} {y}", view.read("Orchard", v, y))
        for v in ("ndvi", "lst", "spei")
        for y in [None, *range(2000, 2025)]
    ]
    # the literature pool of each question: what any system was given
    pools: dict[str, Pool] = {}
    literature = {c.id for c in CASES if c.expect.get("search") or c.expect.get("recalls_cited")}
    for case in {r["case"] for r in raw} & literature:
        chunks = []
        for r in raw:
            if r["case"] != case:
                continue
            chunks += [f"{p['title']}. {p.get('abstract') or ''}" for p in r.get("papers", [])]
            chunks += [p["text"] for p in r.get("passages", [])]
        pools[case] = Pool(list(dict.fromkeys(chunks)), embed)

    done = 0
    lock = threading.Lock()

    def score(r: dict) -> dict:
        nonlocal done
        case = BY_ID[r["case"]]
        text = r.get("answer") or ""
        out = {k: r[k] for k in ("case", "kind", "system", "repeat", "question")}
        out["error"] = bool(r.get("error"))
        if r.get("error"):
            return out
        out["seconds"] = r["seconds"]
        out["timings"] = (r.get("check") or {}).get("timings", {})
        out["first_word"] = r["first_word"]
        out["words"] = len(text.split())
        out["checks"] = expectations(r, case)
        out["passed"] = all(out["checks"].values()) if out["checks"] else None
        topic = words(case.question) | words(" ".join(case.turns))
        # a mention of a paper the system was given is found; any other is looked up
        given = {
            (p["short"].split()[0].strip(","), p.get("year"))
            for p in [*r.get("papers", []), *r.get("earlier_papers", [])]
        }
        out["mentions"] = [
            {"name": n, "year": y, "found": (n, y) in given or mention_exists(cache, n, y, topic)}
            for n, y in mentions(text)
            # repeating a reference the researcher gave is not making one up
            if (n, y) not in mentions(" ".join(case.turns))
        ]
        out["titles"] = [{"title": t, "found": title_exists(cache, t)} for t in titles(text)]
        out["consensus"] = [m.group(0) for m in CONSENSUS.finditer(text)]
        check = r.get("check") or {}
        out["citations_removed"] = len(check.get("removed", []))
        out["cited"] = len(check.get("cited", []))
        if r["case"] in pools:
            claims = sentences(text)
            pool = pools[r["case"]]
            # the passages are kept with each verdict, so people can judge the same evidence
            out["statements"] = [
                {
                    "claim": c,
                    "pool": pool_support(cache, pool, c, embed, judge),
                    "evidence": evidence(pool, c, embed),
                }
                for c in claims
            ]
            support = check.get("support") or []
            out["own_support"] = [s["status"] for s in support]
            cites = [m for m in GROUP.finditer(text)]
            out["page_citations"] = sum(bool(m.group(2)) for m in cites)
            out["all_citations"] = len(cites)
            out["relevance"] = [
                relevance(cache, case.question, p, lean)
                for p in r.get("papers", [])
                if p.get("venue") != "Your library"
            ]
            out["read"] = r.get("read", {})
        if r["kind"] == "data" or (case.workspace and r["kind"] == "follow-up"):
            checked = check_numbers(text, [("question", case.question), *truth])
            out["numbers"] = [{"text": n.text, "true": n.status == "verified"} for n in checked]
        with lock:
            done += 1
            print(f"[{done}/{len(raw)}] {r['case']} {r['system']} #{r['repeat']}", flush=True)
        return out

    with ThreadPoolExecutor(WORKERS) as pool:
        scored = list(pool.map(score, raw))  # in the order of raw, whatever order they finish
    cache.save()
    with (folder / "scored.jsonl").open("w") as f:
        for s in scored:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
