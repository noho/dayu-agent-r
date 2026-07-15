# WU-SEMANTIC-OWNERSHIP-01 R04 plan-entry Controller validation

## 1. Gate identity

- active work unit：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01`。
- internal remediation sub-WU：R04 Awaiting provider resolution config 与 Host composition。
- plan artifact：`docs/host/wu-semantic-ownership-01-r04-awaiting-provider-resolution-composition-plan.md`。
- accepted code baseline：`f7006a80`；`dc565d8c` 仅为 R03 completion / R04 transition 文档提交。
- 本记录只裁定是否进入双路 plan review，不接受计划、不授权 implementation。

## 2. Motivation and owner validation

动机成立。当前代码仍同时存在以下直接证据：

1. `tool_discovery.json` 的三个 Fins awaiting provider 尚无显式 `awaiting_resolution_mode`；
2. `dayu/service/host_assembly.py::with_entrypoint_wait_poller_policy` 仍以 scene-selected tool 构造无参 `WaitPollerRuntimePolicy()`；
3. `dayu/service/entrypoint_runtime.py` 仍调用该 scene-derived helper；
4. `dayu/config/host_runtime.json` 尚无完整 `wait_poller_policy` snapshot；
5. `dayu/host/wait_adapter.py` 仍拥有部署数值 defaults，以及 `WaitPoller` / `WaitPollerSupervisor` 的 `None -> WaitPollerRuntimePolicy()` fallback。

这些证据与 Controller discussion、`docs/host/design.md` 和 umbrella plan §11 直接一致：provider config 拥有恢复 mode，`host_runtime.json` 拥有 Host deployment policy，Service 只组合 typed inputs，scene 不拥有后台 runtime authority。

## 3. Plan completeness validation

Controller 已完整读取 204 行计划并确认：

- 固定 slug、base、目标、成功条件、非目标和 stop condition 自足；
- `poll|callback|manual`、完整 12 字段 required policy、Service composition 和 Host execution owner 唯一；
- R05 timeout/LOST 状态机、Engine handshake、Issue 175、callback transport、统一 authorization、permission DSL、Issue 142/151/177/178 和 R05-R12 均未进入实现范围；
- 三个 slices 按 provider mode -> runtime policy -> composition 的依赖顺序切分，未超过 umbrella 上限；
- composition matrix 覆盖 no-provider、manual、poll enabled/disabled、missing registry、callback missing transport、disabled provider、非法 mode 和 scene-independence；
- tests、逐文件 `>=80%` coverage、全量 pyright、README trigger、source/propagation/security scans、真实 assembly smoke 与 handoff 均有明确 gate；
- 变更前等价验证基线为 `325 passed, 3 warnings`。多 dotted-module coverage 会触发仓库既有 NumPy double-load 工具限制，计划改用单一 `--cov=dayu` session 并从 JSON 逐文件读取覆盖率；该替换已直接运行通过。

## 4. Allowlist adjudication for review

umbrella §7.4 的 R04 顶层 manifest 漏列 `dayu/host/wait_adapter.py`，但 umbrella §7.5 R04-S2 与 §11.3 明确要求删除该文件中的 policy defaults、无参构造和 fallback。当前代码也证明这些错误语义由该文件直接拥有。

因此，按 umbrella §7.3 的 current-evidence refinement 规则，Controller 接受把 `dayu/host/wait_adapter.py` 作为 R04-S2 的窄化 owner 文件交给 plan review 挑战。该裁定不扩展到 `dayu/host/api.py`、`dayu/host/open_host.py`、Engine、callback endpoint、授权框架或 R05 状态机；若实施证据要求修改这些边界，必须停止并返回 Controller。

## 5. Verdict

`PASS / READY_FOR_DUAL_PLAN_REVIEW`

计划尚未 accepted，implementation 尚未授权。下一 gate 是 AgentMiMo / AgentDS 对同一 immutable plan target 做并发完整 plan review。
