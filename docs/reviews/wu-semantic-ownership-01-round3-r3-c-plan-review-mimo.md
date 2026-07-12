# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-C Plan Review

## Review Target

- Artifact: `docs/host/wu-semantic-ownership-01-round3-r3-c-fins-storage-atomicity-plan.md`
- Posture: adversarial plan review
- Reviewer: AgentMiMo
- Generated: `date +%Y%m%d-%H%M%S` -> `20260712-231537`

## Must-Read Documents Consumed

- AGENTS.md
- `docs/reviews/wu-semantic-ownership-01-round3-r3-c-goal-confirmation.md`
- `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round3-controller-adjudication.md`
- `docs/phaseflow-umbrella-optimization-control.md`
- `docs/host/issues-implementation-control.md`
- `docs/host/design.md`
- `docs/engine/design.md`
- `dayu/README.md`
- `dayu/fins/README.md`

## Code Facts Verified

| Claim | Source | Verified |
|---|---|---|
| `_normalize_ticker()` falls back to `strip().upper()` | `_fs_storage_utils.py:30-52` | Yes |
| `store_file()` only strips filename, only checks SourceHandle | `_fs_blob_core.py:141-154` | Yes |
| `commit_batch()` swaps before COMMITTED journal | `_fs_storage_infra.py:260-270` | Yes |
| Recovery treats SWAPPED_TARGET as committed | `_fs_storage_infra.py:725-728` | Yes |
| `LocalFileStore.put_object()` uses fixed `.part`, no fsync | `local_file_store.py:63-78` | Yes |
| `_write_json()` uses UUID temp, fsync, dir-sync | `_fs_storage_utils.py:463-487` | Yes |
| `_local_path_from_uri()` resolves without containment check | `_fs_storage_utils.py:196-218` | Yes |
| `wait_adapter.py` imports Host API, durable state, wait_adapter | `wait_adapter.py:49-74` | Yes |
| Upload `token = None` before `commit_batch` | `docling_upload_service.py:399-402` | Yes |
| Test freezes incomplete state on failure | `test_docling_upload_service.py:288-322` | Yes |
| Existing commit tests are happy-path only | `test_fins_storage_provider.py:2198,2427,2511` | Yes |

## Assumptions Tested

1. S1 storage identity contract is implementable without caller fallback.
2. S2 single-document atomicity can be achieved without holding batch across network/await.
3. CN/HK temp-less contract (pdf_bytes) doesn't drift into security policy.
4. S3 Host snapshot / Service-owned Fins wait glue boundary is clean.
5. 3 slices are justified under umbrella optimization control.
6. Validation commands are sufficient and not overly broad.

## Findings

### 001-未修复-中-S2 token lifecycle contract under-specified

- **位置**: S2 "Exact allowed changes" item 3, "Contract And State-Machine Decisions" -> "Single-document mutation contract"
- **问题类型**: 契约缺失
- **当前写法**: "重排 token lifecycle：operation exception 才显式 rollback；commit failure依赖storage all-or-nothing并原样传播，不使用 `token=None` 绕开状态"
- **反例/失败场景**: Implementation agent 看到当前 bug 是 `token = None` 导致 commit failure 后无法 rollback。修复方案有两种：(a) 移除 `token = None`，在 `commit_batch()` 成功后才消费 token，失败时 exception handler 仍可 rollback；(b) 完全依赖 storage commit all-or-nothing，不在 caller 侧 rollback commit failure。两种方案的行为不同：方案 (a) 对 commit failure 做 rollback（token 已被 storage 消费则 rollback 是空操作），方案 (b) 直接传播 commit exception 不做 rollback。Plan 没有明确选哪种。
- **为什么有问题**: `docling_upload_service.py:417-420` 的 `except Exception` 分支在 commit failure 后调用 `rollback_batch(token)`。如果 storage 的 `commit_batch()` 已经消费了 token（`finally` 块 pop active_batches），rollback 会因为 token 无效而抛 `ValueError`，导致原始 commit error 被二次异常覆盖。Plan 的 contract 说 "commit failure依赖storage all-or-nothing并原样传播"，但没说 caller 侧的 rollback 是否仍应尝试。
- **直接证据**: `docling_upload_service.py:399-420` 当前逻辑；plan S2 item 3 文本；`_fs_storage_infra.py:290-294` finally 块消费 token。
- **影响**: Implementation agent 可能保留 caller 侧 rollback 逻辑，对已消费 token 二次 rollback 导致 ValueError 覆盖原始 commit error。
- **建议改法和验证点**: Plan 应明确：(1) caller 对 commit failure 只传播不 rollback（token 已被 storage 消费）；(2) caller 对 operation exception（commit 前）才 rollback。测试应断言 commit failure 后不做 rollback 且原始 commit error 传播。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 002-未修复-低-S2 cancellation-during-batch rollback mechanism implicit

