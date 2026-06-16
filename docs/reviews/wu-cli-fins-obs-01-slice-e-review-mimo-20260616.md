# WU-CLI-FINS-OBS-01 Slice E Review

## Gate

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: E, README / design-adjacent docs / tests synchronization
- Reviewer: AgentMiMo
- Date: 2026-06-16
- Scope: uncommitted diff of `dayu/README.md`, `dayu/service/README.md`, `dayu/fins/README.md`, `tests/README.md`; codex implementation doc `docs/reviews/wu-cli-fins-obs-01-slice-e-implementation-codex.md`
- Design truth sources: `docs/host/design.md`, `docs/engine/design.md`
- Plan truth source: `docs/host/wu-cli-fins-obs-01-replacement-plan.md` Slice E
- Control doc: `docs/host/issues-implementation-control.md`

## Review checklist

### 1. README consistency with current code

| Claim | Code evidence | Verdict |
|---|---|---|
| direct commands = `AsyncIterator[FinsEvent]` | `FinsIngestionRuntime.download/preprocess/upload` all return `AsyncIterator[FinsEvent]`; `FinsDirectCommandService.download/process/process_filing/process_material/upload_filing/upload_material` all return `AsyncIterator[FinsEvent]` | PASS |
| awaiting tools = `ToolAwaitingOutcome(EXTERNAL_JOB)` + lightweight observation handle | `start_observed_download/preprocess/upload` return `FinsObservationHandle`; `FinsObservationStatus` has PENDING/RUNNING/SUCCEEDED/FAILED/CANCELLED/LOST | PASS |
| legacy job-store only as legacy runtime foundation | `start_download/start_preprocess/start_upload/read_job/read_job_events/request_cancel` still exist on `FinsIngestionRuntime` but READMEs consistently mark them as legacy, not consumed by Service direct or awaiting tools | PASS |
| `FinsEvent` contract: PROGRESS/RESULT, SUCCESS/FAILURE/CANCELLED | `FinsEventType.PROGRESS/RESULT`, `FinsResultStatus.SUCCESS/FAILURE/CANCELLED` confirmed via `dayu.fins.direct_events` | PASS |
| `FinsObservationHandle` contract matches plan | Fields: `handle_id`, `operation_kind`, `created_at`; status: PENDING/RUNNING/SUCCEEDED/FAILED/CANCELLED/LOST; snapshot: `handle/status/message/result/error_kind/retry_after_seconds` | PASS |

### 2. No misleading descriptions remaining

| Misleading pattern | Search result | Verdict |
|---|---|---|
| "CLI direct durable job" | Not found in any README outside explicit legacy context | PASS |
| "job event sidecar" as direct/awaiting concept | Only in `fins/README.md` legacy section and `tests/README.md` legacy test descriptions | PASS |
| "terminal fallback" for Fins direct | Not found; `service/README.md` line 21 "terminal fallback" refers to Host entrypoint outbox fallback for Agent runs, which is a different correct concept | PASS |
| "request_cancel(job_id)" as direct/awaiting path | Only in `fins/README.md` legacy helpers section, explicitly scoped: "Service direct 和 awaiting tools 不消费该路径" | PASS |
| "job store" without legacy qualifier | `fins/README.md` consistently uses "legacy job store" or "legacy ingestion job store"; `dayu/README.md` uses "ingestion runtime" without job store reference | PASS |

### 3. No over-exposure of implementation details or future plans

| Check | Result | Verdict |
|---|---|---|
| No future plan language in READMEs | All descriptions are current-code factual | PASS |
| No internal implementation class names exposed unnecessarily | READMEs use business-semantic descriptions (direct stream, observation handle, legacy job helpers) | PASS |
| No `docs/host/design.md` or `docs/engine/design.md` edited | Confirmed: Slice E plan explicitly states these should not change; diff confirms no changes | PASS |
| Fins/README extension guidance mentions durable mini-design trigger | Line 675: "只有明确需要跨进程或跨重启恢复未完成 Fins ingestion 时，才应单独设计最小 durable operation ledger" — this is appropriate boundary guidance, not future plan | PASS |

