# OCR Review Loop

## Context

Started an OCR-driven review loop on 2026-05-03 for branch `feat/refactor-style`.

The active tracked diff only changes `AGENTS.md` by adding the managed Open Code Review
instruction block. The `.ocr/` directory is currently untracked setup material from OCR
initialization.

## Decisions

- Review artifacts live in `.ocr/sessions/2026-05-03-feat-refactor-style/`.
- `README.md` remains untouched, per repository instructions.
- The user request contains conflicting commit instructions: "Do not commit any changes" and
  "Make commits at the end of each review and fix round". Treat commits as requiring explicit
  clarification unless the user resolves the conflict.
- Password updates should sync Samba before saving a new app password hash. Samba password changes
  are effectively write-only from the app's perspective because old plaintext passwords are not
  retained, so a failed Samba sync must leave `users.json` on the old usable password.
- The same ordering applies to the legacy migration path that refreshes an existing admin user.
- The migration path should call a named `UserManager` operation for resetting the existing admin
  user instead of reaching into password persistence helpers directly.
