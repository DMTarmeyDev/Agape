# Agape V5.6 - Public Research + Project Continuity

- Public research gaps are separated from user/private missing information.
- The Review page hides the extra-information section when nothing useful can be researched.
- When public evidence could improve a project, a collapsed **Extra information could be gathered** menu appears with an explicit Gather button.
- Gather public information now invokes the real Document Studio research stack (SearXNG, Brave where configured, DuckDuckGo fallback, Companies House/academic/video routes where relevant, Trafilatura/BeautifulSoup extraction).
- Public evidence is passed into the AI form-fill prompt with URLs; unsupported/private facts remain unresolved.
- New pasted/uploaded work is automatically saved as a reusable user project and appears in Projects/Workspace.
- Download Manager retains multiple projects/jobs, persists locally, and hydrates completed file entries from Mainframe history.
- Workflow Bridge wrapper status is unwrapped before Mainframe history synchronisation.
- Document Studio recreates writable runtime directories before CLI/provider work to reduce stale-path WinError failures after moves/reinstalls.
- Bundles a ready-to-use North West commercial flooring recovery/recycling feasibility research project.
- Browser QA now targets the top-level Advanced summary explicitly, avoiding Playwright strict-mode collisions with nested summaries.
