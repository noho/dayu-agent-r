# Semantic Ownership Code Review — AgentDS 主线

## Scope

- Mode: all repository
- Branch: phase/host-issues-control
- Output file: docs/reviews/fullrepo-semantic-ownership-review-ds.md
- Included scope: `dayu/fins/` (ingestion, tools, storage, pipelines, domain, processors), `dayu/cli/`, `dayu/config/` (prompts, manifests), `dayu/host/` (durable, memory, compact, run_input), `dayu/engine/contracts/`
- Excluded scope: `dayu/tools/web/` (仅抽样), `dayu/render/`, `utils/`, `workspace/`, `tests/` (仅抽样关键测试文件)
- Parallel review coverage:
  - Shard 1 (a28b881e): Fins ingestion — download/upload/preprocess/docling/storage/pipelines/domain → **covered**
  - Shard 2 (a34ec4fb): Fins tools/schema — tool definitions, 参数 schema, LLM-safe output, tool result material → **covered**
  - Shard 3 (a382ed6e): CLI/UI — prompt/interactive/session commands, cancel/retry, service 层 → **covered**
  - Shard 4 (aea517ae): Config/prompt — manifests, scenes, base prompts, compact, runtime config → **covered**
  - Shard 5 (a3a4e2cc): LLM-facing/docs/tests — memory/evidence, engine 投影, durable, README → **covered**
- Not-covered areas: `dayu/fins/processors/` 下各具体 form processor（form_type_utils, sec_*_processor 等）的逐行走读；`dayu/tools/` 下非 web 工具；`tests/` 下全部测试文件（仅由 shard 5 抽样）; `dayu/documents/` 模块

## Findings

### 1. [HIGH] `FinsPreprocessResultSummary` 的 `skipped_count` 将 `not_supported` 合并计数，与 `skipped_document_ids` 语义矛盾

