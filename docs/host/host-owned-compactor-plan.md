# Host-owned LLM context compactor for public opener implementation plan

## 0. 范围

本 plan 覆盖 public opener 下 context compactor ownership 收口：普通 Service 只提供 compactor runner / storage 配置，由 Host 在 `open_host(options)` 内部构造并持有 LLM compactor。

`docs/host/design.md` 是本 work unit 的设计真源。本 plan 只把 design 中已冻结的 Host-owned compactor public opener contract 拆成可执行实现切片；当 plan 与 design 发生冲突时，以 `docs/host/design.md` 为准，implementation 必须先回到 controller 处理设计冲突，不能自行按 plan 覆盖 design。

目标实现完成后，普通 Service-facing public contract 不再暴露 `ContextCompactor` port。是否保留 `ContextCompactor` seam 必须以 Host 内部测试和职责分离为理由：它可以作为 Host internal / low-level test seam 存在，但不能进入 `OpenHostOptions`、包根普通 public contract 或 manual smoke 的 Service 装配路径。

目标架构固定以下边界：Service 不实现 `ContextCompactor.compact(...)`；provider / transport failure 复用 Engine runner 层 bounded retry；LLM 脏输出 / candidate reject 由 Host compaction operation 做 bounded semantic repair attempts；真实 LLM 调用不得发生在 Host write transaction 内。

## 1. 动机判断

### 1.1 问题真实存在

问题成立，且不是表面命名问题。

当前设计真源已经把 Context Governance 定位为 Host owner：Host 负责 context budget、compact 编排、`CONTEXT_COMPACTION_REQUESTED` / `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED`、compact artifact、quality check、memory projection 消费边界。Service 的职责是业务入口、身份解析、场景装配和调用 Host，不应拥有 Host governance 的状态机或候选结构。

当前代码能跑通 compact smoke，但路径是：调用方/测试侧实现 `ContextCompactor.compact(...)`，再通过 `CompactorExecutionBaseline(context_compactor=...)` 注入 `OpenHostOptions`。这让 Service-facing construction boundary 接触到了 Host compaction request/candidate 低层结构，实质上把 compact prompt、candidate builder 和失败语义的一部分外放给调用方。

### 1.2 严重性判断

严重性中高。它不会立刻破坏 EventLog truth，因为 dispatch / ingest 仍由 Host 做 quality check、artifact 写入和 canonical event append；但它会破坏 public contract 的长期边界：

- Service 可以通过自定义 `ContextCompactor` 决定如何解释 `CompactionRequest`、如何拼 prompt、如何构造 `CompactionCandidate`，这已经进入 Host governance 语义。
- `CompactionCandidate` 不是普通部署配置，而是 Host compact canonical path 的候选结构；让 Service 构造它，会让 Host 以后很难演进 candidate schema、quality check、prompt/scene 和 memory projection contract。
- manual smoke 的 `DeepSeekContextCompactor` 和 `tests/host/test_public_compact_smoke.py` 的 `_RealLLMContextCompactor` 都复制了 LLM 调用、prompt 和 candidate mapping；这会诱导真实生产 Service 也照抄。

### 1.3 目标路径判断

目标路径是：Service 只提供 runner spec/options、artifact root、ContextBudgetPolicy 等部署/存储/预算输入；Host 在 opener 内部构造 Host-owned LLM compactor。当前只有一套 compactor policy，`policy_ref` 不作为 Service-facing 参数暴露；Host 内部记录固定 policy id / version 用于 EventLog / artifact / diagnostic 审计。semantic repair 预算来自 Host context budget policy 的 `max_compaction_attempts_per_operation` typed 字段，含第一次 proposal attempt 与后续 repair attempts；不得用魔法数字、raw policy string 或 Service callback 表达。收口点在 `open_host.py` 的 public opener composition root：把 public runner/storage 配置转换成 internal `HostLocalExecutionOptions.context_compactor`，同时从包根 public namespace 移除 direct compactor port 暴露。

## 2. 当前 public contract 泄漏点清单

### 2.1 `dayu.host.api.CompactorExecutionBaseline.context_compactor`

当前 `CompactorExecutionBaseline` 是包根 public export，字段包含：

- `context_compactor: ContextCompactor | None`
- `compactor_runner_spec: RunnerSpec | None`
- `compactor_runner_options: RunnerCallOptions | None`
- `compact_artifact_root: pathlib.Path`
- `compact_artifact_create_parent_dirs: bool`

其中 `context_compactor` 是核心泄漏点。它让普通 Service-facing options 接收 Host internal typed port。

### 2.2 `OpenHostOptions.compactor_baseline`

`OpenHostOptions.compactor_baseline: CompactorExecutionBaseline | None` 把上述 port 进一步提升为 public opener contract。`open_host._local_execution_options_from_open_host_options(...)` 当前直接把 `compactor_baseline.context_compactor` 透传到 `HostLocalExecutionOptions.context_compactor`。

### 2.3 `dayu.host.__init__` 包根导出

包根当前导出 `CompactorExecutionBaseline`。`dayu/host/README.md` 也把它列入普通 opener / handle public contract。这会把低层 compactor port 误标为普通 Service 应依赖的稳定类型。

