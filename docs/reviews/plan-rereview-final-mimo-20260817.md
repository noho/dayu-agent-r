# UF-FIX11 Plan Final Re-Review — DS-RR1/DS-RR2 Closure Verification

## Review Target and Scope

- **Reviewed target**: `docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md`（经 A1-A10 + DS-RR1/DS-RR2 修订）
- **Fix2 artifact**: `docs/gateflow/uf-fix11-plan-rereview-fix2-20260817.md`
- **DS re-review**: `docs/reviews/plan-rereview-ds-20260817.md`
- **Scope**: 仅核对 DS-RR1/DS-RR2 是否完整关闭，确认 parser 前移到 Slice 2 未引入 material/ownership/slice drift。不重开已关闭 A1-A10。

## DS-RR1 Closure Verification

**Finding**: §6.6 要求"所有 FILING terminal JSON 显式携带 warnings"，但 Slice 2 未点名 SEC/CN failure event builder，漏改会把 typed failure 退化为 generic failure。

**Plan 修订验证**:

1. **Slice 2 Exact changes 第 8 点** ✅ 已修复
   - 原文："SEC/CN 只从 shared outcome 序列化成功/skip warnings；枚举并收敛所有 filing terminal producer：normal `ok`/`skipped` 使用 shared warnings，early cancelled/delete 显式 `warnings=[]`，`_build_sec_filing_failure_event(...)` 与 `_build_cn_filing_failure_event(...)` 构造的每个 failed result 都必须把 `warnings=[]` 传入各自 result builder。禁止 failure builder 省略字段，也禁止从 exception/message 推断 warning；不触碰 material/download semantics。"

2. **Slice 2 Tests** ✅ 已修复
   - 原文："真实 failure producer/roundtrip：分别新增 `test_sec_filing_failure_event_roundtrips_typed_reason_with_empty_warnings` 与 `test_cn_filing_failure_event_roundtrips_typed_reason_with_empty_warnings`（名称可按文件惯例微调但语义不得变）。测试必须执行真实 filing workflow 触发 `_build_sec_filing_failure_event`/`_build_cn_filing_failure_event`，不得手工拼 result dict 或 mock parser；从 terminal event 取 `payload["result"]`，先断言 raw `warnings == []`，再调用 `FinsUploadPipelineResult.from_pipeline_json(..., source_kind=SourceKind.FILING)`，断言原 `FinsUploadFailureReason` 的 code/kind/message 保留且 parsed `warnings == ()`。"

3. **Slice 2 Stop condition** ✅ 已修复
   - 原文："任一 SEC/CN filing terminal producer（尤其 `_build_sec_filing_failure_event`/`_build_cn_filing_failure_event`）省略 `warnings`，或 failure roundtrip 退化为 generic exception failure；"

**结论**: DS-RR1 已完整关闭。Plan 明确点名两个 failure builder，要求显式 `warnings=[]`，增加真实 producer roundtrip tests，并在 stop condition 中拦截。

## DS-RR2 Closure Verification

**Finding**: Slice 2 的 SKIP+commit 分支 wiring 未写死 `batch_terminal_started` capability 转交，漏设会把已 durable 的成功提交反转为异常终态。

**Plan 修订验证**:

1. **Slice 2 Exact changes 第 4 点** ✅ 已修复
   - 原文："SKIP + preserve intent 必须严格执行 `stage_upload_company_meta_decision(...) -> batch_terminal_started = True -> batching_repository.commit_batch(batch) -> build_prepared_filing_skip_result(...) -> dataclasses.replace(...)`。flag 必须在 commit 调用前设置，表示 capability 已转交 storage；commit 成功或抛错后 outer `finally` 均不得二次 rollback。该分支禁止调用 `publish_prepared_upload(...)`、`commit_prepared_upload_batch(...)` 或 stage 任何 filing/source asset。"

2. **Slice 2 Tests** ✅ 已修复
   - 原文："SKIP capability 成功：terminal-aware batching spy 断言执行顺序为 stage -> capability transfer -> commit，`commit_count == 1`、caller `rollback_count == 0`，返回 `skipped` 且 alias/company outcome durable；若 outer finally 尝试 rollback 已消费 token，测试必须直接失败。"
   - 原文："SKIP capability 失败：让 `commit_batch` 在消费 capability 后抛既有 storage/typed error，断言原异常/typed failure 保留、`commit_count == 1`、caller `rollback_count == 0`、无 warning；禁止 finally 二次 rollback 覆盖主异常。另保留 commit 前 stage error 仍恰好 rollback 一次的对照断言，证明 flag 只在 capability 真正转交前后分界。"

