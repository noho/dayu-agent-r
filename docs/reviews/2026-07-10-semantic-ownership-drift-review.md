# 语义所有权漂移 / 最小设计陷阱 深度审查

**审查日期:** 2026-07-10
**审查范围:** 全仓库（`dayu/`, `tests/`, `utils/`）
**审查方法:** 5维度并行子代理审查 + 主审查员去重交叉验证
**审查维度:** 状态机漂移、重复语义事实/下游修复、存储/Schema、协议适配器/边界反转、测试/Fakes

---

## 结论

本仓库在架构纪律方面整体良好——分层边界清晰、禁止兼容性代码的约束被严格执行、没有发现生产代码为旧测试保留分支。但在**持久层语义类型化**、**跨模块 payload 解析**、**adapter 层领域决策泄漏**三个方向存在系统性的最小设计陷阱。

**最高风险发现（需要优先修复）:**

1. `event_type` 是裸字符串，贯穿整个 EventLog 持久层，无 closed-set 验证
2. `CONTEXT_COMPACTED` payload 字段常量和解析逻辑在 3 个模块中独立重复
3. `execution_target` / `queue_policy` 无任何类型约束或 CHECK 约束
4. assistant final answer text 有 4+ 条不一致的解析路径
5. 财报下载 adapter 硬编码了产品级过滤语义和 LLM 行为指令

---

## 维度一：状态机漂移（State Machine Drift）

### SM-1 [高] 终端事件类型字符串常量在 3 个模块中独立定义

**语义事实:** Host 侧终端事件类型标识（`RUN_SUCCEEDED`, `RUN_FAILED`, `RUN_CANCELLED` 等）

**正确 owner:** `dayu/host/lifecycle_events.py` 中的 `HostRunEventType` 枚举（声明为 canonical source）

**漂移位置:**
- `dayu/host/lifecycle_events.py:16-29` — `HostRunEventType` 枚举，声明为唯一真源
- `dayu/host/durable/run_transition.py:88-106` — 私有 `_EVENT_TYPE_*` 字符串常量，**未导入** lifecycle_events
- `dayu/host/engine_ingest.py:225-236` — 私有 `_EVENT_TYPE_*` 字符串常量，**未导入** lifecycle_events 或 run_transition

**直接证据:** 三个模块各自定义 `_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"` 等常量，值相同但来源独立。

**失败场景:** 若任一模块的常量值变更而其他模块未同步更新，事件路由将静默失败——写入的 event_type 与查询的 event_type 不匹配，导致状态转换丢失。

**修复建议:** `run_transition.py` 和 `engine_ingest.py` 必须从 `lifecycle_events.py` 导入，或抽取到一个共享的 `_event_type_constants` 模块。

**验证点:** 全局搜索 `_EVENT_TYPE_` 前缀，确认只有一处定义。

---

### SM-2 [高] 三套终端事件类型集合定义，Engine→Host 映射无单一权威表

**语义事实:** 哪些事件是终端事件、Engine 终端事件如何映射到 Host 状态

**正确 owner:** 应有一个 Engine→Host 终端事件映射表

**漂移位置:**
- `dayu/engine/contracts/engine_events.py:509-516` — `TERMINAL_ENGINE_EVENT_TYPES = {FINAL_ANSWER, RUN_FAILED, RUN_CANCELLED, RUN_SUSPENDED}`
- `dayu/host/lifecycle_events.py:31-36` — `HOST_RUN_TERMINAL_EVENT_TYPES = {RUN_SUCCEEDED, RUN_FAILED, RUN_CANCELLED, RUN_LOST}`
- `dayu/host/engine_ingest.py:895-1006` — `_ingest_validated` 方法通过模式匹配分散处理，`_final_answer_plan`、`_run_failed_plan`、`_close_active_cancel` 各自处理不同映射

**直接证据:** `RUN_SUSPENDED` 在 Engine 层是终端，映射到 Host 的 `WAITING`（非终端）；`FINAL_ANSWER` 映射到 `SUCCEEDED`；`RUN_FAILED` 可映射到 `FAILED` 或触发 recovery 变为 `RECOVERING`。映射逻辑分散在 3+ 个函数中。

**失败场景:** 新增 Engine 事件类型时，无法从单一位置确认需要哪些 Host 状态转换。

