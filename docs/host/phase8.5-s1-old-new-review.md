# P8.5 Slice 1 OLD/NEW Review

- review gate name: additional code review
- reviewed target: OLD `/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py` vs NEW Slice 1 `RuntimeTruncateManager` / `HostToolRuntime` / framework tool boundary
- reviewer conclusion: fail
- artifact path: `docs/host/phase8.5-s1-old-new-review.md`

## Conclusion

fail

NEW 没有把 OLD 的 Engine 层位置、弱类型、兼容分支照搬过来，这是正确的。核心截断 / 补读可靠性机制大多已保留或加强：NEW 有 Host 私有 manager、async lock、run/session binding、TTL、single-use、limit clamp、`compare_digest` scope token、terminal guard 和 ordinary `ToolExecutionOutcome`。

但 OLD/NEW 对照支持既有 Slice 1 review 的一个阻塞 finding：NEW 的 durable owner scope guard 没有覆盖真实 `execute_tool_call()` 路径。OLD 没有 Host attempt fencing，所以这不是 OLD 必须照搬的问题；它是 P8.5 NEW design 引入 Host-owned governance 后未接住的执行边界问题。credential-only scrub 与 validation command 两个既有 findings 也仍成立，但它们不是 OLD TruncationManager 可靠性回退。

## Findings

### 01-未修复-[高]-durable owner scope guard 没有进入真实 ToolRuntime 执行路径

- **入口/函数**: `HostToolRuntime.execute_tool_call()`
- **文件(行号)**: `dayu/host/_tool_runtime.py:214`, `dayu/host/_tool_runtime.py:264`, `dayu/host/_tool_runtime.py:289`, `dayu/host/_tool_runtime.py:300`
- **输入场景**: durable runtime 在没有 `ToolRuntimeOwnerScope` 的上下文中执行业务工具截断或 framework `fetch_more`，例如 stale worker / 错误装配直接调用 `ToolRuntimeToolExecutor(runtime).execute(request)`。
- **实际分支**: `_resolve_appender()` 会在 durable + no scope 时抛错，但真实入口 `execute_tool_call()` 不调用它；framework 分支直接执行 `self._framework_tools.fetch_more_definition().executor.execute(request)`，业务分支直接调用底层 executor 并 `apply_truncation()`。
- **预期行为**: 按 NEW design `docs/host/design.md:1117-1119`，`fetch_more` 的 fencing 与补读实现属于 Host 私有实现；P8 durable attempt owner 语义应约束 runtime state mutation，避免 owner scope 外 issue / consume cursor。
- **实际行为**: owner scope guard 是死保护。测试只直接调用私有 `_resolve_appender()`，不能证明真实 `execute_tool_call()` 会拒绝 no-scope durable execution。
- **OLD 对照证据**: OLD `execute_fetch_more()` 只用 `RLock` 保护 cursor store（`/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py:160`），没有 Host attempt fencing；因此 OLD 不能反证该问题。NEW 引入 Host governance 后，应比 OLD 多一层 owner boundary。
- **直接证据**: `dayu/host/_tool_runtime.py:214-231` 定义 guard；`dayu/host/_tool_runtime.py:264-343` 真实执行路径无 guard 调用；既有 review artifact `docs/host/phase8.5-s1-code-review.md:32-44` 已指出同一问题。
- **影响**: durable cursor store 可在 owner scope 外被创建或消费，破坏 Host-owned governance truth；尤其 `fetch_more` single-use 消费是 manager state mutation，不能只靠 EventLog append fencing 兜住。
- **建议修复与验证点**: 在 `execute_tool_call()` 的 durable 路径建立真实 scope 校验，或由 controller 明确裁决 runtime execution 不需要 owner scope 并删除死 guard / 改测试。新增测试必须通过真实 `ToolRuntimeToolExecutor.execute()` 覆盖 durable + no scope 下业务截断和 `fetch_more` 都不会 mutation。
- **严重级别**: 高

### 02-未修复-[高]-credential-only scrub finding 仍成立，但不是 OLD/NEW truncation 机制回退

