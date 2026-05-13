# Host Phase 0 / P0 - Engine Context Compaction Event 语义前置 Plan

当前 gate: plan  
角色: AgentCodex planning worker  
日期: 2026-05-13  
结论: ready for plan review  

## 0. Source-Of-Truth Hierarchy

本计划按以下真源层级执行：

- Host 架构与 Host 语义真源是 `docs/host/design.md`，尤其是 §25 `Context Governance` 与 §25.1 `Compact Event 响应路径`。
- `docs/host/implementation-control.md` 是实施编排与追踪真源，只用于确认 P0 的 gate、范围、依赖、追踪项和 residual risk destination；它不替代 Host 架构真源。
- Engine 设计与当前 Engine contract 真源是 `docs/engine/design.md`、`dayu/engine/README.md` 与 `dayu/engine/contracts/*` 中的当前代码契约。

因此，P0 的 Engine contract cleanup 只能支撑 `docs/host/design.md` 已定义的 Host Context Governance 语义：proactive compaction 属于 Host pre-dispatch input governance，reactive Engine overflow 只是 provider overflow fallback。P0 不得借 Engine cleanup 重新定义 Host 架构、Host canonical compact event schema、Host recovery 状态机或 Host budget policy。

## 1. Goal And Motivation

### 1.1 目标

本 P0 只清理 Engine provider context overflow 事件契约，把 `context_compaction_requested` 明确为 provider overflow 后的 reactive fallback 诊断事实，并去掉 `ContextBudgetSnapshot(0, 0, 0)` 这种会被误读成真实预算的占位表达。

P0 结束后，Host 后续 Phase 10 Context Governance / Compaction 可以依赖以下稳定语义：

- Engine 不做 proactive context governance。
- Engine 不做 compact / retry / budget threshold policy。
- Engine provider overflow 只产出 reactive `context_compaction_requested`，随后以 recoverable `run_failed(context_compaction_required)` 收口。
- provider overflow 路径中的 budget unknown 必须显式表达，不能继续用 `0/0/0` 编码未知。
- Host 必须使用自身 estimator / tokenizer / policy 记录 before / after budget，不能消费 Engine overflow 事件里的占位预算。

### 1.2 问题是否真实存在

问题真实存在，且是公共契约语义问题，不是单纯文档措辞问题。

直接证据：

- `dayu/engine/agent.py` 在 `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED` 分支构造 `ContextCompactionRequestedData`，当前填入 `ContextBudgetSnapshot(prompt_tokens=0, completion_tokens=0, total_tokens=0)`。
- `dayu/engine/contracts/engine_events.py` 定义 `ContextCompactionRequestedData.budget_state: ContextBudgetSnapshot`，类型层面要求调用方看到一个预算快照。
- `dayu/engine/contracts/agent_run.py` 的 `ContextBudgetSnapshot` docstring 明确写着 provider HTTP context overflow 无 usage 时 Engine 填入 `0/0/0` 作为占位快照。
- `docs/engine/design.md` §15 写明 context overflow 时使用 `ContextBudgetSnapshot(prompt_tokens=0, completion_tokens=0, total_tokens=0)` 作为占位快照。
- Host 架构真源 `docs/host/design.md` §25 / §25.1 已明确 proactive threshold compaction 属于 Host Context Governance，Engine event 只是 reactive fallback。
- 实施编排与追踪真源 `docs/host/implementation-control.md` 追踪区写明该 `budget_state` 只是占位诊断载体，不代表真实 budget，并要求改成 optional / unknown 语义或明确 unknown marker。

### 1.3 严重性判断

严重性成立，但边界是 P0 阻塞 Phase 10，不阻塞 Host Phase 1-9。

原因：

- 如果不先修改公共契约，后续 Host implementation agent 可能把 `0/0/0` 当成真实 prompt / completion / total token snapshot，导致 Host compact 诊断、policy decision 或测试期望建立在错误数据上。
- 该误解会把 Engine reactive fallback 错看成 Engine 已负责 context budget governance，从而违反 `UI -> Service -> Host -> Engine` 分层边界。
- 但当前问题不影响 Engine 普通 final/tool/cancel 路径，也不要求提前实现 Host Context Governance，所以不应扩大到 Host implementation code。

