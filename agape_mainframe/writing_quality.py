from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

# Conservative UK-English allowances. The checker suggests rather than blindly
# correcting unknown words, because project names, product names and people
# must never be changed just because a dictionary does not know them.
UK_ALLOWLIST = {
    "organisation", "organisations", "organise", "organised", "organising",
    "optimise", "optimised", "optimising", "optimisation", "colour", "colours",
    "favour", "favourite", "centre", "centres", "licence", "licences", "travelling",
    "modelling", "catalogue", "catalogues", "programme", "programmes", "behaviour",
    "labour", "neighbour", "neighbours", "specialise", "specialised", "specialising",
    "customise", "customised", "prioritise", "prioritised", "realise", "realised",
    "analyse", "analysed", "analysing", "defence", "offence", "grey", "metre",
    "litre", "cheque", "fulfil", "fulfilment", "judgement",
    # Common technical/product terms that are valid project language and must not
    # be "corrected" into ordinary dictionary words.
    "agape", "ollama", "stdout", "stderr", "sqlite", "json", "yaml", "toml",
    "python", "powershell", "webview", "github", "localhost", "api", "apis",
    "http", "https", "url", "urls", "rag", "llm", "llms", "codex", "claude",
    "openrouter", "huggingface", "webhook", "webhooks", "runtime", "backend",
    "frontend", "filesystem", "filename", "filenames", "workflow", "workflows",
}

# Only very high-confidence mechanical typo fixes are applied automatically to
# a cleaned preview. The original uploaded file remains untouched on disk.
COMMON_TYPOS = {
    "teh": "the",
    "adn": "and",
    "taht": "that",
    "thsi": "this",
    "thier": "their",
    "recieve": "receive",
    "recieved": "received",
    "recieving": "receiving",
    "seperate": "separate",
    "seperately": "separately",
    "definately": "definitely",
    "occured": "occurred",
    "occuring": "occurring",
    "untill": "until",
    "wich": "which",
    "becuase": "because",
    "enviroment": "environment",
    "goverment": "government",
    "managment": "management",
    "buiness": "business",
    "grammer": "grammar",
    "relevent": "relevant",
    "completly": "completely",
    "availble": "available",
    "infromation": "information",
    "inistall": "install",
    "instal": "install",
    "docuemnt": "document",
    "complate": "complete",
    "dont": "don't",
    "eption": "option",
}

_WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z'’-]{2,}\b")
_URL_EMAIL_RE = re.compile(r"https?://|www\.|\b\S+@\S+\b", re.I)
_ESCAPED_BREAK_RE = re.compile(r"(?<!\\)\\(?:r\\n|n)")


def _normalise_prose_escapes(text: str) -> tuple[str, int]:
    """Turn escaped prose line-break markers into real line breaks before checking.

    Imported/pasted text sometimes arrives containing the two literal characters \n
    rather than an actual newline. Without this pass, a marker such as \nAgape
    is tokenised as the fake word ``nAgape``. A single isolated escape can be
    legitimate technical content, so normalise when there are multiple markers or
    when a marker is immediately followed by prose/heading content.
    """
    source = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    matches = list(_ESCAPED_BREAK_RE.finditer(source))
    if not matches:
        return source, 0
    prose_hint = len(matches) >= 2 or bool(re.search(r"(?<!\\)\\(?:r\\n|n)(?=[A-Za-z0-9#*•-])", source))
    if not prose_hint:
        return source, 0
    source = re.sub(r"(?<!\\)\\r\\n", "\n", source)
    source = re.sub(r"(?<!\\)\\n", "\n", source)
    source = re.sub(r"(?<!\\)\\t", "\t", source)
    return source, len(matches)


