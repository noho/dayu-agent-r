# Host P5 Code Review

## 结论

通过本轮 P5 review，未发现 P0/P1/P2 阻断 finding。

当前 uncommitted P5 实现与目标语义基本一致：主 happy path 是模型在同一 run 内先调用 `huge_echo`，Engine 注入带 `truncation.next_action="fetch_more"` 与 `fetch_more_args` 的 ToolMessage，随后模型再通过普通 tool call 调用 framework `fetch_more`；Host `ToolRuntime` 识别 framework 工具名并路由补读，不把 cursor/token 治理下沉给 Engine，也不走业务 executor。

## Findings

无阻断 finding。

## 重点核查

### success path actor

- `dayu/engine/agent.py:1035-1125` 仍由 Engine tool loop 从 Runner tool call 产出 `TOOL_CALL_REQUESTED`，再调用 `ToolExecutor.execute`，然后产出 `TOOL_RESULT_ACCEPTED`。
- `dayu/engine/agent.py:1157-1196` 只把工具结果作为 ToolMessage 注入下一轮 Runner 输入，没有在 Engine 内解释 cursor 或 scope token。
- `dayu/host/_tool_runtime.py:233-236` 只在工具名为 framework `fetch_more` 时走 Host runtime 补读；普通业务工具仍先走业务 executor。
- `dayu/host/_tool_runtime.py:289-338` 的 framework `fetch_more` 路径调用 `fetch_more(parsed)`，没有调用业务 executor。

### 是否能抓住“模型未发 fetch_more，脚本代补读”

测试能抓住这个错误实现：

- `tests/host/test_phase5_multiturn_no_governance_smoke.py:443-452` 要求 EventLog 中存在 framework `fetch_more` 的 `TOOL_CALL_REQUESTED`，且该事件参数已 redacted。
- `tests/host/test_phase5_multiturn_no_governance_smoke.py:455-459` 要求 `ToolExecutionProbe.tool_names == ["huge_echo", "fetch_more"]`，该 probe 只包在 Engine 调用的 `ToolExecutor` 外层；如果脚本直接用 `harness.fetch_more_tool_result()` 代补读，不会出现 `fetch_more` probe 记录。
- `utils/smoke_host_multiturn_no_governance.py:1163-1169` 的 smoke success 条件同样要求 `probe.tool_names` 同时包含 `huge_echo` 和 framework `fetch_more`。单纯由 public harness 补读追加 completed fact 不能让 smoke 成功。

### cursor / scope token 边界

- `dayu/engine/agent.py:272-296` 只在 LLM-facing ToolMessage projection 中生成 `truncation.fetch_more_args`。
- `dayu/host/_event_translation.py:101-104` 在 EngineEvent 写入 Host RunEvent 前做 redaction。
- `dayu/host/_event_translation.py:117-139` 对 framework `fetch_more` 的 RunEvent 参数只保留非敏感 `limit`。
- `dayu/host/_event_translation.py:142-169` 从 `TOOL_RESULT_ACCEPTED` 的 outcome 中移除仅供 LLM roundtrip 的 truncation 凭证。
- `tests/host/test_phase5_multiturn_no_governance_smoke.py:443-452` 覆盖 EventLog repr 和 framework request repr 不含 `scope_token`。
- `dayu/host/_conversation_memory.py:681-831` memory projection 只从 canonical RunEvent 生成摘要；由于 RunEvent 已 redacted，cursor 原文和 scope token 不会进入 memory projection。

### ToolTruncateSpec 多策略

- `dayu/host/_tool_runtime.py:590-625` 仍按 `ToolTruncateSpec.strategy` 处理 `text_chars`、`text_lines`、`list_items`、`binary_bytes`，没有退化成 `huge_echo` 专用逻辑。
- `tests/host/test_phase2_tool_runtime_truncation.py:281-307` 覆盖非 `huge_echo` 的多策略截断。

### terminal 后 append

- `dayu/host/_tool_runtime.py:481-491` terminal run 后 `fetch_more` 返回 typed failure，不追加 RunEvent。
- `tests/host/test_phase5_multiturn_no_governance_smoke.py:402-465` 覆盖 terminal 后 public `fetch_more_tool_result()` 负例不追加 EventLog。