**修复建议:** 在 `engine_ingest.py` 中建立 `_ENGINE_TO_HOST_TERMINAL_MAP: dict[EngineEventType, HostRunEventType]` 映射表。

---

### SM-3 [中] Dispatch 记录终端状态依赖 nullable 字段推断

**语义事实:** Dispatch 记录是否已被 worker 接受

**正确 owner:** `DispatchRecordRow.status` 应表达此语义

**漂移位置:** `dayu/host/durable/state.py:301-333, 4886-4971`

**直接证据:** `DispatchRecordRow` 使用 `cancelled_at: str | None`、`cancelled_event_id: str | None`、`worker_accepted_at: str | None`、`worker_accept_event_id: str | None`、`worker_accept_event_sequence: str | None` 五个 nullable 字段作为状态指标。`cancel_starting_dispatch_record_row` 的 CAS guard 检查 `worker_accepted_at IS NULL` 等三个字段。

**失败场景:** "worker 是否已接受？"这个问题需要检查三个 nullable 字段的 conjunction，而非单一状态值。新增状态维度时需要扩展 null-check 组合。

---

### SM-4 [中] SQL 查询硬编码非终端状态集合，未使用已有的 frozenset

**语义事实:** 哪些 Run 状态是"活跃的"

**正确 owner:** `dayu/host/durable/state.py:71-75` 的 `NON_TERMINAL_RUN_STATUSES` frozenset

**漂移位置:** `dayu/host/durable/state.py:1596-1607` (`read_active_run_for_session`)

**直接证据:** SQL 查询内联硬编码 `AND status IN (?, ?, ?, ?, ?)`（ACCEPTED, RUNNING, WAITING, CANCELLING, RECOVERING），未从 `NON_TERMINAL_RUN_STATUSES` 派生。`read_non_terminal_runs`（1711-1763）使用六值集合。

**失败场景:** 若 `RunStatus` 新增成员，这些查询将静默遗漏新状态的 Run。

**修复建议:** 在 Python 层从 `NON_TERMINAL_RUN_STATUSES` 动态构建 SQL IN 子句。

---

### SM-5 [中] CANCELLED wait 记录被同时视为终端和活跃

**语义事实:** Wait 记录的 `CANCELLED` 状态语义

**正确 owner:** `WaitRecordStatus.CANCELLED` 应是纯终端状态

**漂移位置:** `dayu/host/durable/state.py:2082-2094, 2153-2239`

**直接证据:** `read_wait_records_for_poll_observation` 返回 `WAITING` 和 `CANCELLED` 两种记录。`claim_wait_record_for_poll` 对 `CANCELLED` 记录使用与 `WAITING` 相同的 CAS guard，以 `poll_abandoned_at IS NULL` 作为门控。

**失败场景:** `CANCELLED` 状态具有双重语义——既是终端（永远不会 resolve），又是活跃的（poller 仍需处理 abandonment）。如果 poller 逻辑变更，可能误处理已取消的记录。

---

### SM-6 [中] Fins wait adapter 自行计算超时，忽略已有的 deadline/expires 字段

**语义事实:** Wait 记录是否超时

**正确 owner:** `WaitRecordRow.deadline_at` / `expires_at` 字段

**漂移位置:** `dayu/fins/ingestion/wait_adapter.py:609-619`

**直接证据:** `_transient_pending_expired` 从 `wait_record.created_at` 计算年龄，对比硬编码 `_TRANSIENT_PENDING_MAX_SECONDS = 300.0`。`WaitRecordRow` 已有 `deadline_at` 和 `expires_at` 字段（state.py:456-457），但 adapter 忽略它们。

---

### SM-7 [低] FollowupSnapshot 行为约束仅在 API 层校验

**漂移位置:** `dayu/host/api.py:2399-2402` — `accepted_run_status != RunStatus.RECOVERING` 校验

**直接证据:** Host 持久层的 `mark_running_run_recovering_row`（state.py:3861-3919）不阻止后续 follow-up 提交，约束仅在 `FollowupSnapshot.__post_init__` 中检查。

---

### SM-8 [低] Session timeline cursor 从 nullable 字段推断而非 status 列

