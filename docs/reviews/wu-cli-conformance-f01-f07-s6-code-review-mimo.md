# Code Review — WU-CLI-CONFORMANCE-F01-F07 S6 / F06

## Scope

- Mode: current changes（未提交，base `64c581f1`）
- Branch: `codex/interactive-oracle`
- Base: `64c581f1f03f51e2651f822a1b2dcfb775f16c94`
- Output file: `docs/reviews/wu-cli-conformance-f01-f07-s6-code-review-mimo.md`
- Included scope: 6 files（2 production、3 test、1 design doc）+ implementation artifact
- Excluded scope: frozen registry、archive docs、review artifacts
- Parallel review coverage: 无

## Context 读取

| 来源 | 状态 |
|---|---|
| `AGENTS.md` | 已读取 |
| Accepted plan `wu-cli-conformance-f01-f07-plan-codex.md` §8 | 已读取（F06 机械重命名闭包定义） |
| Plan-fix `wu-cli-conformance-f01-f07-plan-fix-codex.md` §3.3 | 已读取（F06 机械重命名闭包） |
| Frozen F06 `F06-context-governance-trigger-name` | 已读取 |
| Implementation artifact `wu-cli-conformance-f01-f07-s6-implementation-codex.md` | 已读取 |
| 六文件 diff（`git diff 64c581f1`） | 已读取 |
| Host design `docs/host/design.md` trigger 表 | 已读取 |

## Findings

未发现实质性问题。

## Verification Summary

### 1. Producer → strict persistence/read → generic ingest → public trace 闭合

**producer 闭合**：`run_input.py` 的两条 producer 路径均已切换到 `_RUNNER_CALL_TRIGGER_CONTEXT_GOVERNANCE_RESOLVED`：
- `_prepared_candidate_kind_and_trigger()` L6674：`candidate.context_fallback_decision_ref is not None or candidate.compact_artifact_refs` 分支
- `_runner_call_kind_and_trigger()` L7979：`started_payload.start_reason is RECOVERY or record_input.fallback is not None` 分支

两者复用同一个 module-level symbol（L338），无 inline literal。

**strict persistence/read 闭合**：`_runner_call_manifest.py` 的 `_RUNNER_CALL_TRIGGER_REASONS` frozenset（L147-162）只含 `context_governance_resolved`，旧 literal 已删除。

**generic ingest 闭合**：`test_engine_ingest_mapping.py` 验证 success compact recovery manifest（L1416/1430）和 failed fallback recovery manifest（L2793/2795）的 hot/durable round-trip。`test_run_input_builder.py` 验证 `_single_runner_call_manifest_payloads` helper 通过 `event_payload_object` strict 解析 durable payload。

**public trace 闭合**：`test_tool_trace_projection.py` L2446-2458 验证 `runner_call_trigger_reason` 透传且不生成 `context_compaction_outcome`/`compact_artifact_ref`/`fallback_action`。

### 2. Success/fallback 都只用 `context_governance_resolved`

- Success compact 路径：`test_engine_ingest_mapping.py` L1416（hot）+ L1430（durable manifest）
- Failed fallback 路径：`test_engine_ingest_mapping.py` L2793（hot）+ L2795（durable manifest）
- RunInput builder success 路径：`test_run_input_builder.py` L3771-3776
- RunInput builder fallback 路径：`test_run_input_builder.py` L3941-3947

两条路径的 trigger reason 均为 `context_governance_resolved`，`post_compaction_dispatch` kind 正确配对。

### 3. 旧 symbol/literal 零残留 + 旧/unknown 输入 strict 拒绝

**零残留扫描**：
- `rg 'context_compaction_completed' dayu/ tests/ docs/host/design.md`：0 命中
- `rg '_RUNNER_CALL_TRIGGER_CONTEXT_COMPACTION_COMPLETED' dayu/ tests/`：0 命中

旧值仅存在于 `docs/host/archive/`（frozen historical evidence）和 `docs/reviews/`（review artifacts），均为只读历史文档。

