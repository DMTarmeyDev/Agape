<!-- AGAPE_GITHUB_BADGES_BEGIN -->
[![CI](https://github.com/DMTarmeyDev/Agape/actions/workflows/ci.yml/badge.svg)](https://github.com/DMTarmeyDev/Agape/actions/workflows/ci.yml)
[![CodeQL](https://github.com/DMTarmeyDev/Agape/actions/workflows/codeql.yml/badge.svg)](https://github.com/DMTarmeyDev/Agape/actions/workflows/codeql.yml)
[![GitHub stars](https://img.shields.io/github/stars/DMTarmeyDev/Agape?style=flat)](https://github.com/DMTarmeyDev/Agape/stargazers)
[![GitHub issues](https://img.shields.io/github/issues/DMTarmeyDev/Agape)](https://github.com/DMTarmeyDev/Agape/issues)
[![Last commit](https://img.shields.io/github/last-commit/DMTarmeyDev/Agape)](https://github.com/DMTarmeyDev/Agape/commits/main)
<!-- AGAPE_GITHUB_BADGES_END -->
Agape

Human-first AI project development, automation, and workspace software.

Agape is an experimental AI workspace designed around a simple idea:

The user should decide what they want done. Agape should handle how it gets done.

Instead of making ordinary users manage AI models, agents, databases, terminals, providers, or automation pipelines, Agape aims to hide that complexity behind a clear task-oriented interface.

Project Status

Status: Early Alpha / Active Development

Agape is under active development. Some features are incomplete, experimental, or may change between builds.

The project is currently focused on:

Making the interface simple for non-technical users

Automatically choosing suitable AI models and tools

Improving project execution and progress reporting

Making errors visible and understandable

Connecting local and online AI providers

Building reliable testing, checkpoints, rollback, and recovery

Reducing unnecessary technical controls from the main interface

Keeping advanced tools available without forcing normal users to understand them

Agape should not yet be treated as production-ready software.

What Agape Is

Agape is intended to become a single workspace where a user can:

Describe what they want to achieve

Create or open a project

Give Agape instructions, documents, or files

Press Start Work

See clear project progress

Allow Agape to select suitable models, tools, and workflows automatically

Review results, files, errors, and decisions

Continue improving the project from the same workspace

The long-term goal is for technical complexity to remain behind the scenes unless the user deliberately opens advanced settings.

Human-First Design

The normal Agape workflow should feel like this:

Tell Agape what you want
        |
        v
Create / Open Project
        |
        v
Add instructions or files
        |
        v
Start Work
        |
        v
Agape plans the work
        |
        v
Agape selects models + tools
        |
        v
Work runs automatically
        |
        v
Progress is shown clearly
        |
        v
Result / error / next action

The normal user should not need to understand:

Model names

Model providers

Agent architecture

Database internals

Terminal commands

Automation engines

API routing

Diagnostic systems

Internal project IDs

Artifact storage structure

These can still exist as advanced features.

Core Principles

1. Human first

Use normal language instead of technical language wherever possible.

2. One obvious next step

The interface should make it clear what the user should do next.

3. Automatic routing

Agape should automatically choose an appropriate available AI model, provider, tool, or workflow whenever practical.

4. Progressive disclosure

Simple controls first. Advanced controls only when requested.

5. Visible progress

When work starts, Agape should clearly show that the project has started and display its progress.

6. Useful errors

A task must never simply say:

Completed with error

without explaining what failed.

Errors should show:

What failed

Which step failed

A useful explanation

Whether anything completed successfully

What Agape will try next

What the user can do if intervention is required

7. Safe automation

Automated changes should use testing, checkpoints, validation, and rollback where appropriate.

Main Features

Agape is being developed around the following capabilities.

Projects

Create, open, continue, and manage AI-assisted projects.

A project should contain the context required to continue work without forcing the user to repeatedly explain the same task.

Start Work

A clear Start Work action begins the project workflow.

After starting, the UI should show:

Project started

Current stage

Current task

Progress

Completed steps

Errors

Final result

Suggested next action

Automatic AI Model Routing

Agape is designed to work with multiple AI models rather than being tied to one model.

The routing layer can eventually choose between:

Local models

Online models

Coding models

Reasoning models

Fast models

Higher-quality models

Specialist tools

Model selection should normally be automatic.

Advanced users may still be given manual controls.

Local AI

Agape can be developed to work with local model systems such as Ollama and other compatible local inference tools.

Local models can be useful for:

Private work

Repetitive tasks

Low-cost processing

Offline operation

Fast lightweight tasks

Online AI Providers

The architecture is intended to support online AI providers alongside local models.

Provider connections should be optional and securely configured.

Documents

Agape includes work toward document creation and document-processing workflows.

The intended flow is:

User request
    |
    v
Collect required information
    |
    v
Choose suitable AI/tool
    |
    v
Generate document
    |
    v
Validate output
    |
    v
Save / export

File Input

Projects should be able to receive information by:

Typing or pasting text

Uploading a file

Using a template

Reusing existing project information

Templates

Templates can provide structured starting points for repeatable work without forcing the user to manually construct a prompt.

Artifacts

Agape can track useful project outputs such as:

Generated files

Builds

Releases

Test reports

Checkpoints

Backups

Instructions

Summaries

Exports

Source code should not be unnecessarily duplicated just to create more artifacts.

Database

Persistent project information can be stored in a database so projects can be resumed and inspected.

The database layer should remain largely invisible to ordinary users.

Testing

Testing is a major part of the Agape architecture.

Planned and developing test coverage includes:

Unit tests

API tests

Browser tests

UI interaction tests

Workflow tests

Security tests

Installation tests

Regression tests

Model/provider tests

The goal is eventually to automatically test every important button, link, form, and project workflow before a release is considered usable.

Checkpoints and Rollback

Before major automated changes, Agape should be able to create a checkpoint.

If validation fails, the system should be capable of returning to a known-good state.

Automation

Agape is intended to perform multi-step work rather than only generating chat responses.

Examples include:

Creating code

Editing code

Running tests

Diagnosing failures

Repairing problems

Creating documents

Processing files

Managing project artifacts

Running development workflows

Optional Developer Tools

Developer-oriented tools may be added as optional components rather than forced into the normal interface.

Examples may include:

Aider

Coding assistants

Test runners

Browser automation

Local model runtimes

Development libraries

Diagnostic tools

These should be installable or enabled only when useful.

Simplified Main Interface

The main interface is intended to focus on a small number of user-facing areas.

Home

Create Project
Open Project

Ask Agape

Recent Work

Settings

Technical areas should normally be moved into Settings, Advanced, or Developer Tools rather than filling the primary navigation.

Example User Workflow

Create a project

The user describes the outcome:

Create a small website for my flooring business.

Agape gathers missing information

Agape asks only for information that is genuinely required.

Start work

The user presses:

Start Work

Progress appears

For example:

Project started

[â– â– â– â– â– â– â–¡â–¡â–¡â–¡] 60%

Completed:
âœ“ Project plan
âœ“ Page structure
âœ“ Initial code

Working on:
â†’ Testing website

Next:
â—‹ Repair any test failures
â—‹ Package completed project

If something fails

Instead of hiding the failure:

Testing failed

Problem:
The Contact page returned a 404 error.

Completed successfully:
âœ“ Home page
âœ“ Services page
âœ“ Navigation

Agape is now:
â†’ Checking the missing Contact route

Technical details
[Show]

Suggested Project Structure

The exact repository structure may evolve, but the project should remain modular.

agape/
â”‚
â”œâ”€â”€ app/
â”‚   â”œâ”€â”€ ui/
â”‚   â”œâ”€â”€ projects/
â”‚   â”œâ”€â”€ workflows/
â”‚   â”œâ”€â”€ routing/
â”‚   â”œâ”€â”€ providers/
â”‚   â”œâ”€â”€ documents/
â”‚   â”œâ”€â”€ artifacts/
â”‚   â”œâ”€â”€ database/
â”‚   â””â”€â”€ settings/
â”‚
â”œâ”€â”€ tests/
â”‚   â”œâ”€â”€ unit/
â”‚   â”œâ”€â”€ api/
â”‚   â”œâ”€â”€ browser/
â”‚   â”œâ”€â”€ workflow/
â”‚   â””â”€â”€ security/
â”‚
â”œâ”€â”€ tools/
â”‚   â”œâ”€â”€ installers/
â”‚   â”œâ”€â”€ diagnostics/
â”‚   â””â”€â”€ optional/
â”‚
â”œâ”€â”€ docs/
â”‚
â”œâ”€â”€ scripts/
â”‚
â”œâ”€â”€ README.md
â”œâ”€â”€ LICENSE
â””â”€â”€ .gitignore

Provider Architecture

Agape should avoid hard-coding the whole application to one AI provider.

A simplified architecture is:

User Task
   |
   v
Agape Task Planner
   |
   v
Model / Tool Router
   |
   +--> Local Model
   |
   +--> Online AI
   |
   +--> Coding Tool
   |
   +--> Document Tool
   |
   +--> Browser / Test Tool
   |
   v
Validation
   |
   v
Result

A provider failure should not automatically mean the whole project fails when another suitable provider or tool is available.

Error Handling

All important failures should be recorded in a structured form.

Example:

{
  "status": "failed",
  "stage": "document_generation",
  "message": "The selected AI provider did not return a valid document.",
  "completed_steps": [
    "project_loaded",
    "requirements_checked"
  ],
  "next_action": "try_alternative_provider"
}

The normal UI should convert this into clear human language.

Raw technical details should remain available under an expandable section for debugging.

Security Direction

Agape may eventually connect to accounts, AI providers, email services, files, local applications, and external systems.

Security principles include:

Never store passwords in plaintext

Prefer OAuth where supported

Encrypt stored secrets

Use operating-system credential protection where practical

Separate test and production accounts

Use least-privilege permissions

Validate uploaded files

Validate external input

Keep security logs

Avoid exposing internal services directly to the public internet

Require confirmation for sensitive or destructive operations

Test authentication and authorization boundaries

Keep secrets out of Git repositories

Never commit API keys, passwords, OAuth tokens, private certificates, or other secrets to GitHub.

Installation

Installation is currently evolving and may differ between development builds.

A future stable installation flow should aim to be:

Download
   |
   v
Run installer
   |
   v
Agape checks required components
   |
   v
Choose optional components
   |
   v
Install
   |
   v
Run automated self-test
   |
   v
Open Agape

Optional dependencies should be clearly separated from required dependencies.

Development Goals

The immediate development priorities are:

Make Start Work reliably launch a project

Add a persistent project-started status banner

Add live project progress

Show current workflow stage

Replace vague error states with useful error information

Automatically choose an appropriate AI provider/model

Add provider fallback when possible

Simplify project creation

Support text input and file upload from the same workflow

Improve template selection

Improve document-generation reliability

Test every main navigation link

Test every important button

Test every form

Add end-to-end browser testing

Improve installation validation

Improve checkpoint and rollback handling

Reduce duplicate/unnecessary artifacts

Improve database management

Move technical controls into Advanced Settings

Improve security validation

Package reliable Windows releases

Longer-Term Roadmap

Phase 1 â€” Reliable Core

Projects

Start Work

Progress reporting

Error reporting

File input

Templates

Persistent project state

Phase 2 â€” Intelligent Routing

Automatic model selection

Local/online provider routing

Provider fallback

Tool selection

Cost/performance-aware routing

Phase 3 â€” Automated Development

Code generation

Repository-aware editing

Automated testing

Browser testing

Repair loops

Checkpoints

Rollback

Phase 4 â€” Connected Workspace

Documents

Email

Cloud storage

Communication tools

External services

Optional plugins/connectors

Phase 5 â€” Multi-Device Agape

Windows desktop

Web access

Lightweight mobile interface

Server-assisted heavy processing

Advanced Mode

Advanced users and developers may need access to:

Model selection

Provider configuration

Model routing logs

Agent/workflow details

Database tools

Terminal history

Diagnostics

Test reports

Artifact management

Developer tools

Security diagnostics

These controls should remain available without becoming requirements for normal use.

Repository Rules

Contributors should follow these basic principles:

Keep the normal UI human-readable.

Do not expose technical controls without a user need.

Do not hard-code the application to one AI model.

Keep model/provider logic modular.

Add tests for important new behaviour.

Report errors clearly.

Avoid silent failures.

Keep secrets out of source control.

Prefer small replaceable modules over tightly coupled code.

Preserve rollback paths for risky automated changes.

Testing Philosophy

A feature is not complete merely because the code runs once.

For major workflows, testing should attempt to verify:

Open page
    |
    v
Use control
    |
    v
Submit realistic data
    |
    v
Verify result
    |
    v
Verify stored state
    |
    v
Verify error path
    |
    v
Repeat after restart

Important workflows should eventually be tested automatically before release.

Current Limitations

Because Agape is still in early development:

Some UI controls may not yet be connected

Some workflows may fail without enough diagnostic information

Provider integrations may require additional configuration

Installation scripts may change

Browser and desktop builds may behave differently

Automatic model routing is still being improved

Security work is ongoing

APIs and database schemas may change

Documentation may lag behind experimental builds

Please report reproducible problems with enough information to identify the failing build and workflow.

Contributing

Contributions, testing, ideas, and bug reports are welcome.

When reporting a bug, include where possible:

Agape build/version

Windows or operating-system version

What you clicked

What you expected

What happened

Error message

Relevant log output

Whether the issue is reproducible

Do not include passwords, API keys, tokens, or private account information in bug reports.

Vision

Agape is not intended to be another interface that requires the user to become an AI engineer.

The intended experience is:

Tell Agape the result you need. Agape works out the technical path, shows its progress, explains problems clearly, and gives you the finished work.

The complexity can exist.

The user should not have to carry it.

License

A licence has not yet been specified for this repository.

Before publishing the project for public reuse, add an appropriate LICENSE file and update this section.

Disclaimer

Agape is experimental software under active development.

Review important generated outputs before relying on them, especially where actions affect production systems, security, financial information, legal documents, or external accounts.
<!-- AGAPE_GITHUB_COMMUNITY_BEGIN -->
## Community, support and project status

Agape is under active **alpha** development. The project is focused on human-first AI workflows, model/provider flexibility, safe automation, testing, checkpoints, and rollback.

- **Questions and ideas:** use [GitHub Discussions](https://github.com/DMTarmeyDev/Agape/discussions).
- **Bugs and feature requests:** use [GitHub Issues](https://github.com/DMTarmeyDev/Agape/issues).
- **Contributing:** see [CONTRIBUTING.md](CONTRIBUTING.md).
- **Support:** see [SUPPORT.md](SUPPORT.md).
- **Security:** see [SECURITY.md](SECURITY.md) and avoid posting vulnerabilities publicly.
- **Roadmap:** see [ROADMAP.md](ROADMAP.md).

If Agape is useful to you, starring the repository helps other people discover the project.
<!-- AGAPE_GITHUB_COMMUNITY_END -->
