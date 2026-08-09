# Interactive Conversation Memory Closure F08-F10 Aggregate Deepreview

## Scope

- **Mode**: Current Changes Mode (aggregate deepreview)
- **Branch**: `codex/interactive-oracle`
- **Base**: `68ba4038` (accepted plan checkpoint)
- **Review range**: `68ba4038..fd15b660` (3 commits: F08, F09, F10)
- **Output file**: `docs/reviews/wu-interactive-memory-closure-f08-f10-aggregate-deepreview-mimo.md`
- **Included scope**: 52 files changed, 8226 insertions, 181 deletions
  - 6 production files: `compact_material.py`, `compact_pipeline.py`, `compaction.py`, `compaction_operation.py`, `context_governance.py`, `dispatch.py`
  - 1 prompt file: `conversation_compaction_user.md`
  - 1 manifest file: `cli_init_workspace_manifest_v1.json`
  - 10 test files
  - 34 slice review/fix/adjudication artifacts
- **Excluded scope**: generated/vendor/build/cache, frozen baseline files (read-only verification only)
- **Parallel review coverage**: 4 subagents covered implementation files, test files, design docs, and slice artifacts

## Frozen Baseline Verification

| File | Expected SHA-256 (from accepted-plan checkpoint) | Current SHA-256 | Status |
|------|--------------------------------------------------|-----------------|--------|
| `docs/cli_ci_oracles.json` | `da04923193a04c0e33eca9c60e0d8eb919b74963b2c2f4170954be2f07261201` | `da04923193a04c0e33eca9c60e0d8eb919b74963b2c2f4170954be2f07261201` | ✓ Match |
| `docs/cli_ci_scenarios.json` | `7c991d14ebc79f9f8e8c66d9eb94c10156c5a36eecd3bb11df24ed18cbca2093` | `7c991d14ebc79f9f8e8c66d9eb94c10156c5a36eecd3bb11df24ed18cbca2093` | ✓ Match |
| `docs/reviews/wu-interactive-memory-closure-f08-f10.md` | `95a09543fc7f1a2a09f99dbe2c2c014e71ac22f2c386dc5364f6a1a2d14b1b08` | `95a09543fc7f1a2a09f99dbe2c2c014e71ac22f2c386dc5364f6a1a2d14b1b08` | ✓ Match |

## Test & Type Verification

| Check | Result |
|-------|--------|
| Focused owner suite (10 test files) | 418 passed, 1 skipped |
| Pyright (6 production files) | 0 errors, 0 warnings, 0 informations |
| Frozen baseline digests | All 3 match accepted-plan checkpoint |

## Findings

### 未发现实质性问题

经过对 52 个变更文件的完整走读、跨 slice 数据一致性检查、frozen baseline 验证、测试覆盖分析和架构边界审查，未发现实质性问题。

## Cross-Slice Data Truth Consistency Analysis

### F08: Prompt Meaningful-Summary/Null

**审查结论**: ✓ 正确自足，不伪装 deterministic verifier。

- Prompt 使用纯业务语言定义"有意义摘要"：至少一条完整、可独立理解的业务陈述
- null 语义自足：清除旧 summary，不影响其它四类 memory
- Host 不做自然语言 heuristic（设计明确 non-goal）
- SHA 三级溯源链完整：prompt raw → manifest entry → smoke test frozen constant
- Memory projector owner test 通过完整生产链验证 null replacement（accepted event → projector → snapshot → JSON round-trip）

### F09: Canonical Manifest/EventLog/Hot/Public Resolver Identity

**审查结论**: ✓ 同源且 fail-closed。

- 核心修复：`DurableCompactorProposalManifestRecorder.record_compactor_proposal_manifest` 将 `EventLogAppendRequest.payload_ref` 和 `payload_digest` 从 `None` 改为 `manifest_descriptor.payload_ref` 和 `manifest_digest`
- 数据流同源：manifest descriptor → hot JSON inline → EventLog row descriptor → Tool Trace projector → formal resolver
- 所有 consumer（artifact、EventLog、Memory、Tool Trace、RunInput）从同一份 accepted root truth 和 canonical manifest truth 派生
- Identity mismatch 通过 `HostDurableError` fail-closed
- 测试覆盖：single success、invalid→repair→success、四次 exhaustion fallback