## 2. Non-Goals And Scope Boundary

本 P0 不做：

- 不实现 Host Context Governance。
- 不修改 Host implementation code。
- 不实现 Host compact policy、budget estimator、RunInputBuilder compact provider、EventLog canonical compact events 或 recovery state machine。
- 不把 proactive context governance 放进 Engine。
- 不让 Engine compact、retry、重构 messages、计算 threshold、调用 tokenizer 或持久化 compact artifact。
- 不新增兼容 wrapper、兼容 re-export 或旧接口兼容读取。
- 不把显式诊断事实塞进 `metadata` 或 extra payload。
- 不改变 EngineEvent wire value `context_compaction_requested`。
- 不改变 Runner context overflow classifier 的 provider 信号矩阵，除非测试发现当前路径无法覆盖既定契约。

允许范围：

- Engine context overflow event data type。
- Engine provider overflow 分支的事件 data 构造。
- Engine contract / agent / runner 相关测试。
- `docs/engine/design.md`、`dayu/engine/README.md`、`dayu/README.md`、`docs/host/implementation-control.md` 的语义同步。
- `tests/README.md` 仅在测试分层说明需要变化时更新。

## 3. Affected Files Or Modules

### 3.1 必然候选

- `dayu/engine/contracts/engine_events.py`
  - `ContextCompactionRequestedData` 当前字段为 `budget_state: ContextBudgetSnapshot`。
  - 需要改为 `ContextBudgetSnapshot | None`，并更新中文 docstring。
- `dayu/engine/contracts/agent_run.py`
  - `ContextBudgetSnapshot` docstring 当前记录 `0/0/0` 占位语义。
  - 需要删除占位说明，改为只描述真实快照；unknown 由使用方字段 `None` 表达。
- `dayu/engine/agent.py`
  - `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED` 分支当前构造 `ContextBudgetSnapshot(0, 0, 0)`。
  - 需要改成 `budget_state=None`，保留 reason、provider_request_id 与 recoverable `RunFailedData`。
- `tests/engine/test_engine_event_contract.py`
  - 当前锁定 `ContextCompactionRequestedData` 字段集合含 `budget_state`。
  - 需要增加或更新断言，确认字段仍必填但可为 `None`，且 `budget_state=ContextBudgetSnapshot(1000, 500, 1500)` 这类真实 snapshot 合法；unknown 不再靠 `0/0/0`。
- `tests/engine/test_agent_phase2.py`
  - 当前覆盖 context overflow 映射到 `context_compaction_requested` 与 recoverable `run_failed`。
  - 需要增加断言 `compact_event.data.budget_state is None`，并继续断言 provider_request_id、iteration_completed、terminal failure。
- `tests/engine/runners/openai/test_http_error_event.py`
  - 必须补 Runner HTTP context overflow event-path 回归测试，确认 HTTP 400 context overflow body 产出 `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED`、保留 `provider_request_id`，并以 `RunnerDoneData(FinishReason.ERROR)` 收口。

### 3.2 条件候选

- `dayu/engine/contracts/__init__.py`、`dayu/engine/__init__.py`、`tests/engine/test_package_exports.py`
  - 本计划默认不新增公共类型、不删除公共导出，因此不应修改。
  - 只有 pyright 或导出测试证明类型导出需要同步时才允许最小修改。
- `dayu/engine/contracts/runner_events.py`
  - 默认不改；现有 `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED` 说明已表达由 Host 决定是否 compact。
  - 只有文档同步时发现措辞仍暗示 Engine budget governance，才允许改 docstring。
- `dayu/engine/runners/openai/error_classifier.py`
  - 默认不改；现有职责是 provider adapter 边界识别 context overflow。
- `dayu/engine/runners/openai/runner.py`
  - 默认不改；现有职责是把 provider overflow 归一为 `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED`。

### 3.3 文档候选

- `docs/engine/design.md`
  - §15 必须删除 `0/0/0` 占位快照说明，改为 unknown / optional 语义。
