# Plan Review — Host Phase 0 / P0 Engine Context Compaction Event 语义前置

- review gate: plan review
- reviewer: AgentDS
- review target: `docs/host/phase0-engine-context-compaction-plan.md`
- 日期: 2026-05-13
- 结论: **pass**（无 blocker；6 findings，1 中 / 5 低）

## 0. Review Scope

本次 review 按 controller 指定的 adversarial plan review 范围执行：

- 动机与严重性
- `budget_state` 契约表达（optional vs unknown marker）
- 是否误用 implementation-control 作为架构真源
- scope 是否夹带 Host implementation / proactive governance / Engine compact/retry/tokenizer
- affected files 完整性与宽度
- slices 粒度与 file ownership
- tests 覆盖（contract、event ordering、provider_request_id、run_failed recoverable、0/0/0 sentinel 清理、pyright）
- docs update 是否符合 README 职责边界
- residual risk destination 完整性

## 1. Evidence Sources Reviewed

| 真源 | 用途 | 审查范围 |
| --- | --- | --- |
| `docs/host/design.md` §25, §25.1 | Host Context Governance 架构真源 | 验证 plan 不重新定义 Host 架构 |
| `docs/host/implementation-control.md` | 实施编排真源 | 验证 plan 不把编排文件当架构真源 |
| `docs/engine/design.md` §15 | Engine 设计事实真源 | 验证 0/0/0 占位确实存在 |
| `dayu/engine/README.md` | Engine 开发手册 | 验证术语与边界说明 |
| `dayu/README.md` | 项目级术语真源 | 验证 Context Governance 术语 |
| `dayu/engine/contracts/engine_events.py:256-269` | `ContextCompactionRequestedData` 定义 | 验证 `budget_state: ContextBudgetSnapshot` 非 optional |
| `dayu/engine/contracts/agent_run.py:34-49` | `ContextBudgetSnapshot` 定义与 docstring | 验证 `0/0/0` 占位语义存在 |
| `dayu/engine/agent.py:1240-1264` | context overflow 分支 | 验证 `ContextBudgetSnapshot(0,0,0)` 构造点 |
| `dayu/engine/contracts/__init__.py` | 契约子包导出 | 验证 re-export 路径完整 |
| `dayu/engine/__init__.py` | 包根导出 | 验证 re-export 路径完整 |
| `tests/engine/test_engine_event_contract.py` | 合约测试 | 验证字段集合锁定与 sentinel 断言缺失 |
| `tests/engine/test_agent_phase2.py:543-587` | 集成测试 | 验证 `budget_state is None` 断言缺失 |
| `tests/engine/runners/openai/test_http_error_event.py` | Runner HTTP error 测试 | 验证 Runner 级 context overflow 回归测试缺失 |
| `tests/engine/test_package_exports.py` | 导出白名单测试 | 验证导出集不影响 |

## 2. Findings

### 01-证据失效-[低]-plan-s0-真源层级声明与 implementation-control 职责一致

Plan §0 的 Source-Of-Truth Hierarchy 声明：

> `docs/host/implementation-control.md` 是实施编排与追踪真源，只用于确认 P0 的 gate、范围、依赖、追踪项和 residual risk destination；它不替代 Host 架构真源。

**验证结果**：与 `docs/host/implementation-control.md` 自身声明完全一致：

> 本文档不得引入新的架构边界、状态机、公共接口或事件语义。若实施编排过程中发现需要新的架构决策，应先和用户讨论并同步到 `docs/host/design.md`。

Plan 对真源层级的理解正确，未误用 implementation-control 作为架构真源。**无问题。**

controller decision status: `no-action-required`

---

### 02-已修复-[中]-plan-phase5-vs-phase10-budget-state-none-ownership

Plan §11 将 `budget_state=None` 的 Host reactive ingest 处理归属为：

> deferred to Phase 5 dispatch / reactive failure closeout 或 Phase 10，按 controller 当前 phase map 裁决。

**证据**：

- `docs/host/implementation-control.md` Phase 5 范围包括 "EngineEvent ingest mapping and terminal closeout"，Phase 10 范围包括 "reactive Engine overflow recovery path"。
- `docs/host/design.md` §25.1 reactive path 约束："Host 必须先按 attempt_id + execution_id 校验 context_compaction_requested"，以及 "CONTEXT_COMPACTION_REQUESTED payload 至少记录 trigger source、provider / runner error refs、provider request id、budget snapshot refs"。
- 当前 Host design 已要求 Host canonical compact event 携带 `budget snapshot refs`（§25.1 第 2032 行），但未区分 refs 来自 Engine event 还是 Host estimator。