### 2.4 `HostLocalExecutionOptions`

`HostLocalExecutionOptions` 当前是低层本地执行配置，字段包含 `context_compactor`、`compactor_runner_spec`、`compactor_runner_options`、`compactor_policy_ref`、`compact_artifact_root`。它已不作为普通 Service-facing 包根导出，但仍是内部 scheduler / low-level tests 的装配 seam。该层可以保留 `context_compactor`，但必须明确为 Host internal / low-level test seam；`compactor_policy_ref` 若保留，也只能是 Host 内部 diagnostic field，不能由 Service-facing opener 传入。

### 2.5 `dispatch.py` proactive compact 调用

`HostDispatchScheduler` 在 pre-start Context Governance 中从 `self._local_execution.context_compactor` 取 compactor 并调用 `compactor.compact(request)`，随后 Host 做 quality check、artifact 写入和 `CONTEXT_COMPACTED`。该调用 owner 应保持在 Host 内部。

### 2.6 `engine_ingest.py` reactive compact 调用

`EngineEventIngestor` 对 Engine `context_compaction_requested` reactive fallback 同样接收 `context_compactor` 并调用 `compact(request)`。这是 Host reactive governance 路径，不能让 Service 提供的自定义 compactor 参与治理语义。

### 2.7 manual smoke

`utils/smoke_host_public_multiturn.py` 定义 `DeepSeekContextCompactor(ContextCompactor)`，内部自行：

- 拼 compactor system/user prompt；
- 调用 `run_agent_and_wait(AgentRunRequest(...))`；
- 禁用 tools；
- 把 LLM summary 映射为 `CompactionCandidate`；
- 通过 `CompactorExecutionBaseline(context_compactor=compactor, ...)` 注入 `OpenHostOptions`。

这是需要从 public opener / smoke 中移除的 Service-side compactor 装配样式。

### 2.8 public compact smoke

`tests/host/test_public_compact_smoke.py` 定义 `_RealLLMContextCompactor(ContextCompactor)`，形态与 manual smoke 类似，并从 `dayu.host` 包根导入 `CompactorExecutionBaseline`。该测试目前证明了 public opener 能接通 compactor，但同时固化了泄漏 contract。

### 2.9 README 表述

根 README 明确写到 manual smoke 通过 `OpenHostOptions` 注入 compactor baseline。`dayu/host/README.md` 把 `CompactorExecutionBaseline` 写入 opener public contract，并写到 public opener 装配 compactor baseline。文档需要跟着目标 contract 改成“Service 提供 compactor runner/config baseline；Host 内部构造 Host-owned LLM compactor”。

## 3. 目标架构

### 3.1 Public opener contract

普通 Service / `OpenHostOptions` 只提供 compactor 运行与存储配置，不提供 `ContextCompactor` 实例，不提供 prompt，不提供 candidate builder。

目标 public type：

```python
@dataclass(frozen=True, slots=True)
class CompactorRunnerBaseline:
    """Host-owned LLM compactor 的构造期运行配置。"""

    compactor_runner_spec: RunnerSpec
    compactor_runner_options: RunnerCallOptions
    compact_artifact_root: pathlib.Path
    compact_artifact_create_parent_dirs: bool = True
```

`OpenHostOptions` 字段从：

```python
compactor_baseline: CompactorExecutionBaseline | None
```

改为：

```python
compactor_runner_baseline: CompactorRunnerBaseline | None
```

### 3.2 Host-owned compactor

新增 Host 内部 `LLMContextCompactor(ContextCompactor)`，由 `open_host.py` 在 `_local_execution_options_from_open_host_options(...)` 或邻近私有 helper 中构造，并注入 `HostLocalExecutionOptions.context_compactor`。

放置位置固定为 `dayu/host/llm_compaction.py`。

不得放入 `dayu.runtime`，因为它需要理解 Host `CompactionRequest` / `CompactionCandidate`、Host prompt/scene、candidate mapping 和 quality-check 预期，属于 Host Context Governance 内部能力，不是层中立 runtime primitive。

第一版构造边界完整、固定，避免实现者再次把 prompt 或 candidate builder 下放给 Service。签名固定为：

```python
class LLMContextCompactor(ContextCompactor):
    def __init__(
        self,
        *,
        runner_spec: RunnerSpec,
        runner_options: RunnerCallOptions,
    ) -> None: ...
```

内部固定策略：

- System prompt 和 user prompt builder 是 Host private helper，不进入 public options。
- `AgentPolicy` 由 Host 固定为 compactor 专用策略：`allow_tool_calls=False`、`tool_execution_timeout_seconds` 使用 Host 内部常量、`max_iterations` 使用小的固定上限。
- `tool_schemas=()`，`tool_executor` 使用 Host internal rejecting executor 或等价 no-tool executor。
- `AgentRunRequest.session_id/run_id` 使用 compaction request 中的 Host ids 派生诊断 id，不作为 durable truth。
- `CancellationToken` 第一版不从 Service 传入。由于当前 `ContextCompactor.compact(request)` port 没有 token 参数，Host-owned compactor 依赖 Runner timeout / retry 做上界控制；LLM 调用返回后必须重新检查 durable Run/Attempt 状态，状态已变化则丢弃结果并按 stale/skip 路径收口。主动取消 compactor call 不在本计划范围；若实现需要增加该能力，必须作为 Host-owned cancellation extension，不把 Service cancellation token 注入 compactor。

