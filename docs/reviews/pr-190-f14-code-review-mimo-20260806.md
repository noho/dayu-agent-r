# Code Review

## Scope

- Mode: current changes
- Branch: `codex/interactive-oracle`
- Base: `b222b8b064f096d899a9de708e45cd1fb6e732e6` (accepted plan commit)
- Output file: `docs/reviews/pr-190-f14-code-review-mimo-20260806.md`
- Included scope:
  - `dayu/host/compact_material.py` (production code)
  - `tests/host/test_compact_material.py` (owner tests)
  - `tests/host/test_dispatch_scheduler.py` (integration test helper)
  - `tests/host/test_run_input_builder.py` (integration test helper)
  - `dayu/host/README.md` (documentation)
  - `docs/host/design.md` (documentation)
- Excluded scope: `dayu/engine/**`, `dayu/config/prompts/**`, provider/model, UI, Service, CLI
- Parallel review coverage:
  - Subagent 1: `compact_material.py` 全部 10 个关键函数逐行走读 — 未发现实质性问题
  - Subagent 2: `test_compact_material.py` F14 相关 12 个测试函数 — 发现 2 个中/低覆盖缺口
  - Subagent 3: `test_dispatch_scheduler.py` + `test_run_input_builder.py` fixture 修改 — 未发现实质性问题
  - Subagent 4: `README.md` + `design.md` 文档变更 — 发现 1 个文档准确性问题

## Conclusion

**NEEDS_FIX**

实现核心算法正确，严格按 accepted plan 的两阶段算法执行。fail-closed 行为完整，ref 完整性校验覆盖 missing/self/forward/cross-session 场景。321 个受影响测试全部通过，pyright 0 errors，覆盖率 84%。需要补充 2 个测试覆盖缺口和 1 个文档修正。

## Findings

### 1-未修复-中-缺少 rolling monotonicity 多轮测试（plan A.3）

- **入口/函数**: test suite
- **文件(行号)**: `tests/host/test_compact_material.py`
- **输入场景**: 3+ 轮 accepted compact，每轮消费不同 Run group
- **实际分支**: 当前 `test_pre_dispatch_cumulative_accepted_chain_advances_only_complete_groups` 只覆盖 2 轮，且只验证最终 frontier 绝对值
- **预期行为**: accepted plan A.3 要求"多轮 rolling compact 断言 frontier 单调不回退，但只能跨越已消费完整 groups；保留 group 内 canonical order、不同 group 间 EventLog order，无 gap/duplicate"
- **实际行为**: 2 轮测试覆盖了 cumulative 消费和 shared current_input_ref，但未构造 3+ 轮场景，也未做 `frontier_1 <= frontier_2` 的显式单调断言。如果实现引入回退 bug，当前断言可能碰巧通过
- **直接证据**: plan `docs/gateflow/pr-190-f14-accepted-coverage-frontier-plan-20260806.md` 第 212-213 行
- **影响**: 无法验证 3+ 轮 rolling 场景下 frontier 的单调性和 order 不变量
- **建议改法和验证点**: 新增测试构造 3 个 raw group + 3 轮 accepted compact（可复用同一 current_input_ref），每轮消费一个 group，断言每轮 frontier 单调递增且 material_blocks 保持 canonical order、无 gap/duplicate。显式 `assert frontier_i <= frontier_{i+1}`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 2-未修复-中-缺少 reconnect 场景测试（plan C.4）