**分析**：`budget_state=None` 的首次校验（字段存在、非空预期）属于 Phase 5 EngineEvent ingest 的结构验证层；`None` 的语义解释（"Engine 无预算参考，Host 必须用自身 estimator"）属于 Phase 10 Context Governance 的策略层。Plan 当前将两者合并 defer 到 "Phase 5 或 Phase 10"，未显式区分 ingest validation vs semantic interpretation 的责任切分点。

**建议**：Plan 无需修改；但 controller 在 P0 closeout 时应在 `docs/host/implementation-control.md` 追踪区显式记录：Phase 5 负责 `budget_state=None` 的结构校验（字段不为 None 时允许通过但不假设语义），Phase 10 负责 `None` 的策略语义（使用 Host estimator 替代）。

controller decision status: `pending-controller-decision`

---

### 03-已修复-[低]-plan-s1-sentinel-grep-multiline-gap

Plan §6 P0-S1 completion signal 使用正则：

```bash
rg -n "ContextBudgetSnapshot\\(\\s*prompt_tokens=0|0/0/0|占位快照" dayu tests
```

**证据**：`ContextBudgetSnapshot` 构造在 `dayu/engine/agent.py:1249-1253` 当前是多行 keyword-argument 形式：

```python
ContextBudgetSnapshot(
    prompt_tokens=0,
    completion_tokens=0,
    total_tokens=0,
)
```

**分析**：正则 `ContextBudgetSnapshot\\(\\s*prompt_tokens=0` 能匹配 `ContextBudgetSnapshot(prompt_tokens=0,...` 单行形式，但若未来代码用多行 keyword args 写入 `prompt_tokens=0`（每行一个参数），该正则会漏检。不过 `0/0/0` 作为辅助 pattern 加上 `占位快照` 中文语义 pattern 提供了多层防御。且主要防线是代码变更（`agent.py` 删除构造点）和测试断言（`budget_state is None`），grep 只是 defense-in-depth。

**建议**：无需修改 plan；implementation agent 可在 P0-S1 closeout 时补充更保守的多行搜索或在 completion report 中注明搜索局限性。

controller decision status: `no-action-required`

---

### 04-已修复-[低]-plan-s1-contract-test-both-none-and-real-snapshot

Plan §6 P0-S1 expected assertions：

> `budget_state=None` 是合法 unknown。

**证据**：

- `tests/engine/test_engine_event_contract.py:172-179` 当前 `test_provider_request_id_fields_are_locked` 只锁定 `ContextCompactionRequestedData` 字段名集合 `{"iteration_id", "budget_state", "reason", "provider_request_id"}`，不验证字段类型或值。
- `ContextBudgetSnapshot` 是 `frozen=True, slots=True` dataclass，三个 `int` 字段均无默认值、无校验器。`ContextBudgetSnapshot(0, 0, 0)` 在类型系统层面始终合法。

**分析**：Plan 要求新增 `budget_state=None` 合法性断言，但未同时要求保留 "非零真实快照仍可构造" 的覆盖。如果 implementation agent 在新增 `None` 测试时移除了所有 `ContextBudgetSnapshot` 构造断言（当前测试中本就没有），不会造成回归；但如果 agent 额外误加 "禁止 ContextBudgetSnapshot(0,0,0)" 的断言（如 `pytest.raises`），则会与类型系统允许的 int 三元组冲突。

**建议**：P0-S1 exact allowed changes 已明确 "不得用 ContextBudgetSnapshot(0, 0, 0)、负数或其它 sentinel 表达 unknown"，此为 docstring 约定而非类型级禁止。Implementation agent 在合约测试中应同时覆盖两个 case：`budget_state=None` 合法，`budget_state=ContextBudgetSnapshot(1000, 500, 1500)` 合法。当前 plan 未显式要求后者，但类型系统不变所以无回归风险。

controller decision status: `no-action-required`（由 implementation agent 自行保证测试覆盖不退化）

---

### 05-已修复-[低]-plan-runner-events-docstring-check

Plan §3.2 对 `dayu/engine/contracts/runner_events.py` 的处理：

> 默认不改；现有 `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED` 说明已表达由 Host 决定是否 compact。只有文档同步时发现措辞仍暗示 Engine budget governance，才允许改 docstring。

**证据**：

- `dayu/engine/contracts/runner_events.py:51`：`CONTEXT_LENGTH_EXCEEDED` 的 docstring 当前写 "provider 明确报告上下文长度超限"。
- 该描述是 provider 信号分类，不含 Engine budget governance 语义。与 `docs/engine/design.md` §15（当前含 0/0/0 占位语义）不同，runner_events.py 的 docstring 不涉及 budget snapshot。
- `dayu/engine/runners/openai/error_classifier.py` 的 `detect_context_overflow` 也不涉及 budget。

