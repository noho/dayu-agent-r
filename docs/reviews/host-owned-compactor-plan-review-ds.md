# Host-owned compactor plan 对抗性 review

## 审查范围

- Plan artifact: `docs/host/host-owned-compactor-plan.md`
- 审查命题：plan 是否阻塞正确实施 Host-owned LLM context compactor，是否遗漏 public contract 收口、Service/Host 分层、typed API 迁移、测试可执行性或回滚安全性
- 审查方法：逐 slice 推演实现，核对代码事实（`dayu/host/api.py`、`dayu/host/open_host.py`、`dayu/host/dispatch.py`、`dayu/host/engine_ingest.py`、`dayu/host/__init__.py`、`tests/host/test_package_exports.py`、`tests/host/test_public_open_host_options.py`、`utils/smoke_host_public_multiturn.py`、`tests/host/test_public_compact_smoke.py`），验证每个变更点的代码位置、类型流和测试边界

## 总体评价

Plan 正确识别了当前 `CompactorExecutionBaseline.context_compactor` → `OpenHostOptions.compactor_baseline` → `open_host._local_execution_options_from_open_host_options()` 的泄漏链，目标架构符合 `docs/host/design.md` 的 Context Governance Host ownership 定位。六个 slice 的顺序推进合理：先切 public contract，再补 Host-owned 实现，再接线，最后迁移 smoke/README。

无 blocking finding。以下逐项列出验证过程、non-blocking 观察与 residual risks。

---

## Slice 1: API shape 与 public export 收口

### 验证

修改范围覆盖了四个关键文件：

| 文件 | 需要变更 | plan 是否覆盖 |
|---|---|---|
| `dayu/host/api.py` | 新增 `CompactorRunnerBaseline`，改 `OpenHostOptions.compactor_baseline` → `compactor_runner_baseline`，更新 `__post_init__` 验证 | 覆盖（api.py 列入修改范围） |
| `dayu/host/__init__.py` | 移除 `CompactorExecutionBaseline` import/export，新增 `CompactorRunnerBaseline` | 覆盖 |
| `tests/host/test_public_open_host_options.py` | 更新 import 与 validation 测试 | 覆盖 |
| `tests/host/test_package_exports.py` | 更新 `EXPECTED_API_EXPORTS` | 覆盖 |

### 代码事实核对

当前 `api.py:1150-1156` 的 `OpenHostOptions.__post_init__` 验证：

```python
if self.compactor_baseline is not None and not isinstance(
    self.compactor_baseline, CompactorExecutionBaseline
):
    raise TypeError(...)
```

plan Slice 1 修改范围列出 `dayu/host/api.py`，隐含覆盖该验证。当前 `api.py:1039` 字段声明为 `compactor_baseline: CompactorExecutionBaseline | None`，改为 `compactor_runner_baseline: CompactorRunnerBaseline | None` 后，`isinstance` 检查目标从 `CompactorExecutionBaseline` 变为 `CompactorRunnerBaseline`。此变更在 Slice 1 step 2 语义范围内。

当前 `dayu/host/__init__.py:58` 导入 `CompactorExecutionBaseline`，`__init__.py:154` 在 `__all__` 中导出。Slice 1 step 3/5 覆盖了移除和替换。

### Non-blocking 观察

1. **`CompactorExecutionBaseline` 降级路径不够具体**：plan step 3 写 "保留在 `dayu.host.api` 仅供低层测试 / internal composition；或直接改名为 internal private type"——两条路径差异大（保留 vs 改名），实现者需自行裁决。建议实现前确认选哪条：若选保留，`CompactorExecutionBaseline` 仍在 `dayu.host.api` 模块中可被 import，需确认低层测试的 import 路径不需要适配；若选改名（如 `_CompactorExecutionBaseline`），需同步更新所有低层测试 import。

2. **`test_public_open_host_options.py:266-283` 的 `test_compactor_baseline_validates_typed_fields` 测试**：当前测试直接构造 `CompactorExecutionBaseline` 并验证其自身 `__post_init__`。改为 `CompactorRunnerBaseline` 后，该测试需更名为测试新类型的自身验证（拒绝空 policy ref、错误 Runner 类型），plan Slice 1 step 4 已覆盖。

---

## Slice 2: Host-owned LLM compactor 内部类

### 验证

plan 正确将 `LLMContextCompactor` 定位为 Host 内部类，放置于 `dayu/host/llm_compaction.py`，实现 `ContextCompactor` protocol。

### 代码事实核对

