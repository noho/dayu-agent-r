# WU-CM-06 Terminal Summary Text Policy Convergence Plan

## Goal Confirmation

GitHub Issue #94 is open and #81 has been closed, so the previous deferred prerequisite is gone. The motivation is valid, but the implementation should be narrow: current code already has several pieces of the policy in place, so WU-CM-06 should converge and test the policy rather than redesign terminal taxonomy or add a new public result API.

Direct code evidence:

- `dayu/host/engine_ingest.py` writes terminal summary payloads for succeeded, failed, lost, and empty-final-answer failure paths.
- `dayu/host/read_api.py` only projects `HostFinalAnswerView` for `RUN_SUCCEEDED`; failed, cancelled, and lost terminal events set `final_answer=None`.
- `dayu/host/terminal_summary_payload.py` already restricts assistant final-answer continuity to `RUN_SUCCEEDED.final_answer` or terminal summary artifact `content`.
- `dayu/host/_terminal_answer.py` already rejects bare `RUN_SUCCEEDED.content`, `summary_text`, and nested `summary` as assistant final-answer sources.
- `dayu/host/compact_material.py`, `dayu/host/memory.py`, and `dayu/host/run_input.py` consume these helpers in different paths; tests cover parts of the behavior but do not yet present one complete policy matrix.

## Non-Goals

- Do not change Run terminal taxonomy.
- Do not introduce a new public result read API.
- Do not make terminal summary an evidence-backed fact source.
- Do not let compact / episode summary become terminal summary or assistant final answer.
- Do not redesign compaction memory semantics beyond the text policy tests needed here.
- Do not add compatibility wrappers or re-export-only modules.

## Policy Target

The policy to freeze is:

| Terminal / continuity path | Allowed assistant final-answer text source | Forbidden sources |
|---|---|---|
| `RUN_SUCCEEDED` payload | non-empty `final_answer` | bare `content`, `summary_text`, nested `summary` |
| `RUN_SUCCEEDED` with terminal summary descriptor | digest-checked terminal summary artifact `content`, only when `final_answer` is missing or blank | artifact `summary_text`, nested `summary`, broken descriptor |
| `RUN_FAILED` / governance failure | no assistant final answer; terminal summary remains diagnostic only | error `message` as answer, compact / episode summary |
| `RUN_CANCELLED` | no assistant final answer; cancellation reason is terminal status display only | cancellation reason as answer |
| `RUN_LOST` | no assistant final answer; lifecycle diagnostic is terminal status display only | lifecycle reason as answer |
| Compaction material / run input continuity | uses strict assistant final-answer continuity resolver; may fall back from `RUN_SUCCEEDED` descriptor to digest-checked terminal summary artifact `content` | must not use bare `content`, `summary_text`, nested `summary`, failed/cancelled/lost diagnostic text |
| Conversation Memory selected recent window | uses inline `RUN_SUCCEEDED.final_answer` only, leniently; does not follow terminal summary artifact descriptor indirection | must not create evidence-backed facts from terminal summary or assistant final answer |

Text handling:

- Missing or blank allowed text returns `None`.
- Strict policy raises for malformed allowed fields; lenient policy treats malformed allowed fields as missing.
- Disallowed fields are ignored even when malformed.
- Overlong allowed text is preserved by this policy helper; truncation belongs to display, storage, or budget-specific callers, not to terminal text source selection. Caller-side truncation verification is out of scope for WU-CM-06 and remains owned by each caller's budget/display tests.

## Slice 1: Policy Matrix Tests

Allowed files:

- `tests/host/test_terminal_summary_payload.py`
- `tests/host/test_public_host_event.py`, only if non-success terminal public-event coverage needs a small assertion update
- `tests/host/test_read_api_terminal_policy.py`, or the nearest existing read API projection test file, for focused EventLog row -> HostEvent projection assertions
- `tests/host/test_engine_ingest_mapping.py`, only for a focused `empty_final_answer` terminal summary shape assertion
- `tests/host/test_memory_projection.py`, only if evidence-backed fact separation needs a focused assertion
- `docs/reviews/wu-cm-06-s1-implementation-report.md`

Exact changes:

- Add a test that proves `assistant_final_answer_continuity_text(...)` prefers non-empty `RUN_SUCCEEDED.final_answer` over terminal summary artifact `content`.
- Add tests that missing one terminal summary descriptor side (`terminal_summary_ref` or `terminal_summary_digest`) returns `None` and does not fall back to bare `content` / `summary_text`.
- Add tests for malformed descriptor field types raising `HostDurableError`.
- Add tests that overlong `final_answer` and overlong artifact `content` are preserved by the source-selection helper; document in the test name/docstring that caller-side truncation is out of scope.
- Add direct read API projection tests for `RUN_FAILED`, `RUN_CANCELLED`, and `RUN_LOST` EventLog rows proving their projected `HostEvent.final_answer` is `None`. Dataclass construction tests do not satisfy this requirement because they do not exercise `_host_event_from_row(...)` / read API projection logic.
- Add or strengthen an `empty_final_answer` ingest test proving Host governance converts empty Engine `final_answer` to `RUN_FAILED` and the terminal summary payload does not contain displayable final-answer `content`.
- Add a focused memory projection assertion proving assistant terminal text enters only `selected_recent_window` with `MemoryIncludedReason.SELECTED_RECENT_WINDOW`, not evidence-backed fact memory; also prove descriptor-only `RUN_SUCCEEDED` does not materialize an assistant item in memory projection.

Validation:

- `pytest tests/host/test_terminal_summary_payload.py tests/host/test_read_api_terminal_policy.py tests/host/test_engine_ingest_mapping.py tests/host/test_memory_projection.py -q`
- `python -m pyright dayu/ tests/ utils/`

## Slice 2: Naming / Docstring Convergence

Allowed files:

- `dayu/host/terminal_summary_payload.py`
- `dayu/host/_terminal_answer.py`
- `tests/host/test_terminal_summary_payload.py`, only if docstring wording needs test alignment
- `docs/reviews/wu-cm-06-s2-implementation-report.md`

Exact changes:

- Tighten module and function docstrings to name the policy explicitly as assistant final-answer continuity text source selection.
- Clarify that terminal summary artifact `content` is a fallback source only for `RUN_SUCCEEDED` continuity, not a general terminal summary or fact source.
- Clarify consumer differences: compaction material / run input use the strict continuity resolver with artifact fallback; memory selected recent window uses the inline run-payload reader only and remains lenient.
- Clarify that overlong handling is not performed in these helpers.
- Do not rename public imports, introduce compatibility re-exports, or change helper return values unless Slice 1 exposes a real behavior defect.

Validation:

- `pytest tests/host/test_terminal_summary_payload.py -q`
- `python -m pyright dayu/ tests/ utils/`

## README Decision

Check but likely do not update:

- `dayu/host/README.md`: update only if WU-CM-06 changes stable developer-facing Host terminal event behavior or public contracts. Test/docstring convergence alone should not change README.
- `tests/README.md`: update only if WU-CM-06 adds a new test layer, command, or maintenance rule. Adding tests to existing Host test files should not change README.

## Acceptance

- Terminal text source policy is covered by focused tests.
- Success, failure, cancel, lost, and governance-failure boundaries do not masquerade as assistant final answer.
- Empty, missing, malformed, and overlong text cases are explicitly covered for allowed sources.
- Compact / episode summary and assistant final answer remain semantically distinct.
- Memory projection does not upgrade terminal summary into evidence-backed facts.
