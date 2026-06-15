# WU-CLI-01 Plan Re-Review — AgentDS Adversarial Verification Pass

- **Reviewed target**: `docs/host/wu-cli-01-cli-entrypoint-plan.md`（fix 后版本）
- **Work unit**: WU-CLI-01 CLI entrypoint integration
- **Gate**: plan re-review gate（plan fix 后二次 review）
- **Previous reviews**:
  - `docs/reviews/plan-review-20260614-130113.md` (MiMo)
  - `docs/reviews/wu-cli-01-plan-review-ds.md` (DS)
- **Controller adjudication**: `docs/reviews/wu-cli-01-plan-review-controller-adjudication.md`
- **Fix report**: `docs/reviews/wu-cli-01-plan-fix-codex.md`
- **Re-review timestamp**: 2026-06-14T13:26:21+08:00
- **Reviewer**: AgentDS

## Re-Review Stance

本轮只做 re-review：逐项验证 fix report 中 claimed "已修复" 的 12 个 accepted findings 是否真正关闭，
范围不超出 controller adjudication 确定的 fix scope。不新增 implementation，不修改 plan。

验证方法：对照 plan 当前文本、真实 Host/Fins API 源码、真实 config manifest，逐条判定。

---

## Accepted Findings 逐项验证

### 1. CancelRunRequest uses context/client_request_id/reason/mode=CancelMode.GRACEFUL

| 属性 | 结论 |
|------|------|
| 状态 | **已修复** |

**证据**：

- Plan line 339-341（state machine step 9）：
  `构造 CancelRunRequest(context=<cancel HostCallContext>, client_request_id=<本 turn 本 run 稳定 cancel id>, reason="cli_sigint", mode=CancelMode.GRACEFUL)`
- Plan line 491-492（S2 `cancel_entrypoint_run_and_wait` 参数 `EntrypointCancelRequest` 含 `mode: CancelMode`）
- Plan line 511（S2 helper 构造）：
  `CancelRunRequest(context=request.context, client_request_id=request.client_request_id, reason=request.reason, mode=request.mode)`
- Plan line 608（S3 prompt cancel）：完整字段 `context=<cancel context>, client_request_id="dayu-cli:prompt:...", reason="cli_sigint", mode=CancelMode.GRACEFUL`
- Plan line 684（S4 interactive cancel）：同样完整四个字段
- Plan line 514：重复 Ctrl-C 复用同一 `client_request_id`，利用 Host `(run_id, client_request_id)` 幂等
- 真实 API 对照：`CancelRunRequest` at `dayu/host/api.py:1878-1881` 字段为 `context: HostCallContext`、`client_request_id: str`、`reason: str`、`mode: CancelMode`，与 plan 一致
- Plan line 92：明确 `CancelMode` 当前唯一 public 值为 `CancelMode.GRACEFUL`
- S2 测试（line 543）：断言 `CancelRunRequest` 字段完整性，重复 cancel 复用同一 `client_request_id`

**结论**：四个必填字段全部在 plan 中显式定义，幂等策略明确，与真实 Host API 完全一致。

---

### 2. ReadOutboxTerminalItemsRequest uses OutboxTerminalCursor, seen_terminal_event_ids, projection status, has_more, caught-up-without-match handling

| 属性 | 结论 |
|------|------|
| 状态 | **已修复** |

**证据**：

- Plan line 331（state machine step 7 outbox fallback）：
  - 初始 cursor：`OutboxTerminalCursor(event_sequence=last_observed_event_sequence)`，watcher 无产出时 `OutboxTerminalCursor(event_sequence=0)`
  - 请求固定 `ReadOutboxTerminalItemsRequest(after=cursor, seen_terminal_event_ids=tuple(sorted(seen_terminal_event_ids)), limit=50)`
- Plan line 332-336（outbox 四种状态处理）：
  - `has_more=True`：必须继续分页读取，不能睡眠后重头读
  - `projection_status == LAGGED`：重试 `get_run(...)` + outbox read，直到 caught up/failed/找到目标/timeout
  - `projection_status == FAILED`：立即升级为 Service error，包含 `projection_error_code` / `projection_error_message`
  - `projection_status == CAUGHT_UP` + `has_more=False` + 找不到 terminal item + `get_run` 已确认终态：按 contract violation 处理为 Service error
