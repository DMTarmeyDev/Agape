# Agape V5.6.1 R2.3 - Saved Project Context Repair

- Fixes auto-saved project messages that used literal `\n` markers instead of real line breaks.
- Recovers older saved projects by normalising legacy escaped line breaks before deterministic fact extraction.
- Preserves explicit labelled facts from saved project context before AI form completion, including organisation, industry, geography, product/service, budget and success measures.
- Fixes public-research evidence assembly so evidence blocks use real line breaks.
- Improves persistent project naming by preferring organisation/purpose/timeline and meaningful source filenames over vague task labels such as `facts` or repeated generic prompts.
- Review fields no longer display literal `None` values or repeat internal model fallback wording; unresolved private fields are shown as clear human prompts.
- Public research opportunities now use concise human-facing wording when the source has not yet established a value.

Validation: main suite 150/150 PASS; Unified suite 57/57 PASS; full dummy/browser QA 25/25 PASS; browser console errors 0; page errors 0.
