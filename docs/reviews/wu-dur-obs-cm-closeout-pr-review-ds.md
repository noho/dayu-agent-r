# AgentDS PR 118 Deep Review

## Verdict: pass

无 blocking finding。PR 118 可进入 `draft-PR-pass`。

## Evidence Reviewed

| 证据来源 | 结论 |
|---|---|
| `gh pr view 118 --json` | draft PR，state=OPEN，base=main，0 errors/checks（draft 阶段正常） |
| `gh pr diff 118` | 21,107 行新增，439 行删除，48 个文件变更 |
| `git status` | 工作区干净，无未提交修改 |
| `pyright` | 0 errors, 0 warnings, 0 informations |
| `pytest tests/engine/test_engine_event_contract.py tests/host/test_context_compact_events.py -q` | 48 passed |
| `pytest tests/host/test_compaction_operation.py tests/host/test_engine_ingest_mapping.py -q` | 105 passed |
| `pytest tests/host/test_run_input_builder.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py -q` | 89 passed |
| `pytest tests/host/test_public_compact_smoke.py tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_tool_wiring_smoke.py -q` | 13 passed, 1 skipped |
| 1 skipped test | `test_real_compactor_public_opener_compacts_and_preserves_continuity` — 环境门控，PR body 已声明为 residual，non-blocking |
| `docs/host/issues-implementation-control.md` residual 表 | 所有 tracking items 处于 closed / transferred-to-issue；WU-ENG-02-S3-R1 已转 issue #119 |
| 最近 residual fix commits | 81402233（runner call iteration link）、454f2aa0（compactor trigger enum）、e92c4118（outcome manifest ref）、56afea6e（usage correlation→issue）— 均小范围、有测试覆盖、有 review artifact |
| `AGENTS.md` 约束 | LLM-facing 文本、架构硬约束、编码硬约束、README 同步规则均已核对 |
| `docs/host/design.md` | 新增 runner-call reconstruction 冷热分离、tool-call request atoms、compactor input projection 等设计段落，与实现一致 |

## Blocking Findings

无。

## Non-blocking Findings / Residuals

### NF-1: Real compactor smoke 环境门控（已声明 residual）

- **文件**: `tests/host/test_public_compact_smoke.py`
- **证据**: `test_real_compactor_public_opener_compacts_and_preserves_continuity` 默认 SKIPPED，需 `DAYU_RUN_REAL_COMPACTOR_SMOKE=1`
- **影响**: 真实 LLM compactor 路径的端到端正确性未经 CI 验证；当前 only deterministic fake compactor 有覆盖
- **Owner**: PR body 已声明 "real provider matrix and real compactor smoke remain environment-gated"
- **Severity**: non-blocking，已在 PR description residual risk 中声明

### NF-2: GitHub checks 缺失

- **证据**: `gh pr view 118` 返回 `statusCheckRollup: []`
- **影响**: 无 CI 自动运行；但本地 pyright + pytest 均已通过，PR 为 draft 状态，checks 通常不触发
- **Severity**: non-blocking，draft PR 阶段正常；mark ready for review 前确认 CI 配置可用即可

### NF-3: `utils/smoke_host_public_diagnostics.py` 为诊断辅助脚本，非独立入口

- **证据**: PR body "utils/smoke_host_public_diagnostics.py is a diagnostics helper, not a standalone runner-call smoke entry point"
- **影响**: 不影响生产代码；诊断脚本无测试覆盖要求（CLAUE.md 明确 `utils/` 下脚本无覆盖率要求）
- **Severity**: non-blocking

## Key Design Observations（非 finding，仅记录）

### O-1: `_append_iteration_started_events` 状态机设计正确

