# WU-TOOLS-01-F01-01 Slice 2 Code Re-Review Controller Adjudication

## Scope

- Work unit: `WU-TOOLS-01-F01-01`
- Gate: code re-review
- Slice: Slice 2 - storage batch lock convergence
- Fix artifact: `docs/reviews/wu-tools-01-f01-01-fix-slice2-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-tools-01-f01-01-code-rereview-slice2-mimo.md`
  - `docs/reviews/wu-tools-01-f01-01-code-rereview-slice2-ds.md`

## Verdict

Slice 2 code re-review passed.

Both review agents confirmed accepted finding A1 is fixed:

- `_release_ticker_lock` keeps unconditional `_ticker_lock_tokens.pop(...)`.
- Effective token selection now prefers the popped cached token and falls back to explicit token.

No blocking open questions remain.

## Controller Decision

Slice 2 is accepted for the accepted slice commit gate.

Next gate: `accepted slice commit`.

## Residual Risks

- `dayu/fins/_file_lock.py` deletion remains Slice 3.
- Runtime token release idempotency remains owned by `dayu.runtime.filelock` and is covered by runtime tests.
- Stale lock, lease, fencing, crash recovery ownership and distributed lock semantics remain out of scope by design.

No unclassified residual risk remains for Slice 2.

## Validation

- Read MiMo and DS re-review artifacts.
- Verified both artifacts mark A1 as `已修复`.
- Verified cited code uses `cached_token = self._ticker_lock_tokens.pop(ticker, None)` followed by `effective_token = cached_token or token`.
