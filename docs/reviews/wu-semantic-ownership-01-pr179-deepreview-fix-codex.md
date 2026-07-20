# WU-SEMANTIC-OWNERSHIP-01 PR179 deepreview accepted-finding fix — AgentCodex

## Gate 与范围

- Work unit：`WU-SEMANTIC-OWNERSHIP-01`既有 umbrella WU。
- Gate：Draft PR 179 deepreview accepted finding fix。
- Finding：仅 `PR179-DR-F01`。
- Controller 裁决：`docs/reviews/wu-semantic-ownership-01-pr179-deepreview-controller-adjudication.md`，实施前 SHA-256 `1bf581def05e4e4fd080d62ab4bd4cf1826c56cbd7e5a6ca021299dc0371b3b9`。
- 两路 review 证据：
  - `docs/reviews/wu-semantic-ownership-01-pr179-deepreview-ds.md`，SHA-256 `e7953063af1e32155df62c469e330d7371d5a70606f9d5b18946db0a5d7c1a8e`。
  - `docs/reviews/wu-semantic-ownership-01-pr179-deepreview-mimo.md`，SHA-256 `6e03d5a32f48facf4d0988d49d0c82f2219a64a6e37c8b39888bb0a3f744a085`。
- 本 gate 不创建新 WU / sub-WU / feature / issue，不修改 Controller adjudication 或 `docs/host/issues-implementation-control.md`，不 stage / commit / push。

## 第一性原理与 root cause

Finding 成立，严重度 `Medium`的评估准确。当前 production 构造点都向非 `ALLOW` 决策提供了 message，因此不是已观测的用户事故；但 `ToolRuntimePolicyPort` 返回的 `ToolPolicyDecision.message` 类型允许 `None`，端口或未来调用点可以产生 malformed 非 `ALLOW` 决策。

修复前直接证据：

1. `_governed_failure_outcome()` 使用 `policy_decision.message or _TOOL_RUNTIME_GOVERNED_ERROR`。
2. `_TOOL_RUNTIME_GOVERNED_ERROR` 的值为 Host 内部码 `host_tool_governed_error`。
3. 该 helper 是 governed `ToolFailedOutcome.message` 的直接产生者，outcome 会先进入 accept candidate / Engine 返回路径，再可被 Tool Trace、accepted-result projection、Memory、RunInput 和 Compact Material 消费。
4. 既有 `_validate_policy_decision_fields()` 只在 accept-governance 构造边界被调用；它能阻止 malformed candidate 持久化，但不能追溯保证更早的 outcome 生成边界安全。

Root cause 是 governed-failure projection owner 未在产生 LLM-readable message 前强制复用 policy-decision 字段组合不变量，而是用 Host 内部码填充缺失的业务 message。这是 owner 边界缺口，不是下游 renderer / Tool Trace / Memory 的过滤问题。

## 语义 owner

- Policy-decision 字段组合不变量 owner：`dayu.host.tool_runtime._validate_policy_decision_fields()`。
- Governed failure outcome 投影 owner：`dayu.host.tool_runtime._governed_failure_outcome()`。
- Accept / audit 构造防线：`ToolAcceptGovernance.__post_init__()` 通过同一 `_validate_policy_decision_fields()` 校验。
- Tool Trace、accepted-result projection、Memory、RunInput、Compact Material 是下游消费者，本 fix 未向它们增加 normalization、fallback、字段黑名单或内部码过滤。

## 实施

### Production

`dayu/host/tool_runtime.py`：

- 删除不再有合法引用的 `_TOOL_RUNTIME_GOVERNED_ERROR`。
- `_governed_failure_outcome()` 在构造 outcome 前调用既有 `_validate_policy_decision_fields()`：
  - 非 `ALLOW` 决策必须同时携带非空 reason code 和非空白业务可读 message。
  - `message=None`、空字符串和纯空白 message 均在 outcome 生成前 `ValueError` fail closed。
  - `ALLOW` 不得进入 governed-failure projection。
  - `REUSE` 同样不是 failure decision，不得被误投影为 failure；这与既有 governed-error accept candidate 校验一致。
- outcome message 只使用通过校验的 `policy_decision.message`；reason code 仍留在 governance / digest / audit / diagnostic 语义中，不替代业务 message。
- 所有合法 governed decision 的 error code、message、hint 和 accept 行为保持不变。

### Tests

`tests/host/test_toolruntime_executor.py`：

- 参数化对抗测试覆盖 `message=None`、`message=""`、纯空白 message。
- 每个 malformed decision 同时在 governed outcome owner 和 `ToolAcceptGovernance` accept/audit 构造边界失败，不产生 outcome 或可持久 candidate。
- 对抗测试覆盖 `ALLOW` 误入，并额外锁定 `REUSE` 不被降格为 failure。
- 合法 governed decision 测试确认序列化 outcome 只保留业务可读 message，不包含内部 reason code 或已删除 fallback 码。

## Source / propagation proof