当前两处真实 compactor 实现——`utils/smoke_host_public_multiturn.py` 的 `DeepSeekContextCompactor` 和 `tests/host/test_public_compact_smoke.py` 的 `_RealLLMContextCompactor`——形态一致：
- 硬编码 system/user prompt
- 调用 `run_agent_and_wait(AgentRunRequest(...))`，tools 禁用
- 使用 rejecting tool executor
- `_candidate_from_summary()` 将 LLM 输出映射为 `CompactionCandidate`
- thread-based async 包装（manual smoke）

plan Slice 2 描述的 `LLMContextCompactor` 结构与此对齐，且明确：
- 构造参数只接收 `RunnerSpec`/`RunnerCallOptions`/policy ref（不接收 prompt/candidate callback）
- 内部调用 `run_agent_and_wait`
- 使用 Host-owned private helpers 构造 prompt 和 candidate
- 禁用 tools

### Non-blocking 观察

1. **Prompt/scene 位置未指定**：plan Section 3.3 写 "第一版应采用 Host 通用、财报语义中立的 prompt"，但未指定 prompt 存放位置。建议明确：prompt 作为 `dayu/host/llm_compaction.py` 模块级私有常量（如 `_COMPACTOR_SYSTEM_PROMPT`、`_COMPACTOR_USER_PROMPT_TEMPLATE`），或独立 `dayu/host/compactor_prompts.py` 文件。这属于实现细节，不阻塞 plan 有效性，但建议在 plan 中补充一句以避免 implementation 时自行决定引入新模块或新配置机制。

2. **`CompactionRequest` 到 Engine `AgentRunRequest` 的映射未详细说明**：plan 写 "内部调用 Engine public runner API：`run_agent_and_wait(AgentRunRequest(...))`"，但 `CompactionRequest` 携带的是 `input_event_refs`、`current_user_input_ref`、`tool_fact_refs` 等 ref，不是消息列表。`LLMContextCompactor` 需要将这些 ref 映射为 `AgentRunRequest.messages`。当前 smoke 实现的策略是将 refs 格式化为用户消息文本。plan 应在 Slice 2 中明确：`LLMContextCompactor` 将 `CompactionRequest` 的 ref 元数据格式化为文本消息（不解析 payload），Engine 负责实际消息构造。

3. **单元测试覆盖边界清晰**：plan Slice 2 step 6 列出的测试覆盖点（final answer → candidate mapping、空 summary fail fast、refs 保留、tools 禁用）是可验证的单元测试范围。"用 fake worker / monkeypatch `run_agent_and_wait`" 的策略正确避开了网络依赖。

---

## Slice 3: open_host 内部构造与 local execution 映射

### 验证

plan 正确识别了关键变更点：`_local_execution_options_from_open_host_options()`（`open_host.py:599-659`）。

### 代码事实核对

当前 `open_host.py:623-627`：

```python
context_compactor=(
    compactor_baseline.context_compactor
    if compactor_baseline is not None
    else None
),
```

变更后逻辑：

```python
compactor_runner_baseline = options.compactor_runner_baseline
context_compactor=(
    LLMContextCompactor(
        runner_spec=compactor_runner_baseline.compactor_runner_spec,
        runner_options=compactor_runner_baseline.compactor_runner_options,
        policy_ref=compactor_runner_baseline.compactor_policy_ref,
    )
    if compactor_runner_baseline is not None
    else None
),
```

同时 `compactor_runner_spec`/`compactor_runner_options`/`compactor_policy_ref`/`compact_artifact_root`/`compact_artifact_create_parent_dirs` 字段继续从 `compactor_runner_baseline` 映射到 `HostLocalExecutionOptions`（来源从 `CompactorExecutionBaseline` 变为 `CompactorRunnerBaseline`，字段名和类型不变）。

### Non-blocking 观察

1. **`LLMContextCompactor` 构造是否需要更多参数**：plan 写构造参数只接收 runner spec/options/policy ref。但 `LLMContextCompactor.compact()` 内部调用 `run_agent_and_wait()` 时，Engine 需要知道 artifact root（compact artifact 写入位置）和可能的 budget policy。这些当前通过 `HostLocalExecutionOptions` 的 `compact_artifact_root` 字段传递给 `EngineEventIngestor`（dispatcher 在 `dispatch.py:2170-2185` 构造 `EngineEventIngestor` 时传入）。确认：artifact root 不是 `LLMContextCompactor` 的构造参数，而是 Host dispatch/ingest 层的职责——compactor 只负责 LLM 调用和 candidate 映射，artifact 写入由 dispatch/ingest 在 compact 调用返回后执行。plan 3.4 节确认了这一点："Host 现有 `check_compaction_candidate(...)`、artifact store、context events 和 memory projection 消费边界不变。"

