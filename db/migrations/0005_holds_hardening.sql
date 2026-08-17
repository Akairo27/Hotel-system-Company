-- Phase 1 hardening, pre-launch (holds has zero production rows, so plain
-- NOT NULL additions are safe — no backfill needed):
--
-- requires_full_payment: hold_window_for's decision was computed in
-- create_hold and discarded. Persisting it lets confirm_hold enforce it
-- later instead of trusting a value that no longer exists by the time
-- confirmation happens.
--
-- idempotency_key: a retried WhatsApp message must never create a second
-- hold for the same request.

ALTER TABLE holds ADD COLUMN requires_full_payment boolean NOT NULL;
ALTER TABLE holds ADD COLUMN idempotency_key text NOT NULL;
ALTER TABLE holds ADD CONSTRAINT holds_idempotency_key_unique UNIQUE (idempotency_key);