### 3.3 Prompt / scene ownership

compact prompt/scene 归 Host-owned compactor 内部管理。第一版应采用 Host 通用、财报语义中立的 prompt，职责是把 Host `CompactionRequest` 映射为受控 summary input，要求 LLM 只输出 episode summary 所需的短文本或受控 JSON，再由 Host-owned mapper 生成 `CompactionCandidate`。

Service 不能传：

- compactor system prompt；
- candidate builder；
- preservation evidence builder；
- pinned state patch builder；
- quality check override；
- compact event payload；
- artifact writer。

Service 可以传：

- `RunnerSpec`；
- `RunnerCallOptions`；
- artifact root；
- artifact root create-parent-dir 行为；
- Host `ContextBudgetPolicy`。

当前只有一套 compactor policy，policy id / version 由 Host 内部固定并写入 diagnostic / artifact metadata。Service 不传 raw `policy_ref`。Host semantic repair 次数上限由 `ContextBudgetPolicy.max_compaction_attempts_per_operation` 控制，属于 typed governance budget，不是 compactor policy selector。多套 scene-specific compaction policy 不在本计划范围；后续若需要，必须作为 Host-recognized typed policy profile 重新设计 public contract，不能暴露 raw prompt、raw policy string 或 callback。

### 3.4 Candidate 结构 owner

`LLMContextCompactor` 内部负责把 LLM 输出映射为 `CompactionCandidate`。第一版可保持与 smoke 当前 candidate mapping 同等保守：

- 必须保留 `current_user_input_ref`；
- `preserved_input_event_refs` 至少覆盖 `request.input_event_refs`；
- `preserved_tool_fact_refs` / `preserved_verified_fact_refs` 来自 request；
- `preservation_evidence` 使用 request refs 构造；
- `budget_after_compact` 使用保守估算值，不能直接信任 LLM；
- episode summary / pinned state 的文本来自 LLM summary，但 refs 与三态 patch 由 Host 构造。

Host 现有 `check_compaction_candidate(...)`、artifact store、context events 和 memory projection 消费边界不变。

### 3.5 Internal seam 保留边界

`ContextCompactor` 不作为普通 public seam 保留，也不作为 package root 稳定 contract 暴露。它最多继续作为：

- `dayu.host.compaction` 内部 typed boundary；
- `HostLocalExecutionOptions.context_compactor` 的 low-level test seam；
- `tests.host.fake_compaction.FakeContextCompactor`、dispatch scheduler 单元测试、engine ingest mapping 单元测试使用的低层 seam。

保留它的唯一理由是让 Host governance 在无网络测试中验证 compact accepted/rejected、EventLog/artifact/memory 边界，而不要求真实 LLM。如果实现中可以通过 Host-owned `LLMContextCompactor` + fake runner / fake runner factory 覆盖这些 deterministic tests，则应优先收窄甚至移除显式 `ContextCompactor` 注入 seam。无论哪种实现，它都不得出现在普通 Service-facing package root / `OpenHostOptions` public contract、manual smoke 的 Service 装配路径或 README 普通用法中。

### 3.6 Retry、repair、EventLog / HostEvent 与事务边界

Compactor LLM 调用失败与 LLM 返回脏数据必须区分。