- **入口/函数**: test suite
- **文件(行号)**: `tests/host/test_compact_material.py`
- **输入场景**: correction 退出 selected recent floor 后，ordinary RunInput 从正式 accepted replacement / Memory 与正确 raw frontier 得到一致语义
- **实际分支**: 无对应测试
- **预期行为**: accepted plan C.4 要求"reconnect：correction 退出 selected recent floor 后，ordinary RunInput 仍只能从正式 accepted replacement / Memory 与正确 raw frontier 得到一致语义"
- **实际行为**: 当前测试覆盖了 restart（关闭重开 durable store 后 view 一致），但未覆盖 reconnect 场景——即 protected group 离开 recent floor 后被第二次 compact 消费，断言 Memory/RunInput 的 frontier 和语义一致
- **直接证据**: plan 第 234 行
- **影响**: 无法验证 correction group 离开 recent floor 后 RunInput/reconnect 的语义一致性
- **建议改法和验证点**: 新增测试构造 correction group 在 recent floor 内被保护 → 离开 floor → 被第二次 compact 消费的场景，断言 reconnect 后 Memory/RunInput 的 frontier 和语义一致
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 3-未修复-低-design.md 将 material coverage frontier 校验错误归类为 "build 启动前"

- **入口/函数**: design.md 文档描述
- **文件(行号)**: `docs/host/design.md` diff 中 "Compact material data block build 启动前必须校验" 段落
- **输入场景**: 维护者阅读 design.md 理解校验时机
- **实际分支**: 文档描述为 "build 启动前必须校验...material coverage frontier 必须与 cumulative accepted compacted_source_refs...一致"
- **预期行为**: `_validate_accepted_compact_entry_references` 在 chain 构建期间执行（校验 current_input_ref 和 previous ref），material coverage frontier 的 prefix proof 和 atomic proof 在 build 流程内部执行（`_conservative_unconsumed_row_start_sequence` + `_unconsumed_atomic_material_blocks`）
- **实际行为**: 文档把两类不同时间点的校验合并描述为 "build 启动前"，夸大了 pre-build validation 的范围
- **直接证据**: `build_pre_dispatch_compact_material_view` 行 505-544：chain 构建期间做 ref 校验，material 投影期间做 frontier 校验
- **影响**: 误导维护者对校验时机的预期，不影响正确性
- **建议改法和验证点**: 将描述改为 "build 期间必须校验"，或分两处描述：chain 构建时校验 ref 完整性，material 投影时校验 frontier 一致性
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无

## Residual Risk

1. **FY2024/2025 evidence ownership (plan B.2)**: plan 要求"FY2024 旧 fact refs 保持原值；FY2025 correction 只能从新的 accepted tool evidence atom 进入新的 replacement，refs 非空且不借用旧 ref"。这是 production CLI observation 级别的验证，当前 unit tests 已覆盖 evidence_id ≠ EventLog event_id 的基本分离，但完整的 FY2024/2025 场景需要真实 CLI observation 验证
2. **cancelled/stale/late 状态机**: 当前测试只覆盖 CONTEXT_COMPACTION_ATTEMPT_REJECTED 和 CONTEXT_COMPACTION_FAILED 两种 non-accepted event type。cancelled/stale/late 本质上不产生 CONTEXT_COMPACTED（与 rejected/failed 走同一查询排除路径），但未在此文件显式覆盖。plan 允许复用既有 scheduler/operation owner tests
3. **`run_id=None` canonical row**: 生产中是否存在 `run_id=None` 的 canonical row 需确认。当前实现对此做了防御性处理（conservative frontier 保守保留，atomic proof 兜底），但无显式测试覆盖
4. **Coverage**: `dayu/host/compact_material.py` 单文件覆盖率 84%（≥80% 目标），未覆盖行主要是错误路径的极端情况

## Implementation Quality Summary

### 正确实现的要点