### F10: Turn-Group Atomicity, Bounded Selection, Feedback Boundary Binding

**审查结论**: ✓ 原子性、边界绑定和 accepted durable truth 均正确。

**Turn-group atomicity**:
- `_AtomicMaterialUnit` 按 `turn_group_id` 分组，完整 group 或 singleton
- `_collective_exclusion_reason` 在 unit 级别应用固定优先级排除
- 两阶段选择：phase 1 合并原子 unit + 集体排除；phase 2 仅对 eligible unit 应用 prefix budget
- 超 cap unit 不跨 cap、不拆分、不跳过（设计明确要求）

**Bounded selection**:
- Root selection 携带完整、稳定排序的 `TurnGroupMembership` 和 `SelectedBlockProvenance`
- Reactive transient pass 绑定 root selection digest，形成精确 non-overlapping partition
- Pipeline `_validate_segment_against_source_snapshot` 验证 block partition、group proof 和 transient root binding

**Feedback boundary binding**:
- `CompactRepairFeedbackV2` 携带 `request_digest` 和 `source_boundary_digest`
- Dispatch `_repair_feedback_for_request` 仅在双 digest 精确匹配时传递 feedback
- Request 或 source boundary 变化清除旧 feedback

**Accepted durable truth**:
- Operation `_validate_operation_root_request` 在 durable acceptance 前验证 turn-group 完整性
- Multi-pass aggregate 后做 root revalidation
- Terminal permit：零 terminal 允许当前 writer；精确一个匹配 terminal 将 late result 变为 diagnostic-only no-op；多个 terminal/wrong trigger/wrong operation fail closed

### F08 Prompt/Hash/Manifest Consumers 与 F09/F10 Runner Trace 一致性

**审查结论**: ✓ 互相一致。

- F08 prompt SHA-256 (`5f5a5151...`) 正确写入 manifest entry，manifest SHA-256 (`9ebdeab5...`) 正确写入 smoke test frozen constant
- F09 EventLog row descriptor 使用与 manifest descriptor 相同的 `payload_ref`/`payload_digest`
- F10 的 `CompactSegmentSelection` digest 包含 scope、memberships、provenance，与 F09 的 manifest identity 独立但不冲突
- 所有 LLM-facing 文本不含内部治理标识（event_id、payload_ref、digest、cursor）

## Architecture Boundary Review

### Semantic Ownership

| 语义 | 正确 Owner | 实际实现 | 状态 |
|------|-----------|---------|------|
| Session summary null 选择规则 | conversation compaction prompt | prompt 三子弹点 | ✓ |
| Field shape/cap/accept-reject | Host Context Governance | `accept_compact_candidate_v2` | ✓ |
| Runner-call canonical manifest identity | Host runner-call manifest recorder | `DurableCompactorProposalManifestRecorder` | ✓ |
| Tool Trace hot projection | Host Tool Trace projector | 同一 descriptor 派生 | ✓ |
| Material block/turn-group identity | Host compact material builder | `_AtomicMaterialUnit` + `TurnGroupMembership` | ✓ |
| Segment/cap selection | Host compact segment selector | `select_compact_segment` 两阶段 | ✓ |
| Repair feedback binding | Host proactive compaction scheduler | `_repair_feedback_for_request` 双 digest | ✓ |
| Accepted input completeness | Host Context Governance operation | `_validate_operation_root_request` | ✓ |

### LLM-facing 文本约束

- ✓ Prompt 使用纯业务语言，不含代码类型名、内部模块名、Host 实现术语
- ✓ Prompt-local labels 是不透明引用标签，不携带位置、时间、重要性、优先级语义
- ✓ 结构化输出在 prompt 中自足说明字段名、含义、类型、必填性、允许值和最小示例
- ✓ 系统状态、调度状态、Host/Engine 内部治理信息未伪装为财报事实或业务事实
- ✓ Tool schema、memory/compact/evidence material 提供业务可读语义

### 反向依赖与 God Object 检查

