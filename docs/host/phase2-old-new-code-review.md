# Host P2 OLD / NEW 代码对比 Review

## 审查结论

OLD / NEW code review 通过。当前 P2 实现没有把 OLD `fetch_more` schema、`fetch_more_args`、`project_for_llm` 半协议迁回 Engine，而是把 schema-driven truncate、cursor lifecycle、scope token、TTL、single-use、limit clamp 与 page structure 收束到 Host 内部 `ToolRuntime`，方向符合 `docs/host/phase2-plan.md` 与上一轮 `docs/host/phase2-old-new-review.md`。

本次未发现阻塞 P2 合入的 OLD / NEW 语义缺口。但有 2 个建议在 P2 内收紧：一个是补读失败事实应避免写入调用方伪造的 run/session；另一个是 binary bytes 改为 base64 `JsonValue` 后需要在 README 或契约说明中明确这是 NEW 的 JSON 安全化差异。

## Findings

### P2-已修复：`fetch_more` 在完成 cursor 绑定校验前写入 requested / failed 事实，可能把事实写到错误 Run

修复状态：已修复。NEW `fetch_more` 已调整为先读取可信 cursor record，再按 record owner run 做 terminal /
binding / token / TTL 校验并决定事实归属。cursor 不存在时不写请求 run fact；cursor 存在但 binding
mismatch 时，拒绝与失败事实写入 owner run，错误 run 不会被创建或污染。

**OLD 直接证据**

- OLD `execute_fetch_more` 先从 `arguments.cursor` 找内部 cursor record，随后校验 TTL、run scope、scope token；失败时直接返回 typed error，不会产生跨 run 审计事实：`/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py:160-182`。
- OLD run scope 校验只接受同一 run，跨 run 返回 `cursor_scope_mismatch`：`/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py:732-753`。

**NEW 代码证据**

- NEW `fetch_more` 先用 `request.run_id` 做 terminal 检查，然后立即 `_append_fetch_requested(request)`，再用 `request.cursor.value` 找 record 并校验 binding：`dayu/host/_tool_runtime.py:342-377`。
- `_append_fetch_requested`、`_fetch_failure` 都使用 `request.run_id` / `request.session_id` 写 RunEvent：`dayu/host/_tool_runtime.py:820-842`、`dayu/host/_tool_runtime.py:993-1010`。
- 现有测试覆盖跨 session / run / tool_call 被拒绝，但只断言 result error，没有断言错误 Run 不被污染：`tests/host/test_phase2_tool_runtime_boundary.py:232-260`。

**影响**

如果调用方持有 run A 的 handle，却构造 `ToolFetchMoreRequest(run_id="run_B", cursor=run_A_cursor, ...)`，NEW 会在 run B 写入 `tool_fetch_more_requested` 和 `tool_fetch_more_failed`，然后才发现 cursor run mismatch。P2 比 OLD 安全收紧了 session / run / original tool_call 绑定，但当前事件写入顺序会让 canonical RunEvent 与真实 cursor owner 不同源，削弱 Host 事实层可信度。

这不是阻塞，因为 cursor 原文和 scope token 仍只来自受控 handle，且真正补读会被拒绝；但这是 P2 自身承诺的治理事实边界，建议在本阶段修掉。

**建议**

先按 cursor 原文查 record，并完成 TTL、session / run / original tool_call、fingerprint、scope token 校验，再追加 `tool_fetch_more_requested`。若需要记录拒绝事实：

- cursor 不存在时只能写入请求 run 的 `tool_fetch_more_failed`，因为没有 owner record。
- cursor 存在但 binding mismatch 时，优先不要写入请求 run；可以写入 owner run 的 `tool_cursor_denied` / `tool_fetch_more_failed`，或只返回 typed failure 并把跨 run 审计留给 P6 observer。
- 补测试：伪造 run_id / session_id / tool_call_id 时，原 run 和伪造 run 的 RunEvent 行为必须明确且不互相污染。

### P3-已修复：binary bytes 改为 base64 字符串是可接受差异，但需要契约/文档显式说明

修复状态：已修复。已在 `dayu/contracts/tool_schema.py` 与 `dayu/host/README.md` 明确
`binary_bytes` 的截断与补读 public `JsonValue` 返回 base64 ASCII 字符串，`unit="bytes"` /
`value_summary` 表示原始字节大小，且不是 OLD LLM projection 的 `content_base64` 包装结构。

