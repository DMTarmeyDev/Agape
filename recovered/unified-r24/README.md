# Agape Unified R3.0 — Human First

Human-first Agape document/project front end with selectable AI router and subject-aware research-source routing.

## Local services
- Core R8: 8797
- Document Studio R31.11: 8800
- Work Engine R1.3: 8820
- Unified R3.0: 8840

## Current human-first behaviour
- Gold Standard **model selector** in Step 3 and Settings.
- Automatic Top N reviewer selection from 2 to 10 connected AI provider/model pairs; default is 3 for faster normal work; 2–10 remains selectable.
- Custom reviewer mode lets the user tick the exact connected AI/model pairs to use.
- Optional lead-reviewer selector; Automatic remains the recommended default.
- If 10 are requested but only 6 are connected, Agape uses all 6, records **6/10 available**, and never pretends 10 reviewed the work.
- Every Gold Standard job snapshots requested reviewers, actual reviewers used, selection mode, and lead choice into job/result history.
- Removes the old hidden four-reviewer cap.
- Proposal-readiness stage after one-document intake remains: **Find Missing Information with AI**, **Questions only you can answer**, then **Go ahead → choose quality**.
- Research Sources manager remains in Settings with top-10 subject-aware research-source ranking.
- Preserves Agape Router as default, with LiteLLM optional.

## Research catalogue
Companies House, ONS, FCA Register/Handbook, Contracts Finder/Find a Tender, OpenCorporates, Crunchbase, Dealroom, Apollo, GDELT, Google Trends, X, YouTube, LinkedIn and Reddit. Agape chooses the best ten for the actual subject rather than always using the same ten.

## Run
`START-AGAPE-UNIFIED.ps1`

Open http://127.0.0.1:8840/
## Installer repair R1
The packaged fake integration test now isolates LOCALAPPDATA as well as AGAPE_UNIFIED_DATA, so a real R2.3/R2.4 migrated setup cannot be mistaken for a failed fresh-install test. Live router/theme settings are still migrated and preserved normally.


## Automatic document validation recovery

Repair R1 handles Document Studio `GENERATED_DOCUMENT_VALIDATION_FAILED` responses as a recoverable quality gate instead of immediately failing the job.

For business proposals/plans, Unified now adds an explicit pre-generation quality contract covering TAM / SAM / SOM, Customer Personas, Recommendation / Next Step, and Sources / Evidence. If Document Studio still reports missing or short sections, Unified parses the exact validator result, runs up to two targeted regeneration/repair passes with deep research/RAG enabled and the active router's repair route, revalidates, records the repair history in the job result, and only surfaces a failure if the repaired document still cannot pass validation.
