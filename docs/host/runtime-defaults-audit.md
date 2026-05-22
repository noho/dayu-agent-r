# Host Runtime Defaults Audit

本清单只记录当前代码内默认值事实与建议归属，不在本轮做未裁决重构。

| 位置 | 默认值 | 当前用途 | 是否已属于 Host option / Run spec / Agent policy | 建议归属 |
| --- | --- | --- | --- | --- |
| `dayu.host.tool_runtime` | `_TOOL_RESULT_SIZE_LOG_THRESHOLD_BYTES = 65536` | 仅用于大工具结果透传日志摘要触发，不改变 outcome | 否 | Host diagnostic/log policy |
| `dayu.host.tool_runtime` | `_DEFAULT_ACCEPT_RETRY_ATTEMPTS = 2`、`_DEFAULT_ACCEPT_BACKOFF_SECONDS = 0.0` | Tool fact accept ack 默认有限重试 | 否，`ToolRuntimeBuildRequest.retry_policy` 可显式覆盖 | Host ToolRuntime option |
| `dayu.host.tool_runtime` | `_DEFAULT_TRUNCATION_TTL_SECONDS = 600` | 显式 truncation spec 未给 TTL 时补齐 effective spec | 否 | Host tool truncation policy |
| `dayu.host.tool_runtime` | `_DEFAULT_TEXT_CHARS_TRUNCATION_LIMIT = 4096` | text chars 截断默认 limit | 否 | Host tool truncation policy |
| `dayu.host.tool_runtime` | `_DEFAULT_TEXT_LINES_TRUNCATION_LIMIT = 200` | text lines 截断默认 limit | 否 | Host tool truncation policy |
| `dayu.host.tool_runtime` | `_DEFAULT_LIST_ITEMS_TRUNCATION_LIMIT = 100` | list items 截断默认 limit | 否 | Host tool truncation policy |
| `dayu.host.tool_runtime` | `_DEFAULT_BINARY_BYTES_TRUNCATION_LIMIT = 4096` | binary bytes 截断默认 limit | 否 | Host tool truncation policy |
| `dayu.host.tool_runtime` | `_TRUNCATION_EXPIRED_CLEANUP_LIMIT = 64`、`_TRUNCATION_EXPIRED_CLEANUP_SCAN_LIMIT = 256` | cursor 过期清理的单次工作上限 | 否 | Host ToolRuntime maintenance option |
| `dayu.host.open_host` | `_SESSION_WATCH_POLL_INTERVAL_SECONDS = 0.05` | public watch 无事件时轮询间隔 | 否 | Host watch option |
| `dayu.host.open_host` | command context fallback `context_window_size=8192`、`reserved_output_tokens=1024` | 未传 context policy 时构造 command options fallback | 是，来自 Host opener 边界 fallback | 继续归属 Host option，建议显式配置化 |
| `dayu.host.context_policy` | soft ratio `0.8`、hard ratio `0.9`、compact 次数默认 `1` | `default_context_budget_policy` helper 的默认 policy | 是，构造 Host context budget policy 时使用 | Host context budget policy |
| `dayu.host.llm_compaction` | `_COMPACTOR_MAX_ITERATIONS = 1`、`_COMPACTOR_TOOL_TIMEOUT_SECONDS = 1.0` | Host-owned compactor Engine request 的 AgentPolicy 默认 | 否 | Compactor Run spec / Agent policy profile |
| `dayu.host.llm_compaction` | `_MAX_SAFE_OUTCOME_MESSAGE_CHARS = 240` | compactor proposal 失败消息日志/异常摘要截断 | 否 | Host diagnostic/log policy |
| `dayu.host.compaction_operation` | `_MAX_SAFE_EXCEPTION_MESSAGE_CHARS = 240` | compaction attempt 失败日志摘要截断 | 否 | Host diagnostic/log policy |
| `dayu.host.compaction_operation` | next decision 字符串 `retry_semantic_repair` / `fail_compaction` | compaction attempt reject payload | 否 | Host context governance policy enum |
| `dayu.host.projection` | `_MIN_BATCH_LIMIT = 1`、`_READ_ONE_EVENT_LIMIT = 1` | ProjectionRunner 单步扫描与批次下限 | 否 | Projection runner option |
| `dayu.host.memory` | memory projection policy helper 默认值 | conversation memory projection 截断、保留窗口、摘要行为 | 部分通过 `MemoryProjectionPolicy` 显式构造 | Host memory projection policy |
| `dayu.runtime.cancellation` | `_DEFAULT_POLL_INTERVAL_SECONDS = 0.05` | cancellation token 轮询间隔 | 否，runtime 层中立默认 | Runtime cancellation option |
| `dayu.runtime.lane` | claim TTL `30.0`、heartbeat `10.0`、busy timeout `5.0`、poll interval `0.05` | runtime lane 默认配置 | 否，`LaneConfig` / `SQLiteLaneCoordinatorConfig` 可覆盖 | Runtime lane config |
| `dayu.engine.agent` | `_EXCEPTION_MESSAGE_MAX_LENGTH = 240` | runner/provider exception 进入 Engine failed 事件前脱敏截断 | 否 | Engine diagnostic/log policy |
| `dayu.engine.agent` | fallback prompt 由 `AgentPolicy` 提供，测试 helper 默认 `"请直接回答。"` | force-answer fallback | 是 | Agent policy |