- 真实 API 对照：`ReadOutboxTerminalItemsRequest` at `dayu/host/api.py:2754-2756` 字段为 `after: OutboxTerminalCursor`、`seen_terminal_event_ids: tuple[str, ...]`、`limit: int`，与 plan 一致；`OutboxTerminalCursor` at line 2610 为 `event_sequence: int`；`OutboxTerminalItemsBatch` at line 2816-2836 包含全部 plan 引用的字段
- Plan line 97：正确声明 `OutboxTerminalItem.dedupe_key` 必须等于 `terminal_event_id`，与真实 API line 2699-2701 一致
- S2 测试（line 547）：显式覆盖 `CAUGHT_UP` 命中、`CAUGHT_UP` + `has_more=True` 分页后命中、`CAUGHT_UP` caught-up-without-match 转 Service error、`LAGGED` 重试、`FAILED` 转 Service error

**结论**：cursor 管理策略完整，四种 projection_status 和 has_more 分页全部有显式处理规则，与真实 Host API 一致。

---

### 3. HostCallContext uses real fields actor/source/request_id/authorization_claims/operation_context, and UI adapter vs reusable Service boundary is clear

| 属性 | 结论 |
|------|------|
| 状态 | **已修复** |

**证据**：

- Plan line 91：显式声明真实字段为 `actor: str`、`source: str`、`request_id: str`、`authorization_claims: tuple[AuthorizationClaim, ...]`、`operation_context: OperationContext`，且明确"本计划不得使用 review artifact 中旧表述的 caller / service / metadata 字段名"
- 真实 API 对照：`HostCallContext` at `dayu/host/api.py:1330-1334` 字段完全一致
- Plan line 295-296：明确职责划分——"CLI / UI adapter 负责构造 HostCallContext，因为 actor、source、auth claims、用户可见 command / scene / ticker 都来自入口层；reusable dayu.service.entrypoint_runtime 只接收并透传 context，不在 Service helper 内硬编码 CLI 身份"
- Plan line 297-307：CLI 默认值全部具体定义：
  - `actor="cli-user"`
  - `source="dayu-cli"`
  - `request_id="dayu-cli:<command>:<uuid4hex>:<operation>"`（每次 Host API 调用生成新 id）
  - `authorization_claims=()`
  - `operation_context.operation_name`: `dayu_cli.<command>.<operation>`
  - `operation_context.operation_kind`: `cli_prompt` / `cli_interactive` / `cli_init` / `cli_fins_direct`
  - `operation_context.business_domain`: `fins`（不写 `host` 伪装管理面）
  - `operation_context.business_object_type/business_object_id`: 仅在用户提供 `--ticker` 时设 `"ticker"` / ticker 值
  - `operation_context.scenario`: scene id（`prompt` / `interactive`）或 Fins direct 命令名
  - `operation_context.correlation_id`: 本次 CLI invocation id
- 真实 API 对照：`OperationContext` at `dayu/host/api.py:1253-1259` 包含 `operation_name`、`operation_kind`、`business_domain`、`business_object_type`、`business_object_id`、`scenario`、`correlation_id`，与 plan 完全一致
- Plan line 308：`cli_invocation_id = uuid4().hex`，interactive 每轮递增 `turn_index`，Service helper 不生成这些入口身份 id
- Plan line 309-313：`HostCallContext.request_id` 与 mutating request `client_request_id` 明确分开，各有生成规则
- S2 测试（line 543）：断言 `HostCallContext` 字段必须为当前 `dayu.host.api` 真实字段

**结论**：HostCallContext 字段使用真实 API 字段名，UI adapter 与 Service boundary 职责清晰分离，所有 CLI 默认值具体可实施。

---

### 4. compose_submit_followup_request_with_overrides + ServiceRunOverrides shape is concrete and reusable

| 属性 | 结论 |
|------|------|
| 状态 | **已修复** |

**证据**：

- Plan line 209-210：选择"保留现有 `compose_submit_followup_request(...)` 行为不变；新增 `ServiceRunOverrides` 与具体 sibling helper `compose_submit_followup_request_with_overrides(...)`"——不再是二选一
- Plan line 252-258：`ServiceRunOverrides` 字段明确定义：
  - `temperature: float | None`
  - `tool_execution_timeout_seconds: float | None`
  - `max_iterations: int | None`
  - `fallback_mode: str | None`
  - `fallback_prompt: str | None`
  - `max_consecutive_failed_tool_batches: int | None`