**分析**：Plan 将 runner_events.py 标记为 conditional candidate 是保守且正确的。P0-S2 documents sync 阶段应顺便目检该 docstring，确保不残留 "Engine 计算 budget" 或 "Engine compact" 等旧语义。Plan 已覆盖此检查路径（P0-S2 expected assertions 含 "Engine 不负责 proactive budget governance"），但未在 P0-S2 exact allowed changes 中显式列出 runner_events.py 作为可选项。

**建议**：P0-S2 implementation agent 应目检 `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED` 的 docstring；如无需修改，在 completion report 中记录 "checked, no change needed"。

controller decision status: `no-action-required`

---

### 06-已修复-[低]-plan-dayu-readme-deduplication

Plan §8 要求更新 `dayu/README.md`：

> Context Governance 术语处补充：Engine reactive event 不携带真实 Host budget；Host 使用自身 estimator / policy。

**证据**：

- `dayu/README.md:118` 当前已写：
  > Engine emit `context_compaction_requested` 是 provider context overflow 后的 reactive fallback。
  > Context Governance 不直接写 memory、audit、trace 或 outbox projection。

**分析**：现有术语表条目已将 `context_compaction_requested` 定性为 reactive fallback，与 plan 要求补充的语义高度重叠。如果 P0-S2 不加区分地追加新句子，可能在术语表中产生冗余或轻微矛盾（如"Engine reactive event 不携带真实 Host budget"与已有 "reactive fallback" 语义重复）。Plan 应指导 implementation agent 以**替换/精化**现有条目为目标，而非**追加**新条目。

**建议**：P0-S2 exact allowed changes 应将 `dayu/README.md` 的操作从 "补充" 改为 "精化已有 Context Governance 术语条目，明确 Engine overflow event 的 budget_state 在 provider overflow 路径为 None，Host 使用自身 estimator/policy"。

controller decision status: `pending-controller-decision`（可接受当前措辞，由 implementation agent 自行判断）

---

## 3. Cross-Cutting Verification

### 3.1 动机验证

结论：**真实成立。**

- `dayu/engine/agent.py:1249-1253` 直接构造 `ContextBudgetSnapshot(0,0,0)`，且 `docs/engine/design.md` §15 明确记载此为占位语义。问题存在于代码、合约 docstring 和设计文档三层。
- 严重性边界正确：只阻塞 Phase 10，不影响 Phase 1-9。

### 3.2 Contract 表达验证

结论：**`budget_state: ContextBudgetSnapshot | None` 是最小、可维护、可测试的表达。**

对比分析：

| 方案 | 新增类型 | 下游分支 | 与现有风格一致性 | unknown 语义清晰度 |
| --- | --- | --- | --- | --- |
| `ContextBudgetSnapshot \| None`（plan 选择） | 0 | 0 | 与 `provider_request_id: str \| None` 一致 | 需 docstring 说明 |
| 新增 `UnknownBudget` enum | 1 enum | +1 pattern match 分支 | 无先例 | 最清晰 |
| 新增 `UnknownBudgetSnapshot` dataclass | 1 dataclass | +1 isinstance 分支 | 无先例 | 中等（看起来像另一种 snapshot） |
| 保留 `ContextBudgetSnapshot(-1,-1,-1)` sentinel | 0 | 依赖约定 | 无先例（现有 sentinel 正是要清理的） | 最差（sentinel 伪装成数据） |

Plan 选择 `| None` 的理由（不引入新公共类型、不增加下游分支、不让 unknown 像 snapshot）均成立。

### 3.3 Scope 验证

结论：**scope 干净，未夹带 Host implementation 或 proactive governance。**

逐一验证：
- `dayu/engine/contracts/engine_events.py` → Engine contract，在允许范围 ✓
- `dayu/engine/contracts/agent_run.py` → Engine contract，在允许范围 ✓
- `dayu/engine/agent.py` → Engine 实现，仅改 overflow 分支构造，不新增 governance ✓
- tests → Engine 测试，在允许范围 ✓
- docs → 同步语义，不把 Phase 10 写成已完成 ✓
- Host implementation code → 不在 affected files，non-goal 明确排除 ✓
- Engine compact/retry/tokenizer/policy → non-goal 明确排除 ✓

### 3.4 Slices 验证

结论：**两个 slice 粒度合理，file ownership 清晰。**

- P0-S1（engine-contract-unknown-budget）：5 个必然文件 + 3 个条件文件，单一语义闭环（contract → 实现 → 测试），可直接实施、独立验证。
- P0-S2（docs-contract-sync）：4 个必然文件 + 2 个条件文件，仅文档同步，依赖 P0-S1 完成。

两个 slice 不会诱导 implementation agent 提前做 future-slice 工作。

### 3.5 Tests 覆盖验证