- `dayu/engine/README.md`
  - 必须同步 Engine overflow 关键机制与事件流说明，明确 `budget_state=None` 表示未知。
- `dayu/README.md`
  - 当前已说明 Engine emit 是 reactive fallback；应精化已有 Context Governance 术语条目，加入 budget unknown 边界。不要机械追加重复段落，不要把未来 Phase 10 写成已完成。
- `docs/host/implementation-control.md`
  - P0 implementation 完成时必须回写追踪区：最终契约、验证命令、residual risks / deferred items destination。
- `docs/host/design.md`
  - 默认不改。现有 §25 / §25.1 已明确 proactive 属 Host、reactive 来自 Engine。
- `tests/README.md`
  - 默认不改。只有新增测试改变测试分层说明时才同步。
- 根目录 `README.md`
  - 不改。本 P0 不改变用户安装、CLI、配置或常用工作流。

## 4. Contract Changes

### 4.1 最终表达

采用 optional 表达 unknown：

```text
ContextCompactionRequestedData.budget_state: ContextBudgetSnapshot | None
```

约束：

- 字段保持必填，无默认值；调用方必须显式面对该字段。
- `None` 是唯一的 unknown / not reported 表达。
- 不得用 `ContextBudgetSnapshot(0, 0, 0)`、负数或其它 sentinel 表达 unknown。
- `ContextBudgetSnapshot` 只表示真实、可解释的 token snapshot；它不承载 unknown marker，不负责预算计算。
- provider overflow 路径当前没有可靠 usage，也没有 Engine estimator，因此必须传 `None`。
- P0 不要求在 `ContextBudgetSnapshot` dataclass 类型级禁止零值；禁止的是把 `0/0/0` 当作 unknown sentinel。若未来调用方能证明某个真实 snapshot 数值为零，应按真实 snapshot 语义处理，而不是 unknown。

该方案比新增 `UnknownContextBudgetSnapshot` marker 更保守：

- 不引入新公共 dataclass / enum。
- 不增加下游 pattern matching 分支。
- 不让 unknown 看起来像另一种 snapshot。
- 与现有 `provider_request_id: str | None`、`raw_payload: JsonValue | None` 的公共契约风格一致。

### 4.2 保留的诊断事实

P0 必须保留以下事实，不得为删除 `0/0/0` 而丢失诊断能力：

- provider overflow reason：
  - `ContextCompactionRequestedData.reason` 继续使用 `context_compaction_required`。
  - `RunFailedData.error_code` 继续使用 `context_compaction_required`。
  - Runner 层仍以 `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED` 表达 provider overflow 分类。
- `provider_request_id`：
  - 从 `RunnerHTTPErrorData.provider_request_id` 透传到 `ContextCompactionRequestedData.provider_request_id`。
  - `RunnerDoneData.provider_request_id` 继续提升到 `IterationCompletedData.provider_request_id`。
  - terminal `RunFailedData.provider_request_id` 继续保留同一 provider request id。
- `usage_reported`：
  - 保持独立 `UsageReportedData` 事件。
  - overflow HTTP error 路径不得合成 usage，也不得把 usage 塞进 compaction data。
  - 如果未来某 Runner 在 overflow 前已经真实报告 usage，已报告的 `usage_reported` 仍按事件流事实存在；P0 不新增聚合逻辑。
- `iteration_completed`：
  - Runner `RunnerDoneData(FinishReason.ERROR)` 后仍产出 `iteration_completed`。
  - `context_compaction_requested` 不是 run terminal；最终仍以 recoverable `run_failed(context_compaction_required)` 收口。

### 4.3 Error Semantics

- Runner context overflow 不属于 Runner 内部 retry。
- Engine context overflow 不属于 Engine compact / retry。
- Engine 把 provider overflow 转为 recoverable failure candidate，最终 terminal 是 `run_failed(recoverable=True)`。
- Host 是否恢复、如何 compact、是否新建 Attempt、是否失败，由 Host Phase 10 policy 决定。

### 4.4 State Semantics