- Plan line 259-263：`compose_submit_followup_request_with_overrides(...)` 参数和内部逻辑明确：
  - 参数包含 `context`、`session_id`、`client_request_id`、`scene_inputs`、`user_prompt`、`tool_names`、`behavior`、`target_run_id`、`host_assembly`、`run_overrides`
  - 内部先调用既有 `compose_submit_followup_request(...)` 生成 base request
  - 再用 `ordinary_selection` 与 `agent_policy_config` 生成完整 typed `RunnerCallOptions` / `AgentPolicy`
  - `dataclasses.replace(...)` 覆盖到 `runner_options` / `agent_policy`，不传 patch dict
- Plan line 470：`EntrypointRuntimeRequest` 从 `dayu.service.host_assembly` 复用 `ServiceRunOverrides`，不在 entrypoint runtime 里重复定义
- Plan line 493：固定使用 `dayu.service.host_assembly.compose_submit_followup_request_with_overrides(...)`，不得在 `entrypoint_runtime.py` 里另写第二套 override merge

**结论**：策略明确（新增 sibling 不修改现有函数），`ServiceRunOverrides` 字段和 `compose_submit_followup_request_with_overrides` 签名具体，合并逻辑可跟踪，复用边界清晰。

---

### 5. Fins upload wrapper maps to FinsIngestionRuntime.start_upload typed union API

| 属性 | 结论 |
|------|------|
| 状态 | **已修复** |

**证据**：

- Plan line 102：正确声明 `FinsUploadRequest` 是 `FinsUploadFilingRequest | FinsUploadMaterialRequest` 联合类型，runtime 没有 `start_upload_filing(...)` 或 `start_upload_material(...)` 方法
- Plan line 728：`start_upload_filing(...)` wrapper 构造 `FinsUploadFilingRequest(ticker=..., source_kind=SourceKind.FILING, action=..., files=..., fiscal_year=..., fiscal_period=..., amended=..., filing_date=..., report_date=..., company_name=..., ticker_aliases=..., overwrite=...)`，再调用 `FinsIngestionRuntime.start_upload(request, cancellation_token=...)`
- Plan line 729：`start_upload_material(...)` wrapper 构造 `FinsUploadMaterialRequest(ticker=..., source_kind=SourceKind.MATERIAL, action=..., files=..., form_type=..., material_name=..., document_id=..., internal_document_id=..., fiscal_year=..., fiscal_period=..., amended=..., filing_date=..., report_date=..., company_name=..., ticker_aliases=..., overwrite=...)`，再调用 `FinsIngestionRuntime.start_upload(request, cancellation_token=...)`
- Plan line 741-745：upload call path 固定为 CLI → `FinsDirectCommandService.start_upload_filing/material(...)` → typed request → `runtime.start_upload(request)`，CLI 不直接调用 runtime 也不寻找不存在的方法
- 真实 API 对照：`dayu/fins/ingestion_runtime.py:1528` 提供 `def start_upload(self, request: FinsUploadRequest, ...) -> FinsIngestionJobStart`
- S5 测试（line 774）：upload wrapper tests 断言 `start_upload_filing(...)` 传入 `FinsUploadFilingRequest`、`start_upload_material(...)` 传入 `FinsUploadMaterialRequest`

**结论**：wrapper 语义明确标注为 convenience wrapper，内部显式构造 typed request 后调用 `runtime.start_upload(...)` union API，不假想不存在的独立方法。

---

### 6. Interactive watcher lifecycle has attach-before-submit, aclose, multi-turn isolation, failed/cancelled/lost policy

| 属性 | 结论 |
|------|------|
| 状态 | **已修复** |

**证据**：