### 4. Tests README accuracy

| Test file description claim | Code/test evidence | Verdict |
|---|---|---|
| `test_fins_ingestion_tools.py`: observation handle contract, corrupt token → LOST, poll adapter terminal/corrupt/missing/transient mapping | Matches Slice D0/D implementation and test coverage | PASS |
| `test_fins_ingestion_runtime.py`: legacy job persistence, direct stream PROGRESS/RESULT, stream producer silent end → failure result, legacy sidecar coverage | Matches Slice C implementation; legacy coverage explicitly labeled "legacy" | PASS |
| `test_fins_direct.py`: Service AsyncIterator pass-through, no job handle exposure | Matches Slice A implementation | PASS |
| `test_fins_commands.py`: CLI consumes AsyncIterator, cancellation, no request_cancel(job_id) | Matches Slice B implementation | PASS |

### 5. Verification commands sufficiency

| Check | Result | Verdict |
|---|---|---|
| Codex ran full pytest suite | 281 passed, 3 warnings — covers all Fins, CLI, and Service tests | PASS |
| Codex ran pyright | 0 errors across `dayu/ tests/ utils/` | PASS |
| Codex ran `git diff --check` | clean | PASS |

### 6. Design doc alignment

| Check | Result | Verdict |
|---|---|---|
| `docs/host/design.md` stream terminology | "EngineEvent stream" / "Host event stream" terminology boundaries preserved; Fins direct stream correctly not conflated with these | PASS |
| `docs/engine/design.md` Section 1.1 | Fins `AsyncIterator[FinsEvent]` is not called "EngineEvent stream" or "Host event stream" in any README | PASS |
| Replacement plan Slice E stop condition | "不得修改 docs/host/issues-implementation-control.md" — confirmed not modified | PASS |

### 7. README update constraints compliance

| README | Has constraints | Checked constraints | Verdict |
|---|---|---|---|
| `dayu/README.md` | Yes: "只写当前代码已实现的总揽级设计意图" | Edits are cross-package stable boundary descriptions, matching current code | PASS |
| `dayu/fins/README.md` | Yes: "先核对 dayu.fins 当前代码" | All descriptions verified against runtime API, observation handle contract, and direct event contract | PASS |
| `dayu/service/README.md` | No explicit constraints | Limited edits to stable Service boundary descriptions | PASS |
| `tests/README.md` | "测试事实以当前代码和测试目录为准" | Test ownership descriptions match current test coverage | PASS |

## Non-blocking observations

1. **`service/README.md` "terminal fallback" disambiguation**: Line 21 uses "terminal fallback" to describe Host entrypoint outbox fallback for Agent runs. This is correct and unrelated to the removed Fins terminal fallback. No action needed, but a future reader could confuse the two if context is missing. Not blocking because the surrounding text clearly scopes it to `entrypoint_runtime` and Host `get_run(...)` / `read_outbox_terminal_items(...)`.

2. **`fins/README.md` paragraph density**: The Fins README has several very long paragraphs (e.g., the ingestion runtime section, the state machine section). Readability could be improved with more sub-headings or bullet lists. Not blocking because content accuracy is the review scope; formatting is cosmetic.

## Conclusion

**PASS**

All five review focus points pass:

1. READMEs accurately describe direct commands = `AsyncIterator[FinsEvent]`, awaiting tools = `ToolAwaitingOutcome(EXTERNAL_JOB)` + lightweight observation handle, legacy job-store only as legacy runtime foundation.
2. No misleading CLI direct durable job, job event sidecar, terminal fallback, or `request_cancel(job_id)` descriptions remain outside explicit legacy context.
3. No over-exposure of implementation details or future plans; design docs untouched.
4. Tests README accurately describes direct stream / awaiting handle / legacy job-store coverage.
5. Verification commands (pytest 281 passed, pyright 0 errors, git diff --check clean) are sufficient for a docs-only change.

No blocking findings.