- `context_compaction_requested` 是非终态 diagnostic / trigger event。
- `iteration_completed` 只表示本轮 RunnerEvent stream 已结束，不是 run terminal。
- `run_failed(context_compaction_required, recoverable=True)` 是 Engine 本次 run terminal。
- Host reactive path 才可把当前 Attempt 关闭并让 Run 进入 `RECOVERING`；Engine 不产生 Host Run / Attempt 状态迁移。

## 5. Implementation Decisions

### 5.1 Target APIs And Types

- 修改 `ContextCompactionRequestedData.budget_state` 类型为 `ContextBudgetSnapshot | None`。
- 保留 `ContextCompactionRequestedData.reason: str`，不在 P0 引入新 reason enum。
- 保留 `ContextBudgetSnapshot` dataclass 及包根导出。
- 保留 `EngineEventType.CONTEXT_COMPACTION_REQUESTED` wire value。
- 保留 `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED`。

### 5.2 Ownership Boundaries

- Host 语义以 `docs/host/design.md` 为准；P0 不能重新定义 Host 架构。
- Engine owns provider overflow reactive event contract。
- Runner owns provider HTTP / protocol normalization and context overflow classification。
- Host owns proactive and reactive compaction governance after ingest。
- `dayu.runtime` 不参与本 P0。
- Fins storage 不参与本 P0。

### 5.3 Documentation Boundary

- Engine docs 写“当前代码如何工作”：provider overflow -> event with unknown budget -> recoverable run_failed。
- Host docs 不写 Engine 实现细节；只保留 Host governance boundary 和 ingest expectation。
- `docs/host/implementation-control.md` 追踪区记录 P0 完成事实和 residual risks，供 Phase 10 plan 引用。

## 6. Implementation Slices

### Slice P0-S1: Engine Contract And Overflow Event Semantics

- Slice id: `P0-S1`
- Short name: `engine-contract-unknown-budget`
- Objective:
  - 修改 Engine 公共事件契约，使 provider overflow 的 budget unknown 由 `None` 表达。
  - 移除 `0/0/0` sentinel 生产路径。
  - 保持 provider_request_id、reason、iteration_completed 与 recoverable run_failed 诊断事实不回归。
- Allowed files / modules:
  - `dayu/engine/contracts/engine_events.py`
  - `dayu/engine/contracts/agent_run.py`
  - `dayu/engine/agent.py`
  - `tests/engine/test_engine_event_contract.py`
  - `tests/engine/test_agent_phase2.py`
  - `tests/engine/runners/openai/test_http_error_event.py`
  - `dayu/engine/contracts/__init__.py`、`dayu/engine/__init__.py`、`tests/engine/test_package_exports.py`，仅当 pyright 或导出锁定测试证明必须同步时允许。
- Dependencies:
  - 无前置 implementation slice。
- Exact allowed changes:
  - `ContextCompactionRequestedData.budget_state` 改为 `ContextBudgetSnapshot | None`。
  - 更新该 dataclass 中文 docstring，写明 `None` 表示 provider overflow 边界预算未知 / 未上报。
  - 更新 `ContextBudgetSnapshot` 中文 docstring，删除 `0/0/0` 占位描述，明确该类型只表示真实快照，不做计算。
  - `dayu/engine/agent.py` context overflow 分支改为传 `budget_state=None`。
  - 保留 `_ERROR_CONTEXT_COMPACTION_REQUIRED`、`_CONTEXT_COMPACTION_REQUIRED_MESSAGE`、`provider_request_id`、`recoverable=True`。
  - 更新或新增测试断言 `ContextCompactionRequestedData(..., budget_state=None, ...)` 合法。
  - 更新或新增测试断言 `ContextCompactionRequestedData(..., budget_state=ContextBudgetSnapshot(1000, 500, 1500), ...)` 这类真实 snapshot 合法。
  - 更新 `test_context_overflow_http_error_maps_to_compaction_required_fact`，断言 `compact_event.data.budget_state is None`。
  - 在 `tests/engine/runners/openai/test_http_error_event.py` 增加 Runner HTTP context overflow event-path 测试，断言 400 context overflow body 产出 `RunnerHTTPErrorData.error_code is RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED`、保留 `provider_request_id`、后续 `RunnerDoneData.finish_reason is FinishReason.ERROR`。