- **位置**: S2 "Required state/rollback matrix" -> generic download create/overwrite, CN/HK new filing rows
- **问题类型**: 状态机漏洞
- **当前写法**: Matrix says "source/blob/processed/commit -> document absent" for cancel cases. Plan contract says "batch 内不 yield/await，因此 async generator close 只能发生在无 active storage batch的边界".
- **反例/失败场景**: 如果 implementation agent 在 batch 内意外放入了一个 yield/await（例如日志输出或 checkpoint），asyncio task cancel 会在 batch 内触发。此时 CancelledError 需要被 catch 并调用 rollback_batch()，否则 batch staging 残留。Plan 没有显式说明 batch scope 的 exception handling pattern。
- **为什么有问题**: Plan 的 invariant "batch 内不 yield/await" 是正确的设计约束，但没有说明 implementation 如何强制执行。例如 CN/HK workflow 当前有 yield 在 progress 报告中（`cn_download_filing_workflow.py` 的 FinsEvent yield）。如果 implementation agent 没有正确分离 yield 和 batch scope，cancel 会在 batch 内触发。
- **直接证据**: plan S2 "Single-document mutation contract" item 6 "batch 内不 yield/await"；CN/HK workflow 当前使用 yield 报告 progress。
- **影响**: 如果 batch 内有 yield，cancel 会留下 staging 残留，违反 all-or-nothing。
- **建议改法和验证点**: Plan 应补充：batch scope 必须用 try/finally 包裹，finally 中对未消费 token 做 rollback_batch()。测试应断言 batch 内 CancelledError 触发后 staging 被清理。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 003-未修复-低-S1 commit_batch recovery phase semantics require explicit rewrite contract

- **位置**: S1 "Exact allowed changes" item 3, "Contract And State-Machine Decisions" -> "Batch commit state machine"
- **问题类型**: 状态机漏洞
- **当前写法**: "重写 `commit_batch()` commit point与pre-commit rollback；同步重写 orphan recovery phase解释"
- **反例/失败场景**: Current recovery at `_fs_storage_infra.py:725-728` treats `SWAPPED_TARGET` phase as "committed" (deletes backup). Plan's state machine says `SWAPPED_TARGET` is "尚未对 caller committed" and recovery should restore pre-batch state. This is a semantic reversal. If implementation agent doesn't change recovery logic to match the new contract, `SWAPPED_TARGET` recovery will delete backup (current behavior) instead of restoring it (plan's desired behavior).
- **为什么有问题**: The plan's state machine diagram explicitly says `SWAPPED_TARGET` means "尚未对 caller committed" and "COMMITTED 之前异常：删除本次新 target（如已 swap），恢复 backup（如原 target 存在）". But current recovery code at line 725-728 does the opposite: it deletes backup when both backup and target exist. Implementation agent needs to know this is a behavioral change, not just a rewrite.
- **直接证据**: `_fs_storage_infra.py:725-728` recovery for `SWAPPED_TARGET` deletes backup; plan state machine says recovery should restore backup.
- **影响**: If implementation agent treats this as a cosmetic rewrite, recovery behavior won't change, and crash between swap and COMMITTED will leave new target in place (current behavior) instead of restoring old target (plan's contract).
- **建议改法和验证点**: Plan's S1 should explicitly state: "recovery 对 SWAPPED_TARGET 恢复 backup、删除 new target，与当前行为相反". Test should assert: crash between swap and COMMITTED -> old target restored, new target absent.
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 004-未修复-低-S3 WaitAdapterSnapshot created_at type derivation implicit

