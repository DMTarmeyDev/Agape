# Agape AI Studio - Production Process

## Model

This follows standard software-production ideas: small changes, targeted verification, integration tests, release-candidate gates, immutable releases, rollback, traceable requirements and machine-readable evidence.

## Fast patch loop

1. Patch the smallest responsible component.
2. Compile/syntax-check only changed code.
3. Run its targeted component tests.
4. Run the live test template for that subsystem.
5. Repair until the narrow gate is PASS.
6. When the subsystem is complete, run the entire required Studio suite.
7. Build the release package.
8. Extract the exact package into `%TEMP%` and test those bytes again.
9. Promote only when every required quality item is PASS.
10. Publish the Markdown report and quality ledger; closed items appear under **Passed**.

## When full testing is required

Full regression is required when shared API/context/startup code changes, the database schema changes, a subsystem is complete, or before any package is promoted.

A small internal change does **not** trigger the full suite until its targeted gate passes.

## Aider position

Aider sits between planning and Studio testing:

`Task -> Tool Planner -> Aider (when suitable) -> changed files -> Studio tests -> PASS/repair -> checkpoint`

Aider never owns release acceptance. Deterministic formatter/linter/spelling jobs stay with extensions. Aider is optional and can be replaced without changing the Studio core.

## Evidence

- Terminal: short `GATE::...=PASS/FAIL` lines only.
- Markdown: complete evidence and AI repair queue.
- JSON: machine-readable quality state.
- Studio `Passed` menu: every completed requirement backed by a successful release gate.
- Failed/open items remain visible until closed; they are never converted into PASS by documentation alone.