- **入口/函数**: `_execute_preprocess_request` → `FinsPreprocessResultSummary` 构造
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:3526-3531`
- **输入场景**: 预处理请求包含部分文档无可用处理器（`not_supported`）且部分文档已有产物被跳过（`skipped`）
- **实际分支**: `skipped_count=len(skipped_ids) + len(not_supported_ids)` (行 3526)，但 `skipped_document_ids=tuple(skipped_ids)` (行 3529)，`not_supported_document_ids` 单独存储 (行 3531)
- **预期行为**: `skipped_count` 应仅等于 `len(skipped_document_ids)`；`not_supported` 应有独立计数字段
- **实际行为**: 同一对象的两个字段对 "skipped" 的定义矛盾——`skipped_count` 包含 `not_supported`，但 `skipped_document_ids` 不包含
- **直接证据**:
  - 构造点：`ingestion_runtime.py:3526` 做 `len(skipped_ids) + len(not_supported_ids)`
  - 下游绕过 count 直接用 IDs：`ingestion_runtime.py:3198-3204` (`_run_preprocess_job`) 用 `len(summary.not_supported_document_ids) > 0` 而不看 `skipped_count`
  - 同样绕过：`ingestion_runtime.py:2769-2784` (`_produce_direct_preprocess`) 同样用 `len(summary.not_supported_document_ids) > 0`
  - 两条路径均使用相同 copy-paste 布尔表达式判定失败，见 Finding 8
- **影响**: 只看 `skipped_count` 的 UI/日志消费者看到膨胀数字；且 `skipped_count` 语义不可信迫使下游都绕过它直接用 IDs
- **建议改法和验证点**: 在 `FinsPreprocessResultSummary` 增加 `not_supported_count` 字段，`skipped_count` 只等于 `len(skipped_document_ids)`。构造点显式分别赋值。下游改为 `summary.not_supported_count > 0`
- **修复风险（低）**: 已有 persisted job record 的 `skipped_count` 历史值会变低，需确认监控/告警不依赖旧值
- **严重程度（高）**: High —— 同一 dataclass 内部两个字段对同一事实定义矛盾，且下游消费者已用规避行为（不用 count、用 IDs）证明了 count 不可信

### 2. [HIGH] Upload pipeline 结果契约是 loose `dict[str, JsonValue]`，runtime consumer 被迫用 fallback/类型守卫防御

- **入口/函数**: `SecUploadWorkflowHost._build_result` → `_upload_summary_from_result` 消费链
- **文件(行号)**:
  - `dayu/fins/pipelines/sec_upload_workflow.py:76-79,237-254` —— pipeline 产出 loose dict
  - `dayu/fins/service_runtime.py:255-345` —— `_upload_summary_from_result` 及三个 helper（`_upload_result_text`, `_optional_upload_result_text`, `_upload_result_bool`）做松散解析
- **输入场景**: Upload pipeline 完成，产出 result dict
- **实际分支**: `_upload_result_text(result, key, fallback="unknown")` —— 缺失 key 时静默 fallback (行 292)；`_optional_upload_result_text` —— 非字符串或空白返回 `None` (行 308-325)；`_upload_result_bool` —— 非 bool 返回 `False` (行 328-345)
- **预期行为**: Pipeline 应产出 typed result（如 `UploadResultSummary` dataclass），runtime 不做 defensive parsing
- **实际行为**: Pipeline 用 `**upload_result.payload` 展开 dict 作为结果 (sec_upload_workflow.py:254)；runtime 用 `isinstance(value, str)` + fallback 防御缺失/错误类型
- **直接证据**: 完整防御链在 `service_runtime.py:287-345`（四个函数专用于从 loose dict 中安全提取字段）；ingestion_runtime.py:2862 对同一 dict 做字符串比较 `summary.status.strip().lower() == _UPLOAD_RESULT_STATUS_FAILED`
- **影响**: 若 pipeline 改字段名或增删字段，runtime 静默降级为 `status="unknown"` 而非在 contract 层暴露
- **建议改法和验证点**: 在 pipeline 层定义 typed `UploadPipelineResult` dataclass；pipeline 返回 typed object；runtime 直接消费 typed object
- **修复风险（中）**: 上游 pipeline 事件流（`UploadFilingEvent` / `UploadMaterialEvent`）也以 dict payload 传递结果，需确认事件消费者不受 typed contract 变更影响
- **严重程度（高）**: High —— 核心数据流（upload → result summary）无 typed contract，迫使 3 层 consumer 各自做防御解析

### 3. [HIGH] `session resume` 从 prompt.py / interactive.py 导入私有函数，绕过公共 API

- **入口/函数**: `run_session_command` → `_run_session_resume`
- **文件(行号)**:
  - `dayu/cli/commands/session.py:36-41` —— 从 prompt.py 导入 `_execute_prompt_on_existing_session` 和 `_prepare_prompt_existing_session_execution`
  - `dayu/cli/commands/session.py:41` —— 从 interactive.py 导入 `_execute_interactive_on_existing_session` 和 `_prepare_interactive_existing_session_execution`
- **输入场景**: `dayu-cli session resume` 需要在已存在的 Host Session 上运行 prompt 或 interactive
- **实际分支**: 直接 import 并调用 prompt.py / interactive.py 的私有（`_` 前缀）函数
- **预期行为**: 执行入口应是两个模块的公开导出函数，或提取到 Service 层作为共享入口点
- **实际行为**: session.py 绕过公共 API 消费 prompt.py / interactive.py 的内部实现细节
- **直接证据**: prompt.py:635 `__all__` 仅导出 `CliCommandUsageError` 和 `run_prompt_command`；interactive.py:889 `__all__` 仅导出 `CliInteractiveUsageError` 和 `run_interactive_command`。被导入的四个 `_` 前缀函数不在任何模块的 `__all__` 中
- **影响**: prompt.py / interactive.py 内部重构可能破坏 session resume，但类型检查器或 linter 不会警告——这些函数不是公开 API
- **建议改法和验证点**: 将四个私有函数提升为公开函数（移除 `_` 前缀），加入 `__all__`；长期方案：提取到 `dayu/service/` 作为共享 DTO
- **修复风险（低）**: 机制性变更（重命名/重新导出），不改变业务逻辑
- **严重程度（高）**: High —— CLI 模块间跨边界消费私有实现，违反分层架构硬约束

### 4. [HIGH] Fins ingestion 工具 LLM-facing 文本多处暴露 Host 治理概念（wait / 等待状态 / 调度）

- **入口/函数**: `build_fins_download_tool()`, `build_fins_preprocess_tool()`, `build_fins_upload_tool()`, Fins read tools cancelled outcome
- **文件(行号)**:
  - `dayu/fins/tools/download_tools.py:153` —— `"调用后等待工具结果返回；"`
  - `dayu/fins/tools/preprocess_tools.py:150` —— `"调用后等待工具结果返回；"`
  - `dayu/fins/tools/upload_tools.py:246` —— `"调用后等待工具结果返回；"`
  - `dayu/fins/tools/download_tools.py:105,113` —— `"下载任务启动失败，未进入等待状态。"`
  - `dayu/fins/tools/preprocess_tools.py:104,112` —— `"预处理任务启动失败，未进入等待状态。"`
  - `dayu/fins/tools/upload_tools.py:119,127` —— `"上传任务启动失败，未进入等待状态。"`
  - `dayu/fins/tools/fins_tools.py:80` —— `_FINS_CANCELLED_HINT = "当前工具调用已停止；等待新的用户指令或后续调度。"`
- **输入场景**: Ingestion 工具被 LLM 调用（正常路径 + 启动失败路径 + 取消路径）
- **实际分支**: 三条 LLM-facing 文本路径均包含 Host governance 概念
- **预期行为**: LLM-facing 文本应仅用业务语言描述行为，不含 `wait`、`等待状态`、`调度` 等治理概念
- **实际行为**: Tool description 暴露 `等待工具结果返回`（Host wait adapter 机制）；失败消息暴露 `未进入等待状态`（Host state machine 内部状态）；取消 hint 暴露 `后续调度`（Host/Engine 调度系统）
- **直接证据**: 三处文本分别位于 tool schema description、`_failed_outcome` 构造、`_FINS_CANCELLED_HINT` 常量——均为 LLM-facing 投影的入口点
- **影响**: LLM 上下文被注入无关治理信息；memory/compact 材料持久化并反复回灌给 LLM；LLM 可能基于 `未进入等待状态` 做非预期推理
- **建议改法和验证点**: tool description 删除 "等待工具结果返回"（`start_*` 前缀已暗示异步）；失败消息去除 "未进入等待状态" 后缀；取消 hint 改为 `"当前工具调用已停止；请等待新的用户指令。"`
- **修复风险（低）**: 纯文本修改，不改变工具行为
- **严重程度（高）**: High —— 违反 CLAUDE.md LLM-facing 文本约束："不得把系统状态、调度状态、Host/Engine 内部治理信息伪装成财报事实、业务事实或用户可见结论"；9 个 Fins read 工具全部共享同一 `_FINS_CANCELLED_HINT`

### 5. [MEDIUM] Compaction user prompt 中 `evidence_kind` 枚举用管道概念（tool_result / tool_source_text / accepted_evidence_material）替代业务语义

- **入口/函数**: `conversation_compaction_user.md` prompt → LLM compaction 输出 schema
- **文件(行号)**:
  - `dayu/config/prompts/scenes/conversation_compaction_user.md` —— `evidence_kind` 字段定义，允许值 `tool_result|tool_source_text|accepted_evidence_material`
  - `dayu/host/compact_material.py:75-79` —— `_EVIDENCE_PREFIX = "E"` 标签前缀
- **输入场景**: Compaction 运行时，LLM 需要为每条事实标注 `evidence_kind`
- **实际分支**: LLM 必须区分 `tool_result`（原始工具返回）和 `tool_source_text`（工具返回中的源文本）和 `accepted_evidence_material`（已通过校验的证据材料）
- **预期行为**: 分类维度应是业务语义（如 `财报原文` / `网页资料` / `计算推导`），而非工具管道阶段
- **实际行为**: 模型被迫理解内部实现概念（"tool_result 和 tool_source_text 的区别"），增加了认知负担和分类错误风险
- **直接证据**: prompt 中的枚举值直接对应 `CompactMaterialSection.EVIDENCE_MATERIAL` 的内部标签体系；`execution_profiles.json` 中 `memory_projection_policy` 依赖此字段做记忆分层
- **影响**: Compaction 结果的消费者（memory projection、fact selection、answer anchor 提取）依赖 LLM 正确区分管道阶段；若 LLM 分类错误，下游记忆质量受损
- **建议改法和验证点**: 将 `evidence_kind` 从 LLM 输出 schema 移除，由 Host 在构建 compaction 输入时预标注每个 evidence material 条目的 `evidence_kind` 元数据；LLM 仅需引用已有分类
- **修复风险（中）**: 需要将 `evidence_kind` 推导逻辑绑定到 tool provider 的输出 schema 上；若新工具类型产生新证据形态，Host 预标注逻辑需同步更新
- **严重程度（中）**: Medium —— LLM-facing schema 直接暴露内部管道分类体系；但当前 LLM 已通过训练适应了此分类，修改涉及 compaction pipeline 两端的协调

### 6. [MEDIUM] Compaction user prompt 中 `trace_kind` 枚举包含 `user_visible_run_state`，泄漏 Host 运行期治理概念

- **入口/函数**: `conversation_compaction_user.md` prompt → LLM compaction 输出 schema
- **文件(行号)**:
  - `dayu/config/prompts/scenes/conversation_compaction_user.md` —— `trace_kind` 字段定义，允许值 `user_input|assistant_final_answer|user_visible_run_state`
  - `dayu/host/compaction.py:40-47` —— `CompactMaterialSection.TRACE_MATERIAL` 分类
- **输入场景**: Compaction 运行时，LLM 收到包含运行期状态事件（进度更新、阶段转换）的 trace 材料
- **实际分支**: LLM 在 compaction 输出中可为运行期状态事件标注 `trace_kind: user_visible_run_state`
- **预期行为**: 运行期状态不应作为 LLM 需要理解和分类的 `trace_kind` 合法值；Host 应在注入 trace 材料前过滤/改写治理事件
- **实际行为**: "run state" 是 Host/Engine 治理概念，LLM 被要求理解并处理它。compaction 后的 `forward_intents` 可能被运行期噪音污染
- **直接证据**: prompt 中 `user_visible_run_state` 作为合法 `trace_kind`；Host 在 `compact_material.py` 中构建 `trace_material` 时将运行期状态事件注入 compaction_request
- **影响**: Compaction 可能将 "正在等待工具结果" 误保留为 `pending_user_visible_task`；forward_intents 被运行期噪音污染
- **建议改法和验证点**: 从 `trace_kind` 枚举移除 `user_visible_run_state`；如需保留用户可见进度，由 Host 在注入时改写为 `user_input` 或 `assistant_final_answer` 类型的等价表述
- **修复风险（低）**: 某些运行期状态确实包含业务相关信息（如 "正在处理第三章"），简单丢弃可能丢失进度上下文。需要 Host 侧做语义提取后再注入
- **严重程度（中）**: Medium —— 违反 CLAUDE.md "不得把系统状态、调度状态、Host/Engine 内部治理信息伪装成财报事实"

### 7. [MEDIUM] `readable_source_text` 混合内部 ref（`tool_result_event:xxx` / `digest:xxx`）与业务文本，下游用黑名单过滤

- **入口/函数**: `_readable_source_text_from_refs` → `_llm_facing_evidence_source_text`
- **文件(行号)**:
  - `dayu/host/compact_material.py:2420-2431` —— `_readable_source_text_from_refs` 将 `OpaqueEvidenceRef.ref_kind:ref_id` 拼接入 `readable_source_text`
  - `dayu/host/run_input.py:233-241` —— `_INTERNAL_EVIDENCE_SOURCE_PREFIXES` 黑名单（`tool_call_event:`, `tool_result_event:`, `event:`, `eventlog:`, `payload:`, `artifact:`, `digest:`）
  - `dayu/host/run_input.py:3035-3058` —— `_llm_facing_evidence_source_text` 用黑名单过滤
- **输入场景**: 证据材料被构造为 `RunInputMaterialBlock`，其 `readable_source_text` 字段包含混合内容
- **实际分支**: 生产方（`compact_material.py`）将内部 ref ID 与业务分类拼接为一个纯文本字段；消费方（`run_input.py`）用黑名单过滤还原
- **预期行为**: `RunInputMaterialBlock` 应区分业务可读类别与内部 ref 描述符，LLM-facing 路径只取前者
- **实际行为**: 字段名 "readable" 暗示 LLM 可直接消费，但实际包含内部治理标识；黑名单在消费方自行维护，不在生产方契约中
- **直接证据**: `_readable_source_text_from_refs` 将 `OpaqueEvidenceRef`（包含 Host 内部分配的不透明 `ref_id`）格式化为 `ref_kind:ref_id` 字符串直接写入 `readable_source_text`；下游必须逐一匹配黑名单前缀做字符串过滤
- **影响**: 若新增内部 ref 类型，黑名单需手动同步更新；当前有效但防御边界在消费方而非生产方
- **建议改法和验证点**: 在 `RunInputMaterialBlock` 上新增 `source_category_labels` 字段（纯业务可读），与现有 `readable_source_text` 分离；或将 `readable_source_text` 重命名为 `source_note_raw`，由生产方直接构造不含内部标识的版本
- **修复风险（低）**: 当前黑名单过滤正确，问题在可维护性而非正确性
- **严重程度（中）**: Medium —— 违反 "memory/evidence material 必须提供业务可读语义；不得用裸 event_id、payload_ref、digest 代替模型完成任务所需的信息"

### 8. [MEDIUM] Tool schema description 承诺的具体输出格式与 `wait_adapter._completed_outcome()` 实际投影格式不一致

- **入口/函数**: `build_fins_download_tool()` / `build_fins_preprocess_tool()` / `build_fins_upload_tool()` → `_completed_outcome()`
- **文件(行号)**:
  - `dayu/fins/tools/download_tools.py:153` —— `"结果会说明发现、下载、跳过、拒绝和失败的文档数量。"`
  - `dayu/fins/tools/preprocess_tools.py:150` —— `"结果会说明选中、处理、跳过和失败的文档数量。"`
  - `dayu/fins/tools/upload_tools.py:246` —— `"结果会说明上传、删除、转换或失败情况。"`
  - `dayu/fins/ingestion/wait_adapter.py:451-458` —— 实际输出为通用 `{operation, status, title, details: [{label, value}]}` 结构
- **输入场景**: Ingestion 工具调用完成，LLM 收到工具结果
- **实际分支**: Tool schema description 由各工具独立撰写，承诺具体字段；但实际 LLM-facing 输出由 `wait_adapter.py` 统一构造为通用 `title + details` 结构
- **预期行为**: Description 承诺与 actual output 应来自同一 contract 或至少互相校验
- **实际行为**: Description 承诺的字段名（"发现、下载、跳过、拒绝"）与实际输出的 `{label, value}` 结构无编译期或运行时校验
- **直接证据**: description 字符串在 download/preprocess/upload_tools.py 各自手写；actual output 在 wait_adapter.py:451-458 统一构造为 `_completed_outcome()` 的通用格式
- **影响**: LLM 根据 schema description 预期收到结构化计数，但实际收到通用 `{title, details}`；LLM 必须自行从 `details` 数组解析业务语义
- **建议改法和验证点**: 将工具描述改为通用承诺（如 "结果会以摘要形式说明操作执行情况"），或在 `_completed_outcome()` 中按工具类型提供差异化结构化输出
- **修复风险（中）**: 若改 description 为通用承诺，可能降低 LLM 对输出的信任度；若改 `_completed_outcome()` 为差异化输出，需要 wait_adapter 感知工具类型
- **严重程度（中）**: Medium —— 两个模块对同一 LLM-facing 事实（"工具返回结果的格式"）各自独立定义，无 contract 绑定

### 9. [MEDIUM] Preprocess 失败判定规则（`not_supported` / `failed` / `processed` 的布尔组合）在两个消费者中 copy-paste 重复

- **入口/函数**: `_produce_direct_preprocess` 与 `_run_preprocess_job`
- **文件(行号)**:
  - `dayu/fins/ingestion_runtime.py:2769-2784` —— `_produce_direct_preprocess` 的失败判定
  - `dayu/fins/ingestion_runtime.py:3198-3204` —— `_run_preprocess_job` 的失败判定
- **输入场景**: 预处理完成，需判断整体是否成功
- **实际分支**: 两处完全相同的布尔表达式：`summary.processed_count == 0 and (summary.selected_count == 0 or summary.failed_count > 0 or len(summary.not_supported_document_ids) > 0)`
- **预期行为**: 判定规则应是 `FinsPreprocessResultSummary` 的一个方法（如 `is_successful()`），作为该语义的唯一真源
- **实际行为**: 判定逻辑在两个 consumer（direct stream 路径和 job 路径）各自 copy-paste 重建
- **直接证据**: 两次出现的布尔表达式字符级相同，且在 Finding 1 的语义 bug（`skipped_count` 包含 `not_supported`）中，两处都绕过 `skipped_count` 直接用 `not_supported_document_ids` —— 说明它们被同步维护但无共享 contract
- **影响**: 修改判定规则（如 "`not_supported_count > 0` 不算失败"）需要改两处；若不同步，两条路径的行为会分歧
- **建议改法和验证点**: 在 `FinsPreprocessResultSummary` 上提供 `is_successful() -> bool` 方法；两处 consumer 改为调用该方法
- **修复风险（低）**: 纯提取共享方法，不改变判定逻辑
- **严重程度（中）**: Medium —— 业务规则（"何时预处理算失败"）的 source of truth 未被收敛到 domain 模型

### 10. [MEDIUM] CLI 层重复了 Service 层 `_ensure_result_event` 的缺失结果事件构造（死代码在错误边界）

- **入口/函数**: `_consume_fins_direct_events` → `_missing_result_event`
- **文件(行号)**:
  - `dayu/cli/commands/fins.py:715-731` —— `_consume_fins_direct_events` 在 `async for` 循环后检查 `event.result is None` 并调用 `_missing_result_event()`
  - `dayu/cli/commands/fins.py:899-920` —— CLI 层自己的 `_missing_result_event()` 构造 Fins 业务结果事件
  - `dayu/service/fins_direct.py:485-510` —— Service 层的 `_ensure_result_event()` 已保证每个流都以 RESULT 事件结束
- **输入场景**: Fins direct 命令（download/upload/process）的事件流在未产生 RESULT 事件时结束
- **实际分支**: Service 层的 `_ensure_result_event` 已保证每个流都会 yield RESULT 事件（即使流提前结束也 yield failure RESULT），CLI 层的检查代码永远不会触发
- **预期行为**: CLI 层应信任 Service 层的契约；若 Service 层保证被绕过，应抛出硬错误而非静默构造 fallback
- **实际行为**: CLI 层保留了一个永远不会触发但会静默掩盖 Service 层契约缺失的 dead code path
- **直接证据**: `fins_direct.py:485-510` —— `_ensure_result_event` wrapper 保证流结束前必定 yield RESULT；`fins.py:726` —— CLI 层的 `_missing_result_event()` 调用是死代码
- **影响**: 若未来新增 Fins 流源未使用 `_ensure_result_event`，CLI fallback 会静默产生虚假 FAILURE 事件，而非让缺失契约暴露
- **建议改法和验证点**: 从 CLI 移除此 fallback；若 `async for` 正常完成（无 RESULT），抛出 `RuntimeError` 或 `FinsDirectUsageError`
- **修复风险（低）**: 纯删除死代码并替换为显式错误
- **严重程度（中）**: Medium —— CLI 层构造 Fins 业务结果事件，违反 "CLI 只消费 Service 层事件并渲染" 的边界；当前是死代码但掩盖了潜在契约缺失

### 11. [MEDIUM] `HostApiError` 结构化错误处理在 prompt / interactive / session 命令间不一致

- **入口/函数**: `run_prompt_command` / `run_interactive_command` / `run_session_command`
- **文件(行号)**:
  - `dayu/cli/commands/session.py:152-155,621-642` —— session 命令有专用 `_host_error_context(exc)` 格式化和 `_exit_code_for_host_error(exc)` 退出码映射（NOT_FOUND → 2, 其余 → 1）
  - `dayu/cli/commands/prompt.py:143-146` —— prompt 命令将 `HostApiError` 作为通用 `Exception` 捕获：`render_cli_error(f"dayu-cli prompt: {exc}")` 并返回退出码 1
  - `dayu/cli/commands/interactive.py:209-212` —— interactive 命令同样作为通用异常处理
- **输入场景**: Host 返回结构化错误（如 `NOT_FOUND`、`INVALID_STATE`）
- **实际分支**: session 命令展示 `host_code=NOT_FOUND host_message=...` 并返回退出码 2；prompt/interactive 打印 `dayu-cli prompt: NOT_FOUND: ...` 并返回退出码 1
- **预期行为**: `HostApiError` 的呈现格式和退出码映射应在所有命令间共享
- **实际行为**: Prompt 和 interactive 用户得到更差的错误消息（无 code/message 分离），且退出码语义不一致（NOT_FOUND 在 session 返回 2=用法错误，在 prompt/interactive 返回 1=通用失败）
- **直接证据**: session.py:632-642 有完整的 `_exit_code_for_host_error` 映射；prompt.py:143 用通用 `except Exception as exc` 捕获 `HostApiError`
- **影响**: Shell 脚本调用者无法可靠区分 "NOT_FOUND"（用法错误）和真正的运行时失败
- **建议改法和验证点**: 在 CLI 共享模块（如 `output.py`）添加 `render_host_api_error()` 和 `exit_code_for_host_api_error()`；三个命令的异常处理程序统一使用
- **修复风险（低）**: 仅影响 CLI 错误呈现层
- **严重程度（中）**: Medium —— 同一结构化错误的治理逻辑（格式化和退出码）在三个命令中各自实现，consumer 体验不一致

### 12. [MEDIUM] `ingest_method` 字符串标志位在 4 个模块各自硬编码、各自松散解析

- **入口/函数**: `ingest_method` 的写入与读取分布在多个模块
- **文件(行号)**:
  - `dayu/fins/ingestion_runtime.py:81` —— `_DOWNLOAD_INGEST_METHOD: Final[str] = "download"`
  - `dayu/fins/pipelines/sec_upload_workflow.py:221` —— `"ingest_method": "upload"`（硬编码在 meta dict）
  - `dayu/fins/pipelines/sec_rebuild_workflow.py:122` —— `str(previous_meta.get("ingest_method", "")).strip().lower() != "download"`（排除式过滤）
  - `dayu/fins/domain/document_models.py:351,377` —— `ingest_method: str = "download"`（在 rejected artifact 模型）
- **输入场景**: 文档的来源判别（download vs upload）需要在 rebuild workflow 中过滤
- **实际分支**: rebuild workflow 使用排除式过滤（`!= "download"`），而非白名单显式匹配
- **预期行为**: `ingest_method` 应定义为 enum（如 `IngestMethod`）或 Literal type；所有写入方使用该类型，读取方使用类型匹配
- **实际行为**: 4 个位置以字符串字面量写入和读取；rebuild workflow 的 `!= "download"` 排除式过滤意味着新增 `ingest_method="manual"` 会被静默放过
- **直接证据**: `sec_rebuild_workflow.py:122` 的过滤逻辑是 `!= "download"` 而非 `in {IngestMethod.DOWNLOAD}`
- **影响**: 新增 ingest 方式时，rebuild workflow 的过滤逻辑可能静默放过不应处理的文档
- **建议改法和验证点**: 在 domain 层定义 `IngestMethod` 枚举；所有写入方使用 enum 值；读取方使用 enum 匹配
- **修复风险（低）**: 需修改 4 个模块的字符串为 enum 引用；已有的 persisted meta dict 中 `ingest_method` 是字符串，需在边界处转换
- **严重程度（中）**: Medium —— 文档来源判别标志在 4 个模块中无统一类型契约，依赖字符串字面量和排除式过滤

## Open Questions

1. **Finding 1 的 persisted job record 影响面**：已有 job record 的 `skipped_count` 在修复后会变低——是否有 dashboard、监控告警或下游分析脚本依赖该数值？
2. **Finding 5 的 evidence_kind 迁移路径**：若将 `evidence_kind` 从 LLM 输出 schema 移除、改为 Host 预标注，compaction prompt 的结构化输出 schema 需要变更——这是否影响已有的 compacted memory 的向后兼容？
3. **Finding 8 的 wait_adapter 工具感知**：`_completed_outcome()` 当前不感知工具类型，若改为按工具类型差异化输出，wait_adapter 需要工具类型感知——这会引入 wait_adapter 对 tool provider 的耦合，是否可接受？

## Residual Risk

- **测试覆盖不足**：本次 review 未逐行走读 `dayu/fins/processors/` 下的所有 form processor（约 30 个文件），也未完整审查 `tests/` 目录。这些区域可能存在额外的 semantic ownership 违规。
- **跨 shard 盲区**：5 个 shard 独立审查不同的模块边界，可能存在跨边界（如 Fins tools → Config prompt → Host wait_adapter 的端到端链路）的 semantic ownership 违规未被单独捕获。
- **Finding 7 的黑名单维护**：`_INTERNAL_EVIDENCE_SOURCE_PREFIXES` 黑名单当前正确但依赖人工维护；若未来新增内部 ref 类型而未同步更新黑名单，LLM 上下文可能重新被治理标识污染。
- **Finding 5/6 的 compaction 端到端验证**：compaction 输出的 `evidence_kind` 和 `trace_kind` 分类正确性目前无自动化验证——依赖 LLM 自行判断的分类可能在生产中漂移。

---

**Review 完成时间**: 2026-07-09 12:44 UTC+8

**Review Agent**: AgentDS (Fins / CLI / config / prompt / LLM-facing 主线)

**Sub-agent shards**: a28b881e (Fins ingestion), a34ec4fb (Fins tools/schema), a382ed6e (CLI/UI), aea517ae (Config/prompt), a3a4e2cc (LLM-facing/docs/tests)