`dayu/host/engine_ingest.py` 中的 link resolution 逻辑（line ~2820-2953）按以下顺序处理：
1. 已有 link event → 校验 link 一致性（mismatch → `ENGINE_EVENT_REJECTED`）
2. 无 link → 查找 unlinked prepared manifest → ambiguous（>1）→ fail closed
3. 无 prepared manifest → 有 prior iteration observation → limited-signal manifest（tool continuation）
4. 无 prepared manifest → 无 prior observation → fail closed（missing manifest）
5. 单一 prepared manifest → 写入 `RUNNER_CALL_INPUT_ITERATION_LINKED` → digest 校验 → mismatch fail closed

每个分支都有明确的 reject reason，fail closed 行为一致。

### O-2: Proposal manifest 写入时机正确

`DurableCompactorProposalManifestRecorder.record_compactor_proposal_manifest()` 在 compactor runner call **之前**（而非之后）写入 manifest。artifact 写入顺序正确：先写 compactor input projection artifact → 再写 manifest artifact → 再写 SQLite payload descriptors → 最后 append EventLog canonical fact。符合 design.md 中 "artifact 发布必须先于 EventLog canonical append" 的设计约束。

### O-3: LLM-facing 文本改进符合 AGENTS.md 约束

`conversation_compaction.md` 和 `conversation_compaction_user.md` 的变更：
- 删除了内部类型名 `ConversationCompactOutputVNext`
- 不再暴露 `Host-owned context compaction 组件` 等 Host 实现术语
- 新增自足字段说明：字段名、类型、必填性、允许值、label 规则
- label 明确为"本次请求内的引用标签"，不伪装为业务事实
- 所有允许值（`trace_kind`、`intent_type`、`status`、`reason`、`evidence_kind`）均自足说明

### O-4: Compactor outcome manifest ref 设计正确

`CONTEXT_COMPACTED` payload 新增 `accepted_proposal_manifest_ref` / `accepted_proposal_manifest_digest`，`CONTEXT_COMPACTION_ATTEMPT_REJECTED` payload 新增 `proposal_manifest_ref` / `proposal_manifest_digest`。使用 `_validate_optional_ref_digest_pair` 确保 ref/digest 必须成对出现。符合 design.md 中 "compact outcome payloads reverse-reference the proposal manifest via ref/digest pairs" 的设计约束。

### O-5: Engine `IterationStartedData` 扩展后向兼容

新增 `role_sequence_digest` 和 `runner_input_serializer_schema_version` 为 frozen dataclass 新增字段，不影响已有 consumer。Engine 不依赖 Host 状态机，只描述自身可观测输入形态。

### O-6: `TOOL_CALL_REQUESTED` durable request atoms 设计正确

ToolRuntime accept barrier 写入 `TOOL_CALL_REQUESTED` canonical fact 时，small arguments 内联，large arguments 写 `tool_call_arguments_json` payload descriptor；semantic query 可选，短文本内联，长文本写 `tool_call_semantic_query_text` descriptor。Compaction evidence 路径通过 `payload_resolution.tool_call_request_atoms()` 读取 durable atoms 并校验同源（tool_call_id + tool_name + normalized_arguments_digest），不匹配时 fail safe 输出 limited-signal 文本。

## Validation Commands

已执行验证：

```bash
source .venv/bin/activate && pyright
# → 0 errors, 0 warnings

python -m pytest tests/engine/test_engine_event_contract.py tests/host/test_context_compact_events.py -q
# → 48 passed

python -m pytest tests/host/test_compaction_operation.py tests/host/test_engine_ingest_mapping.py -q
# → 105 passed

python -m pytest tests/host/test_run_input_builder.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py -q
# → 89 passed

python -m pytest tests/host/test_public_compact_smoke.py tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_tool_wiring_smoke.py -q
# → 13 passed, 1 skipped
```

## Draft-PR-pass Recommendation

**通过。** 无 blocking finding。所有 residual 均有 owner（环境门控、issue #119）。代码变更与设计真源一致，状态机 fail-closed 路径完整，LLM-facing 文本符合 AGENTS.md 约束，测试覆盖充分，pyright 零错误。PR 118 可进入 `draft-PR-pass`。
