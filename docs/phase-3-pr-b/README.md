# Phase 3 — PR B: hotels/room types admin screen

Status: built and verified, both locally and against the real
`hotel-sales-agent-dev` Supabase project. Not yet pushed/opened as a PR.

## What's in this branch

- `db/migrations/0014_hotels_room_types_admin_access.sql` — grants
  `authenticated` `SELECT, INSERT, UPDATE` on `hotels`/`room_types` (no
  `DELETE`), plus RLS policies: any active `app_users` row (admin or
  sales) can `SELECT`; only `current_app_role() = 'admin'` can `INSERT`/
  `UPDATE`. Migration 0001 deferred these grants explicitly ("grants for
  the admin dashboard arrive in phase 3").
- `admin/app/hotels/{page.tsx,actions.ts}` — hotel list, admin-only add/
  rename forms.
- `admin/app/hotels/[hotelId]/{page.tsx,actions.ts}` — one hotel's room
  types, admin-only add/rename forms.
- `admin/lib/types.ts` — `Hotel`, `RoomType` (mirrors migration 0001;
  neither table has a cost column, so there's no ARCHITECTURE.md §8
  masking concern here, unlike `allotments`/`quotes`).
- `admin/app/dashboard/page.tsx` — nav link into `/hotels`.
- `tests/integration/test_hotels_room_types_rls.py` — 14 new tests
  against real Postgres.

## Decisions confirmed with the user before writing any RLS/schema code

Per CLAUDE.md §10 ("always ask before touching `pricing/`/`inventory/`,
RLS, or schema"), asked before starting:

1. **Write authorization: RLS policy, not a service_role Server Action.**
   Unlike `app_users` (PR A), there's no self-escalation risk here — a
   `hotels`/`room_types` row isn't "owned" by the writer — so a plain
   admin-only RLS policy is sufficient and is the standard approach.
2. **Sales role: read-only.** Sales can see inventory options while
   quoting but cannot create or rename a hotel/room type.
3. **No delete in this PR.** Both tables are FK-referenced by
   `allotments`/`holds`; hard-delete vs. soft-delete/deactivate is a
   separate decision. No role but `service_role` holds a `DELETE` grant
   today, unchanged from before this migration.
4. **No new schema fields.** `hotel_name`/`room_type_name` are the only
   columns; this PR ships CRUD for exactly what exists.

## A real RLS behavior worth documenting: denied UPDATE doesn't raise

Found while writing the first version of the "sales cannot update"
tests, empirically, not by assumption: unlike a denied `INSERT` (which
raises `psycopg.errors.InsufficientPrivilege` because Postgres actively
checks `WITH CHECK` against the row being inserted), a denied `UPDATE`
does **not** raise. RLS's `USING (current_app_role() = 'admin')` clause
just filters the target row out of the update entirely — a non-admin's
`UPDATE ... WHERE id = X` matches **zero rows**, silently, with no error.
Verified directly against local Postgres before trusting it:

```
rowcount: 0
actual name after: ('Original',)
```

This is correct, secure Postgres RLS behavior (the row is genuinely
unchanged), but it means the two "cannot update" tests assert on
`cursor.rowcount == 0` and the unchanged value, not on a raised
exception — an exception-based assertion here would be testing something
that doesn't happen and could pass for the wrong reason if the policy
were silently broken in a way that still returned an error some other
way. The same non-obvious behavior shaped
`admin/app/hotels/actions.ts`'s `renameHotel` (and the `[hotelId]`
equivalent): after `.update(...).select("id")`, an empty `data` array —
not a thrown error — is the real "not permitted" signal, so both actions
check for that explicitly and redirect with a friendly error.

## Defense in depth: Server Actions re-check the role themselves

Next.js's own Server Actions guide (`node_modules/next/dist/docs/01-app/
02-guides/server-actions.md`, this Next 16.3.1 install) is explicit:
"Render-time gating (only rendering a form on an authenticated page) is
not a security boundary, because requests can be sent without going
through the UI." Every write action calls `requireAdmin()` first, which
re-reads `getCurrentAppUser()` and redirects with a clear error if the
caller isn't an active admin — a friendly fast path in front of the RLS
policy, which remains the actual, real enforcement layer (verified by
the test suite above).

## API note: `.returns<T>()` is deprecated in this postgrest-js version

`@supabase/postgrest-js` (bundled in `@supabase/supabase-js@2.112.3`)
marks `.returns<T>()` `@deprecated` in favor of
`.overrideTypes<T, { merge: false }>()` — confirmed by reading
`node_modules/@supabase/postgrest-js/src/PostgrestBuilder.ts` directly
rather than assuming the older API from training data (per `admin/
AGENTS.md`'s warning that this Next.js/ecosystem install may differ from
what a model was trained on). Both list-fetching queries in this PR use
`overrideTypes`, not `returns`.

## Verification

- **Local**: `uv run pytest` — 193 passed (179 before this PR + 14 new).
  `ruff check .`, `ruff format --check .`, `mypy` (43 files), `sqlfluff
  lint db/migrations` all clean. `npm run build` (admin/) succeeds;
  `npx eslint .` and `npx tsc --noEmit` both clean.
- **Real Supabase (`hotel-sales-agent-dev`, `galvhxwnllqnbnbasjlq`)**:
  migration 0014 applied via the Supabase MCP (confirmed grants before/
  after via `information_schema.role_table_grants`); `get_advisors`
  shows no new findings tied to `hotels`/`room_types`. Created a second
  test user, `admin-test@example.com` / `TestAdminPass!2026Aug`
  (`app_role='admin'`), alongside the existing `sales-test@example.com`
  from PR A — both are reusable dev-project fixtures now, same as PR A's
  precedent. Ran `next dev` against the real project (inline env vars —
  `.env.local` is still blocked at every tool layer, see
  `docs/phase-3-pr-a/README.md`) and drove the actual `/hotels` and
  `/hotels/[hotelId]` screens through `claude-in-chrome`:
  - Signed in as `admin-test@example.com`: created a hotel
    ("فندق الاختبار"), created a room type under it ("غرفة فاخرة"),
    renamed the room type ("جناح ملكي") — all persisted for real.
  - Signed in as `sales-test@example.com`: both screens render the same
    data read-only — no add/rename forms — confirming the UI's
    `isAdmin` gating matches the RLS design.
  - Left the test hotel/room type and both test users in place as
    reusable dev fixtures (matches PR A's `sales-test@example.com`
    precedent) rather than deleting them — there is no DELETE grant to
    do so through the app layer anyway, by this PR's own design.

## Not covered by this PR

- Delete/deactivate for hotels or room types (explicit decision above).
- Any field beyond `hotel_name`/`room_type_name` (explicit decision
  above).
- Frontend automated tests — `admin/` has no test runner installed yet
  (Jest/Vitest/Playwright would be a new dependency requiring approval
  per CLAUDE.md's dependency rules); verification here is `eslint`/`tsc`
  (both CI gates) plus the live manual pass documented above.
- CI wiring for `admin/`'s `eslint`/`tsc` gates — `.github/workflows/
  ci.yml` still has no frontend job at all; this predates PR B (PR A
  didn't add one either) and is out of this PR's scope.