- Plan line 324（attach 顺序）："在提交 follow-up 前调用 `watch_session_events(session_id)`，立即创建 live watcher"，调用点早于 `submit_followup(...)`
- Plan line 349（aclose）："实现应定义窄 `ClosableHostEventIterator` Protocol 表达 `aclose()`，fake Host watcher 也实现它，避免把 watcher 生命周期留给 GC"
- Plan line 350（multi-turn isolation）："interactive 多轮不得复用上一轮 watcher、queue、cursor 或 `seen_*` 集合；只可在 CLI 输出层保存已展示 terminal 的高水位用于用户界面去重，不可影响下一轮 Host terminal wait 的 run_id 过滤"
- Plan line 329（per-turn 去重集合）：每 turn 维护 `last_observed_event_sequence`、`seen_event_ids: set[str]`、`seen_terminal_event_ids: set[str]`、`seen_dedupe_keys: set[str]`，用 `event_id` / `dedupe_key` / `event_sequence` 去重
- Plan line 328（watcher queue 缓存）："watcher queue 可以先收到 terminal，再等 `submit_followup(...)` 返回；Service 在知道 `accepted_run_id` 后再按 run id 过滤"
- Plan line 349：每次 `submit_entrypoint_turn_and_wait(...)` 创建新的 watcher、队列和去重集合；terminal/error/cancel/timeout 后取消 drain task 并关闭 watcher
- Plan line 674-678（interactive terminal fatal/nonfatal policy）——见 item 12
- S2 测试（line 545）：fast terminal race test 验证 submit 返回前 terminal 已入 watcher
- S2 测试（line 549）：watcher lifecycle tests 验证每 turn 新 watcher、drain task 取消 + `aclose()` 被调用、第二轮不接收第一轮残留 event、重复 `event_sequence`/`dedupe_key` 不重复返回 terminal

**结论**：watcher 完整生命周期由 plan 显式定义：attach-before-submit、aclose、per-turn 隔离、去重、缓存队列。所有 policy 具体可实施。

---

### 7. Explicit --config behavior is concrete

| 属性 | 结论 |
|------|------|
| 状态 | **已修复** |

**证据**：

- Plan line 123：未传 `--config` 且默认 `workspace/config` 不存在 → 不报错，返回 `config_overlay_dir=None`，使用 package 默认 config
- Plan line 124：传入 `--config` → 相对路径按 project workspace root 解析，再 `expanduser().resolve(strict=False)`；绝对路径直接 resolve
- Plan line 125：显式路径不存在、存在但不是目录、或 resolve 后不在 project workspace root 内 → fail fast，CLI exit 2，不得静默 fallback 到 package 默认配置
- Plan line 126：显式目录存在但缺少 `prompts/` 或 `prompts/manifests/` → 仍作为 config overlay 传给 `ConfigLoader`；prompt asset / manifest root 可按现有 resolver 规则 fallback 到 package 默认
- Plan line 453-455（S2 `resolve_runtime_locations` 扩展）：explicit config overlay 的 resolver 行为与 `--config` CLI 行为对齐

**结论**：四路径（默认存在、默认不存在、显式合法、显式非法）全部显式定义，行为可机械翻译为代码。

---

### 8. --ticker maps to fins_default_subject and base_user defaults are concrete

| 属性 | 结论 |
|------|------|
| 状态 | **已修复** |

**证据**：

- Plan line 99（代码证据）：`prompt.json` 与 `interactive.json` 当前真实 `context_slots` 均为 `fins_default_subject` 与 `base_user`
- 真实 manifest 验证：`dayu/config/prompts/manifests/prompt.json` 和 `interactive.json` 的 `context_slots` 均为 `[{"name": "fins_default_subject", "value_type": "string", "required": true}, {"name": "base_user", "value_type": "string", "required": true}]`
- Plan line 578-581（S3 prompt --ticker mapping）：
  - `--ticker` 映射为 `context_slot_values["fins_default_subject"] = ticker_value.strip()`
  - 未传 `--ticker` 时 `context_slot_values["fins_default_subject"] = "未指定具体公司"`
  - `context_slot_values["base_user"]` 默认 `"本地 CLI 用户"`
- Plan line 648-650（S4 interactive）：同样映射，同样默认值
- Plan line 581：明确约束 "不得把 request_id、event id、cursor 或其它 Host 内部治理 id 塞进 LLM-facing context slot"
- S3 测试（line 619）：prompt manifest integration 使用真实 `prompt.json` 验证两个 slot 均被填充

**结论**：slot key 与真实 manifest 完全对齐，默认值显式定义，semantic safety 约束明确。

---

### 9. init --reset deletion whitelist is explicit and excludes Fins data / runtime lane DB / user files

| 属性 | 结论 |
|------|------|
| 状态 | **已修复** |

**证据**：