- **Transport / provider failure**：网络错误、timeout、5xx、rate limit、stream idle timeout 等由 Engine Runner 按 `RunnerSpec.max_retries`、`Retry-After` 与 retry policy 在一次 compactor proposal call 内做 bounded retry。Host 不重复实现 HTTP retry，不把 retry 策略交给 Service。
- **Compactor 单次 proposal**：`LLMContextCompactor` 只负责把一个 immutable `CompactionRequest` 和 Host-owned prompt/scene 映射为一次 LLM proposal；它不决定是否 retry / repair，不写 EventLog，不写 artifact，不更新 memory projection。
- **Host semantic repair / retry**：非 final answer、空 summary、解析失败、candidate shape 非法、缺 preservation evidence、quality check reject、compact 后仍超过 hard threshold，由 Host Context Governance 按 `ContextBudgetPolicy.max_compaction_attempts_per_operation` 编排 bounded attempts。该字段含第一次 proposal attempt 与后续 repair attempts，必须为正整数。每次 repair attempt 复用同一个 immutable compaction request、同一个 operation id、同一套 Host prompt/scene，并在 LLM call 前后 recheck durable state。
- **不做 Service replay**：脏数据不是 public `replay_run`，也不是 Service retry。repair attempt 是 Host-owned governance 行为；retry budget 耗尽后写 `CONTEXT_COMPACTION_FAILED`，不写 compact artifact，不写 `CONTEXT_COMPACTED`，不更新 memory projection。
- **EventLog 留痕**：一次 operation 至少写 `CONTEXT_COMPACTION_REQUESTED` 和最终 `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED`；Host-level semantic repair attempt reject 应写 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` canonical fact，payload 承载诊断语义，记录 operation id、attempt number、failure category、repairable、runner attempt summary refs、quality / parse / budget diagnostic refs 和 next policy decision。
- **HostEvent 映射**：不新增 `HostEventKind`。当前 public contract 只有 `PROGRESS`、`SUCCEEDED`、`FAILED`、`CANCELLED`，且 `dayu.host.read_api._host_event_from_row(...)` 只把 `RUN_SUCCEEDED` / `RUN_FAILED` / `RUN_CANCELLED` 映射为 terminal HostEvent，其余 EventLog row 统一映射为 `HostEventKind.PROGRESS`。实现必须保持这个保守映射：
  - `CONTEXT_COMPACTION_REQUESTED` -> `HostEventKind.PROGRESS`；
  - `CONTEXT_COMPACTED` -> `HostEventKind.PROGRESS`；
  - `CONTEXT_COMPACTION_FAILED` -> `HostEventKind.PROGRESS`；若该 compact failure 使 Run 收口失败，随后由对应 `RUN_FAILED` row 映射为 terminal `HostEventKind.FAILED`；
  - `CONTEXT_COMPACTION_ATTEMPT_REJECTED` -> committed EventLog canonical fact，不是 diagnostic-only log；若进入 session watch / run stream，则只能按现有 public projection 暴露为 `HostEventKind.PROGRESS` 或 `HostEventView(event_class=canonical_fact, event_type=...)`，不得新增 attempt-specific HostEventKind，也不得伪装成 terminal failure；
  - Engine runner 内部 HTTP retry 不写 EventLog compact fact，不 emit HostEvent，只进 runner log / aggregated diagnostic。
- **LLM call 不得位于 Host write transaction 内**：Host 可以在 write transaction 内冻结 input snapshot / append `CONTEXT_COMPACTION_REQUESTED`，但真实 LLM 调用必须发生在 transaction 外。LLM 返回后再开启新的 write transaction，recheck Run/Attempt/dispatch 状态与 expected cursor，再写 `CONTEXT_COMPACTED` 或 `CONTEXT_COMPACTION_FAILED`。这样 provider retry/timeout 不会持有 SQLite write lock，也不会把外部 nondeterminism 扩散到 durable mutation 临界区。

## 4. 最小切片实现步骤

### Slice 1: API shape 与 public export 收口

目标：先切断 Service-facing direct port。

修改范围：

- `dayu/host/api.py`
- `dayu/host/__init__.py`
- `tests/host/test_public_open_host_options.py`
- `tests/host/test_package_exports.py`

步骤：

1. 新增 `CompactorRunnerBaseline` dataclass，字段只保留 runner/options/artifact 配置，不包含 `ContextCompactor`，也不包含 raw `policy_ref`。
2. `OpenHostOptions` 字段改为 `compactor_runner_baseline: CompactorRunnerBaseline | None`。
3. 删除普通 Service-facing 的 `CompactorExecutionBaseline` 路径：`OpenHostOptions` 不再引用它，`dayu.host` 包根不再导出它，manual smoke / public compact smoke 不再构造它。低层测试如需直接注入 fake compactor，应改为构造 `HostLocalExecutionOptions(context_compactor=...)` 或直接实例化 internal scheduler / ingestor；不要保留仅为旧导入路径服务的兼容 class / wrapper。
4. 更新 validation tests：验证 `CompactorRunnerBaseline` 拒绝错误 Runner 类型、错误 path/bool，并确认不存在 Service-facing `policy_ref` 字段。
5. 更新 package export tests：断言包根不导出 `CompactorExecutionBaseline`，导出 `CompactorRunnerBaseline`。

不做：

- 不删除 `ContextCompactor`。
- Slice 1 不修改 dispatch / ingest governance 逻辑；transaction 边界审计与必要调整放在 Slice 4。

### Slice 2: Host-owned LLM compactor 内部类

目标：把 manual smoke / public smoke 的真实 LLM compactor adapter 收回 Host。

修改范围：

- 新增 `dayu/host/llm_compaction.py`
- 新增 `tests/host/test_llm_compaction.py`

步骤：

1. 实现 `LLMContextCompactor(ContextCompactor)`，构造签名固定为：

   ```python
   def __init__(
       self,
       *,
       runner_spec: RunnerSpec,
       runner_options: RunnerCallOptions,
   ) -> None: ...
   ```

2. 构造参数只接收 runner/options；不接收 prompt、candidate callback、quality callback、artifact writer、policy ref 或 cancellation token。
3. Host-owned prompt 放在 `dayu/host/llm_compaction.py` 的模块级私有常量 / 私有 helper 中。第一版 prompt 必须是通用、财报语义中立、无工具调用的 compact scene：要求模型只产出简短 episode summary，不允许模型声明保留 refs、改写 evidence 或决定 pinned state。
4. 内部调用 Engine public runner API：`run_agent_and_wait(AgentRunRequest(...))`。`CompactionRequest` 中的 event/tool/fact refs 被格式化为 compactor user message 的元数据文本；第一版不在 compactor 内解析 durable payload，不把 payload lookup 引入 LLM adapter。
5. compactor request 使用独立 diagnostic `run_id`，禁用 tools，`tool_schemas=()`，使用 rejecting tool executor，`AgentPolicy.allow_tool_calls=False`，`max_iterations` 使用 Host 内部小上限；provider / transport timeout 与 retry 只来自 runner spec/options，并复用 Engine `AsyncOpenAIRunner` 的 `RunnerSpec.max_retries` 语义。
6. 当前 `ContextCompactor.compact(request)` 无 cancellation token 参数；第一版不把 Service cancellation token 传入 compactor。外部 LLM 调用完成后，由 dispatch / ingest 在写入结果前重新检查 durable Run/Attempt 状态，状态已变化则丢弃结果并按 stale/failed 路径收口。
7. 使用 Host-owned private helpers 构造 `CompactionCandidate`。LLM 输出只提供 summary 文本；refs、preservation evidence、budget estimate、pinned patch 由 Host 代码构造。
8. LLM final answer 为空、非 final answer、解析失败或 summary 不满足最小约束时直接抛出 typed compaction proposal failure；不在 `LLMContextCompactor` 内做 dirty-output replay。Host compaction operation 捕获该 failure 后决定是否发起 semantic repair attempt。
9. 新增 `tests/host/test_llm_compaction.py`，至少覆盖：
   - `test_llm_context_compactor_builds_tool_disabled_request`
   - `test_llm_context_compactor_maps_final_answer_to_candidate`
   - `test_llm_context_compactor_rejects_empty_or_non_final_output`
   - `test_llm_context_compactor_preserves_host_owned_refs_and_evidence`
   - `test_llm_context_compactor_uses_runner_retry_policy_without_owning_semantic_repair`

测试实现要求：

- 不引入网络 pytest。
- `LLMContextCompactor` public 构造签名不得为了测试扩展 runner / callback seam；优先在 `tests/host/test_llm_compaction.py` 通过 monkeypatch `dayu.host.llm_compaction.run_agent_and_wait` 做 no-network 单元测试。
- monkeypatch 的 fake `run_agent_and_wait` 必须接收 `AgentRunRequest`，记录并断言 request 内的 `runner_spec` 是构造时传入的同一个 `RunnerSpec`，尤其 `RunnerSpec.max_retries` 未被 compactor 改写；`runner_options` 是构造时传入的 `RunnerCallOptions`；`tool_schemas=()` 且 policy 禁止工具调用。
- runner failure 传播测试应让 fake `run_agent_and_wait` 抛出或返回 failed outcome，并断言 `LLMContextCompactor.compact(...)` 不在内部做 semantic repair loop、不吞掉 runner 层失败；semantic repair 只在 Slice 4 的 Host compaction operation 测试中覆盖。
- 不要求真实 provider。

### Slice 3: open_host 内部构造与 local execution 映射

目标：`open_host(options)` 根据 runner baseline 构造 Host-owned compactor，再注入现有 internal scheduler / ingestor seam。

修改范围：

- `dayu/host/open_host.py`
- `dayu/host/context_policy.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_context_policy.py`

步骤：

1. `ContextBudgetPolicy` 新增 `max_compaction_attempts_per_operation: int`，默认构造函数新增同名参数和模块级默认常量；字段必须为正整数。它表示一次 compaction operation 的总 proposal attempt 上限，含第一次 LLM proposal 与后续 semantic repair attempts。
2. 在 `_local_execution_options_from_open_host_options(...)` 中读取 `options.compactor_runner_baseline`。
3. baseline 为 `None` 时维持 fail-closed no capability：`context_compactor=None`、runner/options/artifact root 为 `None`。
4. baseline 非 `None` 时构造 `LLMContextCompactor(...)`，传入 runner spec/options；同时把 artifact root/create-parent-dir 映射到 `HostLocalExecutionOptions`。
5. 显式保持完整注入链：`CompactorRunnerBaseline` -> Host-owned `LLMContextCompactor` -> `HostLocalExecutionOptions.context_compactor` -> `HostDispatchScheduler` -> `EngineEventIngestor`。proactive 与 reactive compact 必须使用同一个 Host-owned instance/config 来源。
6. `HostLocalExecutionOptions.compactor_runner_spec/options` 可以继续保存为 internal diagnostic/config fields；Host 内部可记录固定 compactor policy id / version 作为 diagnostic metadata，但不能成为 Service-facing candidate owner 或 raw string option。
7. Slice 1、2、3 可以作为 Gateflow 本地 slice checkpoint 提交，但只属于同一个 work unit 的中间状态；不得把它们描述或发布为可单独合并的 public contract 状态。Slice 1、2、3、4 必须在同一个 implementation PR readiness boundary 内连续完成，不接受“public API 已切、Host-owned compactor 已接线，但真实 LLM compact 仍可能在 Host write transaction 内执行”的可合并中间态。
8. 更新 tests：
   - baseline none 仍映射为无 compact capability；
   - baseline present 时 `local_execution.context_compactor` 是 Host-owned `LLMContextCompactor`；
   - runner/options/artifact fields 透传正确；
   - 不再能通过 `OpenHostOptions` 注入 arbitrary `ContextCompactor`。
   - `ContextBudgetPolicy.max_compaction_attempts_per_operation` 接受正整数，拒绝 0、负数、bool 和非整数。

### Slice 4: dispatch / reactive governance 保持 owner，拆分外部 LLM 调用与 durable 写入

目标：确认现有治理路径仍只调用 internal seam，不因 API 收口破坏 proactive / reactive compact；同时保证真实 LLM 调用不持有 Host write transaction。

修改范围：

- 必须调整 `dayu/host/dispatch.py` 和 `dayu/host/engine_ingest.py` 的 compact 执行阶段，拆出 request write、transaction 外 LLM call、result recheck/write 三段。
- 必须在 `dayu/host/context_events.py` 新增 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` event type、payload builder 与 validator；同步更新 `tests/host/test_context_compact_events.py`。
- 事件 schema、quality check、artifact store、memory projection owner 不变。
- 更新相关 focused tests。