**OLD 直接证据**

- OLD `binary_bytes` 截断直接返回 bytes chunk，并在续读时继续返回 bytes chunk：`/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py:480-494`、`/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py:719-721`。
- OLD LLM projection 对 bytes 另行编码为 `{"content_base64": ..., "content_encoding": "base64"}`：`/Users/leo/workspace/dayu-agent/dayu/engine/tool_result.py:229-263`。

**NEW 代码证据**

- NEW `binary_bytes` 截断直接把 chunk 编码成 base64 字符串，续读也返回 base64 字符串：`dayu/host/_tool_runtime.py:1268-1302`、`dayu/host/_tool_runtime.py:1324-1326`。
- NEW public result `ToolFetchMoreSucceededResult.value` 是 `JsonValue`，因此不能返回 bytes：`dayu/host/contracts.py:643-660`。
- 测试已覆盖直接 bytes 截断返回 `"YWI="`：`tests/host/test_phase2_tool_runtime_truncation.py:260-275`。

**影响**

这个选择比 OLD 更适合 Host public contract，因为 `JsonValue` 不能承载 bytes，也避免 Engine projection 再做二次转换。但它是行为差异：调用方看到的是裸 base64 string，而不是 OLD projection 的 `content_base64` 对象，也不是 OLD 内部工具结果里的 bytes。

**建议**

保留该实现，但在 `dayu/host/README.md` 或 `dayu/contracts/tool_schema.py` 的契约说明里写清：P2 Host ToolRuntime 的 `binary_bytes` 返回 base64 ASCII 字符串，`unit="bytes"` / `value_summary` 表示原始字节大小；这不是 OLD LLM projection 的 `content_base64` 包装结构。现有测试可再补一条 fetch_more binary bytes 下一页仍返回 base64 string。

## OLD 语义继承矩阵

### 已继承

- schema-driven truncate：NEW 只有存在显式 `ToolTruncateSpec`、启用、策略合法、limit 为正时才截断；对应 OLD `apply_truncation` 的 spec 驱动入口。
- 四类基础策略：NEW 已覆盖 `text_chars`、`text_lines`、`list_items`、`binary_bytes`。
- execute-time cursor：NEW 在底层工具执行成功后立即截断、创建 cursor、写 `tool_result_truncated` / `tool_cursor_issued`，不是等到 fetch_more 时补登记。
- cursor lifecycle：NEW cursor 内部保存，EventLog 只暴露 fingerprint；旧 cursor 成功续读后删除，有剩余时签发下一页新 cursor。
- scope hash / scope token：NEW `scope_hash` 来自工具名和参数；`scope_token` 绑定 cursor、scope_hash、session、run、原始 tool_call 与创建时间。
- TTL 与 opportunistic cleanup：NEW 过期访问会删除 cursor，创建新 cursor 前也会清理过期记录。
- limit clamp：NEW requested limit 为正时 `min(requested, record.limit)`，否则使用原 limit。
- page structure：NEW 对直接值返回下一段；对显式 wrapper field/path 返回保留模板结构的下一段。
- 更强绑定：NEW 比 OLD 多校验 session 与原始 tool_call，且当前测试明确不同 session / run / original tool_call 被拒绝。
- EventLog 安全：NEW 不把 cursor 原文和 scope token 写入 RunEvent，handle 通过非 EventLog public 契约交付。

### 合理后移

- OLD LLM-facing `fetch_more` schema 自动注册：P2 明确不恢复。
- OLD `project_for_llm` 投影 `next_action` / `fetch_more_args`：P2 明确不恢复，测试确认 Engine projection 不泄漏 token。
- 完整 ToolRegistry、工具发现、schema 版本、middleware、display info：P2 非目标。
- 多进程 / Remote cursor store、lease、recovery、fencing：P2 非目标。
- P6 observer、timeline projection、audit observer、P7 lifecycle governance：P2 非目标。
- OLD dict longest text / largest nested list 启发式：NEW 选择严格显式 target，合理收窄。

### 禁止迁回 Engine

