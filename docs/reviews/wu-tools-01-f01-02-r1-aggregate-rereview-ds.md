# WU-TOOLS-01-F01-02-R1 Aggregate Fix Narrow Re-Review (AgentDS)

## Scope

- Mode: narrow re-review（只复核 AGG-F01 修复）
- Branch: `phase/wu-tools-01-f01-02-r1`
- Output file: `docs/reviews/wu-tools-01-f01-02-r1-aggregate-rereview-ds.md`
- Ground truth:
  - Controller accepted AGG-F01（aggregate deepreview MiMo finding 01）:`build_fins_wait_activation_registry(workspace_root=...)` 隐式创建独立 runtime，activation adapter 无法可靠激活 callable 准备的 process-local observation。
  - Codex fix doc: `docs/reviews/wu-tools-01-f01-02-r1-aggregate-fix-codex.md`
- Included scope（仅 AGG-F01 修复涉及的文件）:
  - `dayu/fins/ingestion/wait_adapter.py` — builder 签名 + `from_workspace_root` 删除
  - `dayu/service/host_assembly.py` — production path 调用统一 + 死 helper 删除
  - `tests/fins/test_fins_ingestion_tools.py` — 测试更新 + runtime 共享断言
  - `tests/service/test_host_assembly.py` — Service wiring 断言补强
  - `dayu/fins/README.md` — builder 签名同步
- Excluded scope: AGG-F02（`created_at` 观察项，Controller 未接受）、poll adapter 运行时共享（预存条件，非本次 fix 范围）、已 deferred 的 #89/#90/#92。

## Verification

所有命令在 `source .venv/bin/activate` 后执行，结果复现通过：

| Command | Result |
|---|---|
| `pytest tests/fins/test_fins_ingestion_tools.py tests/service/test_host_assembly.py -q` | 103 passed, 3 warnings |
| `pytest tests/host/test_toolruntime_executor.py tests/host/test_phase7_waiting_integration.py tests/fins/test_fins_ingestion_runtime.py -q` | 108 passed, 3 warnings |
| `pyright` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | 无输出（clean） |

## 逐项验证

### 验证点 1: `build_fins_wait_activation_registry` 签名改为 `runtime` + `tool_names`

**入口**: `dayu/fins/ingestion/wait_adapter.py:209-235`

**证据**:
- 函数签名已改为 `*, runtime: FinsObservationRuntime, tool_names: Sequence[str]` (line 209-210)，原 `workspace_root: Path` 参数已删除。
- builder 内部只用 `_deterministic_tool_names(tool_names)` 做装配期校验 (line 226)，然后用 `FinsIngestionWaitActivationAdapter(runtime=runtime)` 直接构造 adapter (line 227)，不经过任何 `DefaultFinsRuntime.create` 或 `from_workspace_root` 路径。
- 代码内无 `workspace_root` 引用，无 `_require_absolute_workspace_root` 调用（该 helper 仍存在于模块内供 `build_fins_wait_adapter_registry` 使用，line 238）。

**结论: PASS** — builder 不再隐式创建独立 runtime，不再接收 `workspace_root`。

### 验证点 2: `FinsIngestionWaitActivationAdapter.from_workspace_root` 已删除，无死代码

**入口**: `dayu/fins/ingestion/wait_adapter.py:160-185`

**证据**:
- `FinsIngestionWaitActivationAdapter` 现在是纯 `@dataclass(frozen=True, slots=True)` (line 160-161)，只有 `runtime: FinsObservationRuntime` 字段 (line 168) 和 `activate_accepted_wait` 方法 (line 170)。
- 原 `from_workspace_root` classmethod 已完全删除，类定义中无任何残留。
- `grep -rn "from_workspace_root" dayu/fins/ingestion/wait_adapter.py` 仅命中 `FinsIngestionWaitPollAdapter.from_workspace_root` (line 108)，这是 poll adapter 的构造器，仍被 `build_fins_wait_adapter_registry` 合法使用，不是死代码。
- `DefaultFinsRuntime` import (line 40) 仍保留，仅被 `FinsIngestionWaitPollAdapter.from_workspace_root` (line 117) 使用，正确。
- 无兼容性 re-export、透传 wrapper 或旧签名别名。

**结论: PASS** — `from_workspace_root` 已彻底删除，无 dead helper 或 compatibility wrapper。

### 验证点 3: Production Service assembly 正确共享 runtime

**入口**: `dayu/service/host_assembly.py:1756-1789`

**证据**:
- `_fins_wait_activation_registry_from_provider_configs` 仍保留共享 runtime fail-fast:
  - `fins_awaiting_runtime is None` → `ValueError` (line 1780-1781)
  - `not isinstance(fins_awaiting_runtime, FinsIngestionRuntime)` → `ValueError` (line 1782-1783)
- 构造调用已统一为 `build_fins_wait_activation_registry(runtime=fins_awaiting_runtime, tool_names=registry_inputs.tool_names)` (line 1786-1789)，不再手写 `WaitActivationRegistry` registration。
- 注释 (line 1784-1785) 清晰记录共享 runtime 约束。
- 旧的手写 registration（原 line 1790-1799 附近）已删除。
- `FINS_INGESTION_WAIT_ADAPTER_KEY`、`FinsIngestionWaitActivationAdapter`、`WaitActivationAdapterRegistration` 从 `host_assembly.py` imports 中完全移除（`grep` 无命中），这些内部符号由 builder 自行管理。
- `_require_distinct_fins_awaiting_tool_names` helper 已从 `host_assembly.py` 删除（`grep` 全仓库仅命中旧 review docs，生产代码中无残留）。重复名校验由 `build_fins_wait_activation_registry` 内部的 `_deterministic_tool_names` 执行，功能未缺失。

