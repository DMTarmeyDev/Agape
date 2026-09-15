from pathlib import Path
import re, sys, json

p = Path(sys.argv[1])
text = p.read_text(encoding='utf-8-sig')

if 'VERSION = "R31.10"' in text:
    print('DOCUMENT_STUDIO_PATCH=ALREADY_R31_10')
    raise SystemExit(0)
if 'VERSION = "R31.9"' not in text:
    raise SystemExit('UNEXPECTED_DOCUMENT_STUDIO_VERSION')

# Keep changes deliberately narrow and regression-testable.
text = text.replace('VERSION = "R31.9"', 'VERSION = "R31.10"', 1)
text = text.replace('Agape Document Studio R31.9', 'Agape Document Studio R31.10')
text = text.replace('AGAPE_DOCUMENT_STUDIO_R31_9=READY', 'AGAPE_DOCUMENT_STUDIO_R31_10=READY')

marker = '# AGAPE_R31_10_RELIABILITY_FIXES_BEGIN'
if marker in text:
    raise SystemExit('R31_10_MARKER_PRESENT_WITH_R31_9_VERSION')

insert_at = text.find('\ndef serve(port,open_browser=True):')
if insert_at < 0:
    raise SystemExit('SERVE_INSERT_POINT_NOT_FOUND')