**漂移位置:** `dayu/host/durable/state.py` — `_session_timeline_cursor` 从 `closed_at`/`closed_event_id` 推断，而非 `status` 列。

---

## 维度二：重复语义事实 / 下游修复（Duplicated Semantic Facts / Downstream Repair）

### DS-1 [高] CONTEXT_COMPACTED payload 字段常量和解析逻辑在 3 个模块中独立重复

**语义事实:** `CONTEXT_COMPACTED` 事件 payload 的内部结构（session_summary, evidence_backed_facts, answer_anchors, forward_intents, reference_continuity_items）

**正确 owner:** 应由一个共享的 payload schema/contract 模块拥有

**漂移位置:**
- `dayu/host/memory.py:72-97` — 定义 17 个 `_PAYLOAD_FIELD_*` 常量
- `dayu/host/compact_material.py:106-131` — 定义几乎相同的 17 个常量
- `dayu/host/run_input.py:168-205` — 定义第三个重叠集合

**直接证据:** 三个模块各自独立读取和解析同一个 `CONTEXT_COMPACTED` payload 的 accepted candidate mapping、session summary、evidence-backed facts、answer anchors、forward intents。

**失败场景:** payload 结构变更时，必须同步更新三个模块。遗漏任一模块将导致静默数据丢失或解析错误。

**修复建议:** 抽取 `_compact_payload_fields.py` 共享模块，或让 `compact_material.py` 成为唯一的 payload 解析 owner，其他模块消费其投影结果。

---

### DS-2 [高] assistant final answer text 有 4+ 条不一致的解析路径

**语义事实:** "assistant 的最终回答文本是什么？"

**正确 owner:** 应由 `terminal_payload.py` 或 `_terminal_answer.py` 拥有

**漂移位置:**
- `dayu/host/terminal_payload.py:33-51` — 仅读 `final_answer` 字段，无 fallback
- `dayu/host/_terminal_answer.py:35-83` — 读 `final_answer`，fallback 到 terminal artifact，使用 `STRICT_NON_EMPTY`
- `dayu/host/memory.py:1641-1669` — 先试 `event.assistant_final_answer_text`，fallback 到 `assistant_final_answer_text_from_run_payload`，使用 `LENIENT_NON_EMPTY`
- `dayu/host/compact_material.py:2196-2228` — 使用 `assistant_final_answer_continuity_text`（artifact-aware），`STRICT_NON_EMPTY`
- `dayu/host/outbox.py:346-379` — 独立读 `final_answer`，使用自己的 `optional_payload_text`

**直接证据:** 4 个模块各自解析同一语义事实，fallback 策略不同（strict vs lenient, artifact-aware vs inline-only）。

**失败场景:** answer text contract 变更时（如改为存储在 artifact 中），需要审计所有路径。`memory.py` 使用 lenient 策略可能接受空结果，而 `compact_material.py` 使用 strict 策略会拒绝。

**修复建议:** 建立唯一的 `resolve_final_answer_text(event, policy)` 函数，所有消费者调用它。

---

### DS-3 [高] AcceptedToolResultStatus 从原始 JSON 重建（下游修复）

**语义事实:** 工具执行结果的状态（completed/failed/cancelled）

**正确 owner:** `TOOL_RESULT_ACCEPTED` payload 中的 `resolution_kind` 字段

**漂移位置:** `dayu/host/accepted_result_projection.py:366-436`

**直接证据:** `_accepted_status` 有 3 层 fallback：(1) `resolution_kind` → (2) `tool_fact_kind` → (3) `_status_from_raw_outcome` 直接解析 raw outcome JSON 的 `kind` 字符串和 `result.ok` 布尔值。

**失败场景:** 当结构化字段缺失时，投影模块从原始 JSON 重建状态，掩盖了上游数据质量问题。`TOOL_RESULT_ACCEPTED` 事件没有结构化状态应该是 contract violation，而非可恢复条件。

---

### DS-4 [中] Outbox 终端投影独立重复 terminal payload 字段访问

**漂移位置:** `dayu/host/outbox.py:57-68, 346-379` — 独立定义 `_PAYLOAD_FIELD_*` 常量并重新读取 `terminal_payload.py` 已有 accessor 的字段。

---

### DS-5 [中] Evidence 文本组装在 memory.py 和 accepted_result_projection.py 中独立完成