- Concrete implementation instructions:
  - 不要新增 `UnknownBudget` dataclass、enum 或 wrapper。
  - 不要为旧调用方提供兼容构造器或兼容 re-export。
  - 不要把预算 unknown 放入 `metadata`。
  - 不要修改 Runner classifier 信号矩阵。
  - 不要改 Host 代码。
  - 新增或修改的函数 / 类 / 模块 docstring 必须为中文，并说明参数、返回值、异常；本 slice 主要修改 dataclass docstring，不新增复杂逻辑。
- Non-goals:
  - 不实现预算估算。
  - 不合成 usage。
  - 不改变 event ordering。
  - 不把 reason 改成 Host canonical compact trigger source。
- Tests:
  - `source .venv/bin/activate && pytest tests/engine/test_engine_event_contract.py tests/engine/test_agent_phase2.py::test_context_overflow_http_error_maps_to_compaction_required_fact tests/engine/runners/openai/test_http_error_event.py::<new_context_overflow_test_name> -q`
- Expected assertions:
  - `ContextCompactionRequestedData` 字段集合仍包含 `iteration_id`、`budget_state`、`reason`、`provider_request_id`。
  - `budget_state=None` 是合法 unknown。
  - `budget_state=ContextBudgetSnapshot(1000, 500, 1500)` 这类真实 snapshot 合法。
  - `ContextBudgetSnapshot(0, 0, 0)` 不得作为 unknown sentinel，但本 P0 不要求 dataclass 类型级禁止零值。
  - Engine overflow event 序列仍是 `iteration_started -> context_compaction_requested -> iteration_completed -> run_failed`。
  - `provider_request_id == "req_context"` 同时出现在 compaction event、iteration_completed 和 run_failed。
  - terminal `RunFailedData.error_code == "context_compaction_required"` 且 `recoverable is True`。
  - Runner HTTP overflow event-path 测试确认 `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED`、`provider_request_id` 与 `RunnerDoneData(FinishReason.ERROR)` 均不回归。
  - 不再出现 `ContextBudgetSnapshot(0, 0, 0)` 断言或构造。
- Completion signal:
  - Slice tests 通过。
  - `source .venv/bin/activate && pyright` 通过。
  - sentinel 检查通过：生产代码和当前 tests 不得保留旧 unknown-budget sentinel 语义。implementation report 必须记录多行构造检查结果，至少包括对 `ContextBudgetSnapshot(`、`prompt_tokens=0`、`completion_tokens=0`、`total_tokens=0`、`0/0/0`、`占位快照` 的搜索与人工核对结论。
- Stop condition:
  - 如果必须引入 Host estimator、tokenizer、compact retry 或 Host state transition 才能让测试通过，立即停止并交回 controller。
  - 如果 pyright 暴露出 public export 需要破坏性重排，先停止并报告具体错误，不自行发明兼容层。

### Slice P0-S2: Documentation And Phase Tracking Sync

- Slice id: `P0-S2`
- Short name: `docs-contract-sync`
- Objective:
  - 以 P0-S1 的最终代码契约为真源，同步 Engine / Host 边界文档。
  - 回写 Host implementation-control 追踪区，明确 Phase 10 依赖的新语义。
- Allowed files / modules:
  - `docs/engine/design.md`
  - `dayu/engine/README.md`
  - `dayu/engine/contracts/runner_events.py`，仅检查 docstring 是否仍暗示 Engine budget governance；若无需修改，implementation artifact 记录 `checked, no change needed`。
  - `dayu/README.md`
  - `docs/host/implementation-control.md`
  - `tests/README.md`，仅当测试分层说明实际需要更新时允许。
  - `docs/host/design.md` 默认不改；只有发现与 P0-S1 最终契约直接冲突时才允许最小措辞修正。
- Dependencies:
  - 依赖 P0-S1 完成，必须以实际代码契约为准。