def _match_case(source: str, replacement: str) -> str:
    if source.isupper():
        return replacement.upper()
    if source[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def safe_clean(text: str) -> tuple[str, list[dict[str, str]]]:
    """Apply only mechanical, high-confidence writing corrections.

    This deliberately avoids free-form rewriting. Names, dates, prices, IDs and
    technical terms are preserved.
    """
    source, _ = _normalise_prose_escapes(text)
    changes: list[dict[str, str]] = []

    def typo(m: re.Match[str]) -> str:
        raw = m.group(0)
        fixed = COMMON_TYPOS.get(raw.lower())
        if not fixed:
            return raw
        out = _match_case(raw, fixed)
        changes.append({"kind": "spelling", "from": raw, "to": out})
        return out

    # Clean prose line-by-line. Structured/code/log lines are preserved exactly;
    # the writing checker must never rewrite JSON keys, CLI output or technical data.
    cleaned_lines=[]
    punctuation_fixed=False
    spacing_fixed=False
    for line in source.split("\n"):
        if _looks_structured_line(line):
            cleaned_lines.append(line.rstrip())
            continue
        cleaned_line=_WORD_RE.sub(typo,line)
        before=cleaned_line
        cleaned_line=re.sub(r"[ \t]+([,.;:!?])", r"\1", cleaned_line)
        punctuation_fixed = punctuation_fixed or (cleaned_line != before)
        before=cleaned_line
        cleaned_line=re.sub(r"[ \t]{2,}", " ", cleaned_line).rstrip()
        spacing_fixed = spacing_fixed or (cleaned_line != before.rstrip())
        cleaned_lines.append(cleaned_line)
    cleaned="\n".join(cleaned_lines)
    if punctuation_fixed:
        changes.append({"kind": "grammar", "from": "space before punctuation", "to": "punctuation spacing fixed"})
    if spacing_fixed:
        changes.append({"kind": "grammar", "from": "repeated spaces", "to": "single spacing"})

    # Keep the change list useful rather than repeating the same typo hundreds of times.
    unique: list[dict[str, str]] = []
    seen = set()
    for row in changes:
        key = (row["kind"], row["from"].lower(), row["to"].lower())
        if key not in seen:
            seen.add(key)
            unique.append(row)
        if len(unique) >= 40:
            break
    return cleaned, unique


@lru_cache(maxsize=1)
def _spellchecker():
    try:
        from spellchecker import SpellChecker  # type: ignore
        checker = SpellChecker(language="en", distance=1)
        checker.word_frequency.load_words(UK_ALLOWLIST)
        return checker
    except Exception:
        return None


def _looks_structured_line(line: str) -> bool:
    """Return True for code/JSON/log/identifier-heavy lines that are not prose.

    Writing suggestions are for human language. Structured project snapshots,
    source code, command output, paths and JSON keys must be preserved exactly.
    """
    raw=str(line or "").strip()
    if not raw:
        return False
    if re.match(r'^[\[{]|^[\]}],?$', raw):
        return True
    if re.match(r'^["\'][^"\']+["\']\s*:', raw):
        return True
    if re.match(r'^[A-Za-z_][A-Za-z0-9_.-]*\s*=', raw):
        return True
    if re.search(r'https?://|[A-Za-z]:\\|/api/|\b(?:stdout|stderr|json|sqlite|python|powershell)\b', raw, re.I):
        return True
    # Identifier-heavy rows (snake_case, escaped JSON keys, CLI flags) are not prose.
    if raw.count('_') >= 2 or raw.count('\\') >= 2 or len(re.findall(r'--[A-Za-z0-9_-]+', raw)) >= 1:
        return True
    punct=sum(raw.count(ch) for ch in '{}[]:=<>`')
    if punct >= 4 and len(raw.split()) < 40:
        return True
    return False


def _prose_for_suggestions(text: str) -> tuple[str, int]:
    kept=[]; skipped=0
    for line in str(text or '').splitlines():
        if _looks_structured_line(line):
            skipped += 1
            continue
        kept.append(line)
    return "\n".join(kept), skipped


def _spelling_suggestions(text: str, limit: int = 25) -> list[dict[str, Any]]:
    checker = _spellchecker()
    if checker is None:
        return []
    # Avoid feeding structured data, URLs/emails and huge documents into the dictionary pass.
    prose, _ = _prose_for_suggestions(text)
    scrubbed = _URL_EMAIL_RE.sub(" ", prose)
    candidates: dict[str, str] = {}
    for match in _WORD_RE.finditer(scrubbed[:240000]):
        raw = match.group(0)
        low = raw.lower().replace("’", "'")
        if len(low) < 4 or low in UK_ALLOWLIST or low in COMMON_TYPOS:
            continue
        # Capitalised unknowns are frequently people, companies or products.
        if raw[:1].isupper() and match.start() > 0:
            continue
        if any(ch.isdigit() for ch in raw):
            continue
        candidates.setdefault(low, raw)
        if len(candidates) >= 1200:
            break
    unknown = checker.unknown(candidates.keys())
    out: list[dict[str, Any]] = []
    for low in sorted(unknown):
        suggestion = checker.correction(low)
        if not suggestion or suggestion == low:
            continue
        out.append({"word": candidates.get(low, low), "suggestion": suggestion, "kind": "spelling"})
        if len(out) >= limit:
            break
    return out


def _grammar_suggestions(text: str, limit: int = 25) -> list[dict[str, Any]]:
    t, _ = _prose_for_suggestions(text)
    out: list[dict[str, Any]] = []

    for m in re.finditer(r"\b([A-Za-z]{3,})\s+\1\b", t, re.I):
        out.append({"kind": "grammar", "issue": "repeated_word", "text": m.group(0), "suggestion": m.group(1)})
        if len(out) >= limit:
            return out
    for m in re.finditer(r"[ \t]+[,.;:!?]", t):
        out.append({"kind": "grammar", "issue": "punctuation_spacing", "text": m.group(0), "suggestion": m.group(0).lstrip()})
        if len(out) >= limit:
            return out
    for m in re.finditer(r"(?<![A-Za-z])i(?![A-Za-z])", t):
        out.append({"kind": "grammar", "issue": "lowercase_pronoun", "text": "i", "suggestion": "I"})
        if len(out) >= limit:
            return out
    # Flag very long prose sentences for human review without auto-rewriting them.
    for sentence in re.split(r"(?<=[.!?])\s+", t):
        words = sentence.split()
        if len(words) >= 55:
            out.append({"kind": "grammar", "issue": "very_long_sentence", "text": " ".join(words[:16]) + "…", "suggestion": "Consider splitting this sentence for readability."})
            if len(out) >= limit:
                return out
    return out


def check_text(text: str) -> dict[str, Any]:
    original = str(text or "")
    normalised, escaped_breaks = _normalise_prose_escapes(original)
    cleaned, applied = safe_clean(normalised)
    prose_for_suggestions, structured_skipped = _prose_for_suggestions(cleaned)
    spelling = _spelling_suggestions(prose_for_suggestions)
    # Report only issues that remain after high-confidence mechanical cleanup.
    grammar = _grammar_suggestions(prose_for_suggestions)
    return {
        "ok": True,
        "language": "en-GB",
        "chars_checked": len(original),
        "safe_corrections_applied": len(applied),
        "safe_corrections": applied,
        "spelling_issue_count": len(spelling),
        "spelling_suggestions": spelling,
        "grammar_issue_count": len(grammar),
        "grammar_suggestions": grammar,
        "issue_count": len(spelling) + len(grammar),
        "checker": "agape-writing-quality-v1",
        "dictionary_available": _spellchecker() is not None,
        "escaped_line_breaks_normalized": escaped_breaks,
        "structured_lines_skipped": structured_skipped,
    }


def proofread_text(text: str) -> tuple[str, dict[str, Any]]:
    cleaned, _ = safe_clean(text)
    report = check_text(text)
    return cleaned, report