- 不应在 `dayu.engine` 增加 `TruncationManager`、cursor store、TTL 管理或内置 `fetch_more` 工具。
- 不应让 Engine 感知 Host ToolRuntime、cursor store、scope token 或 RunEventStore。
- 不应把 `scope_token`、cursor 原文、`fetch_more_args` 投影到 Engine message / LLM-facing schema。
- 不应为了兼容 OLD 导入路径增加 facade / wrapper / re-export。
- 不应把财报业务语义、文档存取或 `dayu.fins.storage` 规则放进 Host ToolRuntime。

## 其它观察

- `ToolRuntimeCursor.value` 作为受控 handle 的一部分可接受；它没有进入 RunEvent，也未从 `dayu.host.__all__` 暴露内部 runtime 实现。
- `ToolTruncateSpec` 放在 `dayu.contracts.tool_schema` 可接受，因为它是跨 Engine executor request 与 Host runtime 的公共契约；当前没有放进 `dayu.runtime`，符合分层约束。
- `ToolResultSuccess.truncation.scope_token=""` 是刻意不向 Engine projection 泄漏 token；配合 `get_tool_fetch_more_handle(...)` 闭合了 P2 初始 token 交付通道。

## 验证命令

本次是 OLD / NEW code review 文档产出，只阅读 diff、OLD 代码和测试，未运行 pytest / pyright。

已执行的审查命令包括：

```bash
git status --short
git diff --stat
git diff --name-only
sed -n '1,240p' docs/host/phase2-plan.md
sed -n '1,260p' docs/host/phase2-old-new-review.md
sed -n '1,860p' /Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py
rg -n "fetch_more|scope_token|ToolTruncateSpec|single-use|single use|cursor_expired|cursor_scope_mismatch|project_for_llm" /Users/leo/workspace/dayu-agent/dayu /Users/leo/workspace/dayu-agent/tests
git diff -- dayu/host/contracts.py dayu/contracts/tool_schema.py dayu/host/_run_harness.py dayu/host/__init__.py dayu/contracts/__init__.py
sed -n '1,1515p' dayu/host/_tool_runtime.py
sed -n '1,620p' tests/host/test_phase2_tool_runtime_truncation.py
sed -n '1,560p' tests/host/test_phase2_tool_runtime_boundary.py
sed -n '1,320p' tests/host/test_phase2_tool_runtime_eventlog.py
```

## 复审结论

OLD / NEW code review 复审通过。当前 diff 仍符合 P2 OLD / NEW gate，未发现需要阻塞合入的语义缺口。

本轮重点复核结论：

- schema-driven truncate、cursor lifecycle、scope token、TTL、single-use、limit clamp、page structure 仍由 Host-owned
  `ToolRuntime` 承担，未迁回 Engine，也未恢复 OLD LLM-facing `fetch_more` schema / `fetch_more_args` 半协议。
- `fetch_more` 已先按 cursor 原文找到可信 owner record，再以 owner run 做 terminal / binding / token / TTL 校验；跨 run /
  跨 session / 跨 tool_call 拒绝事实写入 owner run，不再污染请求伪造的 run。
- handle 阶段 denied / expired facts 写入 cursor owner RunEvent；terminal run 后 handle / fetch_more 返回 typed failure 且不追加新
  RunEvent，符合 NEW EventLog truth 与 OLD cursor 生命周期可靠语义。
- `binary_bytes` 返回 base64 ASCII `JsonValue` 字符串的 NEW 差异已有契约说明、Host README 说明与直接截断 / fetch_more 测试覆盖；
  这是 public JSON 安全化差异，可接受。
- 完整 ToolRegistry、远程 / 多进程 cursor store、lease / recovery / fencing、P6 observer / audit / timeline projection、P7 lifecycle
  governance 仍属于后续治理范围，不构成本轮 P2 blocker。

## 复审状态

通过。无需追加阻塞 findings。

复审补充验证命令：

```bash
rg -n "fetch_more_args|next_action|scope_token|fetch_more" dayu/engine dayu/host dayu/contracts tests/engine tests/host
nl -ba dayu/host/_tool_runtime.py | sed -n '260,430p'
nl -ba tests/host/test_phase2_tool_runtime_boundary.py | sed -n '180,310p'
nl -ba tests/host/test_phase2_tool_runtime_truncation.py | sed -n '230,360p'
source .venv/bin/activate && pytest tests/host/test_phase2_tool_runtime_truncation.py tests/host/test_phase2_tool_runtime_eventlog.py tests/host/test_phase2_tool_runtime_boundary.py -q
source .venv/bin/activate && pyright
```
