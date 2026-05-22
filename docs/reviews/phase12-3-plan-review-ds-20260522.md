# Phase 12.3 Plan Review — AgentDS

**日期**: 2026-05-22  
**审查对象**: `docs/host/phase12-3-config-usage-governance-plan.md`  
**设计真源**: `docs/host/design.md`  
**总控文档**: `docs/host/implementation-control.md`  
**辅助背景**: `docs/host/config-schema-followup-discussion.md`（仅背景核对，不替代设计真源）  
**审查 Agent**: AgentDS

## Verdict: PASS_WITH_FINDINGS

Plan 整体符合 design.md 和 implementation-control.md 的 P12.3 目标。设计裁决四项（内嵌 agent_policy、删除默认 max_tokens、usage post-call observation、execution profile 显式分档）均正确落地为 slice。Import boundary、public surface 禁止清单、non-goals 均正确。

**发现 1 项 blocking finding（Slice 2 provider_request_id 数据缺口）必须修复后 re-review。无其他 blocking findings。**

---

## Blocking Findings

### B1. Slice 2 `provider_request_id` 数据缺口 — Engine `UsageReportedData` 缺少字段

**严重性**: BLOCKING — 不修复会导致 Host 无法在 USAGE_REPORTED projection signal 中写入 `provider_request_id`。

**证据**:

Plan 第 247 行：
> 不修改 Engine `RunnerUsageRecordedData` / `UsageReportedData` 字段，不修改 Engine Agent loop。

Plan 第 257 行要求 Host projection signal payload 新增：
> `provider_request_id`

Plan 第 284 行测试断言：
> provider_request_id 从 `UsageReportedData.provider_request_id` 进入 payload

但当前 `UsageReportedData`（`dayu/engine/contracts/engine_events.py:274-286`）仅含四个字段：
```python
@dataclass(frozen=True, slots=True)
class UsageReportedData:
    iteration_id: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
```

上游 `RunnerUsageRecordedData`（`dayu/engine/contracts/runner_events.py:134-144`）同样不含 `provider_request_id`：
```python
@dataclass(frozen=True, slots=True)
class RunnerUsageRecordedData:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
```

Engine agent.py:1290-1297 从 `RunnerUsageRecordedData` 构造 `UsageReportedData` 时未传递 `provider_request_id`。Host `_append_projection_signal`（`dayu/host/engine_ingest.py:2020-2057`）接收的 `data: UsageReportedData` 参数不携带该字段。Host 的 `_ValidatedCandidate` 上下文（`engine_ingest.py:272-278`）也不包含 `provider_request_id`。

而 Engine agent 内 `state.provider_request_id`（`agent.py:1385`）在 RunnerDoneData 到达时已被赋值，在 USAGE_REPORTED 事件发出时可用，但未被转发。

**影响**：不解决此缺口，Slice 2 的 `provider_request_id` 验证断言（第 278、284 行）无法通过，usage observation consumer 的实现将不完整。

**建议修复**：

思路 A（推荐）：将 plan 第 247 行的约束从"不修改字段"改为"可新增字段，不删除/重命名已有字段"。同时修改两处：
- `RunnerUsageRecordedData` 新增 `provider_request_id: str | None = None`
- `UsageReportedData` 新增 `provider_request_id: str | None = None`
- Engine agent.py 在构造 `UsageReportedData` 时传入 `state.provider_request_id`
- Runner non_stream_parser.py / sse_parser.py 在构造 `RunnerUsageRecordedData` 时传入已有的 `provider_request_id`

这些改动均向后兼容（frozen=True dataclass，新增 keyword-only 带 default 字段），不破坏现有 Engine 测试，不改变 Engine Agent loop 状态机，不改变 Host durable state machine。

思路 B：在 plan 中说明 Host 如何从非 Engine 路径获取 `provider_request_id`（如从 EventLog 中前序 IterationCompleted 事件关联），并删除第 284 行对 `UsageReportedData.provider_request_id` 的引用。此路径更复杂，不如思路 A 直接。

**确认标准**：plan 修正后，该字段的数据真源明确（Engine event contract）、Host 侧可直接从 `UsageReportedData` 读取，不需要额外查找。

---

## Non-Blocking Observations

### N1. `min_context_window_tokens` 精度假设

Plan 第 359 行使用 `1000000` 表示 1M class。部分 1M 模型实际 context window 为 1,048,576（如 Gemini 2.5 Pro 为 1,048,576）。使用更保守的 1,000,000 会导致该类模型与 1M profile 的 compatibility check 通过（model ≥ min），不会误判不兼容。此值对 fail-fast 路径无害。非阻塞，但建议在 plan 或 implementation notes 中标注此为保守下限而非精确值。

### N2. `context_window_class` 枚举可扩展性

Plan 第 340 行硬编码允许 `"256k"` / `"1m"`。扩展到 128k 或 2M 需改 `_parse_execution_profile` exact field validator。Plan 在第 339 行已标注"第一版"，属合理范围。非阻塞。

