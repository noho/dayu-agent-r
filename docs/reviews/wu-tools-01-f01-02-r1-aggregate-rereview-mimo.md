# Code Review

## Scope

- Mode: aggregate fix narrow re-review (WU-TOOLS-01-F01-02-R1)
- Branch: `phase/wu-tools-01-f01-02-r1`
- Base: aggregate checkpoint `28bba810`，复核 Codex fix commit 之后的未提交 diff
- Output file: `docs/reviews/wu-tools-01-f01-02-r1-aggregate-rereview-mimo.md`
- Included scope:
  - `dayu/fins/ingestion/wait_adapter.py` — `build_fins_wait_activation_registry` 签名变更、`FinsIngestionWaitActivationAdapter.from_workspace_root` 删除
  - `dayu/service/host_assembly.py` — `_fins_wait_activation_registry_from_provider_configs` 改用 builder、`_require_distinct_fins_awaiting_tool_names` 删除、import 清理
  - `tests/fins/test_fins_ingestion_tools.py` — activation registry builder 调用更新 + runtime identity 断言
  - `tests/service/test_host_assembly.py` — Service wiring runtime identity 断言补强
  - `dayu/fins/README.md` — builder 签名文档更新 + runtime 共享语义说明
- Excluded scope: 未变更的 Host activation hook、Fins prepare/activate runtime、Engine contract、LLM-facing schema
- Parallel review coverage: 无

## 复核对象

Controller 接受的 AGG-F01：原 `build_fins_wait_activation_registry(workspace_root=...)` 隐式创建独立 runtime，调用方无法保证与 awaiting callable / poll adapter 共享 process-local observation runtime；应改为显式接收共享 runtime，并让 production Service assembly 使用 builder。

## Findings

未发现实质性问题。

## 逐项验证

### 验证点 1：`build_fins_wait_activation_registry` 签名已改为 `runtime: FinsObservationRuntime + tool_names`

**通过。**

直接证据 `wait_adapter.py:209-235`：

```python
def build_fins_wait_activation_registry(
    *, runtime: FinsObservationRuntime, tool_names: Sequence[str]
) -> WaitActivationRegistry:
```

- 参数 `workspace_root: Path` 已移除，替换为 `runtime: FinsObservationRuntime`。
- 函数体内不再调用 `DefaultFinsRuntime.create(...)` 或 `FinsIngestionWaitActivationAdapter.from_workspace_root(...)`。
- 函数体内不再调用 `_require_absolute_workspace_root(workspace_root)`。
- adapter 构造为 `FinsIngestionWaitActivationAdapter(runtime=runtime)`，直接使用传入 runtime。

### 验证点 2：`FinsIngestionWaitActivationAdapter.from_workspace_root` 已删除，无 dead helper / compatibility wrapper

**通过。**

- `wait_adapter.py` 中 `FinsIngestionWaitActivationAdapter` 类（line 160-185）不再包含 `from_workspace_root` 方法。
- `grep -rn "from_workspace_root" dayu/fins/ingestion/wait_adapter.py` 仅命中 `FinsIngestionWaitPollAdapter.from_workspace_root`（line 108），这是 poll adapter 的独立构造器，不属于 activation 路径。
- `DefaultFinsRuntime` import（line 40）仍被 `FinsIngestionWaitPollAdapter.from_workspace_root` 使用，不是 dead import。
- `_require_distinct_fins_awaiting_tool_names` helper 已从 `host_assembly.py` 完全删除（`grep` 无结果）。其功能已被 `wait_adapter.py` 内的 `_deterministic_tool_names` 覆盖（该函数同时做空值、重复、不受支持校验），删除不丢失校验语义。
- 无旧接口兼容 re-export 或 compatibility wrapper。

### 验证点 3：production path 仍要求 shared runtime，调用 `build_fins_wait_activation_registry(runtime=..., tool_names=...)`

**通过。**

直接证据 `host_assembly.py:1756-1789`：

```python
def _fins_wait_activation_registry_from_provider_configs(
    provider_configs, *, available_tool_names, fins_awaiting_runtime
):
    ...
    if fins_awaiting_runtime is None:
        raise ValueError("Fins wait activation registry requires shared runtime")
    if not isinstance(fins_awaiting_runtime, FinsIngestionRuntime):
        raise ValueError("Fins wait activation registry requires ingestion runtime")
    return build_fins_wait_activation_registry(
        runtime=fins_awaiting_runtime,
        tool_names=registry_inputs.tool_names,
    )
```

- fail-fast 保留：无 runtime → `ValueError`，runtime 类型不是 `FinsIngestionRuntime` → `ValueError`。
- 生产路径现在调用 `build_fins_wait_activation_registry` builder，与 standalone 使用同一个构造逻辑。
- callable / poll / activation 共享 runtime 的行为：`_tooling_options_from_discovery`（line 1712）将同一个 `fins_awaiting_runtime` 传入 `_fins_wait_activation_registry_from_provider_configs`，而 callable 和 poll adapter 也使用同一 discovery 创建的 runtime。

