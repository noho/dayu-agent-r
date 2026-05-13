# Code Review — Host P0-S2 Docs Context Compaction

- Work gate: code review
- Work unit: Host Phase 0 / P0 - Engine Context Compaction Event 语义前置
- Assigned slice: `P0-S2 docs-contract-sync`
- Approved plan path: `docs/host/phase0-engine-context-compaction-plan.md`
- Accepted plan commit: `866f6f5`
- Accepted P0-S1 commit: `ad6d116`
- Implementation artifact: `docs/reviews/gateflow-implementation-host-p0-s2-docs-context-compaction-20260513.md`
- Reviewer: AgentMiMo
- Review date: 2026-05-13

## Review Scope

Review target files:

- `docs/engine/design.md`
- `dayu/engine/README.md`
- `dayu/README.md`
- `docs/host/implementation-control.md`
- `docs/reviews/gateflow-implementation-host-p0-s2-docs-context-compaction-20260513.md`

Files verified as correctly unchanged:

- `dayu/engine/contracts/runner_events.py`：`RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED` docstring 仅表达 provider overflow 分类与 Host 决定是否 compact；无旧 `0/0/0`、Engine budget governance 或 Engine compact / retry 暗示。✓
- `tests/README.md`：现有测试分层说明已覆盖 Engine contract、Runner HTTP error、context overflow classifier；本 slice 是同类文档同步，无需修改。✓
- `docs/host/design.md`：§25 / §25.1 已明确 proactive 属 Host、reactive 来自 Engine；与 P0-S1 最终契约无直接冲突。✓
- 根 `README.md`：无变更，符合计划要求（不改变用户手册入口）。✓

## Review Checklist

### 1. Contract Alignment: `budget_state` is `ContextBudgetSnapshot | None`

| 检查项 | 结果 |
| --- | --- |
| `ContextCompactionRequestedData.budget_state: ContextBudgetSnapshot \| None` | ✓ 代码确认 (`engine_events.py:268`) |
| provider overflow path 使用 `budget_state=None` | ✓ 代码确认 (`agent.py:1248`) |
| `ContextBudgetSnapshot` docstring 删除 `0/0/0` 占位说明 | ✓ 代码确认 (`agent_run.py:34-49`) |
| `docs/engine/design.md` §15 明确 `budget_state=None` | ✓ (`budget_state` 设为 `None`，表示 provider overflow 边界没有可靠预算快照) |
| `dayu/engine/README.md` 关键机制明确 `budget_state=None` | ✓ (provider overflow 路径中的 `budget_state` 为 `None`) |
| `docs/host/implementation-control.md` 追踪区记录 `budget_state=None` | ✓ (P0-S1 已将 `ContextCompactionRequestedData.budget_state` 改为 `ContextBudgetSnapshot \| None`) |

### 2. Engine Boundary: No Proactive Threshold Compaction

| 检查项 | 结果 |
| --- | --- |
| `docs/engine/design.md` §1 "Engine 当前不负责" 包含 proactive threshold compaction | ✓ (新增条目: "Host 上下文预算治理、proactive threshold compaction、context compact / retry、provider-aware tokenizer 或 budget policy") |
| `docs/engine/design.md` §15 边界补强 | ✓ ("不计算 Host budget，也不做 proactive threshold compaction、provider-aware tokenizer 或 Host budget policy") |
| `dayu/engine/README.md` 关键机制边界补强 | ✓ ("Engine 不做 proactive threshold compaction、compact / retry、provider-aware tokenizer 或 Host budget policy") |

### 3. Provider Overflow Path: `None` Not `0/0/0`

| 检查项 | 结果 |
| --- | --- |
| `docs/engine/design.md` §15 无旧 `ContextBudgetSnapshot(0,0,0)` 占位说明 | ✓ 已替换为 `None` |
| `dayu/engine/README.md` 无旧 `0/0/0` 语义 | ✓ |
| `dayu/README.md` 无旧 `0/0/0` 语义 | ✓ |
| `docs/host/implementation-control.md` 追踪区无旧 `0/0/0` 语义 | ✓ |

### 4. Host Budget Policy / Provider-Aware Tokenizer Boundary

| 检查项 | 结果 |
| --- | --- |
| Engine docs 不消费 Host budget | ✓ (`docs/engine/design.md` §15: "是否压缩、如何压缩、如何重新构造消息、如何记录 before / after budget，以及是否再次发起 run，属于调用方在 Engine 之外的职责") |
| Engine docs 不提供 provider-aware tokenizer | ✓ (§1 和 §15 均明确) |
| Engine docs 不提供 Host budget policy | ✓ (§1 和 §15 均明确) |

### 5. `dayu/README.md` Context Governance Terminology Refinement

| 检查项 | 结果 |
| --- | --- |
| 仅精化已有条目，未新增重复段落 | ✓ (只修改了 Context Governance 条目的一句话) |
| 未把 Phase 10 写成已完成 | ✓ (只描述当前边界，不描述未来实现) |
| 内容准确："provider overflow 路径不携带真实 Host budget，Host Context Governance 使用自身 estimator / policy 记录预算并做 compact 决策" | ✓ |

