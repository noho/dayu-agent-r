# WU-TOOLS-01-F03 Slice 2 Code Review Controller Adjudication

## Scope

- Work unit: `WU-TOOLS-01-F03 Web CI Smoke Generation`
- Gate: Slice 2 code review adjudication
- Implementation artifact: `docs/reviews/wu-tools-01-f03-implementation-slice2-codex.md`
- Review artifacts:
  - `docs/reviews/wu-tools-01-f03-code-review-slice2-mimo.md`
  - `docs/reviews/wu-tools-01-f03-code-review-slice2-ds.md`
- Date: 2026-06-10

## Decision Summary

Slice 2 implementation is directionally accepted, but must pass a small fix gate before re-review.

The implementation correctly stays within Slice 2 and satisfies the opt-in / summary / schema validation / external diagnostic-only contract. Required fixes are localized cleanup and clarity items:

- remove or justify dead code;
- replace magic exit codes and inline bucket strings with module constants;
- make the opt-in-but-no-local-case Slice 2 intermediate state visible in summary output;
- clarify why external schema validation uses HTML-level requirements.

## Finding Adjudication

| Finding | Source | Decision | Required action |
|---|---|---|---|
| Exit code `0` / `1` / `2` literals are magic numbers | MiMo Finding 1 | accepted | Add `_EXIT_OK`, `_EXIT_LOCAL_FAILURE`, `_EXIT_SCHEMA_OR_INFRA_FAILURE` or equivalent module constants and replace semantic literals. Test data may still assert numeric exit codes where that is the expected external contract. |
| `not_opted_in` bucket is an inline string | MiMo Finding 2 / DS Finding 4 | accepted | Add `_BUCKET_NOT_OPTED_IN` and use it in `_skipped_summary`. |
| `_STDIO_PREFIX_CHARS` and `_prefix_text` are unused | DS Finding 1 | accepted | Remove unused constant/function unless the fix gate introduces an actual use. |
| Opt-in with no local cases is not visible enough in summary | DS Finding 2 / DS Finding 5 | accepted | Add an explicit skip item or equivalent summary signal when opt-in execution has no local cases in Slice 2, explaining that local fixture smoke is attached by Slice 3. This must not change non-opt-in semantics. |
| External schema validation uses `_CASE_LOCAL_HTML` by design but intent is unclear | DS Finding 3 | accepted | Add a short comment or helper name making clear that external artifacts only require HTML-level requests/fetch facts, not PDF-specific fields. |
| Docling exception type names and default timeout literals | MiMo Findings 3/4 | deferred-with-owner | Defer to Slice 3 or Slice 5 unless touched naturally. |
| Dataclass docstring convention and run-label date format | MiMo Findings 5/6 | accepted-low | No required fix. |

## Required Next Gate

Dispatch AgentCodex for fix gate only.

Expected result:

- update `utils/smoke_web_ci.py`;
- update `tests/tools/web/test_smoke_web_ci.py` if summary or constants affect assertions;
- write `docs/reviews/wu-tools-01-f03-fix-slice2-codex.md`;
- rerun focused smoke tests, diagnostics tests, full pyright, and `git diff --check`;
- do not commit, push, PR, or start Slice 3.