**poll adapter 运行时共享观察**: `_fins_wait_adapter_registry_from_provider_configs` (line 1730-1753) 未被本次 fix 修改，仍通过 `build_fins_wait_adapter_registry(workspace_root=...)` 构造 poll adapter，后者调用 `FinsIngestionWaitPollAdapter.from_workspace_root(workspace_root)` 自建 runtime。这意味着 poll adapter 的 runtime 实例与 tool callable / activation adapter 不同。这是预存条件（fix 前即如此），不属于本次 fix 范围，且生产 poller loop 仍 deferred 到 #90。本次 fix 未改变 poll adapter 行为，不影响 callable / activation 共享语义。

**结论: PASS** — production path 正确共享 runtime，fail-fast 保留，手写 registration 和 `_require_distinct_fins_awaiting_tool_names` 已删除。行为未退化。

### 验证点 4: 测试覆盖 runtime 共享断言

**入口**: `tests/fins/test_fins_ingestion_tools.py:1485-1498`, `tests/service/test_host_assembly.py:808-857`

**证据**:
- `test_fins_wait_activation_registry_binds_fins_adapter_key` (line 1485):
  - 不再使用 `tmp_path` fixture，改用 `_FakeObservationRuntime(snapshots={})` 作为 shared runtime。
  - 调用 `build_fins_wait_activation_registry(runtime=runtime, tool_names=(...))` (line 1490-1493)。
  - 断言 `assert adapter.runtime is runtime` (line 1498) — 使用 `is`（identity），不是 `==`（equality）。
- `test_service_fins_awaiting_wiring_uses_shared_runtime_for_activation` (line 808):
  - 新增断言 `assert activation_adapter.runtime is discovered_tools.fins_awaiting_runtime` (line 843)。
  - 新增断言 `assert activation_adapter.runtime is callable_.runtime` (line 844)。
  - 两条均使用 `is` identity check，证明同一 Python 对象实例。
- 测试断言未弱化，反而比 fix 前更强（新增了两条 identity 断言）。

**结论: PASS** — 测试正确覆盖 runtime 共享，Service wiring 断言补强而非弱化。

### 验证点 5: README 更新准确，无 process/gate 文本泄漏

**入口**: `dayu/fins/README.md` diff

**证据**:
- builder 签名说明已从 `build_fins_wait_activation_registry(workspace_root=..., tool_names=...)` 更新为 `build_fins_wait_activation_registry(runtime=..., tool_names=...)` (line 167)。
- 新增共享 runtime 要求说明 (line 172): "awaiting tool callable 与 wait activation registry 例外：activation adapter 必须接收 awaiting tool callable 使用的同一个 `FinsIngestionRuntime` 实例，因为 prepared observation 是进程内 runtime 状态，不是可由 `workspace_root` 重新发现的持久事实。" — 准确、业务可读、属于稳定文档事实。
- DefaultFinsRuntime 共享语义段落 (line 674-675) 追加例外说明，句子以分号自然衔接，不破坏原有语义。
- 全文无 "WU-TOOLS-01-F01-02-R1"、"Slice"、"gateflow"、"controller"、"AgentMiMo"、"AgentDS"、"accepted commit" 等 process/gate 治理术语。

**结论: PASS** — README 准确同步，无泄漏。

### 验证点 6: 验证命令可信，复现通过

**执行记录**:
- `pytest tests/fins/test_fins_ingestion_tools.py tests/service/test_host_assembly.py -q` → **103 passed**
- `pytest tests/host/test_toolruntime_executor.py tests/host/test_phase7_waiting_integration.py tests/fins/test_fins_ingestion_runtime.py -q` → **108 passed**
- `pyright` → **0 errors, 0 warnings, 0 informations**
- `git diff --check` → **无输出（clean）**

所有命令均在 `source .venv/bin/activate` 后执行，输出与 Codex fix doc 记录一致。

**结论: PASS** — 验证命令可信，无虚假 claim。

## Findings

未发现实质性问题。

所有六个验证点均通过直接代码证据和复现命令验证。fix 精确命中 Controller 接受的 AGG-F01 finding，未引入新问题或退化。

## Open Questions

无。

## Residual Risk

- **Poll adapter 运行时未共享（预存条件，非本次 fix 引入）**: `build_fins_wait_adapter_registry` 仍通过 `FinsIngestionWaitPollAdapter.from_workspace_root(workspace_root)` 为每个 poll adapter 创建独立 runtime，与 tool callable / activation adapter 的共享 `fins_awaiting_runtime` 不是同一实例。`poll_observation(handle)` 内部通过 `self._observations.get(handle.handle_id)` 查找 observation，独立 runtime 的 `_observations` 字典不包含 callable 准备的 observation。生产 poller loop 仍 deferred 到 #90，该问题在 poller loop 实现前不触发实际故障，但应在 #90 中一并处理。建议后续 WU 将 `build_fins_wait_adapter_registry` 也改为接收共享 runtime，确保 poll / activation / callable 三者共用同一 runtime 实例。
- #89（callback endpoint/auth/replay）、#90（production poller loop）、#92（external job physical cancel）风险等级不因本次 fix 改变。

## 综合裁决

**Verdict: PASS**

AGG-F01 修复精确、干净、无副作用。`build_fins_wait_activation_registry` 签名合理收敛到共享 runtime；`from_workspace_root` 彻底删除无残留；production path 统一调用 builder；测试断言准确使用 identity check；README 同步无泄漏；全部验证命令复现通过。