| 覆盖目标 | 状态 | 证据 |
| --- | --- | --- |
| contract：`budget_state=None` 合法 | ✓ plan 要求新增 | P0-S1 exact allowed changes |
| contract：字段集合不退化 | ✓ 已有 `test_provider_request_id_fields_are_locked` | `test_engine_event_contract.py:172-179` |
| event ordering：`iteration_started → context_compaction_requested → iteration_completed → run_failed` | ✓ 已有断言 | `test_agent_phase2.py:571-576` |
| provider_request_id 透传 | ✓ 已有断言，plan 要求保留 | `test_agent_phase2.py:579,581,585` |
| run_failed recoverable=True | ✓ 已有断言，plan 要求保留 | `test_agent_phase2.py:586` |
| `budget_state is None` | ✓ plan 要求新增 | P0-S1 exact allowed changes |
| 旧 0/0/0 sentinel 清理 | ✓ sentinel 搜索 | P0-S1 completion signal |
| pyright | ✓ plan 要求 | §7 validation commands |
| Runner 级 context overflow HTTP 400 回归 | ✓ plan 条件要求 | §3.2 条件候选 |

### 3.6 Docs Update 验证

| 文档 | plan 决策 | 验证 |
| --- | --- | --- |
| `docs/engine/design.md` | 必须更新 | ✓ 命中 Engine design contract 变更 |
| `dayu/engine/README.md` | 必须更新 | ✓ 命中 `dayu/engine/` 修改触发规则 |
| `dayu/README.md` | 必须更新 | ✓ 命中分层关系/Context Governance 边界说明 |
| `docs/host/implementation-control.md` | 必须更新 | ✓ P0 tracking destination |
| `docs/host/design.md` | 默认不改 | ✓ 已有 §25/§25.1 边界正确 |
| 根 `README.md` | 不改 | ✓ 不改变用户入口 |
| `tests/README.md` | 条件 | ✓ 仅测试分层变化时更新 |
| `dayu/config/README.md` | 不改 | ✓ P0 不涉及 |
| `dayu/host/README.md` | 不改 | ✓ P0 不修改 Host 包 |
| `dayu/fins/README.md` | 不改 | ✓ P0 不涉及 |

所有 docs 决策符合 CLAUDE.md README 触发规则与职责边界。无未来 Host Phase 10 被写成已完成的语句。

### 3.7 Residual Risk Destination 验证

| 风险 | destination | 明确性 |
| --- | --- | --- |
| Engine overflow budget unknown 已修复 | `docs/host/implementation-control.md` 追踪区 | ✓ |
| Host estimator/policy/compact artifact | Phase 10 | ✓ |
| Host reactive ingest mapping `budget_state=None` | Phase 5 或 Phase 10 | ⚠ 见 Finding 02 |
| Provider-specific tokenizer adapter | Host later capability | ✓ |
| `reason: str` 保持字符串 | P0 plan review → Host Phase 5/10 | ✓ |
| `ContextBudgetSnapshot` 仍导出但当前不生产真实快照 | P0-S2 docs sync | ✓ |

除 Finding 02 所指的 Phase 5 vs Phase 10 归属歧义外，所有 residual risk 均有明确 destination。

## 4. Reviewer Conclusion

**结论：pass（无 blocker）**

Plan 整体质量高：
- 证据链完整（从 agent.py 源码到 design.md 到 implementation-control.md 三层交叉验证）。
- 真源层级理解正确（未把 implementation-control 当架构真源，未重新定义 Host 架构）。
- Scope 边界干净（明确 non-goals，未夹带 Host implementation、proactive governance、Engine compact/retry/tokenizer）。
- Slices 粒度合理（P0-S1 可独立实施验证，P0-S2 仅文档同步）。
- 合约表达选择 `budget_state: ContextBudgetSnapshot | None` 是最保守、最可维护的方案，与现有 `provider_request_id: str | None` 风格一致。
- 6 findings 中 5 个低严重度、1 个中严重度（Phase 5 vs Phase 10 ownership ambiguity），均为可接受的非阻塞项。

## 5. Open Questions

无 blocking open question。

中严重度 Finding 02 建议 controller 在 P0 closeout 时明确 Phase 5（ingest validation）与 Phase 10（semantic interpretation）对 `budget_state=None` 的责任切分。

## 6. Residual Risk

- 合约测试覆盖 `budget_state=None` 后，`ContextBudgetSnapshot(0,0,0)` 作为合法 int 三元组仍在类型系统允许——这是设计意图，不是 bug（见 Finding 04）。
- `reason: str` 保持字符串不收敛为 enum——plan 已登记为非阻塞风险，deferred to Host Phase 5/10。
- 未来 Runner 如果在 overflow 前已报告 usage data，当前 `budget_state=None` 语义不适用——但 `ContextBudgetSnapshot | None` 类型已为此预留空间；届时该 Runner 直接传入真实 `ContextBudgetSnapshot` 即可。

## 7. Artifact Path

`docs/reviews/gateflow-plan-review-host-p0-engine-context-compaction-ds-20260513.md`