- Exact allowed changes:
  - `docs/engine/design.md` §15 删除 `ContextBudgetSnapshot(0,0,0)` 占位说明，改为 `budget_state=None` / unknown。
  - `docs/engine/design.md` 边界章节补强：Engine 不计算 Host budget，不做 proactive threshold compaction，不 compact / retry。
  - `dayu/engine/README.md` 事件流 / 关键机制处补强：上下文长度超限会提升为 `context_compaction_requested`，该事件的 `budget_state` 在 provider overflow 路径为 `None`。
  - 检查 `dayu/engine/contracts/runner_events.py` 中 `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED` 等相关 docstring。若没有旧 `0/0/0`、Engine budget governance 或 Engine compact/retry 暗示，不修改该文件，并在 implementation artifact 记录 `checked, no change needed`。
  - 精化 `dayu/README.md` 已有 Context Governance 术语条目：只说明当前边界，即 Engine reactive event 在 provider overflow 路径不携带真实 Host budget，Host Context Governance 使用自身 estimator / policy；不得机械追加重复段落，不得写成 Phase 10 已完成。
  - `docs/host/implementation-control.md` 追踪区追加 P0 完成后可回写的稳定事实、验证命令、residual risk destination；不得把未来 Host Phase 10 实现写成已完成。
  - 检查 `tests/README.md` 是否需要调整。若只是新增同类 Engine contract / runner error 测试，不改。
- Concrete implementation instructions:
  - 文档只写当前代码事实，不写未来设计承诺。
  - 不把 Host Phase 10 的 estimator、compact artifact、EventLog schema 细节提前写进 Engine docs。
  - 不修改根 `README.md`，因为本 P0 不改变用户手册入口。
  - 不写过程状态或 changelog。
- Non-goals:
  - 不重写 Host Context Governance 设计。
  - 不新增用户手册内容。
  - 不记录实现过程流水账。
- Tests / validation:
  - 文档 slice 后运行 sentinel 检查，并在 implementation report 说明多行构造检查结果。至少检查 `ContextBudgetSnapshot(`、`prompt_tokens=0`、`completion_tokens=0`、`total_tokens=0`、`0/0/0`、`占位快照`。
  - 允许历史 review artifact 命中旧文本；生产代码、当前 tests、当前 README / design docs 不得保留旧 unknown-budget sentinel 语义。
  - 运行 P0-S1 受影响测试，防止文档 slice 意外改动代码。
- Expected assertions:
  - `docs/engine/design.md` §15 明确 `budget_state=None`。
  - `dayu/engine/README.md` 明确 Engine 不负责 proactive budget governance。
  - `dayu/engine/contracts/runner_events.py` 已检查；如未修改，implementation artifact 写明 `checked, no change needed`。
  - `docs/host/implementation-control.md` 追踪区可以被 Phase 5 / Phase 10 plan 读取到：Phase 5 负责 EngineEvent ingest validation 接受 `budget_state=None`；Phase 10 负责在 Engine overflow budget unknown 时用 Host estimator / policy 生成 before / after budget refs 并决策 compact / recovery。
- Completion signal:
  - 文档旧术语清理完成。
  - README 触发规则已逐项执行或明确不更新。
- Stop condition:
  - 如果文档同步需要改 Host state machine、compact event schema 或 Phase 10 policy 细节，停止并交回 controller，不能扩大 P0。

## 7. Tests And Validation Commands

Implementation agent 必须在 `source .venv/bin/activate` 后运行以下命令。

受影响单元 / 集成测试：

```bash
source .venv/bin/activate && pytest \
  tests/engine/test_engine_event_contract.py \
  tests/engine/test_agent_phase2.py::test_context_overflow_http_error_maps_to_compaction_required_fact \
  tests/engine/runners/openai/test_http_error_event.py::<new_context_overflow_test_name> \
  tests/engine/runners/openai/test_context_overflow_classifier.py \
  -q
```

建议的 Engine 相关回归集合：

```bash
source .venv/bin/activate && pytest tests/engine tests/engine/runners/openai/test_context_overflow_classifier.py -q
```

类型检查：

```bash
source .venv/bin/activate && pyright
```

旧 sentinel 搜索：