### N3. Usage observation 承载于 projection signal 的充分性

Plan 第 543 行将 usage observation durable association 承载于 `USAGE_REPORTED` EventLog projection signal payload，不新增 durable table，并将该决策标注为 non-blocking assumption。此设计与当前 Host projection signal 模式一致（USAGE_REPORTED 已是 PROJECTION_SIGNAL event class），且 plan 明确要求"若 review 证明后续消费无法可靠读取 projection signal，必须停下"。此 caveat 恰当。非阻塞。

### N4. `tests/engine/test_config_models.py` 归属

Plan Slice 1 将 `tests/engine/test_config_models.py` 列入 Allowed Files。该测试文件名含 "engine" 但实际测试的是 ConfigLoader/config model 行为（非 Engine 内部状态机）。Plan 第 198 行限制该测试只做"删除默认 config hint max_tokens 断言，改为断言默认 config 不携带输出 token cap"，不修改 Engine 公共 contract 测试。属合理的 file ownership 判断。非阻塞。

### N5. `_agent_policy_defaults_from_profile` → `_agent_policy_defaults_from_config` 重命名

Plan 第 171 行建议重命名。此方法与旧 catalog 查找 `agent_policy_profiles[...]` 耦合——删除 catalog 后输入从"按 id 查找的结果"变为"内嵌 agent_policy config"，语义变化匹配重命名。此非兼容 wrapper，无违反 non-goals。非阻塞。

### N6. Slice 3 `wechat-*` profile 初始内容

Plan 第 359 行允许 `wechat-*` 与 `standard-*` 共享 baseline（若未确认业务差异）。此设计避免在没有真实业务需求时虚构差异。但需要注意：共享 baseline 意味着 `wechat-256k` 和 `standard-256k` 的 `agent_policy` 完全一致——若未来 Service 需要区分微信场景的 agent policy（如更保守的 max_iterations），需独立修改。Plan 已要求"保留独立 profile id，避免 Service 未来依赖隐式切换"，此约束正确。非阻塞。

### N7. 全量测试回归覆盖

Plan 的 Slice 4 聚合验证包含 focused tests + pyright + import boundary tests（第 450-463 行），但未显式要求运行全量 `pytest` 以确保无 regression。当前 focused test 范围覆盖了 Slice 1-3 的所有修改模块，且 import boundary tests 覆盖了所有关键层。若担心遗漏，建议 Slice 4 追加一条 `pytest tests/ -q --timeout=300` 全量回归检查。非阻塞。

---

## Review Checklist 逐项结论

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | plan 是否以 discussion 文档替代设计真源 | PASS | plan 第 7-8 行明确 design.md 为真源，discussion 仅用于背景核对 |
| 2 | 是否保留旧 schema 兼容读取 / alias / tests | PASS | plan §3.2 non-goals 第 66 行明确不保留；Slice 4 有旧字段扫描 |
| 3 | 是否误删 `RunnerCallOptions.max_tokens` public explicit override | PASS | plan §6 第 123 行明确保留字段名与 explicit override 语义；Slice 1 仅切断默认 config 来源 |
| 4 | ConfigLoader / runtime assembly 是否 import Host / Engine / Service | PASS | plan §5 import boundary 明确禁止；Slice 1-3 均无新增此类 import |
| 5 | usage observation 是否影响当前 dispatch decision | PASS | plan §3.2 non-goals 第 64 行明确不回头修改；Slice 2 实现 decisions 确认 |
| 6 | 是否引入 usage config override 或 `supports_usage` | PASS | plan §3.2 non-goals 第 63 行明确不新增 |
| 7 | Service helper 是否根据 model context window 自动选择 profile | PASS | plan Slice 3 实现 decisions 明确 Service 显式选择，helper 只校验 |
| 8 | Slice 是否过粗 / 夹带 future workflow | PASS | 4 个 slice 各自 scope 清晰，允许文件列表精准，non-goals 排除未来 Service/UI workflow |
| 9 | `provider_request_id` 数据真源 | **BLOCKED (B1)** | `UsageReportedData` 缺少该字段，详见 B1 |
| 10 | File ownership 合理性 | PASS | 每 slice 均有明确 allowed files 列表，跨层文件归属合理 |
| 11 | 测试覆盖充分性 | PASS (见 N7) | 每个 slice 有明确测试 spec、validation commands、acceptance criteria |
| 12 | README sync 触发规则正确 | PASS | 每 slice 明确 README 更新触发条件与职责边界 |
| 13 | 合并后与设计真源一致性 | PASS | 所有设计裁决均正确映射为 plan decisions |

---

## 结论

Plan 质量高，目标对齐精确，slice 划分合理，import boundary 与 public surface 禁止清单均正确。**仅 B1（provider_request_id 数据缺口）为 blocking**，建议采用思路 A（新增字段至 Engine event data class）修复。修复后可升档为 PASS。

---

*AgentDS review complete. Artifact: `docs/reviews/phase12-3-plan-review-ds-20260522.md`*