步骤：

1. 保持 compactor source seam 为 Host internal：`HostDispatchScheduler` 和 `EngineEventIngestor` 只能从 internal `context_compactor` 取 compactor，compactor 来源由 Slice 3 的 Host-owned 注入链提供。这里的“保持”只约束 compactor 来源，不表示 dispatch / ingest 的 compact 控制流保持不变；本 Slice 必须按 step 2-3 重构 request write、transaction 外 LLM call、result recheck/write 三段。
2. Proactive compact 拆成三段：
   - write transaction 内冻结 input snapshot / durable request，append `CONTEXT_COMPACTION_REQUESTED`，提交；
   - transaction 外运行 Host compaction operation：调用 `compactor.compact(request)`，由 runner 层处理 provider / transport bounded retry；Host 根据 proposal failure、parse failure、quality reject 或 budget reject 按 `max_compaction_attempts_per_operation` 编排 bounded semantic repair attempts；
   - 新 write transaction 内 recheck run/attempt/session state、expected cursor 和 artifact root，再写 `CONTEXT_COMPACTED` 或 `CONTEXT_COMPACTION_FAILED`。
3. Reactive fallback 同样拆成 request durable write、transaction 外 LLM call、结果 recheck/write 三段；不得在 Engine event ingest 的 write mutation 临界区内等待 provider。
4. 缺 compactor / artifact root、provider retry exhausted、dirty output repair budget exhausted、quality check reject repair budget exhausted、compact 后仍超过 hard threshold 且 repair budget exhausted 时写 `CONTEXT_COMPACTION_FAILED` 并 fail closed。
5. stale result 策略：LLM 返回后若 run/attempt/session 已被取消、关闭、替换或 cursor 不匹配，不写 `CONTEXT_COMPACTED`；只写必要 diagnostic / failed event，避免过期 compact 覆盖新的 durable state。
6. 保持 quality check、artifact store、`CONTEXT_COMPACTED`、memory projection catch-up 现有 owner 和 event truth。
7. EventLog 使用 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` canonical fact 记录 attempt reject 诊断：每个 Host semantic repair reject 至少记录 operation id、attempt number、failure category、repairable、runner attempt summary refs、quality / parse / budget diagnostic refs 与 next policy decision；不得记录 API key、headers、完整 prompt 或完整 provider payload。
8. 在 `dayu/host/context_events.py` 增加 `build_context_compaction_attempt_rejected_payload(...)` 与 `validate_context_compaction_attempt_rejected_payload(...)`，并复用本模块现有 JSON helper 风格。payload 必填字段为 `operation_id`、`attempt_number`、`failure_category`、`repairable`、`runner_attempt_summary_refs`、`diagnostic_refs`、`next_policy_decision`、`budget_after_attempted_compact`；`attempt_number` 为正整数，`runner_attempt_summary_refs` 与 `diagnostic_refs` 为非空文本列表，`budget_after_attempted_compact` 可为非负整数或 `None`。
9. 更新 `tests/host/test_context_compact_events.py`，覆盖 attempt rejected payload builder 成功路径、缺必填字段、`attempt_number` 为 0 / bool / 非整数、空 diagnostic ref、非法 budget 的失败路径。
10. HostEvent public observation 使用 §3.6 的保守映射：compact canonical facts 不新增 `HostEventKind`，REQUESTED / COMPACTED / FAILED / ATTEMPT_REJECTED 在 session watch 中只映射为 `HostEventKind.PROGRESS`；Run terminal event 继续由 `RUN_SUCCEEDED` / `RUN_FAILED` / `RUN_CANCELLED` 映射；runner 内部 HTTP retry 不 emit HostEvent。
11. 低层 tests 继续可用 `tests.host.fake_compaction.FakeContextCompactor` 直接注入 `HostLocalExecutionOptions` 或 `EngineEventIngestor`，但生产代码不得导入 tests helper，测试命名/README 要说明这是 low-level seam。
12. 新增/更新 focused tests，覆盖 proactive 与 reactive 路径不会在 write transaction 内执行 fake compactor 的外部调用；可用 instrumented transaction runner / fake compactor 记录调用阶段。

### Slice 5: smoke 迁移

目标：manual smoke 和 public compact smoke 不再自己实现 `ContextCompactor`。

修改范围：

- `utils/smoke_host_public_multiturn.py`
- `tests/host/test_public_compact_smoke.py`
- `tests/host/public_smoke_support.py`

步骤：

1. 删除 `DeepSeekContextCompactor` / `_RealLLMContextCompactor` 类及其 compactor 专属 rejecting executor / thread wrapper / candidate mapper 重复逻辑；ordinary runner 仍使用的 DeepSeek runner/options helper 保留并复用。
2. 构造 `OpenHostOptions` 时传 `compactor_runner_baseline=CompactorRunnerBaseline(...)`。
3. manual smoke 的 stdout 不再打印 `compactor.call_count` / `last_summary` 这类调用方对象状态；改为通过 public watch / run snapshot / compact artifact root 检查 compact 结果，必要时读取 artifact 文件名/数量作为人工排查信息。
4. public compact smoke 断言从 “测试侧 compactor call_count >= 1” 改成 Host public/observable 证据：
   - first run terminal succeeded；
   - second run terminal succeeded；
   - compact artifact root 下存在本次运行窗口内新创建或新修改的 artifact；
   - artifact path / metadata 能和本次 smoke session/run window 对上，避免误读旧 artifact；
   - 后续 run continuity 非空或包含稳定 marker；
   - 如测试已有合法 internal event helper，可在非 public correctness 断言里辅助确认 `CONTEXT_COMPACTED`，但 public smoke 主证据仍走 public opener / watch。
5. provider skip 逻辑保留：真实 compactor runner provider 不可用、quota、rate-limit 时精确 skip；不能把网络真实 compactor pytest 变成默认必跑单元测试。

### Slice 6: README 同步

目标：文档不再指导 Service 注入 compactor port。

修改范围：

- `README.md`
- `dayu/host/README.md`
- `tests/README.md` 如测试分层描述涉及 public compact smoke

步骤：

1. 根 README 的 manual smoke 描述改为：ordinary runner 与 Host-owned compactor runner 都使用 DeepSeek 配置；脚本只通过 `OpenHostOptions` 提供 runner/config/artifact root，不实现或注入 `ContextCompactor`，也不传 compactor policy ref。
2. `dayu/host/README.md` opener public contract 列表将 `CompactorExecutionBaseline` 替换为 `CompactorRunnerBaseline`。
3. `dayu/host/README.md` compaction 章节补充：
   - `ContextCompactor` 不从包根导出，不进入 Service-facing opener contract；
   - public opener 内部构造 Host-owned `LLMContextCompactor`；
   - `ContextCompactor` 只保留为 Host internal / low-level test seam。
4. 删除或改写“调用方注入显式 compactor adapter”的表述。
5. README 只写当前代码事实；实现完成前不提前更新。

## 5. 风险与不做事项

### 5.1 风险

- **真实 provider 行为不稳定**：Host-owned `LLMContextCompactor` 会调用真实 LLM，pytest 不应默认依赖网络；真实 smoke 保持 env-gated skip。
- **candidate mapper 过度信任 LLM**：LLM 只应提供 summary 文本；refs、evidence、pinned patch 结构由 Host 构造，quality check 继续兜底。
- **公共 API 破坏面**：`CompactorExecutionBaseline` 已在包根导出，迁移会影响现有 tests/manual smoke。项目已按全新设计处理，不保留兼容 wrapper；但需要一次性更新 docs/tests。
- **reactive compact 漏迁移**：dispatch proactive 和 engine ingest reactive 都要接同一个 Host-owned compactor instance/config，不能只改 pre-start path。
- **artifact 可观测性变化**：manual smoke 原先能直接读 `compactor.call_count`；迁移后应以 artifact/event/public terminal 为证据，避免重新引入测试专用 public hook。
- **LLM 调用事务边界**：如果实现时沿用当前同步 compact 调用位置，真实 provider retry/timeout 可能持有 Host write transaction。实现必须先审计 proactive 与 reactive compact 的 transaction 边界，再接入真实 `LLMContextCompactor`。
- **脏输出误判为低层 retry**：Provider failure 可以 runner retry；脏输出是 Host semantic repair 场景，必须由 Host compaction operation 按 context budget policy 的 attempt 上限 bounded repair，不能交给 Compactor 自行 retry，也不能让 Service replay。
- **Slice 1-4 中间态不可发版**：Slice 1-4 可以形成本地 checkpoint，但只有全部完成并验证后才构成 PR-ready public opener contract。中途若只完成 API 收口与 Host-owned compactor 接线，而未完成 transaction 外 LLM call 拆分，真实 provider compact 仍可能持有 write transaction。

### 5.2 明确不做

- 不让 Service 传 compactor prompt。
- 不让 Service 传 candidate builder / preservation evidence builder / pinned patch builder。
- 不让 Service 传 `ContextCompactor` 实例。
- 不把 compactor 放进 `dayu.runtime`。
- 不把 compact artifact、quality check、`CONTEXT_*` event、memory projection 消费边界移出 Host。
- 不删除 Host quality check / artifact / EventLog truth。
- 不引入网络 pytest 作为默认验证要求。
- 不修改 Engine 以理解 Host context governance。
- 不把 Engine provider overflow 当作 proactive context governance；reactive overflow 继续只是 fallback。
- 不把 runner 内部 HTTP retry 写成 HostEvent，避免 public watch 噪音。
- 不用模块内魔法数字隐藏 semantic repair 次数上限；该上限必须来自 typed Host context budget policy。
- 不保留兼容性 re-export / wrapper 来维持旧 `CompactorExecutionBaseline` 包根路径。

## 6. 验证矩阵

### 6.1 类型与静态检查

- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
- 要求：0 errors；不得新增、扩散或掩盖类型错误。

### 6.2 focused unit / integration tests

按 slice 分批跑：

- `source .venv/bin/activate && pytest tests/host/test_public_open_host_options.py tests/host/test_package_exports.py -q`
- `source .venv/bin/activate && pytest tests/host/test_open_host_runtime.py -q`
- `source .venv/bin/activate && pytest tests/host/test_context_compact_events.py -q`
- `source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py -q`
- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py -q`
- `source .venv/bin/activate && pytest tests/host/test_public_compact_smoke.py -q -rs`