```bash
rg -n "ContextBudgetSnapshot\\(|prompt_tokens=0|completion_tokens=0|total_tokens=0|0/0/0|占位快照" dayu tests docs README.md
```

implementation report 必须说明上述命中的多行构造检查结果。允许历史 review artifact 命中旧文本；生产代码、当前 tests、当前 README / design docs 不得保留旧 unknown-budget sentinel 语义。

Expected failure paths:

- 如果 `ContextCompactionRequestedData.budget_state` 仍为非 optional，pyright 或 contract tests 应失败。
- 如果 Engine overflow path 仍构造 `ContextBudgetSnapshot(0,0,0)`，agent phase2 测试或 sentinel 搜索应失败。
- 如果 contract tests 只覆盖 `None`，没有覆盖真实 `ContextBudgetSnapshot(1000, 500, 1500)`，P0-S1 不得完成。
- 如果 `provider_request_id` 不再透传，agent phase2 测试应失败。
- 如果 event ordering 被改坏，agent phase2 测试应失败。
- 如果 Runner context overflow 被误归为普通 `CLIENT_ERROR`，Runner classifier / HTTP overflow event-path 测试应失败。

覆盖目标：

- 单文件修改覆盖率应维持项目目标。若只改 dataclass typing / docstring，重点依赖 contract tests 和 agent integration test；若新增分支逻辑，必须补分支测试。

## 8. Documentation Update Decision

必须更新：

- `docs/engine/design.md`
  - 命中 Engine design contract 变更。
- `dayu/engine/README.md`
  - 命中 `dayu/engine/` 修改触发规则。
- `dayu/README.md`
  - 命中 Engine / Host 分层关系和 Context Governance 边界说明；只精化已有 Context Governance 术语条目，避免冗余，不把未来 Phase 10 写成已完成。
- `docs/host/implementation-control.md`
  - 本 P0 tracking destination，需回写完成事实与 residual risk。

默认不更新：

- `docs/host/design.md`
  - 当前 §25 / §25.1 已明确 proactive 属 Host、reactive 来自 Engine；除非 implementation 发现直接冲突。
- 根 `README.md`
  - 不涉及安装、配置、CLI、trace/render 入口或用户工作流。
- `tests/README.md`
  - 现有分层说明已覆盖 Engine contract、Runner HTTP error、context overflow classifier；若只是补同类测试，不改。
- `dayu/config/README.md`、`dayu/host/README.md`、`dayu/fins/README.md`
  - P0 不修改对应包或配置入口。

## 9. Review Gates And Stop Conditions

Required gates:

- Plan review。
- Plan fix / re-review，如有 accepted findings。
- User confirmation。
- Accepted plan commit，由 controller 在确认后执行。
- Slice P0-S1 implementation -> code review -> fix -> re-review -> user confirmation -> accepted slice commit。
- Slice P0-S2 implementation -> code review -> fix -> re-review -> user confirmation -> accepted slice commit。

Stop conditions:

- 任何实现需要修改 Host implementation code。
- 任何实现把 proactive context governance 放进 Engine。
- 任何实现要求 Engine compact、retry、估算 provider-aware budget 或新增 tokenizer。
- 任何实现继续保留 `0/0/0` 作为 unknown budget。
- 任何实现为旧 `budget_state: ContextBudgetSnapshot` 接口添加兼容 wrapper / facade。
- 任何实现把 required contract facts 放入 `metadata`。
- pyright 报错涉及更大公共契约设计，且无法在本 P0 文件边界内最小修复。
- plan review 发现 optional 表达不足以满足 Host Phase 10 ingest 的 material contract，需要 controller 裁决。

## 10. Risks And Open Questions

### Blocking Questions For Controller

无。

本计划按用户已给出的决策执行：跳过 phase design，直接进入 P0 plan；P0 允许涉及 Engine contract / docs / tests；不得夹带 Host implementation code。

### Non-Blocking Risks