**漂移位置:**
- `dayu/host/memory.py:1694-1757` — 组装 LLM-facing evidence 文本
- `dayu/host/accepted_result_projection.py:161-227` — 生产 `AcceptedToolResultProjection`

**直接证据:** 两个模块消费同一个 `TOOL_RESULT_ACCEPTED` EventLog 事件，独立提取 tool_name, query, result, source。

---

### DS-6 [中] Evidence envelope 错误处理逻辑逐字重复

**漂移位置:**
- `dayu/host/accepted_result_projection.py:259-278`
- `dayu/host/compact_material.py:2258-2266`

**直接证据:** 两个模块有几乎相同的 try/except 块，检查 `str(exc) == ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH`。

---

### DS-7 [中] Payload text accessor 在多个模块中重新实现

**漂移位置:** `accepted_result_projection.py:759`, `tool_trace.py:2276`, `outbox.py:486`, `compact_material.py`

**直接证据:** `_event_payload` 模块已提供 `optional_payload_text` / `required_payload_text`，但不是所有消费者都使用它。各模块有自己的 `_optional_text` / `_required_text` 变体。

---

### DS-8 [低] 截断模式在两个模块中独立实现

**漂移位置:** `accepted_result_projection.py:57,746` 和 `tool_trace.py:238,2041` — 各自定义 `_TRUNCATED_SUFFIX = "...[truncated]"` 和 `_bounded_text`。

---

## 维度三：存储/Schema — 弱类型契约与隐藏协议（Weak Contract / Hidden Protocols）

### SS-1 [高] event_type 贯穿 EventLog 持久层是裸字符串，无 closed-set 验证

**语义事实:** EventLog 事件类型的合法值集合

**正确 owner:** 应由一个 `EventType` StrEnum 或 Schema CHECK 约束拥有

**漂移位置:**
- `dayu/host/durable/event_log.py:139` — `event_type: str`
- `dayu/host/durable/event_log.py:92` — `EventLogAppendRequest.event_type: str`
- `dayu/host/durable/event_log.py:329-330` — 仅 `_require_non_empty_text` 验证

**直接证据:** 事件类型如 `"USER_INPUT_ACCEPTED"`, `"RUN_SUCCEEDED"`, `"TOOL_CALL_REQUESTED"` 等是裸字符串，散落在 memory.py:89-99、event_log.py:873 等多个模块中。Durable 层无 central enum、无 CHECK 约束、无 closed-set 验证。

**失败场景:** 拼写错误的 event_type 将被静默写入 EventLog，不会被任何层拦截。消费模块按字符串匹配读取，拼写错误导致事件"丢失"。

**修复建议:** 定义 `EventType(StrEnum)` 并在 `EventLogAppendRequest` 和 schema DDL 中强制约束。

---

### SS-2 [高] execution_target / queue_policy 是裸字符串，无任何约束

**语义事实:** Run 的执行目标和排队策略

**正确 owner:** 应由 StrEnum + Schema CHECK 约束拥有

**漂移位置:**
- `dayu/host/durable/state.py:274-275` — `execution_target: str`, `queue_policy: str`
- `dayu/host/durable/schema.py:455-547` — `host_runs` 表 DDL 无 CHECK 约束

**直接证据:** 对比 `source_run_relation`（schema.py:487-489 有 CHECK 约束限制为 `('retry', 'replay')`）和 `resume_policy`（schema.py:707-708 有 CHECK 约束 + `WaitResumePolicy` 枚举）。`execution_target` 和 `queue_policy` 两者都无枚举、无 CHECK、无 closed-set 验证。

**失败场景:** 任意字符串可写入这两个字段，持久层不会拒绝。调用者必须"知道"合法值是什么。

**修复建议:** 定义 `ExecutionTarget(StrEnum)` 和 `QueuePolicy(StrEnum)`，添加 Schema CHECK 约束。

---

### SS-3 [中] RunResultRow.terminal_status 存储为 str 而非 RunStatus

**漂移位置:** `dayu/host/durable/read_model.py:63, 405-407`

**直接证据:** `_run_result_from_host_row` 调用 `_terminal_status_from_text()` 返回 `RunStatus`，然后立即 `.value` 转回 `str` 存储。所有消费者必须重新解析。