1. `rg -n "host_tool_governed_error|_TOOL_RUNTIME_GOVERNED_ERROR" dayu -g '*.py'`：零命中。
2. `rg -n "policy_decision\\.message\\s+or|message\\s*=\\s*policy_decision\\.reason_code|message\\s*=\\s*decision\\.reason_code" dayu/host -g '*.py'`：零命中。
3. 调用链 scan 确认 `_governed_failure_outcome()` 是 ToolRuntime governed outcome 单一构造边界，且当前所有 production 调用点都传入合法业务 message。
4. `_governed_failure_outcome()` 先校验后构造；malformed decision 因此没有 outcome 可供 `accepted_tool_outcome_json()` 序列化。
5. 即使有调用者绕过 outcome helper 直接构造 accept governance，`ToolAcceptGovernance.__post_init__()` 仍复用同一 invariant 拒绝 malformed decision；因此不会产生 accept candidate、EventLog audit fact 或 Tool Trace 输入。
6. Tool Trace、Memory、RunInput 和 Compact Material 只消费 accepted-result projection / typed LLM material；无 outcome 且无 accepted fact 时没有可投影的 LLM material。合法 projection 的四消费者回归测试通过。

## 验证

### Focused / owner tests

- `pytest -q tests/host/test_toolruntime_executor.py -k 'governed_failure_projection'`
  - `6 passed, 62 deselected`。
- ToolRuntime owner aggregate：
  - `pytest -q tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_diagnostics.py tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_effective_bundle.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py`
  - `179 passed`。
- Accepted-result / Tool Trace / Memory / RunInput / Compact Material projection：
  - `pytest -q tests/host/test_accepted_result_projection.py`
  - `34 passed`。
- Phase 6 ToolRuntime integration：
  - `pytest -q tests/host/test_phase6_toolruntime_integration.py`
  - `3 passed`。

### Coverage

- 聚合 coverage 命令：上述六个 ToolRuntime owner test files，带 `-k 'not process' --cov=dayu.host.tool_runtime --cov-report=term --cov-fail-under=80`。
- 结果：`162 passed, 17 deselected`；`dayu/host/tool_runtime.py` `1993 statements / 299 missed / 85%`，达到单文件 `>=80%` 目标。
- 六文件无 coverage 注入的完整 `179 passed` 已包含这 17 个 process 节点。
- 说明：先行尝试对单一 executor test file 启用 `pytest-cov`时，macOS `spawn` 的 15 个 process-backed node 因 coverage 注入导致 multiprocessing function identity `PicklingError`，并且该单文件仅达 `69.59%`。该验证工具组合已被“无 coverage 的全 process 回归 + 排除 process 节点的聚合 owner coverage”取代，不归类为 product failure。

### Type / lint / diff

- Targeted pyright：`python -m pyright dayu/host/tool_runtime.py tests/host/test_toolruntime_executor.py`：`0 errors, 0 warnings, 0 informations`。
- Full pyright：`python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- Ruff：`python -m ruff check dayu/host/tool_runtime.py tests/host/test_toolruntime_executor.py`：`All checks passed!`。
- `git diff --check`：PASS，零输出。
- Staged tree：空；本 gate 未 stage / commit。

## README decision

已先读取：

- `dayu/host/README.md` 的 `Agent更新约束【必须遵守】` 及 ToolRuntime / accept barrier 现有说明。
- `tests/README.md` 的文档职责、Host / ToolRuntime 测试分层说明。

决定：不修改 README。本 fix 只加固既有“ToolRuntime 在 Host accept barrier 前 fail closed”的内部 invariant，不改变公共契约、架构边界、状态机、安装 / CLI / Web / WeChat 工作流或测试分层；把单个 review finding 过程写入开发手册也违反 README 自身写作边界。

## 安全、non-goals 与边界

- 未实现统一 tool authorization framework、permission schema / DSL、role / capability 或 sandbox。
- 未新增下游 normalization / fallback / blacklist / loose parsing。
- 未修改 Web private/custom port 默认 allow、DNS / peer policy 或 resource budget。
- 未修改 Issue 142 / 151 / 175 / 177 / 178 或 WeChat / Web / render tracker 能力。
- 未修改 schema、EventLog 格式、Tool Trace 格式、LLM prompt / tool schema 或 accepted-result projection。
- reason code 仍可作为 Host internal governance / digest / audit / diagnostic 事实；它只是不再被当作 LLM-readable message。
- 工作区中 Controller 的 tracked control doc 和 Controller / 两 reviewer 的 untracked artifacts 均原样保留，本 gate 没有覆盖、删除、stash、reset 或 stage。

## Exact changed paths 与 identity

1. `dayu/host/tool_runtime.py`
   - final file SHA-256 `f376dfe547f5f72c314fe018b28f49b5bdf504476b72484602eed3ba04ec28ea`
2. `tests/host/test_toolruntime_executor.py`
   - final file SHA-256 `d73a69e900baaf619004c061f18c62288783026ea8258fb699ab9370cc80c8b3`
3. `docs/reviews/wu-semantic-ownership-01-pr179-deepreview-fix-codex.md`
   - 本 artifact；最终 hash 由完成报告给出。

Production + test binary diff SHA-256：`810bfb9cc01728cc98725177b613b29cc6483be22f5d833a1fcbf627d8aab6ba`。

## Finding disposition 与 remaining risk

- `PR179-DR-F01`：**已修复，待 Controller 验证与两路完整 PR re-review**。
- 当前 production 合法 decision 构造点行为不变；新的可观测风险只是未来或自定义 policy port 若返回 malformed decision，ToolRuntime 会以 `ValueError` 终止当前调用，而不是生成伪造可读结果；这是本 finding 要求的有意 fail-closed contract。
- 无未分类 residual risk，无新 blocker，无需新 issue / WU / sub-WU。
- Correct next gate：Controller 独立验证，然后 AgentMiMo / AgentDS 对完整 PR diff 并发 re-review；本 artifact 不授权 merge、mark ready、commit、push 或 final closeout。
