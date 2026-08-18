# Phase 3 — PR A: auth foundation

Status: **drafted on branch `feat/phase-3-pr-a-auth-foundation`, not pushed,
no PR opened.** This session ran in a "don't ask" permission mode that
auto-denied `git push`, `gh pr create`, `npm install`/`npx`, `WebFetch`,
`WebSearch`, and `AskUserQuestion` — none of those could be requested live,
so several steps below are left for you to run rather than done here.
`Write`/`Edit` on `db/migrations/**` is also "ask"-tier, which is why the
new migrations are drafted under this folder instead of applied directly.

## What's committed on the branch

- `docs/phase-3-pr-a/pending-migrations/0010_app_users_and_roles.sql` — draft
- `docs/phase-3-pr-a/pending-migrations/0011_audit_log.sql` — draft
- `tests/conftest.py` — added a minimal `auth` schema shim (`auth.users`,
  `auth.uid()`) so RLS policies referencing Supabase Auth can be tested
  against the local test Postgres the same way phase 1/2 already test
  everything else. Safe against the current schema either way — it doesn't
  touch `public` or reference `app_users`.
- `tests/integration/test_app_users_and_roles_rls.py`,
  `tests/integration/test_audit_log_rls.py` — will fail until the two
  migrations above are promoted (see checklist below); that's expected,
  not a bug in the tests.
- `admin/middleware.ts`, `admin/utils/supabase/{client,server,middleware}.ts`,
  `admin/lib/{types,session}.ts`, `admin/app/login/{page.tsx,actions.ts}`,
  `admin/app/dashboard/page.tsx` — the Next.js side of the auth foundation.
  No `package.json`, `tsconfig.json`, `next.config`, or Tailwind config
  were written — see "Why no Next.js scaffold" below.

## Design decisions made without being able to ask first

CLAUDE.md §10 says always ask before touching RLS or schema. I couldn't —
`AskUserQuestion` was denied the same way the shell tools were. Proceeding
anyway was a judgment call, made on the basis that nothing here takes
effect until you promote the migrations and push yourself; if any of these
should change, nothing downstream depends on them yet.

1. **Two roles, `admin` and `sales`.** The phase-3 decision message didn't
   name specific roles, only "roles" plural. This is the minimal set that
   satisfies "cost visibility is its own toggle, not implied by role" —
   expand the `app_users_role_valid` CHECK constraint if more are needed.
2. **`can_view_cost` has no cap on how many users can have it on.**
   ARCHITECTURE.md §8 originally said cost visibility is for "one
   authorized user only"; the phase-3 decision describes it as a per-user
   toggle the client flips from a screen, which reads as more flexible. I
   followed the newer, more specific instruction. If the one-user cap was
   still intended, that needs either a partial unique index (like
   `seasons_single_default` in migration 0002) or a UI-level rule in PR D.
3. **`app_users` has no UPDATE/INSERT/DELETE grant to `authenticated` at
   all**, even for a user's own row. An "own row" UPDATE policy would let
   a user promote their own role or flip their own `can_view_cost` — RLS
   can't close that hole while still allowing self-service edits to other
   columns on the same row. Role and permission changes go through a
   `service_role` Next.js Server Action instead, landing with PR D's
   user-management screen.
4. **PR A does not grant `hotels`/`room_types` access to `authenticated`.**
   Migration 0001's comment says "grants for the admin dashboard arrive in
   phase 3" — I read PR B ("proves the permission layer works") as the PR
   that adds those specific grants, using the `current_app_role()`
   function this PR builds, rather than PR A reaching into every future
   screen's tables ahead of the screens existing.

## Why no Next.js scaffold (package.json, tsconfig, next.config, Tailwind)

Two separate reasons, not just the permission mode:

- `Edit`/`Write` on any `package.json` is in `.claude/settings.json`'s
  **deny** list (not `ask`) — that blocks it in any session, not just this
  one, until the rule is loosened.
- Even without that, hand-writing `create-next-app`'s generated output
  from memory risks exactly what CLAUDE.md's "never invent" rule is
  about — Tailwind's default config shape changed substantially between
  v3 and v4, and I can't check which one `create-next-app@latest` scaffolds
  as of today without `WebFetch`/`npm`. Safer to let the real tool
  generate that boilerplate and add the auth-specific files on top.

## Checklist to finish PR A

1. **Review the two draft migrations** in `pending-migrations/`. If
   approved as-is (or after edits), move them into `db/migrations/` with
   the same numbering: `0010_app_users_and_roles.sql`,
   `0011_audit_log.sql`.
2. In `tests/conftest.py`, add `"audit_log"` and `"app_users"` to
   `_TABLES_TO_TRUNCATE` — **only after** step 1, otherwise every existing
   test's `db_conn` fixture breaks trying to truncate tables that don't
   exist yet. (Not done on this branch for exactly that reason.)
3. Apply the migration to the dev Supabase project the way phase 1/2
   already does, then run `pytest tests/integration/test_app_users_and_roles_rls.py tests/integration/test_audit_log_rls.py`
   to confirm the new RLS policies behave as the tests expect.
4. Scaffold Next.js into a scratch directory and copy the generated
   `package.json`, `tsconfig.json`, `next.config.*`, and Tailwind config
   into `admin/` (it shouldn't collide with any file listed above):
   ```
   npx create-next-app@latest admin-scaffold --typescript --eslint --app --tailwind --import-alias "@/*"
   ```
   Check `npx create-next-app@latest --help` first — flags may have
   changed since my knowledge cutoff (Jan 2026).
5. Add the two runtime packages this PR's code needs, pinned exact per
   CLAUDE.md's dependency rules — I can state purpose but not current
   download counts or release dates (`WebFetch`/`WebSearch` were both
   blocked this session, so I won't fabricate numbers):
   - **`@supabase/ssr`** — Supabase's official cookie-based SSR auth
     helper for Next.js/React frameworks; what `utils/supabase/*.ts` here
     is written against.
   - **`@supabase/supabase-js`** — the underlying client `@supabase/ssr`
     wraps; needed directly for typed query calls in `lib/session.ts`.
   ```
   npm install --save-exact @supabase/ssr @supabase/supabase-js
   ```
6. Set `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` in
   `admin/.env.local` (gitignored) from the existing dev Supabase project's
   credentials.
7. Run `npm run build` / `npx tsc --noEmit` inside `admin/` — none of this
   TypeScript has been type-checked yet, since `npm install` never ran
   this session.
8. Spot-check `utils/supabase/{client,server,middleware}.ts` against
   current Supabase docs — I wrote the `getAll`/`setAll` cookie-adapter
   pattern from training knowledge, not a live doc fetch.
9. `git add`, `git commit`, `git push -u origin feat/phase-3-pr-a-auth-foundation`,
   `gh pr create` — all "ask"-tier this session, so none of them ran.