### 6. `docs/host/implementation-control.md` Tracking

| 检查项 | 结果 |
| --- | --- |
| Phase 0 退出条件更新为 `budget_state=None` | ✓ |
| Phase 10 前置条件更新为"必须使用 Host estimator / policy" | ✓ |
| DS finding 02: Phase 5 owns EngineEvent ingest validation accepting `budget_state=None` | ✓ ("Phase 5 owns EngineEvent ingest validation：必须接受 `budget_state=None` 的 Engine event shape，不把 `None` 当作协议错误，不要求 Engine 提供 Host budget ref") |
| DS finding 02: Phase 10 owns semantic interpretation using Host estimator/policy | ✓ ("Phase 10 owns Context Governance semantic interpretation：当 Engine overflow budget unknown 时，必须使用 Host estimator / policy 生成 before / after budget refs，并决策 compact / recovery") |
| 追踪区背景决议更新 | ✓ (删除旧的 "如果" 假设语态，改为已完成的事实陈述) |
| 当前状态更新 | ✓ (gate 更新为 "P0-S2 code review") |

### 7. README Responsibility Boundaries

| 检查项 | 结果 |
| --- | --- |
| `dayu/README.md` 精化已有 Context Governance 术语，未重复 | ✓ |
| 根 `README.md` 无变更 | ✓ |
| `dayu/engine/README.md` 只写 Engine 边界 | ✓ |
| `docs/engine/design.md` 只写 Engine 当前事实 | ✓ |

### 8. Sentinel / Multiline Check

| 搜索范围 | 结果 |
| --- | --- |
| `dayu/` 生产代码 | 无旧 unknown-budget sentinel ✓ |
| 当前 tests (`tests/engine/test_engine_event_contract.py`) | 仅 `ContextBudgetSnapshot(1000, 500, 1500)` 真实快照，无 `0/0/0` sentinel ✓ |
| `docs/engine/design.md` | 无 `0/0/0`、`占位快照` ✓ |
| `dayu/engine/README.md` | 无 `0/0/0`、`占位快照` ✓ |
| `dayu/README.md` | 无 `0/0/0`、`占位快照` ✓ |
| `docs/host/implementation-control.md` | 无 `0/0/0`、`占位快照` ✓ |
| `tests/README.md` | 无 `0/0/0`、`占位快照` ✓ |

### 9. Plan Compliance

| Plan Item (§6 P0-S2) | 结果 |
| --- | --- |
| `docs/engine/design.md` §15 删除 `0/0/0` 占位说明 | ✓ |
| `docs/engine/design.md` 边界章节补强 | ✓ |
| `dayu/engine/README.md` 事件流 / 关键机制补强 | ✓ |
| `dayu/engine/contracts/runner_events.py` 检查 | ✓ checked, no change needed |
| `dayu/README.md` 精化已有 Context Governance 术语 | ✓ |
| `docs/host/implementation-control.md` 追踪区回写 | ✓ |
| `tests/README.md` 检查 | ✓ checked, no change needed |
| 未修改根 `README.md` | ✓ |
| 未写过程状态或 changelog | ✓ |
| 未把 Host Phase 10 实现写成已完成 | ✓ |

### 10. Validation Evidence

| 验证项 | 结果 |
| --- | --- |
| 受影响测试 (13 passed) | ✓ implementation artifact 报告 |
| pyright (0 errors) | ✓ implementation artifact 报告 |
| sentinel 检查 (已分类) | ✓ 独立验证确认 |

## Findings

无。

## Open Questions

无。

## Residual Risk

以下 residual risks 已在 `docs/host/implementation-control.md` 追踪区正确记录：

1. **Phase 5 EngineEvent ingest validation**：必须接受 `budget_state=None` 的 Engine event shape。已记录，归属 Phase 5。
2. **Phase 10 Context Governance semantic interpretation**：Engine overflow budget unknown 时，必须使用 Host estimator / policy 生成 before / after budget refs 并决策 compact / recovery。已记录，归属 Phase 10。
3. **Provider-specific tokenizer adapter**：不在 P0 范围，归属后续 Host capability work。已记录。
4. **D1 reason string**：`reason: str` 保持自由字符串，deferred to Host Phase 5 / Phase 10 typed ingest mapping。已记录。

## Conclusion

**pass**

Implementation 正确同步了 P0-S1 最终代码契约到所有目标文档。所有 plan items 已覆盖，sentinel 检查通过，旧 `0/0/0` unknown-budget sentinel 已从当前生产文档和 README 中清除，DS finding 02 的 Phase 5 / Phase 10 责任切分已正确记录。

## Artifact Path

`docs/reviews/gateflow-code-review-host-p0-s2-docs-context-compaction-mimo-20260513.md`