- **入口/函数**: `translate_engine_event()` / `serialize_run_event_data()` / `ToolTraceObserver._emit_tool_call()`
- **文件(行号)**: `dayu/host/_event_translation.py:91`, `dayu/host/_run_event_serializer.py:247`, `dayu/host/_run_event_serializer.py:256`, `dayu/host/_tool_trace_projection.py:262`
- **输入场景**: ordinary tool call arguments 或 accepted result payload 包含 `API_KEY` / explicit credentials，同时包含 cursor / `scope_token`。
- **实际分支**: NEW 删除了旧 cursor/scope redaction，但没有增加 credential-only scrub；普通 tool payload 被原样序列化和投影。
- **预期行为**: `docs/host/design.md:1186-1188` 与 `docs/host/phase8.5-plan.md:420-422` 要求 cursor / `scope_token` 保留，但 `API_KEY` / 明确凭证仍 scrub。
- **OLD 对照证据**: OLD TruncationManager 只构造/校验 cursor 与 scope token，不负责 EventLog / trace payload scrub；因此 OLD 不能作为反证。该 finding 来自 NEW design/plan 违约。
- **直接证据**: 既有 review artifact `docs/host/phase8.5-s1-code-review.md:18-30` 已列出代码路径；本次 OLD/NEW 复核未发现 NEW 对普通 tool payload 的 credential-only scrub 入口。
- **建议修复与验证点**: 增加 credential-only scrub helper，断言 `API_KEY` / explicit credential 被遮蔽，而 cursor / `scope_token` 保留；覆盖 EventLog serializer 与 trace JSONL。
- **严重级别**: 高

### 03-未修复-[中]-validation command 引用不存在文件，与 OLD/NEW 机制无关但仍阻塞 gate 可复现

- **入口/函数**: Slice 1 validation gate
- **文件(行号)**: `docs/host/phase8.5-plan.md:449`, `docs/host/phase8.5-s1-implementation-report.md:98`
- **输入场景**: controller / reviewer 按 plan 运行 `pytest tests/contracts/test_tool_declaration.py tests/contracts/test_tool_result.py tests/contracts/test_package_exports.py -q`。
- **实际分支**: `tests/contracts/test_tool_result.py` 不存在；仓库当前文件是 `tests/contracts/test_tool_result_envelope.py`。
- **预期行为**: validation 命令应可复制运行，不依赖 reviewer 手工替换路径。
- **OLD 对照证据**: 该问题不是 OLD/NEW truncation 机制差异，但既有 Slice 1 code review finding 仍未被反证。
- **直接证据**: 既有 review artifact `docs/host/phase8.5-s1-code-review.md:46-58`；implementation report 自身也在 `docs/host/phase8.5-s1-implementation-report.md:101` 记录该命令 collection 前失败。
- **建议修复与验证点**: 修正 plan/report 命令或补回对应测试文件；原命令必须不再 collection-fail。
- **严重级别**: 中

## OLD Mechanisms Retained

- **cursor store + lock**: OLD 用 `RLock` 包住 `execute_fetch_more()` 全流程（OLD:160）；NEW 用 `asyncio.Lock` 包住 `RuntimeTruncateManager.fetch_more()` 全流程（NEW:278），覆盖并发同 cursor single-use。
- **先查 record 再校验**: OLD 先 `get(cursor)`，不存在返回 `cursor_not_found`（OLD:164-166）；NEW 先解析参数，再 `get(parsed.cursor)`，不存在返回 `cursor_not_found`（NEW:278-287），随后才做 terminal / binding / TTL / scope token 校验。
- **TTL 与过期清理**: OLD 创建 cursor 时清理过期项并设置 `expires_at`（OLD:568-591），fetch 当前 cursor 时过期即删除（OLD:167-170）；NEW 创建 cursor 前 `_cleanup_expired()`（NEW:454,608-622），fetch 当前 cursor 过期即 `_remove_cursor()`（NEW:303-309）。
- **context binding**: OLD 只校验 `run_id`，允许同 run 跨 iteration（OLD:732-753）；NEW 同时校验 `session_id` 与 `run_id`（NEW:293-302,645-664），比 OLD 更强。
- **scope token**: OLD 用 SHA-256 token 并普通字符串比较（OLD:679-702,755-782）；NEW token 纳入 cursor / scope_hash / session_id / run_id / tool_call_id / created_at，并用 `hmac.compare_digest()`（NEW:559-566,667-684），比 OLD 更强。
- **limit clamp**: OLD `min(requested, record_limit)`（OLD:726-730）；NEW 等价 `_resolve_fetch_limit()`（NEW:1002-1013）。
- **single-use / next cursor**: OLD 成功补读后旧 cursor pop，有剩余则签发新 cursor（OLD:201-237）；NEW 成功补读后 `_remove_cursor(record.cursor)`，有剩余则先构造 next `ToolTruncationInfo`（NEW:323-342）。并发测试覆盖同 cursor 只有一次成功：`tests/host/test_phase2_tool_runtime_truncation.py:626-664`。
- **terminal guard**: OLD 没有 run terminal 检查；NEW 在 fetch_more 中通过 `terminal_checker.is_terminal(record.run_id)` 返回普通 failed outcome `run_terminal`（NEW:288-292），P5 smoke 覆盖 terminal 后不追加事件且返回 failed：`tests/host/test_phase5_multiturn_no_governance_smoke.py:625-628`。
- **LLM-facing next_action/fetch_more_args**: OLD 在 truncation dict 中直接写 `next_action` / `fetch_more_args`（OLD:646-658）；NEW 把 runtime contract 收敛为 `ToolTruncationInfo`，由 Engine LLM projection 生成 `next_action` / `fetch_more_args`（`dayu/engine/agent.py:273-297`）。这保留了模型可执行补读 hint，同时不让 Engine 持有 manager / cursor store。
- **memory / RunInput 不保留 raw capability**: NEW memory 摘要不写 raw cursor / raw scope token，只写 `truncated=true`、`has_more`、`limit`、`ttl_seconds`、`scope_hash`（`dayu/host/_conversation_memory.py:653-666`）；P5 smoke 断言下一轮 input 不含 `scope_token` / `fetch_more_args`（`tests/host/test_phase5_multiturn_no_governance_smoke.py:630-635`）。

