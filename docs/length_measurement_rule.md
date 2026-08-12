# Uniform Word-Counting Rule

All response-length measurements in this project use this single rule. Apply identically to every corpus: human baseline, dataset transcripts, and synthetic agent output.

## What counts as a word

A **word** is a whitespace-delimited token that contains at least one alphabetic character (any script, including Spanish).

Formally: after splitting on whitespace, a token is counted if `re.search(r'[a-zA-ZÀ-ÿ]', token)` matches.

## What is excluded

Tokens that contain **no alphabetic character** are excluded:
- Standalone punctuation: `...`, `—`, `-`
- Standalone numbers: `42`, `3.5`
- Transcription annotations that are purely symbolic: `(.)`, `(h)`

Tokens that **are** alphabetic but are **transcription annotations** (not participant speech) are also excluded. These are identified by pattern:
- Parenthetical markers: `(.)`, `(h)`, `(2 sec)`, `(5.5 sec)`, `(1.5)` and similar timing/disfluency annotations
- Bracketed markers: `[inaudible]`, `[unintelligible]`, `[anonymized]`, `[speaking on mute]`, `[Transcription commenced ...]`
- Braced markers: `{laughs}`, `{laughter}`

The exclusion regex: `re.match(r'^\(.*\)$|^\[.*\]$|^\{.*\}$', token)` — any token wholly enclosed in `()`, `[]`, or `{}` is excluded, regardless of content.

## Edge cases

| Case | Rule | Example | Count |
|------|------|---------|-------|
| Hyphenated words | One token | `well-known` | 1 |
| Contractions | One token | `don't`, `I'm` | 1 |
| Numbers within speech | Excluded (no alpha) | `42` | 0 |
| Alphanumeric | Counted | `3rd`, `COVID19` | 1 |
| Multi-word annotation | Each word excluded individually | `(2 sec)` → `(2` `sec)` | 0 + 0 |
| Spanish accented | Counted | `también`, `años` | 1 |
| Timestamp artifacts | Excluded by bracket rule | `[00:09:00]` | 0 |

## Implementation

```python
import re

_ANNOTATION_RE = re.compile(r'^\(.*\)$|^\[.*\]$|^\{.*\}$')
_ALPHA_RE = re.compile(r'[a-zA-ZÀ-ɏ]')

def count_words(text: str) -> int:
    """Count words in a transcript turn, excluding annotations."""
    return sum(
        1 for token in text.split()
        if _ALPHA_RE.search(token) and not _ANNOTATION_RE.match(token)
    )
```

## Scope

This rule applies to participant response turns only (not moderator turns). Moderator turns are excluded from length statistics.