2. **reactive path 接线无需额外改动**：`dispatch.py:2174` 从 `self._local_execution.context_compactor` 取 compactor 传给 `EngineEventIngestor`。由于 Slice 3 将 Host-owned `LLMContextCompactor` 注入同一个 `HostLocalExecutionOptions.context_compactor` 字段，proactive（dispatch.py:998）和 reactive（engine_ingest.py:1344）路径自动获得同一实例。plan Slice 4 "原则上不需要改" 的判断正确。

---

## Slice 4: dispatch / reactive governance 保持 owner

### 验证

plan 正确判断 dispatch.py 和 engine_ingest.py 核心逻辑无需改动——二者都通过 `self._local_execution.context_compactor` 或 `self._context_compactor` 引用，而这些引用在 Slice 3 中已替换为 Host-owned 实例。

### 代码事实核对

- `dispatch.py:998`: `compactor = self._local_execution.context_compactor` → 读 `HostLocalExecutionOptions`，Slice 3 覆盖
- `dispatch.py:1063`: `candidate = compactor.compact(request)` → 调用不变
- `dispatch.py:2174`: `context_compactor=self._local_execution.context_compactor` → 传给 `EngineEventIngestor`，不变
- `engine_ingest.py:420`: `context_compactor: ContextCompactor | None = None` → 构造参数类型不变
- `engine_ingest.py:1344`: `compactor = self._context_compactor` → 读已注入实例，不变

### Non-blocking 观察

1. **quality check、artifact store、CONTEXT_COMPACTED、memory projection catch-up**：plan 确认这些 Host 现有路径不变，无需额外验证。

---

## Slice 5: smoke 迁移

### 验证

plan 正确识别了需要删除的 Service-side compactor 实现和需要变更的断言方式。

### 代码事实核对

| 待删除/变更项 | 文件 | plan 覆盖 |
|---|---|---|
| `DeepSeekContextCompactor` 类 | `utils/smoke_host_public_multiturn.py` | Slice 5 step 1 |
| `_CompactorRejectingToolExecutor` | 同上 | 同 step |
| `_RealLLMContextCompactor` 类 | `tests/host/test_public_compact_smoke.py` | Slice 5 step 1 |
| `_candidate_from_summary()` helpers | 同上 | 同 step |
| `compactor.call_count >= 1` 断言 | `tests/host/test_public_compact_smoke.py` | Slice 5 step 4 |
| `compactor_baseline=CompactorExecutionBaseline(context_compactor=compactor, ...)` | 两处 | Slice 5 step 2 |

### Non-blocking 观察

1. **Smoke 断言迁移的精度**：plan Slice 5 step 4 给出的替换证据链为：
   - first run terminal succeeded
   - second run terminal succeeded
   - compact artifact root 下存在 artifact
   - 后续 run continuity 非空或包含稳定 marker
   
   这些是可观测的 public-path 证据。建议实现时在 `test_public_compact_smoke.py` 中：
   - 用 `host.watch_session_events(session_id)` 的 terminal HostEvent 断言两轮 SUCCEEDED
   - 用 `pathlib.Path(artifact_root).glob("**/*")` 断言至少存在一个 compact artifact 文件
   - 用第二轮 user prompt 不含第一轮独有关键信息、第二轮 final answer 包含 continuity marker 的模式（而非精确内容匹配）验证记忆延续

2. **Manual smoke stdout 变更**：当前 manual smoke 打印 `compactor.call_count` 和摘要内容，迁移后改为打印 compact artifact root 下的文件数和文件名列表，这对于人工排查是可用的。plan step 3 已覆盖。

3. **Thread-based async 包装删除**：manual smoke 的 `asyncio.run()` / `threading` 包装是 Service-side compactor 特有的实现细节，Host-owned `LLMContextCompactor` 不需要这些——Engine 的 `run_agent_and_wait` 本身是 async，compactor 在 Host 内部也是 async 环境调用。删除后不会影响功能。

---

## Slice 6: README 同步

### 验证

plan 覆盖了三个 README 的变更点，且遵守 CLAUDE.md 的 "README 只写当前代码事实" 约束。

### Non-blocking 观察

1. **`dayu/host/README.md` 的 `CompactorExecutionBaseline` → `CompactorRunnerBaseline` 替换**：需同步确认 README 中没有残留 "调用方注入显式 compactor adapter" 或 "Service 构造 `ContextCompactor`" 的旧指导。plan step 4 已覆盖此检查。

---

## 跨 slice 一致性检查

### 类型流验证

