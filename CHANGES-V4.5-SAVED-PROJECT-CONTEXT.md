# V4.5 Saved Project Context Reliability

V4.5 fixes a regression where a saved project could prepare successfully yet show all 17 brief fields as unresolved/None.

- Direct facts from the saved project title/source are extracted before AI form completion and locked against an all-None model response.
- GreenStep-style titles preserve explicit organisation/title prefix, sector phrase, business-plan purpose, year and explicit budget statements without inventing private facts.
- User-authored messages remain authoritative. Substantive assistant project summaries are restored as secondary context, while generic questions, acknowledgements, terminal/code chatter and raw JSON remain excluded.
- Review summary reports established facts separately from unresolved items; literal None values are no longer described as completed fields.
- Intake diagnostics record source_seed_count/source_seed_fields for troubleshooting.
- Document Studio remains R31.15; Unified bridge is R4.5 saved-project-context build.

Validation: 81/81 Mainframe tests and 54/54 workflow tests PASS.