- ✓ 无反向依赖：`compaction.py` → `context_governance.py` → `compact_material.py` → `compact_pipeline.py` → `compaction_operation.py` → `dispatch.py` 严格分层
- ✓ 无 God object：每个类职责收敛，无承担过多分支的函数或类
- ✓ 无兼容性代码：无兼容性 re-export、wrapper 或 facade

## Test Coverage Analysis

### 覆盖率

| 文件 | 覆盖率 | 状态 |
|------|--------|------|
| `compact_material.py` | 92% | ✓ ≥80% |
| `compact_pipeline.py` | 88% | ✓ ≥80% |
| `compaction.py` | 85% | ✓ ≥80% |
| `compaction_operation.py` | 86% | ✓ ≥80% |
| `context_governance.py` | 91% | ✓ ≥80% |
| `dispatch.py` | 83% | ✓ ≥80% |
| **组合** | **85%** | ✓ ≥80% |

### 测试覆盖的关键行为

- ✓ Turn-group 原子选择（完整 group 进入或全部排除）
- ✓ Budget cap 在 unit 级别应用（超 cap unit 不拆分）
- ✓ Reactive transient pass 绑定 root selection digest
- ✓ Repair feedback 双 digest 匹配验证
- ✓ Operation root boundary turn-group 完整性验证
- ✓ EventLog row descriptor 与 manifest descriptor 同源
- ✓ Formal resolver identity mismatch fail-closed
- ✓ Session summary null replacement 清除旧 summary
- ✓ Frozen baseline digests 稳定性

### 已知测试限制（非 findings）

- 所有测试使用 `tmp_path` 隔离 SQLite 数据库，无并发访问测试
- 真实 compactor smoke 测试受环境变量门控，仅覆盖 2 个 provider
- 真实 provider 网络故障、SQLite 锁竞争、compactor prompt 截断边界未覆盖
- 五条正式 CLI scenarios 未运行（per explicit prohibition）

## Residual Risk

### 已分类为后续证据/就绪门控

1. **F08 真实 provider 行为**: session_summary:null 在实际 cap 压力下的 compliance 需要 real-provider Agent-in-the-loop 观察（assigned to `interactive.g06.summary-null` scenario）
2. **F09 真实 provider/model/response identity**: 跨进程 CLI 证据 deferred to `interactive.g06.tool-trace-formal` readiness stage
3. **F10 真实 provider 和 CLI scenarios**: deferred to Oracle evidence/readiness gate

### 已分类为未来迭代改进（非当前 correctness residuals）

1. **Operation sorted multiset defense-in-depth**: 如果未来 request constructor 绕过 pipeline，multiset 比较无法防御完整 A<->B swap。当前无绕过路径。建议未来迭代添加 per-block_id 比较。
2. **Transient snapshot validator 不验证 root subset**: 如果未来 transient constructor 绕过 `_single_block_segment_selection`，pipeline 层不拦截 phantom blocks。当前无绕过路径；operation 层捕获。建议未来迭代添加 root subset 验证。

## Conclusion

**PASS**

F08-F10 aggregate deepreview 结论为 PASS。所有三个 slice 的实现正确、测试充分、架构边界清晰、frozen baseline 稳定、跨 slice 数据一致性验证通过。无实质性问题，无阻塞性 open questions，无未分类 residual risks。

### 关键验证点

1. **F08**: Prompt 自足定义 null 语义，Host 不做自然语言 heuristic，Memory projector 通过完整生产链验证
2. **F09**: EventLog row descriptor 与 manifest descriptor 同源写入，formal resolver identity mismatch fail-closed
3. **F10**: Turn-group 原子选择、bounded selection、feedback 双 digest 绑定、operation root boundary 完整性验证均正确实现
4. **跨 slice 一致性**: F08 prompt/manifest consumers 与 F09/F10 runner trace 互不冲突，所有 consumer 从同一份 accepted truth 派生
5. **架构边界**: 无反向依赖、无 God object、无兼容性代码、无 LLM-facing 内部治理泄漏
6. **测试覆盖**: 418 passed, 1 skipped; 6 production files 组合覆盖率 85%; pyright 0 errors
7. **Frozen baseline**: 3 份 baseline SHA-256 与 accepted-plan checkpoint 完全一致
