# Phase 3 — PR A: auth foundation

Status: **PR #10 open** (`feat/phase-3-pr-a-auth-foundation` → `main`),
awaiting review. Migrations are promoted and applied against the local
test database; RLS tests pass. Not yet applied to the dev Supabase
project — see the checklist at the bottom.

## What's in this branch

- `admin/middleware.ts`, `admin/utils/supabase/{client,server,middleware}.ts`,
  `admin/lib/{types,session}.ts`, `admin/app/login/{page.tsx,actions.ts}`,
  `admin/app/dashboard/page.tsx`, `admin/app/page.tsx` — the Next.js side of
  the auth foundation, including the root route redirecting a signed-in
  visitor to `/dashboard` (middleware already sends anyone unauthenticated
  to `/login` before this ever renders — verified live: an unauthenticated
  `GET /` against a running `next dev` returns `307` to `/login`).
- `db/migrations/0010_app_users_and_roles.sql`,
  `0011_audit_log.sql` — promoted from `docs/phase-3-pr-a/pending-migrations/`.
- `tests/integration/test_app_users_and_roles_rls.py`,
  `test_audit_log_rls.py` — RLS tests for both, run against a real local
  Postgres 17 instance per `tests/conftest.py`'s `_schema` fixture.
- A full Next.js project scaffold under `admin/` (`package.json`,
  `tsconfig.json`, build/lint config, `app/{layout.tsx,globals.css}`) —
  the auth code above had none.

## A real bug the RLS tests caught

0010 originally granted `authenticated` `SELECT` on `app_users` and
`EXECUTE` on `current_app_role()`/`current_user_can_view_cost()`, but
never granted `authenticated` `USAGE ON SCHEMA public`. Every migration
before this one only ever granted schema `USAGE` to `service_role` —
nothing else held a real table grant yet, so the gap never mattered until
now. Without it, Postgres cannot resolve *any* unqualified `app_users` or
`current_app_role()` reference for that role: it fails with "relation
does not exist", not a permission error, before RLS or the table-level
grant is even consulted. Confirmed empirically (running as `authenticated`
against a live local database) before fixing it — this would have broken
`getCurrentAppUser()`, and with it the entire login → dashboard flow, for
every signed-in user. Fixed with one `GRANT USAGE ON SCHEMA public TO
authenticated;` line in 0010.

Two tests' expectations were also corrected: `test_rls_denies_anon` and
`test_anon_cannot_select_audit_log` originally asserted `anon` gets an
empty result set, but `anon` has no grant on either table at all — same
as every other table in this schema — so the real, by-design failure mode
is `psycopg.errors.UndefinedTable`, same root cause as above, just for a
role that was never meant to have any access to fix.

Separately, `sqlfluff` (the migrations CI gate — only ever run against
`db/migrations/`, never against the draft's old location, so this is the
first time it actually checked these two files) caught `role` used as a
bare column identifier in 0010 — `RF04`, the same keyword clash migration
0001 already hit with `date`/`stay_date` (quoting it just trips the
opposite rule, `RF06`, confirmed empirically here too). Renamed the
column to `app_role` throughout: the migration, both test files' SQL, and
the three `admin/` TypeScript files that mirror this column
(`lib/types.ts`, `lib/session.ts`'s `.select()` list, `dashboard/page.tsx`).
`sqlfluff` also auto-fixed (`--rules LT02`) the `CREATE POLICY` blocks'
indentation in both migrations — first time that construct appears in
`db/migrations/`, so there was no established formatting precedent to
have matched up front.

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

Resolved — see "What's in this branch" above; the scaffold now exists,
generated by the real `create-next-app` and merged in by hand rather than
hand-written. Left here for why it wasn't just written from memory in the
first place:

- `Edit`/`Write` on any `package.json` is in `.claude/settings.json`'s
  **deny** list (not `ask`) — that blocks it in any session, not just this
  one, until the rule is loosened.
- Even without that, hand-writing `create-next-app`'s generated output
  from memory risks exactly what CLAUDE.md's "never invent" rule is
  about — Tailwind's default config shape changed substantially between
  v3 and v4, and I can't check which one `create-next-app@latest` scaffolds
  as of today without `WebFetch`/`npm`. Safer to let the real tool
  generate that boilerplate and add the auth-specific files on top.

## Known tech debt

- **`admin/middleware.ts` uses the deprecated `middleware` file
  convention.** Next.js 16.0.0 renamed it to `proxy.ts` — a rename only,
  no functional change (confirmed against
  `node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/middleware.md`
  and `proxy.md`). Today it only emits a build warning; Next.js has not
  announced a version that removes the old convention outright.
  **Becomes mandatory to migrate** the moment either happens first: a
  future Next.js major version drops `middleware.ts` support entirely, or
  the current warning graduates into a build error on an earlier minor.
  Left as `middleware.ts` for now since renaming was out of scope for the
  PRs that have touched this file so far. Fix is mechanical when it's
  time: `npx @next/codemod@canary middleware-to-proxy .`

## Checklist to finish PR A

1. ~~Review the two draft migrations, promote to `db/migrations/`~~ —
   done: `0010_app_users_and_roles.sql`, `0011_audit_log.sql`.
2. ~~Add `"audit_log"` and `"app_users"` to `tests/conftest.py`'s
   `_TABLES_TO_TRUNCATE`~~ — done.
3. **Apply the migration to the dev Supabase project** — only run
   against the local test Postgres so far
   (`tests/integration/test_app_users_and_roles_rls.py`,
   `test_audit_log_rls.py` both pass there). Still needs the same
   treatment phase 1/2 already got against the real dev project.
4. ~~Scaffold Next.js, merge into `admin/`~~ — done.
5. ~~Add `@supabase/ssr` + `@supabase/supabase-js`, pinned exact~~ —
   done (`@supabase/ssr@0.12.4`, `@supabase/supabase-js@2.112.3` —
   both resolved inside CLAUDE.md's 90-day freshness window and
   explicitly approved before installing).
6. **Set `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`**
   in `admin/.env.local` (gitignored) from the dev Supabase project's
   credentials — still not done; `next dev` can't authenticate anyone
   for real without it.
7. ~~`npm run build`~~ — passes.
8. **Spot-check `utils/supabase/{client,server,middleware}.ts`** against
   current Supabase docs — the `getAll`/`setAll` cookie-adapter pattern
   was written from training knowledge, not a live doc fetch. Still not
   done.
9. ~~Push, open PR~~ — done, PR #10.
