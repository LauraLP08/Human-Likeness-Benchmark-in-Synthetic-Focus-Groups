"""
Sub-entry Question-1 boundary detection for the human-comparable window.

WHY SUB-ENTRY
Entry-level segmentation is not sufficient. The moderator entry that opens
Question 1 routinely fuses residue in front of the ask — participant names,
a location recap of the introductions, a welcome, confidentiality/instruction
text, or a summary of the presentation round. In two runs it also fuses the
entire session instructions and the Q1 ask into the single opening entry. An
entry-aligned window is therefore content-dirty at its first entry, and would put
introduction material in front of the evaluator.

THE RULE — anchor-and-extend (one rule, all 30 runs)
    1. Locate the boundary entry: the first MODERATOR entry that poses Question 1.
    2. ANCHOR on the LATEST sentence-aligned suffix of that entry that still poses
       Question 1 — the minimal ask.
    3. EXTEND BACKWARD from the anchor, one sentence at a time, only across
       sentences that are residue-free AND positively identified as part of the
       ask (carrying a Q1-distinctive token, or being an ask lead-in / short
       discourse connective). Stop at the first sentence failing either test.
    4. Retain the resulting substring VERBATIM. It is never paraphrased,
       normalised, reconstructed, or replaced with the guide's scripted question.
    5. Include every subsequent entry through the end of the last substantive
       section; exclude the closing section.

Anchoring on the ask and extending backward means the boundary can only ever move
earlier over text POSITIVELY IDENTIFIED as part of the ask. Residue is therefore
excluded by construction, not by enumeration — an unlisted phrasing cannot slip
through. Candidate offsets are sentence and paragraph starts only, so the cut
never lands mid-sentence.

FORBIDDEN RESIDUE CLASSES (requirement 7, enforced as a hard gate)
    participant_name        — any roster first name, from the run's own state
    moderator_self_intro    — "my name's", "I'll be facilitating/moderating/leading"
    welcome                 — "welcome", "thanks for joining", "glad you're here"
    instructions            — recording, research purposes, no right/wrong answers,
                              duration, confidentiality, "jump in", "not an interview"
    presentation_summary    — a cluster of ≥2 non-sentence-initial proper nouns
                              (the location recap of the introductions)

If no offset satisfies both conditions, the run is returned as
HUMAN_REVIEW_REQUIRED with the reason. Nothing is guessed.

Nothing here writes to `output/session_logs/`.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

# Content tokens unique to guide section 1's scripted question across the guide.
Q1_DISTINCTIVE = {"favourite", "favorite", "place", "city", "friends", "spend", "male"}
Q1_MIN_HITS = 2

_MODERATOR_SELF_INTRO = (
    "my name's", "my name is", "i'll be facilitating", "i'll be moderating",
    "i'll be leading", "i'm facilitating", "i'll be running",
)
_WELCOME = (
    "welcome", "thanks so much for joining", "thanks for joining",
    "glad you could", "glad you're all here", "glad you're here",
    "thanks for making the time", "good to have you all here",
    "thanks for coming", "really glad",
)
_INSTRUCTIONS = (
    "recorded", "recording", "research purposes", "no right or wrong",
    "right or wrong answers", "45 minutes", "forty-five minutes", "confidential",
    "anonymous", "stays within the research team", "not attributed",
    "jump in", "not an interview", "conversation, not", "take turns",
    "there are no right", "keep your responses", "speak freely", "ground rules",
    # trailing sentences of the instruction block, found by auditing retained text
    "wait to be asked", "if you disagree", "completely fine", "don't have to wait",
    "feel free to disagree", "no need to wait",
)

# Summaries of the participant presentation round. These survive with no proper
# noun left in them ("Quite a spread."), so they need their own vocabulary.
_PRESENTATION_SUMMARY = (
    "spread", "nice mix", "good mix", "quite a mix", "corners of the country",
    "across the country", "represented here", "range of places", "all over the",
    "bit of everywhere", "different parts of",
)

# Words that may legitimately be capitalised mid-sentence in this corpus without
# indicating a presentation recap.
_PROPER_NOUN_ALLOWLIST = {
    "i", "i'm", "i've", "i'll", "uk", "u.k.", "british", "britain", "england",
    "scotland", "wales", "tuesday", "monday", "friday", "saturday", "sunday",
    "christmas", "google", "tesco", "aldi", "lidl", "asda", "sainsbury's",
    "mcdonald's", "greggs", "quorn", "linda", "beyond", "impossible",
}


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    return (s.replace("’", "'").replace("‘", "'")
             .replace("“", '"').replace("”", '"')
             .replace("–", "-").replace("—", "-"))


def _tokens(s: str) -> set[str]:
    return set(re.sub(r"[^a-z0-9\s']", " ", _fold(s).casefold()).split())


def poses_q1(text: str) -> bool:
    """True if the text still asks Question 1."""
    return len(Q1_DISTINCTIVE & _tokens(text)) >= Q1_MIN_HITS


def _proper_noun_cluster(text: str) -> list[str]:
    """Non-sentence-initial capitalised tokens — the signature of a location /
    name recap such as 'Glasgow, Birmingham, Newcastle, Leeds and rural Scotland'."""
    t = _fold(text)
    found: list[str] = []
    # A token is sentence-initial if preceded by start-of-string or . ? ! : newline
    for m in re.finditer(r"(^|[^.?!:\n]\s+)([A-Z][a-z]{2,})", t):
        tok = m.group(2)
        if tok.casefold() not in _PROPER_NOUN_ALLOWLIST:
            found.append(tok)
    return found


def residue_in(text: str, roster_names: set[str]) -> list[str]:
    """Return the forbidden residue classes present in `text`."""
    low = _fold(text).casefold()
    hits: list[str] = []

    names = sorted(n for n in roster_names
                   if re.search(rf"\b{re.escape(n.casefold())}\b", low))
    if names:
        hits.append(f"participant_name({','.join(names)})")
    if any(p in low for p in _MODERATOR_SELF_INTRO):
        hits.append("moderator_self_intro")
    if any(p in low for p in _WELCOME):
        hits.append("welcome")
    instr = [p for p in _INSTRUCTIONS if p in low]
    if instr:
        hits.append(f"instructions({instr[0]})")
    cluster = _proper_noun_cluster(text)
    if len(cluster) >= 2:
        hits.append(f"presentation_summary_propernouns({','.join(cluster[:4])})")
    summ = [p for p in _PRESENTATION_SUMMARY if p in low]
    if summ:
        hits.append(f"presentation_summary({summ[0]})")
    return hits


def candidate_offsets(text: str) -> list[int]:
    """Sentence and paragraph starts, ascending. Offset 0 is always a candidate,
    so a boundary entry that is already clean is retained whole."""
    offs = {0}
    for m in re.finditer(r"[.?!]['\"’”]?\s+", text):
        offs.add(m.end())
    for m in re.finditer(r"\n+\s*", text):
        offs.add(m.end())
    return sorted(o for o in offs if o < len(text))


# Phrases that introduce the ask itself. These belong to the Q1 ask, not to the
# introduction round, so the boundary may extend back over them.
_ASK_LEAD_IN = (
    "let's get into it", "lets get into it", "let's get into the", "first thing i want to ask",
    "first thing i'd love to hear", "first question", "i want to start", "i want to ask",
    "let's start", "lets start", "let's move on", "let's shift", "let's pick up",
    "we're going to move on", "move into the first", "thinking about", "think about",
    "let's use this as a way", "i'd love to hear",
)


def _is_ask_lead_in(sentence: str) -> bool:
    low = _fold(sentence).casefold().strip()
    if any(p in low for p in _ASK_LEAD_IN):
        return True
    # A short pure discourse connective ("Right,", "Okay, so", "So -") with no
    # proper nouns and no content of its own.
    words = re.sub(r"[^a-z\s']", " ", low).split()
    return len(words) <= 4 and not _proper_noun_cluster(sentence)


def find_q1_offset(text: str, roster_names: set[str]) -> tuple[int | None, str, str]:
    """
    Return (offset, review_status, note) for the start of the substantive Q1 ask.

    SELECTION PRINCIPLE
    Anchor on the LAST offset whose suffix still poses Question 1 — the minimal
    ask — then extend BACKWARD sentence by sentence for as long as each added
    sentence is residue-free AND is itself part of the ask (carries a Q1
    distinctive token, or is an ask lead-in / short discourse connective). Stop
    at the first sentence that fails either test.

    This is deliberately not "earliest residue-free offset". That variant retains
    more text but is only as reliable as the residue vocabulary: an unlisted
    phrasing of a presentation summary ("Quite a spread.", "Nice mix.") or a
    trailing instruction sentence survives it silently. Anchoring on the ask and
    extending backward can only ever move the boundary earlier over text that has
    been positively identified as part of the ask, so unrecognised residue is
    excluded by construction rather than by enumeration.
    """
    if not poses_q1(text):
        return None, "HUMAN_REVIEW_REQUIRED", "boundary entry does not pose Question 1"

    offs = candidate_offsets(text)
    q1_bearing = [o for o in offs if poses_q1(text[o:])]
    if not q1_bearing:
        return None, "HUMAN_REVIEW_REQUIRED", "no sentence-aligned suffix poses Question 1"

    anchor = max(q1_bearing)                      # minimal ask
    earlier = [o for o in offs if o < anchor]
    off = anchor
    extended = 0
    for cand in sorted(earlier, reverse=True):    # walk backward, one sentence at a time
        sentence = text[cand:off]
        if residue_in(sentence, roster_names):
            break
        if not (Q1_DISTINCTIVE & _tokens(sentence) or _is_ask_lead_in(sentence)):
            break
        off = cand
        extended += 1

    suffix = text[off:]
    resid = residue_in(suffix, roster_names)
    if resid:
        return (None, "HUMAN_REVIEW_REQUIRED",
                f"retained span still carries residue after backward extension: {'; '.join(resid)}")

    if off == 0:
        return off, "AUTO_CLEAN", (
            f"whole boundary entry is the ask (anchor at {anchor}, extended back "
            f"{extended} sentence(s) to offset 0)")
    dropped = text[:off]
    classes = residue_in(dropped, roster_names)
    return (off, "AUTO_TRIMMED",
            f"anchored on minimal Q1 ask at char {anchor}, extended back {extended} "
            f"sentence(s) to char {off}; dropped {off} leading chars "
            f"({len(dropped.split())} words) carrying: "
            f"{'; '.join(classes) if classes else 'pre-ask framing / presentation round'}")


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()