如新增 `tests/host/test_llm_compaction.py`：

- `source .venv/bin/activate && pytest tests/host/test_llm_compaction.py -q`

`tests/host/test_llm_compaction.py` 至少包含：

- `test_llm_context_compactor_builds_tool_disabled_request`
- `test_llm_context_compactor_maps_final_answer_to_candidate`
- `test_llm_context_compactor_rejects_empty_or_non_final_output`
- `test_llm_context_compactor_preserves_host_owned_refs_and_evidence`
- `test_llm_context_compactor_uses_runner_retry_policy_without_owning_semantic_repair`

dispatch / ingest transaction 边界至少包含：

- `test_proactive_compaction_calls_llm_outside_write_transaction`
- `test_reactive_compaction_calls_llm_outside_write_transaction`
- `test_compaction_stale_result_does_not_write_compacted_event`
- `test_compaction_repair_attempt_rejection_is_recorded_in_eventlog`
- `test_compaction_attempt_rejected_payload_requires_positive_attempt_number`
- `test_compaction_attempt_rejected_payload_requires_diagnostic_refs`
- `test_compaction_attempt_rejected_maps_to_progress_host_event`
- `test_runner_provider_retry_does_not_emit_host_event`
- `test_context_budget_policy_validates_max_compaction_attempts_per_operation`