1. `reason: str` 继续保持字符串而不是 StrEnum。
   - Working assumption: P0 只解决 budget unknown 误导；reason 当前已有私有常量和 `RunFailedData.error_code` 字符串契约，不在本轮扩 public enum。
   - 风险: 后续 Host ingest 若用自由字符串匹配，仍需自身 typed mapping。
   - 触发回看条件: plan review 明确要求把 `context_compaction_required` 也收敛成公共 enum，且认为这是 P0 blocker。
   - 归属: P0 plan review 裁决；若非 blocker，则 Host Phase 5 / Phase 10 ingest mapping 处理。

2. `ContextBudgetSnapshot` 保持导出，但 provider overflow 当前不再生产真实 snapshot。
   - Working assumption: 该类型仍可表示真实预算快照，不应因为当前 overflow 路径 unknown 就删除公共类型。
   - 风险: 文档若写得不清楚，调用方可能误以为 Engine 总能计算 budget snapshot。
   - 触发回看条件: sentinel 搜索或 README review 发现仍有 `0/0/0` / “Engine budget” 旧语义。
   - 归属: P0-S2 docs sync。

3. Host canonical `CONTEXT_COMPACTION_REQUESTED` payload 仍需要 budget snapshot refs。
   - Working assumption: Engine `budget_state=None` 表示没有 Engine budget ref；Host Phase 10 使用自身 estimator / policy 生成 before / after refs。
   - 风险: Phase 5 ingest 若把 `None` 当作协议错误，会提前拒绝合法 Engine reactive overflow；Phase 10 若等待 Engine budget ref，会无法生成 compact diagnostics。
   - 触发回看条件: Phase 5 plan 编写时发现 EngineEvent ingest schema 强制要求非空 budget，或 Phase 10 plan 编写时发现 canonical event schema 强制要求 Engine-provided budget ref。
   - 归属: Phase 5 owns EngineEvent ingest validation 接受 `budget_state=None`；Phase 10 owns Context Governance semantic interpretation，并用 Host estimator / policy 生成 before / after budget refs。

## 11. Residual Risk Tracking Destination

P0 implementation report 必须把 residual risks 分类并回写或指派：

- Engine overflow budget unknown 已修复：回写 `docs/host/implementation-control.md` 追踪区。
- Host reactive ingest validation 对 `budget_state=None` 的结构接受：deferred to Phase 5 dispatch / reactive failure closeout。Phase 5 owns EngineEvent ingest validation，必须接受 `budget_state=None` 的 Engine event shape，不把 `None` 当作协议错误，不要求 Engine 提供 Host budget ref。
- Host Context Governance semantic interpretation：deferred to Phase 10 Context Governance / Compaction。Phase 10 owns `budget_state=None` 的治理语义，必须在 Engine overflow budget unknown 时使用 Host estimator / policy 生成 before / after budget refs，并决定 compact / recovery。
- Host estimator / policy / compact artifact：deferred to Phase 10 Context Governance / Compaction。
- Provider-specific tokenizer adapter：deferred to Host later capability，不进入第一版 Phase 10。
- P0 closeout 必须把 Phase 5 / Phase 10 的上述责任切分回写 `docs/host/implementation-control.md` 追踪区。

不得关闭 slice 或 work unit，除非每个 residual risk 都有上述 destination。

## 12. Implementation Completion Report Format

Implementation agent 每个 slice 完成后必须写 durable implementation artifact，并在对话中按以下格式报告：

```markdown
## Implementation Report

- Work gate: implementation
- Work unit: Host Phase 0 / P0 - Engine Context Compaction Event 语义前置
- Assigned slice: <P0-S1 或 P0-S2>
- Approved plan path: docs/host/phase0-engine-context-compaction-plan.md
- Changed files:
  - <path>
- Implemented plan items:
  - <item>
- Not implemented:
  - <item and reason, or none>
- Validation commands and results:
  - `<command>`: passed / failed / not run with reason
- Documentation update decision and result:
  - <README/design doc decisions>
- Plan gaps or controller decisions needed:
  - <none or details>
- Residual risks and uncovered areas:
  - <classification: fixed current slice / later slice / later phase / existing issue / new issue or user decision>
- Completion signal:
  - <met / not met>
- Stop condition status:
  - <none hit / hit details>
- Artifact path:
  - <docs/reviews/...>
```