- **位置**: S3 "Contract And State-Machine Decisions" -> "Wait adapter ownership contract", S3 "Required assertions" item 2
- **问题类型**: 契约缺失
- **当前写法**: "Host用自己的timestamp parser投影timezone-aware `created_at`；非法durable timestamp在Host owner处fail closed"
- **反例/失败场景**: If `WaitRecordRow` stores `created_at` as a string (common in SQLite durable rows), Host needs to parse it into `datetime`. If the row stores it as `datetime`, Host just projects it. Plan doesn't specify the raw type or the parser. Implementation agent may use `datetime.fromisoformat()` which in Python 3.11 handles most ISO formats but not all edge cases (e.g., `Z` suffix before 3.11).
- **为什么有问题**: This is a minor contract gap. The plan says Host uses its own parser, which is correct ownership. But without specifying the raw type and parsing contract, implementation agent may make inconsistent choices.
- **直接证据**: plan S3 WaitAdapterSnapshot contract says `created_at` but doesn't specify type derivation.
- **影响**: Low. Implementation agent will likely derive from existing Host timestamp helpers. Risk is minor type inconsistency.
- **建议改法和验证点**: Plan could add one sentence: "created_at 类型为 datetime，Host 从 WaitRecordRow 使用现有 durable timestamp parser 投影". Test should assert timezone-aware datetime.
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 005-未修复-低-S3 README update sequencing with S2

- **位置**: S3 "Allowed documentation files", "README / Documentation Decisions"
- **问题类型**: 测试缺口
- **当前写法**: "以下文档只在三个 production slice 的行为均已落地后做 current-fact 同步；该同步并入 S3/final validation closure，不另拆第 4 个 slice"
- **反例/失败场景**: If S3 is implemented and accepted before S2 (plan says S3 has "no code dependency" on S1/S2 and "建议在S2 accepted后实施"), the README updates in S3 would not include S2's storage atomicity and temp-less CN/HK changes. S3's README list does mention S2 impacts, but the sequencing assumption is that all three slices are done before README sync.
- **为什么有问题**: Plan's stop condition for S3 says "与S1/S2无代码依赖；为减少review互相掩盖，建议在S2 accepted后实施". The word "建议" (recommended) is weaker than "必须" (required). If S3 runs before S2, README would be incomplete.
- **直接证据**: S3 prerequisite says "建议在S2 accepted后实施", not "必须".
- **影响**: Low. The recommendation is clear and controller will likely enforce it. But if S3 runs first, README would miss S2 changes.
- **建议改法和验证点**: Change "建议" to "必须" in S3 prerequisite, or add explicit note: "README sync 必须在 S1+S2+S3 全部 accepted 后执行".
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Focus Area Assessment

### 1. Scope Correction: PASS

The plan correctly excludes all tool-security work:
- Non-Goals section (line 106-116) explicitly lists upload allowlist, URL/TLS/redirect/SSRF provenance, remote byte budgets, and LLM-facing security schema as non-goals.
- "Tool-Security Deferred Items" section (line 503-520) documents all four deferred items with evidence and destination.
- Success signal includes "无 tool schema、prompt、LLM-facing upload/download security text或安全配置变化" (line 102).
- CN/HK `pdf_bytes` change is explicitly framed as removing temp I/O, not adding byte budget (line 198).