---

### SS-4 [中] host_run_results 投影缺乏过期协调机制

**漂移位置:** `dayu/host/durable/read_model.py:140-194`

**直接证据:** `insert_run_result_if_absent` 是 insert-only 函数，无 update 路径，无自动过期检测。

---

### SS-5 [中] await_kind 是裸字符串

**漂移位置:** `dayu/host/durable/state.py:448` — `await_kind: str`，schema.py:705 无 CHECK 约束

**直接证据:** 对比同表的 `resume_policy`（有 CHECK 约束 + `WaitResumePolicy` 枚举）。

---

### SS-6 [中] scope_kind / result_kind 是裸字符串

**漂移位置:** `dayu/host/durable/idempotency.py:37, 46`

---

### SS-7 [中] Descriptor kind 常量是裸字符串，无类型

**漂移位置:** `dayu/host/durable/schema.py:206-260` — `"tool_call_arguments_json"`, `"runner_call_input_manifest"` 等

**直接证据:** `payload_resolution.py:338` 通过 `metadata.get("descriptor_kind")` 字符串比较验证。

---

### SS-8 [中] HostRow 是 dict[str, SQLiteScalar]，列名是裸字符串

**漂移位置:** `dayu/host/durable/transaction.py` — 所有 `*_from_host_row` 函数通过 `row.get("column_name")` 访问

**直接证据:** SQL SELECT 列名和 decoder 中的 `row.get()` 字符串是独立维护的，拼写错误仅在运行时通过 `HostRowDecodeError` 捕获。

---

### SS-9 [中] metadata_json 是不透明 JSON blob

**漂移位置:** `dayu/host/durable/state.py:211, 232` — `SessionRow.metadata_json: str`, `SessionSlotRow.metadata_json: str`

---

### SS-10 [中] 下载拒绝注册表是 dict[str, dict[str, str]] 隐藏形状协议

**漂移位置:** `dayu/fins/storage/repository_protocols.py:263, 268`

**直接证据:** 嵌套 dict 的外键、内键、内值语义完全隐式。

---

### SS-11 [低] Memory snapshot digest 双写

**漂移位置:** `dayu/host/durable/memory.py:1634-1644` — snapshot JSON 内嵌 digest + 独立 column 存储

---

### SS-12 [低] Legacy "verified_fact" 作为特殊 case 处理

**漂移位置:** `dayu/host/durable/memory.py:84, 1485-1495, 1573-1578`

**直接证据:** Schema CHECK 约束已不允许此值，但 integrity scanner 仍需防御性检查旧数据。

---

## 维度四：协议适配器 / 边界反转（Boundary Inversion）

### BI-1 [高] 财报下载 adapter 硬编码产品级过滤语义

**语义事实:** 什么标题的文档是"有效财报"

**正确 owner:** domain/pipeline 层应拥有财报过滤规则

**漂移位置:**
- `dayu/fins/downloaders/cninfo_downloader.py:85-128` — `_TITLE_BLOCKLIST`（"摘要"、"ESG"、"可持续发展"、"审计报告"、"英文版"等）、`_REPORT_NOTICE_TITLE_TOKENS`、`_REPORT_TITLE_TOKENS`、`_TITLE_AMENDED_TOKENS`
- `dayu/fins/downloaders/cninfo_downloader.py:868-869` — `_TITLE_FY_PATTERN` 从标题推断 fiscal year
- `dayu/fins/downloaders/hkexnews_downloader.py:71-113` — 同样模式：`_TITLE_AMENDED_TOKENS`、`_ENGLISH_REPORT_TITLE_TOKENS`、`_PERIOD_INFERENCE_TOKENS`
- `dayu/fins/downloaders/hkexnews_downloader.py:996-1078` — `_infer_fiscal_period_from_text`, `_infer_fiscal_year` 纯领域推断函数

**直接证据:** 这些黑名单关键词和推断函数是产品层面"什么是有效财报"的领域决策，不是 HTTP 协议适配细节。

**失败场景:** 过滤规则变更时需要修改 HTTP adapter 代码，而非 domain 层配置。

**修复建议:** 将过滤规则和推断逻辑抽取到 `dayu/fins/domain/` 或 pipeline 层，adapter 只负责 HTTP 请求/响应。

