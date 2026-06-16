# WU-CLI-SESSION-01 Plan Re-Review (DS)

## Re-Review Meta

- **Re-Review Type**: Focused plan re-review — verify accepted findings closure only; expand only if new blocker found
- **Review Target**: `docs/host/host-issues/wu-cli-session-01-cli-session-management-plan.md` (post-fix)
- **Original DS Review**: `docs/reviews/plan-review-wu-cli-session-01-ds-20260616.md`
- **MiMo Review**: `docs/reviews/plan-review-wu-cli-session-01-mimo-20260616.md`
- **Controller Adjudication**: `docs/reviews/plan-review-wu-cli-session-01-adjudication-20260616.md`
- **Plan Fix Report**: `docs/reviews/wu-cli-session-01-plan-fix-codex-20260616.md`
- **Re-Review Date**: 2026-06-16

## Scope

Per adjudication: 10 accepted findings, 2 rejected-with-reason, 1 deferred-with-owner. Re-review checks only accepted findings closure; new material issues only if blocking.

---

## Finding Closure Verification

### DS F-01 [高] timestamp conversion gap → **已修复**

- **Adjudication**: "The plan must specify how `SessionRow.created_at` / `closed_at` strings become public datetime values, preferably via existing UTC timestamp parsing helpers, and what error is raised for malformed durable data."
- **Plan fix location**: Section 6 "时间戳转换规则" (lines 148-154)
- **Verification**:
  - `parse_utc_timestamp(...)` mandated as sole conversion path — `dayu.host.durable.codec.parse_utc_timestamp` is a verified existing function (used by current `read_api.py`)
  - `created_at` must parse; `closed_at` must parse when non-None
  - Malformed timestamp → `HostDurableError` with message "session row timestamp is invalid" or equivalent; no silent fallback, no raw string exposure
  - Section 9 S1 precise changes explicitly add `parse_utc_timestamp` conversion step (line 375)
  - Section 10 adds `test_list_sessions_rejects_malformed_session_timestamp` assertion (line 638)
- **Residual risk**: None. Conversion contract is unambiguous.

### DS F-02 [中] SessionListItem/SessionSnapshot asymmetry → **已修复**

- **Adjudication**: "Keep `created_at` / `closed_at` on `SessionListItem` as list-summary fields for this WU; do not expand `SessionSnapshot` unless the plan fix proves it is necessary. State this intentional asymmetry clearly."
- **Plan fix location**: Section 6 lines 156
- **Verification**:
  - Explicit decision recorded: "`SessionListItem` 与 `SessionSnapshot` 的不对称是本 WU 的有意设计"
  - Stop condition: "除非 implementation agent 发现直接代码证据证明 `SessionSnapshot` 不扩展会导致 `list_sessions` 无法同源实现，否则不得顺手扩大"
  - Section 10 assertion: "`SessionListItem` 包含 `created_at` / `closed_at`；`SessionSnapshot` 在本 WU 不新增这两个字段" (line 639)
- **Residual risk**: None. Decision is explicit, stop condition is clear.

### DS F-03 / MiMo F05 [中] S5 resume execution core underspecified → **已修复**

- **Adjudication**: "Slice S5 must define the minimal function boundary or two-stage split: session resolution separate from executing prompt / interactive on an existing `session_id`. Include parameters, return type, and stop condition."
- **Plan fix location**: Section 9 Slice S5 "精确变更" (lines 540-563)
- **Verification**:
  - Two-stage split clearly defined:
    1. `_resolve_existing_session_id(host: Host, selector: CliSessionSelector) -> str` — resolves session_id or label+kind → existing OPEN session_id; raises on missing/CLOSED; never creates sessions
    2. `_execute_prompt_on_existing_session(...) -> int` — takes `ParsedCliArgs` + `session_id` + `CliInvocation` inputs; reuses prompt scene/runtime/submit/watch/cancel; never calls `_ensure_prompt_session`/`create_session`/`ensure_session`
    3. `_execute_interactive_on_existing_session(...) -> int` — same pattern for interactive
  - Each function has: parameters, return type, behavior contract, exceptions, stop condition
  - TOCTOU handling for resume at line 563: "若 selector resolution 后、submit 前 Session 被并发关闭或 purge，`submit_entrypoint_turn_and_wait` / Host command precondition 是最终 truth"
  - Stop conditions (lines 584-587): if extraction requires cross-module private state import, extract narrow entry point in-place instead; `session.py` must not directly assemble Service runtime
- **Residual risk**: Low — implementation complexity remains but the plan now defines the minimum acceptable contract. The `CliSessionSelector` type is not formally defined but this is an implementation-level detail (can be a simple dataclass with `session_id | label+kind | original_selector_text`).

### DS F-04 / MiMo F03 [中] label reverse mapping underspecified → **已修复**