## OLD Mechanisms Intentionally Not Copied

- **Engine 层 TruncationManager / ToolRegistry ownership**: OLD 位于 Engine ToolRegistry；NEW 按 P8.5 design 移到 Host 私有 `RuntimeTruncateManager`，Engine 只看 `ToolSchema` / `ToolExecutionRequest` / `ToolExecutionOutcome`。
- **OLD 弱类型 dict contract**: OLD `execute_fetch_more()` 返回 dict result；NEW 返回强类型 `ToolCompletedOutcome` / `ToolFailedOutcome`，符合当前 contracts。
- **历史兼容 scope token 缺失放行**: OLD `_validate_scope_token()` 对旧 cursor 缺 `scope_token` 放行（OLD:773-776）；NEW 要求 `scope_token` 必填（NEW:370-374），这是新 schema 起库下的正确收紧。
- **按新 run 全局 `clear_cursors()`**: OLD Agent 在新 run 前调用 `clear_cursors()`（OLD async_agent:615-617）。NEW Host runtime 面向 run-scoped / future multi-run 语义，不能简单全局清空，否则会破坏并发 run 的合法 cursor；NEW 通过 run/session binding、terminal guard 与 TTL 管理生命周期。
- **启发式选择最大字段**: OLD 在未显式 `target_field` 时会选择最大 text/list 字段（OLD:260-300）。NEW 只对顶层 string/list/binary 自动截断，对 mapping 要求显式 `target_field` / `field_path`（NEW:726-749），符合 plan 中 schema-driven 显式 spec 边界，避免业务规则猜测。
- **专用 RunEvent facts**: OLD/中间实现曾把 truncation / cursor / fetch_more 提升为专用事实；NEW 正确删除，EventLog 只保留普通 tool call request/result。

## Open Questions

- blocking: controller 需要裁决 durable `HostToolRuntime.execute_tool_call()` 是否必须在真实入口校验 owner scope。OLD 没有这个机制，但 NEW design 把 `fetch_more` fencing 归为 Host 私有实现；当前死 guard 状态不能作为通过依据。
- non-blocking: NEW 允许 caller-provided `fetch_more` schema 与私有 schema 完全一致时通过 schema provider。OLD 调用方手工注入 framework schema 是历史事实；P8.5 若要彻底禁止 caller-facing `fetch_more` schema，应在 fix 或后续 P10 明确拒绝策略。

## Validation Notes

- 本次只做 OLD/NEW 代码阅读与证据核对，未运行测试，未修改 production / tests / README，未 commit。
- 读取 OLD: `/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py`、OLD `tool_registry.py`、OLD `async_agent.py` 中 cursor 清理调用点。
- 读取 NEW: `dayu/host/_runtime_truncate_manager.py`、`dayu/host/_tool_runtime.py`、`dayu/host/_framework_tools.py`、`dayu/contracts/tool_result.py`、`dayu/contracts/tool_declaration.py`、`dayu/engine/agent.py`、相关 tests 与既有 `docs/host/phase8.5-s1-code-review.md`。