---

### BI-2 [高] Web search provider 硬编码 LLM 行为指令和工具编排策略

**语义事实:** LLM 在搜索结果为空/有时应执行什么下一步动作

**正确 owner:** prompt/scene 层或 tool schema 的 description 层

**漂移位置:**
- `dayu/tools/web/web_search_providers.py:895-925` — `_build_search_web_hint` 硬编码 LLM 执行指令："当前没有可直接抓取的网页正文。下一步应改写 query…"
- `dayu/tools/web/web_search_providers.py:856-871` — `_build_search_web_next_action` 决定 `fetch_web_page` vs `refine_query`
- `dayu/tools/web/web_search_providers.py:815-853` — `_build_search_web_preferred_summary` 硬编码中文摘要模板

**直接证据:** 工具编排策略（"有结果就抓取，没结果就改写 query"）是 domain/agent 层决策，不应在 search provider 内部决定。LLM 行为指令属于 prompt 层职责。

---

### BI-3 [中] Ingestion runtime 硬编码中文 UI 文案

**漂移位置:**
- `dayu/fins/ingestion_runtime.py:178-181` — `_DIRECT_CANCELLED_MESSAGE = "操作已取消"` 等
- `dayu/fins/ingestion_runtime.py:2779-2810` — producer 内嵌 `"下载准备中"`, `"下载失败"` 等

**直接证据:** runtime 层（Host/Engine 之下）在决定用户看到什么文案。

---

### BI-4 [中] Fins wait adapter 硬编码 LLM-facing hint

**漂移位置:**
- `dayu/fins/ingestion/wait_adapter.py:484` — `"请检查 Fins ingestion 摘要，必要时重新发起对应操作。"`
- `dayu/fins/ingestion/wait_adapter.py:506` — `"如仍需要该财报资料，请重新发起对应操作。"`

---

### BI-5 [中] SEC downloader 引用 CLI 命令名

**漂移位置:** `dayu/fins/downloaders/sec_downloader.py:2035-2038` — 警告消息引用 `dayu-cli init`

**直接证据:** adapter 知道 CLI 命令名，这是 UI/CLI 层产物名称泄漏。

---

### BI-6 [中] Web tools 硬编码 display_name 和取消消息

**漂移位置:**
- `dayu/tools/web/web_tools.py:1194` — `display_name="联网搜索"`, `display_name="抓取网页"`
- `dayu/tools/web/web_tools.py:165-166` — `_WEB_SEARCH_CANCELLED_MESSAGE = "网页搜索工具调用已停止。"`

---

### BI-7 [低] Error classifier 硬编码 provider 英文错误消息片段

**漂移位置:** `dayu/engine/runners/openai/error_classifier.py:35-42` — 6 个 context overflow message markers

**直接证据:** 位于 adapter 边界内且有结构化 code 作为主路径，message 匹配是 fallback。

---

### BI-8 [低] Wait callback endpoint 硬编码认证 reason code 到 HTTP status 映射

**漂移位置:** `dayu/service/wait_callback_endpoint.py:770-781`

---

## 维度五：测试/Fakes — 测试驱动语义漂移（Test-Driven Semantic Drift）

### TF-1 [中] Field-set lock 测试断言精确 dataclass 字段集合

**语义事实:** dataclass 的字段集合是公共契约的一部分

**漂移位置:**
- `tests/host/test_memory_projection.py:99-137` — `_POLICY_FIELDS` 和 `_SNAPSHOT_FIELDS` tuple 锁定精确字段顺序
- `tests/engine/test_engine_event_contract.py:38-57` — 锁定 `EngineEventType` 精确成员集合
- `tests/engine/test_engine_event_contract.py:118-191` — 锁定 12+ dataclass 的精确字段集合
- `tests/contracts/test_tool_result_envelope.py:95-101` — 锁定 `ToolResultSuccess` 和 `ToolResultFailure` 字段集合

**失败场景:** 添加新字段（即使是可选的、向后兼容的）会先触发测试失败，测试套件成为事实上的 schema 注册表。

**正面发现:** 这些测试的设计意图是 contract 稳定性保障。问题在于断言方式——应断言"关键字段存在且类型正确"而非"字段集合完全相等"。

---