- **Adjudication**: "Plan must define exact mapping from Host slot to CLI `KIND` / `LABEL`, including anonymous and non-CLI slots."
- **Plan fix location**: Section 7 "KIND / LABEL 反解" (lines 238-245)
- **Verification**:
  - Four-way mapping fully specified:
    - `slot is None` → `KIND=anonymous`, `LABEL=-`
    - `slot.scope == "cli.prompt"` ∧ `slot.slot_key` starts with `cli.prompt.` ∧ non-empty suffix → `KIND=prompt`, `LABEL=slot_key[13:]`
    - `slot.scope == "cli.interactive"` ∧ `slot.slot_key` starts with `cli.interactive.` ∧ non-empty suffix → `KIND=interactive`, `LABEL=slot_key[16:]`
    - else → `KIND=other`, `LABEL=<slot.slot_key>`
  - Dot-bearing labels explicitly handled: "反解时只移除固定前缀，不按 `.` split" with example `slot_key="cli.prompt.proj.v1"` → `LABEL=proj.v1`
  - Section 9 S3 references this as the authoritative mapping (line 455)
  - Section 10 test assertion covers anonymous/prompt/interactive/other + dot-bearing label (line 645)
- **Residual risk**: None. Mapping is unambiguous.

### DS F-05 [中] purge-by-label TOCTOU → **已修复**

- **Adjudication**: "Plan must state TOCTOU is resolved by Host command precondition checks and require CLI errors to include the original user selector plus Host error context. Add test expectation."
- **Plan fix location**: Section 7 "并发语义" (lines 311-315)
- **Verification**:
  - TOCTOU explicitly acknowledged: "这两个步骤之间存在 TOCTOU 窗口，CLI 不做锁或 CAS"
  - Host truth is final: "Host `purge_session` 的 durable transaction precondition 是最终 truth"
  - CLI error contract: "stderr 同时包含用户原始 selector（例如 `--label foo --kind prompt`）和 Host error context（至少包含 resolved `session_id`、Host error code/message）"
  - Resume TOCTOU also covered at line 315: same pattern for `submit_followup` precondition
  - Section 9 S4: test `purge by label` TOCTOU — fake Host returns session A, then `purge_session(A)` throws `CONFLICT`/`NOT_FOUND`; stderr contains original selector + Host error context (line 514)
  - Section 9 S5: test `resume by label` TOCTOU — same pattern (line 577)
  - Section 10 assertion: "purge/resume by label 的 resolve-then-command TOCTOU 场景下，stderr 包含用户原始 selector 与 Host error context" (line 647)
- **Residual risk**: None. TOCTOU window accepted as design choice; Host truth is final; CLI error contract is explicit.

### MiMo F01 [中] Host Protocol / API export omissions → **已修复**

- **Adjudication**: "Plan must explicitly list `Host` Protocol, `dayu.host.api.__all__`, `dayu.host.__init__`, `_PublicHostHandle`, and `test_package_exports.py` changes."
- **Plan fix location**: Section 6 "Host Protocol / Opener / Read API" (lines 158-167)
- **Verification**:
  - `Host` Protocol in `dayu/host/api.py`: explicitly listed (line 163)
  - `dayu.host.api.__all__`: add `SessionListItem`, `ListSessionsResult` (line 163)
  - `dayu.host.read_api.__all__`: add `list_sessions` (line 164)
  - `_PublicHostHandle` in `dayu/host/open_host.py`: add async `list_sessions()` with `_raise_if_closed()` (line 165)
  - `dayu/host/__init__.py`: import and export `SessionListItem`, `ListSessionsResult`, `list_sessions` (line 166)
  - `tests/host/test_package_exports.py`: sync expected exports (line 167)
  - Section 10: explicit assertion that all four `__all__` lists are in sync (line 641)
- **Residual risk**: None. Every export surface is covered.

### MiMo F04 [低] purge tombstone output format → **已修复**

- **Adjudication**: "Plan must freeze the successful purge output shape enough for tests."
- **Plan fix location**: Section 7 `session purge` error semantics (line 309)
- **Verification**:
  - Fixed format: `Purged session <session_id> (tombstone: <tombstone_ref_prefix>...)`
  - Prefix rule: "去掉空白后的前 12 个字符；若 ref 短于 12 个字符则使用完整 ref，仍保留结尾 `...`"
  - Section 9 S4: "purge 成功输出严格断言" with the format (line 515)
  - Section 10: same assertion (line 646)
- **Residual risk**: None. Format is fully frozen for test assertions.

### DS F-08 [低] list vs concurrent purge snapshot isolation → **已修复**

- **Adjudication**: "Plan should clarify list results are read-transaction snapshots and Host commands remain final truth."
- **Plan fix location**: Section 6 durable helper (line 186) + Section 8 Purged Session (lines 346-347)
- **Verification**:
  - Section 6: "上述'已 purge 不出现'指 read transaction 开始时的 durable snapshot。若并发 purge 在本次 read transaction 开始后提交，本次 `list_sessions` 可以仍看到旧 snapshot；后续 `get_session` / `submit_followup` / `purge_session` 等 Host command 仍是最终 truth"
  - Section 8: "正在运行的 `list_sessions()` 看到的是 read transaction snapshot；并发 purge 可能对该 snapshot 不可见，这是可接受的一致性边界"
- **Residual risk**: None. Snapshot semantics are explicit and accepted.

