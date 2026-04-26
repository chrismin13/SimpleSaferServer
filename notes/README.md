# Project Notes

This directory keeps chronological development notes for substantial SimpleSaferServer tasks.
Notes are working history and handoff context. They are not the canonical source of truth for
current behavior, commands, architecture, or user/operator guidance.

## Naming

- Use four-digit sequential numbers: `0001`, `0002`, `0003`.
- Use short kebab-case titles.
- Never reuse a number, even if a note is deleted during local drafting.

Examples:

- `0001-monolith-to-package-refactor.md`
- `0002-systemd-adapter.md`
- `0003-drive-health-ui-fix.md`

## When To Add A Note

Add a note for work that has meaningful task memory:

- Multi-step refactors.
- Architecture or dependency decisions.
- Work with operational assumptions future maintainers might forget.
- Debugging sessions that reveal important behavior.
- Changes that need follow-up debt tracked beyond a single commit.

Tiny behavior fixes can skip a note unless they reveal a decision, hidden assumption, or useful
handoff context.

## What Notes Must Not Replace

- User/operator behavior belongs in `docs/*.md`.
- Contributor standards belong in `docs/development.md`.
- Durable architecture guidance belongs in `docs/architecture.md`.
- Hidden operational assumptions near code should still be captured in focused comments.
- Related links in `index.html` must still be checked for docs changes.
- `uninstall.sh` must still be checked when files, generated state, services, timers, config, or
  directories are added.

## Note Lifecycle

Keep notes indefinitely. If a note contains information that becomes durable project knowledge,
move that knowledge into the appropriate canonical docs and leave the note as historical context.