### 6.3 Host public smoke / manual smoke

默认不要求真实网络 provider 在 CI 中必跑。需要提供可人工执行入口：

- `source .venv/bin/activate && python utils/smoke_host_public_multiturn.py --help`
- 有 `DEEPSEEK_API_KEY` 且网络可用时，人工运行 manual smoke，确认：
  - Service 只通过 `open_host(options)` 和 public handle 操作；
  - options 只传 compactor runner/config/artifact root；
  - stdout 不输出 API key、headers、完整 prompt 或 provider payload；
  - compact artifact root 下有本次 run window 内产生的 artifact；
  - terminal HostEvent 可展示 final answer；
  - 后续多轮连续性仍成立。

### 6.4 全量 host regression

实现完成并 focused tests 通过后跑：

- `source .venv/bin/activate && pytest tests/host -q`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
- `git diff --check`

### 6.5 README 同步检查

- `README.md` 不再描述 Service 注入 `ContextCompactor` / `DeepSeekContextCompactor`。
- `dayu/host/README.md` 包根 public contract 不再列 `CompactorExecutionBaseline`。
- compaction 章节明确 `ContextCompactor` 是 Host internal / low-level test seam。
- tests README 如提到 compact smoke，应区分 env-gated real provider smoke 与 no-network unit tests。