### AGENTS.md 合规性

- 新增/修改生产代码保持中文模块、类、函数 docstring，目标 pyright 通过。
- 未发现新增 `Any`、`object`、无类型参数或无类型返回值签名。
- framework `fetch_more` schema 内字面量属于 schema 例外；非 schema 的参数名和错误码已模块常量化。
- `dayu.runtime`、Engine/Host 分层边界未发现反向依赖扩散；Engine 未 import Host。
- README 触发项已覆盖 `dayu/engine/README.md`、`dayu/host/README.md`、`tests/README.md`、根 README；`dayu/config/README.md` 的变更是在澄清当前无公共配置 loader / adapter，未写未来设计。

## 剩余风险 / 测试缺口

- 未运行真实 provider smoke，因此 `mimo-v2.5-pro-plan` 在真实网络和真实 tool calling 下是否稳定按 prompt 先调 `huge_echo` 再调 framework `fetch_more`，仍需人工验证。
- 未跑全量测试、全量 coverage；本次只跑了 review 范围相关局部测试和目标文件 pyright。
- 现有 P2 public handle / public `fetch_more_tool_result()` 能力仍保留；P5 测试已确认 success path 不靠它，但后续如果要把 public 补读完全降级为 terminal 后诊断能力，需要单独收敛 API 语义。
- 当前没有专门的“恶意变体”测试去显式模拟脚本先 public 补读再 final；不过现有 success path 断言已经要求 framework `TOOL_CALL_REQUESTED` 与 Engine `ToolExecutor` probe 同时出现，能覆盖该类错误的主要可观察结果。

## 验证命令

已运行：

```bash
git status --short
git diff -- dayu/contracts/tool_declaration.py dayu/contracts/tool_result.py dayu/contracts/__init__.py dayu/engine/agent.py dayu/host/_tool_runtime.py dayu/host/_event_translation.py dayu/host/_run_harness.py utils/smoke_host_multiturn_no_governance.py tests/contracts/test_tool_declaration.py tests/contracts/test_package_exports.py tests/engine/test_agent_phase3_tool_call.py tests/host/test_phase2_tool_runtime_boundary.py tests/host/test_phase2_tool_runtime_truncation.py tests/host/test_phase5_multiturn_no_governance_smoke.py README.md dayu/engine/README.md dayu/host/README.md tests/README.md
rg -n "ToolTruncationInfo\(" dayu tests utils
rg -n "fetch_more_tool_result|get_tool_fetch_more_handle|ToolFetchMoreRequest\(|ToolFetchMoreHandleRequest\(" utils/smoke_host_multiturn_no_governance.py tests/host/test_phase5_multiturn_no_governance_smoke.py dayu/host/_tool_runtime.py dayu/host/_run_harness.py
source .venv/bin/activate && pytest tests/contracts/test_tool_declaration.py tests/contracts/test_package_exports.py tests/engine/test_agent_phase3_tool_call.py tests/host/test_phase2_tool_runtime_boundary.py tests/host/test_phase2_tool_runtime_truncation.py tests/host/test_phase5_multiturn_no_governance_smoke.py -q
source .venv/bin/activate && pyright dayu/contracts/tool_declaration.py dayu/contracts/tool_result.py dayu/engine/agent.py dayu/host/_tool_runtime.py dayu/host/_event_translation.py dayu/host/_run_harness.py utils/smoke_host_multiturn_no_governance.py tests/contracts/test_tool_declaration.py tests/contracts/test_package_exports.py tests/engine/test_agent_phase3_tool_call.py tests/host/test_phase2_tool_runtime_boundary.py tests/host/test_phase2_tool_runtime_truncation.py tests/host/test_phase5_multiturn_no_governance_smoke.py
```

结果：

- review 范围局部测试：65 passed。
- 目标文件 pyright：0 errors, 0 warnings, 0 informations。

未运行：

```bash
source .venv/bin/activate && pytest -q
source .venv/bin/activate && pyright
python utils/smoke_host_multiturn_no_governance.py --case real-provider --log-level DEBUG
```

未运行原因：本次任务要求只做 code review；真实 provider 需要外部 API key / 网络 / provider 可用性，且用户明确不要求运行真实 provider。
