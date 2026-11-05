"""Standing instructions asked for in the conversation: "from now on, answer in French".

The researcher's instructions for Magon are kept per workspace and edited on the Library page.
Asked for in the chat, an instruction is proposed, never saved by Magon: the researcher sees it in
their own words and saves it with a click (AI-07). It is found by code, not by the model, so that
what is proposed is what they wrote, and a model that misreads them cannot change its own rules.
"""

import re

# What starts a standing instruction, and what of it to keep
LEADS = [
    (
        re.compile(
            r"^(?:from now on|going forward|in future|in the future|henceforth)\b[,:]?\s*",
            re.IGNORECASE,
        ),
        "",
    ),
    (
        re.compile(r"^(?:please\s+)?(?:remember|make sure|note) (?:to|that you)\s+", re.IGNORECASE),
        "",
    ),
    (re.compile(r"^(?:i want|i'd like|i would like|i need) you to\s+", re.IGNORECASE), ""),
    (re.compile(r"^(?:please\s+)?make yourself\s+", re.IGNORECASE), "be "),
    (
        re.compile(
            r"^(?:please\s+)?(?=(?:always|never|stop|don'?t ever|do not ever)\b)", re.IGNORECASE
        ),
        "",
    ),
    (
        re.compile(
            r"^(?:please\s+)?(?=(?:answer|reply|respond|write|talk|speak)\s+(?:in|only in|with|using)\b)",
            re.IGNORECASE,
        ),
        "",
    ),
]
# ... and within a longer message: "Thanks. From now on, cite pages."
INSIDE = re.compile(
    r"(?:^|[.!;]\s+)((?:from now on|going forward|in future)\b[^.!?;]*)", re.IGNORECASE
)

# Asides that are not part of the instruction: "..., I'm busy", "..., thanks"
ASIDE = re.compile(
    r"[,;]\s*(?:i'?m|i am|thanks|thank you|please|ok(?:ay)?|because|since)\b.*$", re.IGNORECASE
)

MAX_LENGTH = 300


def standing_instruction(message: str) -> str | None:
    """The instruction a message asks Magon to keep, in the researcher's words, or None."""
    text = " ".join(message.split())
    if not text or text.endswith("?"):
        return None  # a question about how Magon works is not an instruction
    candidates = [text] + [m.group(1) for m in INSIDE.finditer(text)]
    for candidate in candidates:
        for lead, replacement in LEADS:
            if lead.match(candidate):
                rest = lead.sub(replacement, candidate, count=1)
                rest = ASIDE.sub("", rest).strip(" ,.;:!")
                if len(rest.split()) >= 2 and len(rest) <= MAX_LENGTH:
                    return rest[0].upper() + rest[1:] + "."
    return None


def merged(existing: str, instruction: str) -> str:
    """The workspace's instructions with one more line, unless it is there already."""
    lines = [line for line in existing.splitlines() if line.strip()]
    if any(line.strip(" -").lower() == instruction.lower() for line in lines):
        return existing
    return "\n".join([*lines, f"- {instruction}"])