- Plan line 870-877（S7 Exact allowed changes）：
  - 允许删除：`<project_root>/workspace/config/`、`<project_root>/workspace/.dayu/host/`、`<project_root>/workspace/.dayu/artifacts/`、`<project_root>/workspace/.dayu/web_tools_storage_states/`
  - 不允许删除整个 `<project_root>/workspace/.dayu/`（可能包含本 WU 未拥有的 runtime 文件）
  - 尤其不删除 `<project_root>/workspace/.dayu/runtime/runtime_lanes.sqlite3`
  - 不允许删除 `<project_root>/.dayu/`（可能包含 Fins ingestion jobs、SEC cache/throttle、Fins storage batch/backup/lock 状态）
  - 不允许删除 `<project_root>/workspace/fins/`、`<project_root>/fins/`、用户 upload 源目录、用户输出目录或任何不在白名单内的普通文件
- Plan line 876：白名单路径 resolve 后必须仍位于 `<project_root>/workspace/` 下；symlink 逃逸 → fail fast，exit 2，不递归删除
- Plan line 877：白名单路径不存在时跳过，不算错误
- Plan line 870：使用硬编码删除白名单，禁止 glob/pattern 删除
- S7 测试（line 906）：断言 `workspace/.dayu/runtime/runtime_lanes.sqlite3`、`<project_root>/.dayu/`、`workspace/fins/` 和用户普通文件 fixture 均保留

**结论**：白名单枚举精确到具体路径，排除列表显式覆盖 Fins 数据、runtime lane DB、用户文件，symlink 逃逸有防御。可机械翻译为代码。

---

### 10. Unsupported old flags fail fast with exit 2, no silent ignore, no raw payload

| 属性 | 结论 |
|------|------|
| 状态 | **已修复** |

**证据**：

- Plan line 152-153（旧执行覆盖参数 deviation）：
  - `--debug-sse`、`--debug-tool-delta`、`--debug-sse-sample-rate`、`--debug-sse-throttle-sec`、`--enable-tool-trace`、`--tool-trace-dir`、`--max-duplicate-tool-calls`、`--duplicate-tool-hint-prompt`："parser 保留这些旧参数以便给出稳定错误；命令执行前统一 fail fast，输出 unsupported option，exit 2；不得警告后继续、静默忽略或 forward 到 Host raw payload"
- Plan line 162：`--infer`（download）"解析保留但执行时报 unsupported"
- Plan lines 163-164：`--infer`（upload）、`--ci`（process 系列、process_filing、process_material）同样 "解析保留但执行时报 unsupported"
- Plan line 169：`write` 命令不注册，运行走 argparse invalid choice，exit code 2
- Plan line 170：`host`、`sessions`、`runs`、`cancel`、`conv` 不注册
- Plan line 263：unsupported 在 CLI 参数转换阶段 exit 2，不进入 Service helper
- Plan line 584-585（S3）：unsupported 旧执行项报清晰错误并 exit 2
- 全局统一使用公式：parser 保留 → 执行前 fail fast → exit 2 → 不静默忽略，不 raw payload forward

**结论**：所有 unsupported flags 统一 fail-fast 策略，表述从 ambiguous "不做静默忽略" 统一为 "fail fast + exit 2 + no silent ignore + no raw payload"。排除命令走 argparse invalid choice exit 2。

---

### 11. Fins direct poll interval has named default

| 属性 | 结论 |
|------|------|
| 状态 | **已修复** |

**证据**：

- Plan line 369：`DEFAULT_FINS_DIRECT_POLL_INTERVAL_SECONDS = 1.0`
- Plan line 370：`FinsDirectCommandService` constructor 接收 `poll_interval_seconds: float = DEFAULT_FINS_DIRECT_POLL_INTERVAL_SECONDS` 与可注入 `sleep` coroutine
- Plan line 371：`poll_interval_seconds` 必须为有限正数，建议上限 60 秒；非法值在 Service 构造或命令参数转换阶段 fail fast，CLI exit 2
- Plan line 372：测试断言默认值为 1.0 秒，`QUEUED` / `RUNNING` / `CANCELLING` 路径调用注入 sleep，terminal status 不再 sleep
- S5 测试（line 775）：assert default `poll_interval_seconds == 1.0` and fake sleep is called only for nonterminal statuses
- Plan line 371：本 WU 不新增用户可见 `--poll-interval`，"避免扩大旧 CLI 参数面"

**结论**：默认值命名化、可注入、有验证、有测试。用户界面不扩大（follow-up WU 可加 `--poll-interval`）。

---

### 12. Interactive terminal fatal/nonfatal policy is concrete

| 属性 | 结论 |
|------|------|
| 状态 | **已修复** |

**证据**：