### TF-2 [中] Test helpers 直接读写生产 SQLite schema

**漂移位置:**
- `tests/host/public_smoke_support.py:1505-1524` — raw `sqlite3.connect` 查询 `event_log` 表
- `tests/host/recovery_support.py:658-681` — raw SQL UPDATE `host_instances` 表（涉及 4 表 join）
- `tests/host/recovery_support.py:684-710` — raw SQL 操作 `host_projection_checkpoints`
- `tests/host/stress_support.py:731-739` — raw SQL 读 `event_log`
- `tests/host/stress_support.py:1001-1034` — raw SQL 读 `host_instances`

**失败场景:** 测试 helper 的 raw SQL 定义了"正确"的 recovery/liveness 行为，可能与实际 production recovery 代码产生漂移。

---

### TF-3 [中] Fake 实现紧密耦合 production schema

**漂移位置:**
- `tests/host/fake_compaction.py` — 导入 14 个 production vNext 类型
- `tests/host/memory_snapshot_factories.py:139` — 构造完整的 `ConversationMemorySnapshotVNext`

**失败场景:** production schema 变更时 fake 先于 production 代码失败。

---

### TF-4 [低] 两个独立的 FakeCancellationToken 实现

**漂移位置:**
- `tests/host/fake_cancellation.py:14-63` — `StubCancellationToken`，使用 `datetime.now(UTC)`，方法名 `request_cancel()`
- `tests/engine/runners/openai/_fakes.py:250-287` — `FakeCancellationToken`，使用 `datetime.now()`（naive），方法名 `trigger()`

**失败场景:** Protocol 新增方法时，一个 fake 可能被更新而另一个静默漂移。

---

### TF-5 [低] 精确 LLM-facing 文本断言

**漂移位置:**
- `tests/host/test_run_input_builder.py:483-489` — 断言精确中文子串
- `tests/host/test_memory_projection.py:909-916` — 断言精确中文 evidence 文本

**失败场景:** 改善 LLM 可读性时修改措辞会触发测试失败。

---

## 正面发现

以下维度**未发现**语义漂移：

1. **无生产代码为旧测试保留分支** — 生产代码中未发现 test-mode flag 或 test-specific compatibility shim。
2. **无 bug-compatible transform 重复** — 测试 helper 一般使用 production helper 函数（如 `calculate_memory_snapshot_digest`），而非重新实现。
3. **禁止兼容性代码的约束被严格执行** — 旧 config 文件已删除，无兼容性 re-export。
4. **分层依赖方向被严格遵守** — `dayu.runtime` 不导入 `dayu.engine/host/service/fins`。

---

## 修复优先级矩阵

| 优先级 | 发现 | 修复成本 | 影响范围 |
|--------|------|---------|---------|
| P0 | SS-1 event_type 裸字符串 | 低（定义 StrEnum + CHECK） | 全持久层 |
| P0 | DS-1 CONTEXT_COMPACTED payload 解析重复 | 中（抽取共享模块） | 3 个核心模块 |
| P0 | SM-1 终端事件常量重复定义 | 低（统一导入） | 3 个模块 |
| P1 | SS-2 execution_target/queue_policy 无约束 | 低（定义 StrEnum + CHECK） | Run 持久层 |
| P1 | DS-2 final answer text 4 条不一致路径 | 中（统一 resolver） | 5 个模块 |
| P1 | DS-3 AcceptedToolResultStatus 下游重建 | 低（移除 fallback 或报错） | 1 个模块 |
| P1 | BI-1 财报 adapter 硬编码过滤语义 | 中（抽取到 domain 层） | 3 个 downloader |
| P1 | BI-2 search provider 硬编码 LLM 指令 | 中（抽取到 prompt 层） | 1 个模块 |
| P2 | SM-2 终端事件映射无单一表 | 低（建立映射表） | engine_ingest |
| P2 | SM-4 SQL 硬编码非终端状态集合 | 低（动态构建 IN 子句） | 2 个查询 |
| P2 | BI-3/4/5/6 UI copy 泄漏到非 UI 层 | 中（抽取到配置/prompt） | 多个模块 |
| P2 | SS-3~10 其他裸字符串字段 | 低~中 | 各自模块 |
| P3 | TF-1~5 测试耦合 | 中 | 测试套件 |