## 7. Implementation-ready handoff 摘要

实现时按以下顺序推进最小闭环：

1. 先改 public API shape：`CompactorRunnerBaseline` 替代 public `CompactorExecutionBaseline`，包根移除 direct compactor port。
2. 增加 Host-owned `LLMContextCompactor`，用 monkeypatch `dayu.host.llm_compaction.run_agent_and_wait` 的 no-network unit tests 固定 prompt/request/candidate mapping 与 `RunnerSpec.max_retries` 透传边界。
3. 在 `open_host` 内部用 runner baseline 构造 `LLMContextCompactor`，注入现有 `HostLocalExecutionOptions.context_compactor`。
4. 审计并调整 dispatch / engine ingest compact 执行阶段，确保 durable request/result 写入在 transaction 内，真实 LLM call 在 transaction 外，返回后 recheck state 再写结果；Slice 1-4 只能作为同一 PR readiness boundary 交付。
5. 保持 dispatch / engine ingest 的 quality check、artifact、EventLog、memory catch-up owner 不变；provider failure 走 Engine runner retry，dirty output / candidate reject 走 Host semantic repair attempts，并在 `dayu.host.context_events` 固定 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` builder / validator。
6. 迁移 manual smoke / public compact smoke，删除测试侧真实 compactor 实现，并用本次 run window artifact / public watch 作为可观测证据。
7. 最后同步 README，并跑 focused tests、host tests、pyright 与 `git diff --check`。