- Plan line 674-678（S4 Error handling）：
  - `SUCCEEDED`：输出 final answer，回到输入态
  - `FAILED`：输出 `error_message` 或 fallback 错误文案，回到输入态，exit code 暂不结束进程
  - `CANCELLED`：输出取消状态，回到输入态；用户 Ctrl-C 触发时 cancel 操作记 130 语义但 interactive 进程继续运行
  - `LOST`：fatal，输出 lost 诊断，退出 interactive，exit 1
  - Host handle closed、Service assembly error、outbox projection `FAILED`、caught-up-without-match contract violation：fatal，退出 interactive，exit 1
- Plan line 682-685（interactive cancel behavior）：
  - 输入态 Ctrl-D：退出 0
  - 输入态 Ctrl-C：清空当前输入或退出当前 command
  - 运行态第一次 Ctrl-C：构造 `CancelRunRequest(...)`，等待 terminal 并回到输入态
  - 运行态第二次 Ctrl-C：本地 exit 130；若已有 run id，必须已发出 cancel
- S4 测试（line 695）：terminal failed / cancelled / lost 的展示与 fatal / non-fatal 策略

**结论**：四种终态全部有显式 fatal/nonfatal 归类，Host 级错误和 contract violation 也有明确策略，可机械翻译为代码。

---

## 额外裁决重点验证

### 迁移语义而非旧实现

- Plan line 19（Motivation 段首）："它不是迁移旧代码实现，也不能把旧实现目录结构、label registry、dependency setup、interactive UI 或旧 contracts 机械搬进当前仓库"——显式声明
- Plan line 322-323（session label）：使用 Host slot key 语义（`cli.prompt.<label>` / `cli.interactive.<label>`），不依赖旧 label registry 文件
- Plan line 582：明确 "不得使用旧 label registry 文件"
- Plan line 159（init）"不得生成旧 llm_models.json / run.json，不得跑旧 migrations"
- Plan line 160（prompt --ticker）：映射为新 `fins_default_subject` slot，不使用旧 `prompt_mt` 场景
- Plan line 656：交互 UI "不复制旧 interactive_ui.py 的复杂渲染系统"

**验证通过**：plan 固定使用当前 Host public API、Fins runtime API、新 config schema，所有旧实现引用均为 command surface audit 对照源，不复制旧实现结构。

### 只走 Service -> Host public API，Service/Fins approved boundary

- Plan line 232-243（Host public API 调用点白名单）：只允许 `open_host`、`ensure_session`、`create_session`、`submit_followup`、`watch_session_events`、`get_run`、`read_outbox_terminal_items`、`cancel_run`、`cancel_session_runs`
- Plan line 244："不得导入 Host store、scheduler、command/read internal API"
- Plan line 204（CLI 模块允许导入）：`dayu.service`、`dayu.runtime` 基础错误类型、`dayu.fins` 枚举/request 类型和只读 domain value；不得导入 `dayu.engine` 内部
- Plan line 228（Fins storage）："CLI 不直接读取 workspace/fins 下文件结构"
- Plan line 71-72（Fins direct command）："不创建 Host Run，不写 Host EventLog，不使用 Host wait record"
- Plan line 225-228（Fins boundary）："Fins document storage 只通过 dayu.fins.storage 仓储协议与 DefaultFinsRuntime 间接触达"
- Plan line 336（outbox fallback 边界）："不得读取 Host durable internals"

**验证通过**：所有调用点符号化到 Host public API 方法名，Engine internals、Host durable internals、Fins storage scattered reads 均有显式禁止条款。

---

## 最终 Re-Review 结论

**结论：pass**

所有 12 个 controller-adjudicated accepted findings 均处于 **已修复** 状态。逐项对照 plan 当前文本与真实 Host/Fins API 源码、真实 config manifest 后确认：

- 无遗漏字段（CancelRunRequest、HostCallContext、ReadOutboxTerminalItemsRequest、OutboxTerminalCursor 全部使用真实 API 字段）
- 无 ambiguous 二选一（`compose_submit_followup_request_with_overrides` 策略已固定为 sibling helper）
- 无隐式默认值（所有 default 值、slot key、poll interval、path whitelist 均显式字面量）
- 无旧实现 leak（label、init、override、interactive UI 均使用当前 typed contracts）
- 无边界 violation（所有调用只通过 Host public API 和 Service/Fins approved boundary）

本轮未发现新 material finding。Plan 已 code-generation-ready。

## Artifact Path

`docs/reviews/wu-cli-01-plan-rereview-ds.md`