**strict rejection**：`test_runner_call_manifest_rejects_stale_and_unknown_governance_trigger`（L6129-6194）：
- 参数化两个 invalid 值：`"context_compaction_" + "completed"`（旧值，用字符串拼接避免扫描误命中）和 `"unknown_context_governance_trigger"`（未知值）
- hot reader：`pytest.raises(HostDurableError, match="runner_call_trigger_reason")`
- manifest reader：`pytest.raises(HostDurableError, match="runner_call_trigger_reason")`

### 4. 无 alias/re-export/normalize/migration

- 生产代码中无 `context_compaction_completed` 别名或 re-export
- 无 normalization/loose parsing 路径
- 无 migration helper
- `_RUNNER_CALL_TRIGGER_REASONS` 是 closed frozenset，只做 membership check

### 5. Trigger 不冒充 CONTEXT_COMPACTED/FAILED

- `docs/host/design.md` L3166 明确：`context_governance_resolved` 表达"governance 已收口并允许下一次 dispatch"；精确 success/failure outcome 仍只由 `CONTEXT_COMPACTED`/`CONTEXT_COMPACTION_FAILED` 及其 artifact/fallback refs 拥有
- `test_tool_trace_projection.py` L2456-2458 断言 trace summary 中不存在 `context_compaction_outcome`/`compact_artifact_ref`/`fallback_action`
- 实现 artifact §3.3 正确描述 outcome ownership 分离

### 6. 测试证明 roundtrip/hot link/trace 透传

- **roundtrip**：`test_engine_ingest_mapping.py` 从 durable store 写入 → `parse_runner_call_hot_payload` 读取 hot → `sqlite_payload_object` 读取 durable → `parse_runner_call_manifest` strict 解析 → 断言两者一致
- **hot link**：`test_engine_ingest_mapping.py` L6074-6126 的 parametrized `test_iteration_started_links_all_ordinary_dispatch_kinds` 验证 `post_compaction_dispatch`/`context_governance_resolved` pair 在 generic iteration link 中正确工作
- **trace 透传**：`test_tool_trace_projection.py` 直接构造含新 trigger 的 event payload → 投影 → 断言 `trace_summary` 包含新值且不含 outcome fields

### 7. 设计语义一致

- `docs/host/design.md` 的 trigger 表描述准确区分了 trigger（为何允许 dispatch）与 outcome（compact 最终结果）
- implementation artifact 的语义 owner 表与 plan §8/plan-fix §3.3 一致
- `post_compaction_dispatch` kind 同时覆盖 success compact recovery 和 failed fallback recovery，因为 kind 表达 dispatch 机制而非 outcome

### 8. 验证结果

| 校验 | 结果 |
|---|---|
| Focused pytest（275 tests） | PASS |
| Pyright（changed files） | 0 errors, 0 warnings |
| Pyright（full `dayu/ tests/ utils/`） | 0 errors, 0 warnings |
| Coverage `run_input.py` | 84% (>= 80% PASS) |
| Coverage `_runner_call_manifest.py` | 88% (>= 80% PASS) |
| 旧 symbol/literal 零残留 scan | PASS |
| `git diff --check` | PASS |
| Frozen registry SHA-256 保持 | PASS |

## Open Questions

无。

## Residual Risk

- Frozen real-provider CLI evidence refresh 由后续 S8 覆盖，本 slice 不伪报真实 provider scenario 已刷新。
- S7 fresh compaction schema / accept barrier 由后续 S7 覆盖，本 slice 未修改其 schema、repair、Memory 或 terminal semantics。

## Verdict

S6 implementation 正确完成了 F06 的机械重命名闭包。producer、strict persistence/read、generic ingest、public trace 四层全部使用 `context_governance_resolved`；旧 symbol/literal 零残留；旧/unknown 输入 strict fail closed；无 alias/re-export/normalize/migration；trigger 不冒充精确 outcome；测试证明 roundtrip/hot link/trace 透传；设计语义一致。未发现实质性问题。