```
Service 调用方
  └─ OpenHostOptions(compactor_runner_baseline=CompactorRunnerBaseline(...))
       └─ open_host(options)
            └─ _local_execution_options_from_open_host_options()
                 ├─ LLMContextCompactor(RunnerSpec, RunnerCallOptions, policy_ref)  ← Host 内部构造
                 └─ HostLocalExecutionOptions(context_compactor=<LLMContextCompactor>)
                      ├─ HostDispatchScheduler._local_execution.context_compactor  ← proactive
                      └─ EngineEventIngestor._context_compactor                    ← reactive
```

类型流完整，无断裂。

### 回滚安全性

六个 slice 的推进顺序支持增量验证和逐 slice 回滚：

1. Slice 1 完成后：public API shape 已切，但内部仍可用 `CompactorExecutionBaseline`（仍在 `api.py` 中）让低层测试通过
2. Slice 2 完成后：`LLMContextCompactor` 已存在且有单元测试，但尚未接入 open_host
3. Slice 3 完成后：接线完成，端到端可工作
4. Slice 4-6: 验证、smoke 迁移、文档同步

如果 Slice 3 接线后发现问题，可回退 Slice 3 变更（恢复 `_local_execution_options_from_open_host_options` 中读 `compactor_baseline.context_compactor` 的旧逻辑）而不影响 Slice 1-2 的类型定义和单元测试。

---

## Coverage checklist（对照 post-p10.md S4 要求）

| S4 要求 | plan 覆盖 | 备注 |
|---|---|---|
| small budget trigger 触发 proactive compact | Slice 5 smoke 迁移（small budget trigger 由现有 `ContextBudgetPolicy` 小窗口配置提供） | 覆盖 |
| real compactor adapter 通过 public opener 接入 | Slice 3 接线 + Slice 5 smoke | 覆盖 |
| CONTEXT_COMPACTION_REQUESTED → compact artifact → CONTEXT_COMPACTED | Slice 4 保持 canonical event path | 覆盖 |
| memory projection consumption | Slice 4 保持 memory catch-up | 覆盖 |
| subsequent run continuity | Slice 5 step 4 | 覆盖 |
| mock/test-double compactor 不计入 P10.5 success signal | Slice 5 smoke 使用 Host-owned 真实 compactor | 覆盖 |
| compactor execution baseline 与 ordinary Run override 分离 | Slice 3（`compactor_runner_baseline` 独立于 `ordinary_run_baseline`） | 覆盖 |

---

## Residual risks

1. **真实 provider 行为不稳定**：plan 已识别（Section 5.1）。Host-owned `LLMContextCompactor` 调用真实 LLM 时，需要合理的 timeout 和错误处理。plan 未指定 timeout/retry 策略——建议在 `LLMContextCompactor` 实现中，timeout 沿用 `RunnerSpec.default_timeout_seconds` 或 `RunnerCallOptions` 中的超时设置，失败时抛出明确异常由 dispatch/ingest 层写 `CONTEXT_COMPACTION_FAILED`。此风险不阻塞 plan，属于 implementation detail。

2. **`CompactorExecutionBaseline` 的低层测试 import 路径**：当前低层测试（如 `test_dispatch_scheduler.py`）直接从 `dayu.host` 或 `dayu.host.api` import `CompactorExecutionBaseline`。若 Slice 1 将其从包根 `__all__` 移除但保留 class，低层测试可以选择 `from dayu.host.api import CompactorExecutionBaseline` 或改为使用 `HostLocalExecutionOptions` 直接注入 `context_compactor`。plan Section 3.5 确认 `HostLocalExecutionOptions.context_compactor` 作为 low-level test seam 保留——建议实现时检查所有低层测试 import，确保无 import error。

3. **Manual smoke 的 `DeepSeekContextCompactor` 删除后，原脚本中的 compactor 构造逻辑（如 `DeepSeekContextCompactor` 依赖的 `_DeepSeekRunnerSpec()`、`_DeepSeekRunnerOptions()` 等 helper）可能仍被 ordinary runner 路径复用**。plan 未区分哪些 helper 是 compactor 专属（应删除）vs. ordinary runner 共享（应保留）。实现时需仔细检查 `utils/smoke_host_public_multiturn.py` 中 `_DeepSeekRunnerSpec()`、`_DeepSeekRunnerOptions()` 等函数的引用关系。

---

## 结论

无 blocking finding。plan 正确识别了泄漏链、目标架构合理、slice 推进顺序支持增量验证和回滚、验证矩阵覆盖了类型检查/单元测试/smoke/README 四层。

以上 non-blocking 观察和 residual risks 建议在进入 implementation 前由 plan author 确认处理策略，但不阻塞 plan 批准。