override = r'''
# AGAPE_R31_10_RELIABILITY_FIXES_BEGIN
# Promoted from the R2.1 side-load regression work only after isolated testing.
# Scope: Quotation type, PPTX ingestion, section normalization/validation,
# and replacement (not duplication) of repaired weak sections.

QUOTATION_HEADINGS = [
    "Quotation",
    "Customer and Project",
    "Scope of Works",
    "Flooring Areas",
    "Pricing",
    "Programme and Timescale",
    "Payment Terms",
    "Quotation Validity",
    "Acceptance",
]
WRITER_TYPES["Quotation"] = list(QUOTATION_HEADINGS)
APP_TYPES["writer"] = list(WRITER_TYPES.keys())

_R310_ORIGINAL_EXTRACT_INSTRUCTION = _extract_instruction_document

def _r310_display_text(value):
    s = unicodedata.normalize("NFKC", str(value or ""))
    replacements = {
        "\u252c\u00fa": "\u00a3", "\u00c2\u00a3": "\u00a3", "\u00c2\u20ac": "\u20ac",
        "\u00e2\u20ac\u201c": "-", "\u00e2\u20ac\u201d": "-", "\u00e2\u20ac\u02dc": "'", "\u00e2\u20ac\u2122": "'", "\u00e2\u20ac\u0153": '"',
    }
    for bad, good in replacements.items():
        s = s.replace(bad, good)
    return s

def _r310_heading_key(value):
    s = _r310_display_text(value)
    try:
        s = clean_inline(s)
    except Exception:
        pass
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s).casefold()).strip()

def _r310_section_heading(value):
    if isinstance(value, dict):
        for key in ("heading", "title", "name", "section"):
            raw = value.get(key)
            if raw is not None and str(raw).strip():
                return _r310_display_text(raw).strip()
        return ""
    raw = _r310_display_text(value).strip()
    if raw.startswith("{") and raw.endswith("}"):
        try:
            import ast
            parsed = ast.literal_eval(raw)
            if isinstance(parsed, dict):
                return _r310_section_heading(parsed)
        except Exception:
            pass
    return raw

def _r310_normalise_sections(values):
    if values is None:
        return []
    if isinstance(values, (str, dict)):
        values = [values]
    out, seen = [], set()
    for value in values:
        heading = _r310_section_heading(value)
        key = _r310_heading_key(heading)
        if heading and key and key not in seen:
            out.append(heading)
            seen.add(key)
    return out

def _extract_instruction_document(path, max_chars=250000):
    path = Path(path)
    if path.suffix.lower() != ".pptx":
        return _R310_ORIGINAL_EXTRACT_INSTRUCTION(path, max_chars)
    parts = []
    prs = Presentation(str(path))
    for idx, slide in enumerate(list(prs.slides)[:120], 1):
        parts.append(f"# SLIDE {idx}")
        for shape in slide.shapes:
            if hasattr(shape, "text") and str(shape.text).strip():
                parts.append(str(shape.text))
    return clean_text("\n".join(parts))[:max_chars]

def _required_sections(plan):
    sections = _r310_normalise_sections((plan or {}).get("required_sections") or [])
    if (plan or {}).get("doc_type") == "Business Proposal":
        existing = {_r310_heading_key(x) for x in sections}
        for h in REQUIRED_PROPOSAL_HEADINGS:
            if _r310_heading_key(h) not in existing:
                sections.append(h)
                existing.add(_r310_heading_key(h))
    return sections or ["Overview", "Findings", "Recommendations"]

def parse_headings(content):
    return [_r310_display_text(clean_inline(m.group(1))) for m in re.finditer(r"(?m)^#{1,3}\s+(.+?)\s*$", str(content or ""))]

def _r310_min_section_chars(doc_type, heading):
    key = _r310_heading_key(heading)
    compact = (
        "quotation validity", "proposal validity", "validity", "payment terms",
        "commercial terms", "pricing", "price", "subtotal", "total", "vat",
        "flooring areas", "areas", "acceptance", "signature", "decision requested",
    )
    if any(x in key for x in compact):
        return 8
    if doc_type == "Quotation":
        return 35
    if doc_type in ("Business Letter", "Meeting Minutes"):
        return 40
    if doc_type == "Project Plan":
        return 70
    if doc_type in ("Business Proposal", "Business Report", "Technical Report"):
        return 120
    return 80

def validate_generated_document(doc_type, content, required_sections):
    required = _r310_normalise_sections(required_sections)
    heads = parse_headings(content)
    found_keys = {_r310_heading_key(x) for x in heads}
    missing = [h for h in required if _r310_heading_key(h) not in found_keys]
    bodies = {}
    blocks = re.split(r"(?m)^#{1,3}\s+", str(content or ""))[1:]
    for block in blocks:
        lines = block.splitlines()
        heading = _r310_display_text(clean_inline(lines[0]) if lines else "")
        body = "\n".join(lines[1:]).strip()
        key = _r310_heading_key(heading)
        if key and (key not in bodies or len(body) > len(bodies[key])):
            bodies[key] = body
    short = []
    for h in required:
        key = _r310_heading_key(h)
        if key in found_keys and len(bodies.get(key, "")) < _r310_min_section_chars(doc_type, h):
            short.append(h)
    return {"ok": not missing and not short, "headings": heads, "missing": missing, "short": short, "chars": len(str(content or ""))}

def _r310_markdown_blocks(text):
    return list(re.finditer(r"(?ms)^(#{1,3})\s+(.+?)\s*\n(.*?)(?=^#{1,3}\s+|\Z)", str(text or "")))

def _merge_repaired_sections(draft, patch, targets):
    target_keys = {_r310_heading_key(x) for x in targets}
    patch_map = {}
    for match in _r310_markdown_blocks(patch):
        heading = _r310_display_text(match.group(2)).strip()
        key = _r310_heading_key(heading)
        if key in target_keys:
            patch_map[key] = "# " + heading + "\n" + match.group(3).strip()
    if not patch_map:
        return draft
    matches = _r310_markdown_blocks(draft)
    if not matches:
        return draft.rstrip() + "\n\n" + "\n\n".join(patch_map.values())
    prefix = draft[:matches[0].start()].rstrip()
    out = [prefix] if prefix else []
    used = set()
    for match in matches:
        heading = _r310_display_text(match.group(2)).strip()
        key = _r310_heading_key(heading)
        if key in patch_map:
            if key not in used:
                out.append(patch_map[key]); used.add(key)
            continue
        out.append(match.group(0).strip())
    for key, block in patch_map.items():
        if key not in used:
            out.append(block)
    return "\n\n".join(x for x in out if x).strip()

def repair_draft(ctx, plan, research, draft, requested_model="auto", max_rounds=2):
    sections = _required_sections(plan); models = []
    for round_index in range(max(1, int(max_rounds))):
        audit = validate_generated_document(plan.get("doc_type"), draft, sections)
        needs = []
        seen = set()
        for h in audit.get("missing", []) + audit.get("short", []):
            key = _r310_heading_key(h)
            if key and key not in seen:
                needs.append(h); seen.add(key)
        if not needs:
            return draft, audit, models
        system = (
            "You repair professional documents. Return only the exact missing or weak sections requested, "
            "each starting with an exact # heading. Replace weak sections with substantive content. "
            "Use provided facts and research only. Do not invent facts."
        )
        prompt = (
            "FORM_STATE:\n" + json.dumps(_ai_context_snapshot(ctx, 0, 32, False), ensure_ascii=False)
            + "\nPLAN:\n" + json.dumps(plan, ensure_ascii=False)
            + "\nRESEARCH:\n" + _research_for_prompt(research, 9000)
            + "\nCURRENT_DOCUMENT:\n" + draft[-14000:]
            + "\n\nREWRITE THESE SECTIONS COMPLETELY:\n"
            + "\n".join("# " + x for x in needs)
        )
        r = ai_generate(prompt, system, max_tokens=2400, requested_model=requested_model, timeout=240, task="repair")
        patch = str(r.get("content") or "").strip()
        models.append({"provider": r.get("provider"), "model": r.get("model"), "round": round_index + 1})
        draft = _merge_repaired_sections(draft, patch, needs)
    return draft, validate_generated_document(plan.get("doc_type"), draft, sections), models

# AGAPE_R31_10_RELIABILITY_FIXES_END
'''

text = text[:insert_at] + '\n' + override + text[insert_at:]
p.write_text(text, encoding='utf-8')
print('DOCUMENT_STUDIO_PATCH=PASS')
print('DOCUMENT_STUDIO_VERSION=R31.10')