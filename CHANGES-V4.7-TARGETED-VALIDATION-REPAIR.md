# V4.7 targeted validation repair

- Document Studio updated to R31.16.
- Repairs missing/short document sections one section at a time instead of sharing one repair response across multiple headings.
- Each repair prompt includes the exact validator minimum and a higher target body length.
- A strict retry is issued when a repair response is still undersized or uses the wrong heading.
- Repaired sections replace the weak section rather than being appended as duplicate headings.
- Required sections that are genuinely missing remain a hard validation failure.
- If all required sections are present but one remains short after all targeted repairs, the document is still built and returned with `SECTIONS_REMAIN_SHORT_AFTER_TARGETED_REPAIR` rather than being discarded.
- V4.6 safe runtime cutover/watchdog shutdown is preserved.
- Regression coverage includes the exact Findings + Analysis short-section failure.