No scope drift detected.

### 2. Storage Identity and LocalFileStore Atomicity: PASS WITH RISKS

S1 correctly identifies the owner (`_fs_storage_utils`, `_FsStorageInfra`, `_FsBlobMixin`, `LocalFileStore`) and proposes concrete changes. The single-component validator reuse, handle existence check unification, commit point rewrite, and LocalFileStore fsync/replace are all evidence-based.

Risk: Finding 003 (recovery phase semantic reversal) needs explicit statement. Otherwise S1 is implementable.

### 3. Single-Document Ingestion Atomicity: PASS WITH RISKS

S2 correctly identifies the batch scope for upload, generic download, and CN/HK. The "batch 内不 yield/await" invariant is the right constraint. The state/rollback matrix is comprehensive.

Risks: Finding 001 (token lifecycle) and 002 (cancel-during-batch) need clarification.

### 4. CN/HK Temp-Less Asset Contract: PASS

`pdf_bytes` is sufficient. Current code already holds full `response.content` in memory. Removing temp file handoff eliminates a cleanup seam without increasing memory usage or introducing security policy.

### 5. Wait Adapter Relocation: PASS

S3 correctly identifies the ownership chain: Host owns `WaitAdapterSnapshot`, Service owns `FinsObservationRuntime -> Host adapter result` glue, Fins only owns observation runtime. The minimal 3-field snapshot is the right boundary.

Risk: Finding 004 (created_at type) is minor.

### 6. Slice Count: PASS

3 slices are justified:
- Different semantic owners (storage, ingestion, host/service assembly)
- Different validation matrices
- Different failure blast radius (storage commit vs. document mutation vs. import boundary)
- S1 is prerequisite for S2, S3 is independent
- Compliant with `phaseflow-umbrella-optimization-control.md` production-high guidance

### 7. Validation: PASS

Per-slice validation commands are appropriate:
- Focused test commands for each slice
- pyright on full codebase
- `git diff --check`
- Import scans (Fins->Host, temp contract)
- Source scans (NamedTemporaryFile, pdf_path, tool-security diff)
- Coverage target `>=80%` per modified production file

No validation is missing or overly broad.

## Open Questions

None. All findings have sufficient evidence for resolution.

## Residual Risks And Suggested Tracking Destination

| Risk | Classification | Owner / destination |
|---|---|---|
| OS/hardware rollback rename failure may leave physical directory requiring recovery | covered by S1 recovery contract | `dayu.fins.storage` orphan recovery |
| Directory fsync best-effort on unsupported platforms | accepted, tracked if cross-platform requirement increases | Fins filesystem backend portability WU |
| Successfully committed prior document not rolled back on later document failure | accepted non-goal | multi-document transaction WU |
| CN/HK Docling synchronous conversion cannot be hard-interrupted | tracked by existing deferred finding | future process/subprocess isolation WU |
| Tool-security four items | assigned to later work unit | see plan "Tool-Security Deferred Items" |
| DR-024 Docling converter builder fallback | assigned to later work unit | umbrella controller decides future WU |

## Plan Review Conclusion

**Status: pass-with-risks**

The plan is structurally sound: correct owner boundaries, correct scope exclusion, correct slice sequencing, and correct validation design. Five findings were identified, all Low-to-Medium severity. No blocking finding prevents implementation from starting.

The most actionable finding is 001 (S2 token lifecycle contract), which should be clarified before S2 implementation begins. Findings 002-005 are implementation-phase details that the implementation agent can resolve with reasonable judgment, but would benefit from plan-level clarification.

## Artifact Path

`docs/reviews/wu-semantic-ownership-01-round3-r3-c-plan-review-mimo.md`

## Completion Report

- **status**: pass-with-risks
- **artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-plan-review-mimo.md`
- **findings count**: 5
- **blocking questions count**: 0