### DS F-09 [低] interactive_process_slot_key export cleanup → **已修复**

- **Adjudication**: "Plan S2 must explicitly include `host_context.__all__` cleanup if the helper is removed."
- **Plan fix location**: Section 9 Slice S2 (line 417)
- **Verification**:
  - "若 `interactive_process_slot_key(...)` 无其它用途，删除该 helper、测试引用，并同步从 `host_context.__all__` 中移除"
  - Previous plan said "若...无其它用途，删除" without `__all__` mention; now includes it
- **Residual risk**: None. `__all__` cleanup is explicit.

---

## Rejected / Deferred Findings Verification

| Finding | Decision | Plan Representation |
|---------|----------|---------------------|
| DS F-06 list query amplification | deferred-with-owner | Section 12 "List query amplification" (line 691) — deferred to future pagination/performance follow-up |
| DS F-07 no ListSessionsRequest | rejected-with-reason | Section 12 "No ListSessionsRequest" (line 695) — `list_sessions()` follows `get_session`/`get_run` zero-parameter read pattern |
| MiMo F02 resume-by-label full scan | rejected-with-reason | Section 12 "Resume by label uses list_sessions" (line 694) — no `get_session_by_label` in this WU |

All three correctly recorded in plan Section 12 as explicit decisions with rationale.

---

## Architecture Boundary Re-Check

Post-fix check on the user's mandatory review items:

| Check | Result | Evidence |
|-------|--------|----------|
| Host public API/export list covers Host Protocol, api.__all__, read_api.__all__, __init__, _PublicHostHandle, package export tests | **PASS** | Section 6 lines 158-167 + Section 10 line 641 |
| timestamp conversion / SessionListItem vs SessionSnapshot asymmetry converged | **PASS** | Section 6 lines 148-156 + Section 10 lines 638-639 |
| S5 resume execute-on-existing-session boundary code-generation-ready | **PASS** | Section 9 Slice S5 lines 540-563 — two-stage split with explicit functions, parameters, return types, exceptions, stop conditions |
| label reverse mapping converged | **PASS** | Section 7 lines 238-245 — precise 4-way mapping with dot-label example |
| purge/resume TOCTOU converged | **PASS** | Section 7 lines 311-315 + Section 9 S4/S5 tests + Section 10 assertions |
| purge output converged | **PASS** | Section 7 line 309 — frozen format with prefix rules |
| snapshot semantics converged | **PASS** | Section 6 line 186 + Section 8 lines 346-347 |
| interactive_process_slot_key cleanup converged | **PASS** | Section 9 S2 line 417 — explicit `__all__` removal |

## New Findings

**None.** All 10 accepted findings are closed with evidence. No new blocking issue identified during re-review. The plan is now code-generation-ready for all 6 slices.

One minor observation (NOT a finding — no material risk):

- S5's `CliSessionSelector` type is referenced but not formally defined in the plan. This is a simple implementation-level dataclass (likely with `session_id: str | None`, `label: str | None`, `kind: str | None`, `original_selector_text: str`). The implementation agent can define it as a private helper in `session.py`. No plan amendment needed.

---

## Re-Review Conclusion

**PASS**

All 10 adjudication-accepted findings verified as closed in the plan fix. The plan is code-generation-ready. Architecture boundaries, layering, Host public contract, label mapping, TOCTOU semantics, S5 execution boundary, purge output format, export coverage, snapshot isolation, and `__all__` cleanup are all fully specified. No structural blockers remain.

---

## Completion Report

1. **Re-review artifact path**: `docs/reviews/plan-rereview-wu-cli-session-01-ds-20260616.md`
2. **Conclusion**: **PASS**
3. **Finding closure table**:

| Finding | Severity | Status | Evidence |
|---------|----------|--------|----------|
| DS F-01 | 高 | 已修复 | Section 6 timestamp conversion rules + Section 9 S1 + Section 10 test |
| DS F-02 | 中 | 已修复 | Section 6 explicit asymmetry decision + stop condition + Section 10 assertion |
| DS F-03 / MiMo F05 | 中 | 已修复 | Section 9 S5 two-stage split with function contracts |
| DS F-04 / MiMo F03 | 中 | 已修复 | Section 7 precise 4-way mapping with dot-label example |
| DS F-05 | 中 | 已修复 | Section 7 TOCTOU acknowledgment + CLI error contract + S4/S5 tests + Section 10 assertions |
| MiMo F01 | 中 | 已修复 | Section 6 full export surface enumeration + Section 10 sync assertion |
| MiMo F04 | 低 | 已修复 | Section 7 frozen output format with prefix rules |
| DS F-08 | 低 | 已修复 | Section 6 + Section 8 snapshot isolation semantics |
| DS F-09 | 低 | 已修复 | Section 9 S2 `__all__` cleanup |
| DS F-06 | 低 | deferred-with-owner | Section 12 deferred to follow-up |
| DS F-07 | 低 | rejected-with-reason | Section 12 zero-parameter read pattern |
| MiMo F02 | 低 | rejected-with-reason | Section 12 no `get_session_by_label` |

4. **Blocking open questions**: 无