### 验证点 4：tests 覆盖 registry adapter.runtime is shared runtime，Service wiring 断言不弱化

**通过。**

`tests/fins/test_fins_ingestion_tools.py:1485-1498`：

```python
def test_fins_wait_activation_registry_binds_fins_adapter_key() -> None:
    runtime = _FakeObservationRuntime(snapshots={})
    registry = build_fins_wait_activation_registry(
        runtime=runtime,
        tool_names=(DOWNLOAD_TOOL_NAME, PREPROCESS_TOOL_NAME, UPLOAD_TOOL_NAME),
    )
    adapter = registry.resolve_adapter(FINS_INGESTION_WAIT_ADAPTER_KEY)
    assert isinstance(adapter, FinsIngestionWaitActivationAdapter)
    assert adapter.runtime is runtime  # ← 新增断言
```

`tests/service/test_host_assembly.py:839-844`：

```python
assert isinstance(activation_adapter, FinsIngestionWaitActivationAdapter)
assert activation_adapter.runtime is discovered_tools.fins_awaiting_runtime  # ← 新增断言
assert activation_adapter.runtime is callable_.runtime
```

- standalone builder 测试新增 `adapter.runtime is runtime` 断言，证明 builder 直接复用传入 runtime。
- Service wiring 测试新增 `activation_adapter.runtime is discovered_tools.fins_awaiting_runtime` 断言，形成三重 identity 链：`activation_adapter.runtime` → `discovered_tools.fins_awaiting_runtime` → `callable_.runtime`。
- 断言未弱化：原有的 `isinstance` 检查和 `callable_.runtime` identity 断言均保留。

### 验证点 5：README 更新准确，无 process/gate 文本泄漏

**通过。**

`dayu/fins/README.md` 变更：

- line 167：builder 签名更新为 `build_fins_wait_activation_registry(runtime=..., tool_names=...)`。
- line 172：新增说明 "awaiting tool callable 与 wait activation registry 例外：activation adapter 必须接收 awaiting tool callable 使用的同一个 `FinsIngestionRuntime` 实例，因为 prepared observation 是进程内 runtime 状态，不是可由 `workspace_root` 重新发现的持久事实。"
- line 675（diff）：`DefaultFinsRuntime` 描述从 "当前共享语义不是'所有入口必须共享同一个 Python 对象实例'" 修正为 "当前共享语义通常不是'所有入口必须共享同一个 Python 对象实例'；但 awaiting observation 的 tool callable 与 activation adapter 必须共享同一个 `FinsIngestionRuntime` 实例"。

无 "WU-TOOLS-01-F01-02-R1"、"Slice"、"gateflow"、"accepted commit"、"controller"、"AgentMiMo" 等 gate 治理术语。

### 验证点 6：验证命令可信

**通过。** 本 reviewer 独立复现：

| 命令 | 结果 |
|---|---|
| `pytest tests/fins/test_fins_ingestion_tools.py tests/service/test_host_assembly.py -q` | **103 passed**, 3 warnings |
| `pytest tests/host/test_toolruntime_executor.py tests/host/test_phase7_waiting_integration.py tests/fins/test_fins_ingestion_runtime.py -q` | **108 passed**, 3 warnings |
| `pyright` | **0 errors, 0 warnings, 0 informations** |
| `git diff --check` | 无输出 |

测试数量与 Codex fix artifact 报告一致。3 个 warnings 均为 edgar 依赖的 `DeprecationWarning`，与本次变更无关。

## Open Questions

- 无。MiMo 首轮 aggregate deepreview 的 Open Question（standalone builder 与生产路径 runtime 构造方式不同导致误用风险）已被本次修复解决：standalone builder 现在接收外部 `runtime` 参数，不再自建独立实例。

## Residual Risk

- MiMo 首轮 review Item 02（activation adapter 构造 handle 时 `created_at` 使用当前时间而非 prepare 时间）未被本次修复覆盖，Controller 已裁决其不参与当前 activation 查找语义，严重程度为低，无功能影响。
- 本 WU 不覆盖的 production hardening（#89、#90、#92）不因本修复改变风险等级。
- Process-local observation 在 Host 进程重启后丢失的问题与本修复无关，风险等级不变。

## 综合裁决

**PASS。**

AGG-F01 修复完整、准确、无遗漏：
1. `build_fins_wait_activation_registry` 签名已从 `workspace_root: Path` 改为 `runtime: FinsObservationRuntime`，不再隐式创建 runtime。
2. `FinsIngestionWaitActivationAdapter.from_workspace_root` 已删除，无 dead code。
3. production path 通过 fail-fast 确保共享 runtime，并调用统一 builder。
4. tests 覆盖 runtime identity 三重断言，断言未弱化。
5. README 更新准确，无 gate 文本泄漏。
6. 验证命令独立复现通过，数量一致。