1. **accepted chain 读取**: 一次查询全部 CONTEXT_COMPACTED rows，按 sequence ASC 排列，每条 strict parse 一次。fail-closed 完整：event class/type/session 不一致、row 消失、payload 损坏、semantic binding 失败均抛 HostDurableError
2. **ref 完整性校验**: current_input_ref 必须指向同 session 更早的 USER_INPUT_ACCEPTED；PREVIOUS_* source refs 必须指向同 session 更早的 CONTEXT_COMPACTED；self/forward/cross-session/missing 均 fail closed。非 PREVIOUS kind 的 source_refs 语义上不应指向 CONTEXT_COMPACTED，由上游 proposal-boundary binding 保证一致性
3. **consumed refs 累积**: 从 chain 的 compacted_source_refs 按 terminal/boundary order 做 ordered-unique union，不从 flat evidence aggregate 生成。正确区分了 compacted_source_refs（全量 consumed）与 accepted_evidence_mapping_refs（仅 latest replacement evidence）
4. **conservative frontier**: 用 user anchor proof 跳过已消费 Run group prefix，不解析历史 payload。缺 user anchor、多 user anchor、run_id=None 均保守处理
5. **atomic proof**: 对保守 suffix 的 typed blocks 做 all-or-none 校验：block 部分覆盖 fail closed、unit 混合状态 fail closed、非 prefix 模式 fail closed
6. **frontier 派生**: _post_compact_delta_start_sequence 改为纯派生 helper，不再执行 SQL
7. **downstream 同源**: previous_compacted_view 只从 latest strict replacement 构造；represented_evidence_refs 只从 latest entry 投影；material frontier 只使用 chain 的 compacted_source_refs

### 与 plan 的一致性

- ✅ 不新增表、字段、cursor、schema、public contract
- ✅ 删除了重复 payload 解析（_accepted_evidence_mapping_refs_from_compacted_event、_previous_compacted_view_pair_from_compacted_event）
- ✅ _accepted_tool_evidence_delta_blocks 删除了 represented_evidence_refs early skip
- ✅ _pre_dispatch_delta_material_blocks 删除了 event_log_store 和 represented_evidence_refs 参数
- ✅ _post_compact_delta_rows 删除了 start_sequence 参数，读取全部 relevant rows
- ✅ test fixtures 使用真实 current_input_ref 和 per-label source_refs，不是 synthetic defaults
- ✅ README 和 design.md 正确区分了 terminal sequence 与 accepted consumption frontier

### 测试覆盖

| Plan 要求 | 状态 | 测试函数 |
|-----------|------|---------|
| A.1 protected raw 不被消费 | ✅ | test_pre_dispatch_accepted_compact_does_not_consume_protected_raw_suffix |
| A.2 aging 后 eligible + 第二次 compact 消费 | ✅ | 同上（含 aging 场景） |
| A.3 rolling monotonicity 3+ 轮 | ⚠️ | 仅 2 轮，缺显式单调断言 |
| A.4 partial coverage fail closed | ✅ | test_pre_dispatch_partial_atomic_coverage_fails_closed |
| A.5 previous ref 不越界消费 | ✅ | test_pre_dispatch_previous_compact_ref_preserves_uncovered_raw_material |
| A.6 multiple reactive compacts 复用 current_input_ref | ✅ | test_pre_dispatch_cumulative_accepted_chain_advances_only_complete_groups |
| A.6 invalid current_input_ref fail closed | ✅ | test_pre_dispatch_accepted_chain_rejects_invalid_current_input_reference (3 parametrize) |
| A.6 invalid previous ref fail closed | ✅ | test_pre_dispatch_accepted_chain_rejects_invalid_previous_compact_reference (4 parametrize) |
| B.1 evidence_id ≠ EventLog id | ✅ | fixture 使用 evidence:{event_id} 格式 |
| B.2 FY2024/2025 refs 分离 | ⚠️ | 需 production CLI observation |
| C.2 rejected/failed 不推进 frontier | ✅ | test_pre_dispatch_non_accepted_compaction_events_do_not_advance_frontier |
| C.3 restart | ✅ | test_pre_dispatch_accepted_compact_does_not_consume_protected_raw_suffix (含 reopen) |
| C.4 reconnect | ⚠️ | 缺失 |
| D. 同源投影 | ✅ | test_pre_dispatch_second_compact_rolls_from_latest_accepted_proposal |
| Coverage ≥ 80% | ✅ | 84% |
