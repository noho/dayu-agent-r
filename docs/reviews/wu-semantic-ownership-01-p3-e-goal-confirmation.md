# WU-SEMANTIC-OWNERSHIP-01 P3-E Goal Confirmation

## Decision

P3-E 成立，应进入 plan gate。

本 sub WU 解决的不是展示层格式偏好，而是工具结果、Host accepted result 状态、wait callback provider 状态引用、Fins direct stream 终态这几类跨层协作事实的 owner boundary 漂移。当前代码仍存在直接证据，且这些事实会影响 Host/Engine/Service/Fins 之间的契约一致性。

## Goal

收束以下事实的真源与校验边界：

- `ToolResultSuccess.ok` 必须只能为 `True`，`ToolResultFailure.ok` 必须只能为 `False`。
- Fins direct stream 必须把缺失或重复 `RESULT` 作为协议错误处理，不能制造业务失败结果或静默丢弃重复终态。
- generic wait callback endpoint 不能把裸字符串 `provider_status_ref` 伪造成 `WaitProviderStatusRef(adapter_key="callback")`。
- accepted result projection 在需要结构化 accepted result status 时，不能从 raw outcome JSON 降级重建状态。
- 若后续实查发现 governance reason / diagnostic ref 被拼入 LLM-facing `hint`，应在 owner 边界分离；未发现时不得扩大 scope。

## Owner Boundary

- `dayu.contracts.tool_result` 拥有工具结果信封的判别字段不变量。
- Host accept barrier / accepted result projection 拥有 accepted result status 的 durable/typed 读取语义。
- Host wait adapter/callback typed contract 拥有 provider status ref 的结构化身份边界；Service callback mapper只能校验 transport shape 并映射到该 typed contract。
- Fins runtime direct stream protocol 拥有 direct event 的唯一 `RESULT` 终态契约；Service/CLI 只能消费或 fail closed，不能重建业务终态。

## Direct Evidence

- `dayu/contracts/tool_result.py:63` 到 `dayu/contracts/tool_result.py:74` 定义 `ToolResultSuccess.ok: Literal[True]`，但没有 `__post_init__` 运行时校验；错误运行时构造仍可绕过静态类型。
- `dayu/contracts/tool_result.py:77` 到 `dayu/contracts/tool_result.py:106` 只校验 failure 的 `error/message/hint`，未校验 `ok is False`。
- `dayu/service/wait_callback_endpoint.py:553` 到 `dayu/service/wait_callback_endpoint.py:558` 接受裸字符串 `provider_status_ref`，并在 generic callback endpoint 内构造 `WaitProviderStatusRef(adapter_key="callback")`。
- `dayu/host/accepted_result_projection.py:411` 到 `dayu/host/accepted_result_projection.py:460` 在缺少 typed status 字段时从 raw outcome 的 `kind` 或 `result.ok` 推断 accepted status。
- `dayu/fins/ingestion_runtime.py:2709` 到 `dayu/fins/ingestion_runtime.py:2717` 对重复 `RESULT` 执行 `continue`，并在未见 `RESULT` 时产出 `_direct_missing_result_event(...)`。
- `dayu/service/fins_direct.py:497` 到 `dayu/service/fins_direct.py:510` Service helper 对重复 `RESULT` fail closed，但对缺失 `RESULT` 制造 failure `RESULT`，与 accepted scope 中的 typed protocol error 目标不一致。

## Success Signals

- 相关契约构造时 fail closed，测试覆盖错误 `ok` 值、裸字符串 provider status ref、缺失/重复 Fins direct `RESULT`、accepted status raw outcome fallback 移除。
- 修复落在 owner boundary 或直接上游 transport 校验处；下游 read view、CLI 展示和测试夹具不重建这些事实。
- propagation audit 能说明工具结果、accepted result status、wait callback provider status ref、Fins direct terminal event 从产生、校验、持久化/投影到 LLM/user 可见输出的路径一致。
- `source .venv/bin/activate` 后受影响测试、pyright、`git diff --check` 通过，并按 README 触发规则完成检查。

## Non-goals

- 不重新设计 Host wait-resume 状态机。
- 不引入跨进程 Fins direct durable job ledger。
- 不修改 Fins 财报业务下载、预处理或上传语义。
- 不扩大到 P3-F 的 source document/blob/provenance/citation ownership。
- 不扩大到 P3-J 的 EventLog taxonomy 或全局 lifecycle hardening。

## Open Questions

无 blocking open question。进入 plan gate 时需要让 AgentCodex 实查 `hint` 是否仍承载治理 reason / diagnostic ref；若没有直接证据，该项应记录为 rejected/no-op，而不是强行改动。
