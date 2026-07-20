# WU-SEMANTIC-OWNERSHIP-01 P3-I S1 code review controller adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P3-I - Public CLI/package entrypoints and terminal display watermark`
- Slice: `S1 - Public Package Entrypoints And README Truth`
- Gate: code review controller adjudication
- Review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-i-s1-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-i-s1-code-review-ds.md`

## Review summary

- AgentMiMo verdict: `pass`, zero material findings.
- AgentDS verdict: `pass`, one low-severity maintainability finding.

## Finding disposition

| Finding | Disposition | Controller decision |
| --- | --- | --- |
| DS F1 - `_normalize_system_exit_code` repeated across `dayu.web`, `dayu.wechat`, and `dayu.render` entrypoint modules | accepted | Even though the helper is small and DS judged current behavior correct, AGENTS.md requires repeated logic to be extracted. The semantic owner is not Web, WeChat, or render specifically; it is a layer-neutral argparse/SystemExit normalization helper. Fix should extract one typed runtime-neutral helper and make all three entrypoints consume it. The helper must remain standard-library-only and must not introduce Host / Service / Engine / CLI command coupling. |

## Required fix

AgentCodex must:

1. Add a small typed helper in a layer-neutral location, preferably `dayu.runtime`, for normalizing argparse `SystemExit` payloads into integer exit codes.
2. Replace the three duplicate private helpers in `dayu/web/__main__.py`, `dayu/wechat/main.py`, and `dayu/render/render.py`.
3. Keep public entrypoint behavior unchanged.
4. Update or add tests only if existing focused tests do not cover the shared helper path.
5. Run focused S1 tests, module/console help smoke, pyright, README audit, and `git diff --check`.

## Rejected or deferred items

- DS open question about explicit WeChat subcommand non-help tests is not accepted for S1. Current parser routes subcommand non-help executions through the same unavailable diagnostic branch, and S1 already tests non-help diagnostics plus subcommand help. Full subcommand behavior belongs to a future WeChat implementation owner.
- Residual risks around full Web UI, WeChat daemon/service, and real render assets remain intentionally deferred per plan.

## Next gate

Proceed to S1 fix by AgentCodex, then re-review with AgentMiMo and AgentDS.
