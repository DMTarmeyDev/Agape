# Agape V3.8 - Live Progress Heartbeat

- Fixed long document-generation stages that could appear frozen around 45%.
- Document Studio R31.12 now reports planning, research, drafting, validation, export and finalisation milestones.
- A monotonic heartbeat advances safely within the current stage while a long AI provider call is still active, without claiming completion.
- Workflow Bridge R3.4 propagates live Document Studio activity to the parent Mainframe job.
- Mainframe shows elapsed `still active` status if exact progress has not changed for 20 seconds.
- Progress never moves backwards and only reaches 100% on actual completion.
- V3.7 side-by-side Windows upgrade safety remains in place.