3. **Slice 2 Stop condition** ✅ 已修复
   - 原文："SKIP metadata commit 未在 `commit_batch` 前设置 `batch_terminal_started = True`，或 commit 返回/抛错后 outer finally/exception handler 再次 rollback；"

**结论**: DS-RR2 已完整关闭。Plan 写死了 exact sequence，明确 `batch_terminal_started = True` 必须在 `commit_batch` 前设置，增加成功/失败/对照 tests，并在 stop condition 中拦截。

## Parser 前移到 Slice 2 的 Drift 检查

**变更**: A4 的 parser boundary 从 Slice 3 前移到 Slice 2。

**Material/Ownership/Slice Drift 检查**:

1. **Ownership Drift** ❌ 未发生
   - Parser (`FinsUploadPipelineResult.from_pipeline_json`) 的 owner 是 `ingestion_runtime.py`
   - Slice 2 Allowed files 明确包含 `dayu/fins/ingestion_runtime.py`（仅落地 filing/material warnings parser contract，供真实 producer roundtrip）
   - 这是 parser owner 的正常修改，没有引入跨 ownership 边界的修改

2. **Slice Drift** ❌ 未发生
   - Slice 2 Exact changes 第 11 点明确："为让 producer/schema 在同一 slice 可验收，把 A4 的 parser boundary 提前在本 Slice 完成"
   - Slice 3 Exact changes 第 1 点明确："复用 Slice 2 已冻结的 `FinsUploadPipelineResult.from_pipeline_json(result, *, source_kind: SourceKind)` 与 typed warnings；本 Slice 不重新决定 missing/null/closed-shape schema，只做 summary/durable/direct/service 投影并保留 parser regression"
   - 这是一个原子 schema slice，不是 material scope 扩张

3. **Material Scope Drift** ❌ 未发生
   - Slice 2 Allowed files 明确限制修改范围："dayu/fins/ingestion_runtime.py（仅落地 filing/material warnings parser contract，供真实 producer roundtrip）"和 "dayu/fins/service_runtime.py（仅同步全部 parser callsite 的显式 `SourceKind`）"
   - 这是 parser contract 和 callsite 同步，没有扩大到 material scope

4. **Producer/Schema 原子性** ✅ 正确
   - fix2 artifact 第 5.1 节明确："producer 与 strict parser 必须在同一 Slice 2 原子收敛，并用真实 workflow event roundtrip 验证；handcrafted dict 或 mock parser 不能证明生产 builder 正确。"
   - 这是正确的架构决策：producer 和 parser 必须在同一 slice 可验收

**结论**: Parser 前移到 Slice 2 没有引入 material/ownership/slice drift。这是一个原子 schema slice，确保 producer 和 parser 在同一 slice 可验收。

## Open Questions

无。

## Residual Risks

| Residual | Classification | Owner/destination |
| --- | --- | --- |
| name-only metadata batch writer lock/physical swap 成本 | `assigned to later work unit` | 后续性能/存储 work unit |
| material company-name warning | `assigned to later work unit` | 独立 material work unit |
| 真实 CLI evidence、oracle/scenario/frozen evidence | `assigned to later work unit` | evidence work unit |
| durable 后 guard-release/cleanup 报错时不发 warning | `assigned to later work unit` | storage operations work unit |

没有未分类 residual risk。

## Plan Review Conclusion

**pass**

DS-RR1 和 DS-RR2 已完整关闭：

- **DS-RR1**: Plan 明确点名 `_build_sec_filing_failure_event`/`_build_cn_filing_failure_event`，要求显式 `warnings=[]`，增加真实 producer roundtrip tests，并在 stop condition 中拦截。
- **DS-RR2**: Plan 写死了 exact sequence `stage -> batch_terminal_started=True -> commit_batch -> build result -> replace`，增加成功/失败/对照 tests，并在 stop condition 中拦截。

Parser 前移到 Slice 2 没有引入 material/ownership/slice drift。这是一个原子 schema slice，确保 producer 和 parser 在同一 slice 可验收。

Plan 可以进入 implementation。
