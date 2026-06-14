# WU-CLI-01 Plan Re-Review Gate

## Gate

- Work unit: WU-CLI-01 CLI entrypoint integration aligned with dayu-agent CLI
- Gate: plan re-review (post-fix verification)
- Plan artifact: `docs/host/wu-cli-01-cli-entrypoint-plan.md`
- Previous reviews: `docs/reviews/plan-review-20260614-130113.md`, `docs/reviews/wu-cli-01-plan-review-ds.md`
- Controller adjudication: `docs/reviews/wu-cli-01-plan-review-controller-adjudication.md`
- Fix report: `docs/reviews/wu-cli-01-plan-fix-codex.md`
- Re-review timestamp: 2026-06-14T13:35:51+08:00
- Reviewer: AgentMiMo (adversarial re-review)

## Scope

本轮 re-review 的目标是：逐项验证 controller adjudication 中 accepted findings 是否在 plan fix 后真正关闭，同时检查 fix 是否引入新问题、是否仍在复制旧实现或依赖旧内部边界。

## Accepted Findings Verification

### Finding 1: CancelRunRequest uses context/client_request_id/reason/mode=CancelMode.GRACEFUL

**状态：已修复 ✓**

Plan 当前写法（直接代码证据）：

- Plan 第 339 行：`CancelRunRequest(context=<cancel HostCallContext>, client_request_id=<本 turn 本 run 稳定 cancel id>, reason="cli_sigint", mode=CancelMode.GRACEFUL)`
- Plan 第 490 行 `EntrypointCancelRequest` 定义：`context: HostCallContext`、`run_id: str`、`client_request_id: str`、`reason: str`、`mode: CancelMode`
- Plan 第 511-512 行：`CancelRunRequest(context=request.context, client_request_id=request.client_request_id, reason=request.reason, mode=request.mode)`
- Plan 第 608 行 prompt cancel：完整 `CancelRunRequest` 四字段构造
- Plan 第 684 行 interactive cancel：完整 `CancelRunRequest` 四字段构造
- Plan 第 312 行：重复 Ctrl-C 复用同一 `client_request_id` 的幂等策略

与 `dayu/host/api.py:1866-1895` 的 `CancelRunRequest(context, client_request_id, reason, mode)` 完全对齐。`CancelMode.GRACEFUL` 是当前唯一 public 值（`dayu/host/api.py:326-332`）。幂等策略通过 `(run_id, client_request_id)` 复用实现。

---

### Finding 2: ReadOutboxTerminalItemsRequest uses OutboxTerminalCursor, seen_terminal_event_ids, projection status, has_more, caught-up-without-match handling

**状态：已修复 ✓**

Plan 当前写法（直接代码证据）：

- Plan 第 329 行：Service 维护 `seen_terminal_event_ids: set[str]`，terminal event 的 `event_id` 加入该集合
- Plan 第 331 行：Outbox fallback 初始 cursor 为 `OutboxTerminalCursor(event_sequence=last_observed_event_sequence)`；watcher 无事件时用 `event_sequence=0`
- Plan 第 331 行：`ReadOutboxTerminalItemsRequest(after=cursor, seen_terminal_event_ids=tuple(sorted(seen_terminal_event_ids)), limit=50)`
- Plan 第 332 行：每批扫描 `item.run_id == accepted_run_id` 的 terminal item，用 `item.dedupe_key` 去重
- Plan 第 333 行：`has_more=True` 时继续分页读取，不睡眠后重头读
- Plan 第 334 行：`projection_status == LAGGED` 时按 poll interval 重试
- Plan 第 335 行：`projection_status == FAILED` 时升级为 Service terminal observation error，包含 `projection_error_code` / `projection_error_message`
- Plan 第 336 行：`projection_status == CAUGHT_UP` 且 `has_more=False` 仍找不到同 run terminal，同时 `get_run(...)` 已确认终态：按 Host public projection contract violation 处理为 Service error

与 `dayu/host/api.py` 的 `ReadOutboxTerminalItemsRequest`（L2745-2771）、`OutboxTerminalCursor`（L2603-2623）、`OutboxTerminalItemsBatch`（L2815-2836）、`OutboxProjectionStatus`（L2543-2555）完全对齐。所有三种 projection status 都有明确处理路径。

---

### Finding 3: HostCallContext uses real fields actor/source/request_id/authorization_claims/operation_context, and UI adapter vs reusable Service boundary is clear

**状态：已修复 ✓**

Plan 当前写法（直接代码证据）：

- Plan 第 90 行：明确指出当前真实字段为 `actor: str`、`source: str`、`request_id: str`、`authorization_claims: tuple[AuthorizationClaim, ...]`、`operation_context: OperationContext`；明确禁止使用旧表述 `caller` / `service` / `metadata`
- Plan 第 293 行：明确 "CLI / UI adapter 负责构造 HostCallContext"
- Plan 第 295 行：reusable `dayu.service.entrypoint_runtime` "只接收并透传 context，不在 Service helper 内硬编码 CLI 身份"
- Plan 第 296-308 行：完整 CLI 默认值定义：`actor="cli-user"`、`source="dayu-cli"`、`request_id="dayu-cli:<command>:<uuid4hex>:<operation>"`、`authorization_claims=()`、`operation_context=OperationContext(...)` 含全部 7 个字段
- Plan 第 308 行："Service helper 不生成这些入口身份 id，只校验传入字段非空并传给 Host request"

与 `dayu/host/api.py:1317-1348` 的 `HostCallContext` 定义完全对齐。`OperationContext` 字段（`operation_name`、`operation_kind`、`business_domain`、`business_object_type`、`business_object_id`、`scenario`、`correlation_id`）与 `dayu/host/api.py:1238-1290` 一致。UI adapter（构造 context）与 Service（透传 context）的职责边界清晰。

---

### Finding 4: compose_submit_followup_request_with_overrides + ServiceRunOverrides shape is concrete and reusable

**状态：已修复 ✓**

Plan 当前写法（直接代码证据）：

- Plan 第 252-263 行：`ServiceRunOverrides` 字段定义为 `temperature: float | None`、`tool_execution_timeout_seconds: float | None`、`max_iterations: int | None`、`fallback_mode: str | None`、`fallback_prompt: str | None`、`max_consecutive_failed_tool_batches: int | None`
- Plan 第 259 行：新增 `compose_submit_followup_request_with_overrides(...)` sibling helper
- Plan 第 260-262 行：内部先调用既有 `compose_submit_followup_request(...)` 生成 base request，再用 `ordinary_selection` 与 `agent_policy_config` 生成完整 typed `RunnerCallOptions` / `AgentPolicy`，最后 `dataclasses.replace(...)` 到 `runner_options` / `agent_policy`
- Plan 第 471 行：从 `dayu.service.host_assembly` 复用 `ServiceRunOverrides`，不在 entrypoint runtime 里重复定义
- Plan 第 263 行：unsupported 旧 flags 在 CLI 参数转换阶段 exit 2，不进入 Service

与 `dayu/service/host_assembly.py:437-474` 的 `compose_submit_followup_request(...)` 当前固定 `runner_spec=None, runner_options=None, agent_policy=None` 一致。sibling helper 策略明确保留原函数给无 override 调用方。`SubmitFollowupRequest`（`dayu/host/api.py:1934-1967`）的 `runner_options: RunnerCallOptions | None` 和 `agent_policy: AgentPolicy | None` 字段与覆盖目标一致。

---

### Finding 5: Fins upload wrapper maps to FinsIngestionRuntime.start_upload typed union API

**状态：已修复 ✓**

Plan 当前写法（直接代码证据）：

- Plan 第 355 行："upload 由 `FinsDirectCommandService.start_upload_filing(...)` / `start_upload_material(...)` wrapper 构造 `FinsUploadFilingRequest` / `FinsUploadMaterialRequest`"
- Plan 第 728 行：`start_upload_filing(...)` 是 "Service-facing convenience wrapper，不要求 runtime 有同名方法"；"构造 `FinsUploadFilingRequest(...)`，再调用 `FinsIngestionRuntime.start_upload(request, cancellation_token=...)`"
- Plan 第 729 行：`start_upload_material(...)` 同理
- Plan 第 745 行："CLI 不直接调用 `runtime.start_upload(...)`，也不寻找不存在的 `runtime.start_upload_filing(...)` / `runtime.start_upload_material(...)`"

与 `dayu/fins/ingestion_runtime.py:419` 的 `FinsUploadRequest = FinsUploadFilingRequest | FinsUploadMaterialRequest` 和 L1528 的 `start_upload(request: FinsUploadRequest, ...)` 完全对齐。wrapper 构造具体 typed request 再调用 union API 的路径明确。

---

### Finding 6: interactive watcher lifecycle has attach-before-submit, aclose, multi-turn isolation, failed/cancelled/lost policy

**状态：已修复 ✓**

Plan 当前写法（直接代码证据）：

- Plan 第 324-325 行：在提交 follow-up 前调用 `watch_session_events(session_id)`，"调用点必须早于 `submit_followup(...)`"
- Plan 第 349 行："实现应定义窄 `ClosableHostEventIterator` Protocol 表达 `aclose()`，fake Host watcher 也实现它"
- Plan 第 349 行："每次 `submit_entrypoint_turn_and_wait(...)` 调用创建新的 watcher、队列和去重集合；terminal、错误、cancel 或 timeout 后必须取消 drain task 并关闭 watcher"
- Plan 第 350 行："interactive 多轮不得复用上一轮 watcher、queue、cursor 或 `seen_*` 集合"
- Plan 第 548-549 行测试："每一轮都在 submit 前 attach watcher；第二轮不得复用上一轮已关闭或已消费完的 terminal wait state"
- Plan 第 549 行测试："每一轮 terminal / error / cancel 后 watcher `aclose()` 被调用"
- Plan 第 676-679 行 interactive fatal/non-fatal：`LOST` fatal 退出，`FAILED` 继续 REPL，`CANCELLED` 继续 REPL，Host handle closed / outbox projection FAILED / caught-up-without-match 为 fatal

与 `dayu/host/open_host.py:544-565` 的 `watch_session_events(session_id) -> AsyncIterator[HostEvent]` 返回 async iterator 一致。attach-before-submit race-free 逻辑（Plan 第 343-348 行）通过 `_session_live_event_start_cursor(...)` 在 submit 前取得 cursor 实现。

---

### Finding 7: explicit --config behavior is concrete

**状态：已修复 ✓**

Plan 当前写法（直接代码证据）：

- Plan 第 122-126 行：
  - 未传 `--config` 且默认不存在：不报错，`config_overlay_dir=None`
  - 传入 `--config`：相对路径按 project workspace root 解析，再 `expanduser().resolve(strict=False)`；绝对路径直接 resolve
  - 显式路径不存在、不是目录或 resolve 后逃逸：fail fast，CLI exit 2
  - 显式目录存在但缺少 `prompts/` 或 `prompts/manifests/`：仍作为 config overlay 传给 `ConfigLoader`
- Plan 第 453-456 行 S2：`resolve_runtime_locations(...)` 增加 `explicit_config_overlay_dir: Path | None = None`；为 `None` 时保持当前行为；非 `None` 时 resolver 校验路径存在且是目录，否则抛 `RuntimeLocationError`
- Plan 第 528 行 S2 error handling：`explicit --config` 不存在、不是目录或路径逃逸映射为 `RuntimeLocationError` / CLI exit 2

行为契约完整：显式路径有 fail-fast，缺失默认路径有 fallback，路径逃逸有 containment 校验。与 `dayu/runtime/location.py` 的扩展方向一致。

---

### Finding 8: --ticker maps to fins_default_subject and base_user defaults are concrete

**状态：已修复 ✓**

Plan 当前写法（直接代码证据）：

- Plan 第 100 行："`dayu/config/prompts/manifests/prompt.json` 与 `interactive.json` 当前真实 `context_slots` 均为 required string：`fins_default_subject` 与 `base_user`"
- Plan 第 160 行 prompt："`--ticker` 映射为 `context_slot_values["fins_default_subject"]`"，缺省为 `"未指定具体公司"`
- Plan 第 161 行 interactive："`--ticker` 映射为 `context_slot_values["fins_default_subject"]`"，缺省为 `"未指定具体公司"`
- Plan 第 581 行 S3：`context_slot_values["fins_default_subject"] = ticker_value.strip()`
- Plan 第 581 行 S3：`context_slot_values["base_user"]` 默认 `"本地 CLI 用户"`
- Plan 第 602 行 S3 stop condition：若未来 `prompt.json` 移除或重命名这些 slot，manifest 集成测试必须失败
- Plan 第 649-650 行 S4：interactive 同样映射

与实际 manifest 的 `context_slots`（`fins_default_subject` + `base_user`）完全对齐。两个 slot 都有明确的 CLI 参数映射和默认值。stop condition 防止 manifest 变化时 CLI 静默失败。

---

### Finding 9: init --reset deletion whitelist is explicit and excludes Fins data / runtime lane DB / user files

**状态：已修复 ✓**

Plan 当前写法（直接代码证据）：

- Plan 第 871-877 行 S7：
  - 允许删除：`<project_root>/workspace/config/`、`<project_root>/workspace/.dayu/host/`、`<project_root>/workspace/.dayu/artifacts/`、`<project_root>/workspace/.dayu/web_tools_storage_states/`
  - 不允许删除整个 `<project_root>/workspace/.dayu/`（尤其不删除 `runtime_lanes.sqlite3`）
  - 不允许删除 `<project_root>/.dayu/`（可能包含 Fins ingestion jobs、SEC cache / throttle、Fins storage batch / backup / lock 状态）
  - 不允许删除 `<project_root>/workspace/fins/`、`<project_root>/fins/`、用户 upload 源目录、用户输出目录或任何不在白名单内的普通文件
  - 白名单路径 resolve 后必须位于 `<project_root>/workspace/` 下；symlink 或逃逸则 fail fast，exit 2
  - 白名单路径不存在则跳过
- Plan 第 906 行 S7 测试："断言 `<project_root>/.dayu/fins_ingestion/jobs/`、`<project_root>/.dayu/sec_cache/`、`<project_root>/workspace/fins/`、`runtime_lanes.sqlite3` 和用户普通文件 fixture 均保留"

白名单明确枚举 4 个允许删除路径，排除列表覆盖 Fins data、runtime lane DB、用户文件。symlink 逃逸防护和路径 containment 校验完整。测试断言覆盖保留路径。

---

### Finding 10: unsupported old flags fail fast with exit 2, no silent ignore, no raw payload

**状态：已修复 ✓**

Plan 当前写法（直接代码证据）：

- Plan 第 153 行：`--debug-sse`、`--debug-tool-delta`、`--debug-sse-sample-rate`、`--debug-sse-throttle-sec`、`--enable-tool-trace`、`--tool-trace-dir`、`--max-duplicate-tool-calls`、`--duplicate-tool-hint-prompt`："parser 保留这些旧参数以便给出稳定错误；命令执行前统一 fail fast，输出 unsupported option，exit 2；不得警告后继续、静默忽略或 forward 到 Host raw payload"
- Plan 第 152 行：`--web-provider`、`--doc-limits-json`、`--fins-limits-json`：同理
- Plan 第 431 行 S1 测试：`unsupported old flags fail fast`
- Plan 第 614 行 S3 测试：`unsupported old flags fail fast`
- Plan 第 36 行 success signal：`旧 CLI command surface audit 完成，每个不对齐点都有 intentional deviation 说明`

所有 unsupported flags 统一行为：解析保留、执行前 fail fast、exit 2、无静默忽略、无 raw payload。与 `--infer`、`--ci` 的处理策略一致。

---

### Finding 11: Fins direct poll interval has named default

**状态：已修复 ✓**

Plan 当前写法（直接代码证据）：

- Plan 第 369 行："在 `dayu/service/fins_direct.py` 定义 `DEFAULT_FINS_DIRECT_POLL_INTERVAL_SECONDS = 1.0`"
- Plan 第 370 行：`FinsDirectCommandService` constructor 接收 `poll_interval_seconds: float = DEFAULT_FINS_DIRECT_POLL_INTERVAL_SECONDS` 与可注入 `sleep` coroutine
- Plan 第 371 行：`poll_interval_seconds` 必须为有限正数，建议上限 60 秒；非法值 fail fast，CLI exit 2
- Plan 第 372 行测试："断言默认值为 1.0 秒，`QUEUED` / `RUNNING` / `CANCELLING` 路径会调用注入 sleep，terminal status 不再 sleep"
- Plan 第 775 行 S5 测试："Fins direct poll tests assert default `poll_interval_seconds == 1.0`"

命名常量 `DEFAULT_FINS_DIRECT_POLL_INTERVAL_SECONDS = 1.0`，构造函数有默认值，注入 sleep 支持测试，非法值校验完整。

---

### Finding 12: interactive terminal fatal/nonfatal policy is concrete

**状态：已修复 ✓**

Plan 当前写法（直接代码证据）：

- Plan 第 676-679 行 S4：
  - `SUCCEEDED`：输出 final answer，回到输入态
  - `FAILED`：输出 `error_message` 或 fallback 错误文案，回到输入态，exit code 暂不结束进程
  - `CANCELLED`：输出取消状态，回到输入态；用户 Ctrl-C 触发的 cancel 操作仍按 130 语义记录，但 interactive 进程继续
  - `LOST`：fatal，输出 lost 诊断，退出 interactive，exit 1
  - Host handle closed、Service assembly error、outbox projection `FAILED`、caught-up-without-match contract violation：fatal，退出 interactive，exit 1

五种终态全部有明确分类：`SUCCEEDED` / `FAILED` / `CANCELLED` 为 non-fatal（继续 REPL），`LOST` 和 service-level errors 为 fatal（退出）。与旧 CLI 的 "interactive 模式在单轮失败时继续 REPL" 行为一致，但更精确。

---

## Fix Quality Assessment

### 新引入问题检查

逐项检查 plan fix 是否引入新的架构问题或契约缺口：

1. **`ClosableHostEventIterator` Protocol**（Plan 第 349 行）：新增窄 Protocol 表达 `aclose()`，这是对 `AsyncIterator[HostEvent]` 的合理细化，不引入过度设计。fake Host watcher 也需实现该 Protocol，确保测试可验证生命周期。**无问题。**

2. **`EntrypointCancelRequest` 独立 dataclass**（Plan 第 487-491 行）：将 cancel 请求从 submit 请求中分离，避免 Service helper 内部隐式构造 cancel context。字段与 `CancelRunRequest` 1:1 对齐但不含 Host 内部类型（除 `CancelMode`）。**无问题。**

3. **`client_request_id` 与 `HostCallContext.request_id` 分离**（Plan 第 309 行）：明确两者必须不同，前者是幂等键，后者是追踪 id。避免实现 agent 混淆。**无问题。**

4. **`EnsureSessionRequest` 无 context / client_request_id**（Plan 第 313 行）：plan 注意到 `EnsureSessionRequest` 当前 public contract 没有这两个字段，并指定 create path 使用 create context。这表明 plan 研究过实际 API，不是假设。**无问题。**

5. **`watch_session_events` cursor 来源**（Plan 第 324 行、第 343-345 行）：plan 明确 `watch_session_events(session_id)` 在内部调用 `_session_live_event_start_cursor(...)` 取 cursor，submit 前 attach 保证本 turn 事件在 cursor 之后。与 `open_host.py:544-565` 实现一致。**无问题。**

6. **`command_watermark` 不作为 watch cursor**（Plan 第 325 行）：plan 明确 `FollowupSnapshot.command_watermark` "只用于诊断，不作为 watch cursor"，与 `dayu/host/api.py:2335` docstring 一致。**无问题。**

### 旧实现 / 旧内部边界依赖检查

Plan 明确声明 "迁移旧代码的业务逻辑/用户可见语义，并适配新的 Host public contracts/API；不是迁移旧代码实现"。逐项验证：

1. **不导入 Engine 内部**：Plan 第 75 行明确 "CLI 不 import `dayu.engine` contract 来构造 `AgentRunRequest`"。第 202 行 "不得导入 `dayu.engine` 内部"。**无违反。**

2. **不读 Host durable internals**：Plan 第 235 行 "不得导入 Host store、scheduler、command/read internal API"。第 336 行 "不得读取 Host durable internals"。**无违反。**

3. **不散落直接读取 Fins storage**：Plan 第 17 行 "必须通过 approved Service / Fins boundary 触达 Fins runtime 与 `dayu.fins.storage`"。第 229 行 "CLI 不直接读取 `workspace/fins` 下文件结构"。**无违反。**

4. **不移植旧 label registry**：Plan 第 583 行 "`--label` 生成 stable Host slot key，例如 `cli.prompt.<label>`；不得使用旧 label registry 文件"。第 704 行 stop condition。**无违反。**

5. **不移植旧 interactive UI 渲染系统**：Plan 第 656 行 "不复制旧 `interactive_ui.py` 的复杂渲染系统"。**无违反。**

6. **不移植旧 workspace migrations**：Plan 第 879 行 "不执行旧 workspace migrations"。**无违反。**

7. **不生成旧 schema 文件**：Plan 第 878 行 "不生成旧 `llm_models.json` / `run.json`"。**无违反。**

## Architecture Boundary Review

### Layering and dependency direction

- CLI -> Service -> Host -> Engine：plan 严格遵守。CLI 只通过 Service helper 调用 Host public API。
- CLI -> Fins（approved boundary）：Fins direct commands 通过 `FinsDirectCommandService`，不直接读 storage。
- Service helper 不持有 CLI argparse / stdout / stderr 概念：Plan 第 218 行明确。
- `dayu.runtime` 是层中立基础设施：`resolve_runtime_locations(...)` 扩展不引入 CLI 依赖。

### Public contract alignment

- `HostCallContext` 字段与 `dayu/host/api.py:1317-1348` 完全一致
- `CancelRunRequest` 字段与 `dayu/host/api.py:1866-1895` 完全一致
- `ReadOutboxTerminalItemsRequest` 字段与 `dayu/host/api.py:2745-2771` 完全一致
- `OutboxTerminalCursor` 字段与 `dayu/host/api.py:2603-2623` 完全一致
- `SubmitFollowupRequest` 字段与 `dayu/host/api.py:1934-1967` 完全一致
- `FinsUploadRequest` union 与 `dayu/fins/ingestion_runtime.py:419` 一致
- `FinsIngestionRuntime.start_upload` 签名与 `dayu/fins/ingestion_runtime.py:1528` 一致

### Overcoupling check

- CLI 与 Service 通过 typed dataclass 交互，不共享可变状态
- Service helper 与 Host 通过 public Protocol 交互
- Fins direct commands 与 Fins runtime 通过 typed request/response 交互
- 每个 slice 有明确的 allowed files，不跨 slice 穿透

## Open Questions

当前没有阻塞 plan 的 open questions。

## Residual Risks

| Risk | Impact | Owner / Destination | Planned Handling |
| --- | --- | --- | --- |
| 旧 `--infer` alias inference 当前无 approved Fins boundary。 | download / upload 与旧 CLI 行为不完全一致。 | Fins owner；后续 Fins alias inference WU。 | WU-CLI-01 解析保留但执行时报 unsupported。 |
| 旧 `--ci` process snapshot 当前无公共 contract。 | process 系列与旧 CLI 不完全一致。 | Fins / tooling owner；后续 CI snapshot contract WU。 | WU-CLI-01 解析保留但执行时报 unsupported。 |
| 旧 debug / trace / duplicate governance flags 无当前 Host public per-run contract。 | 部分 power-user flags 不可用。 | Host / Service owner；后续 observability / per-run governance WU。 | unsupported fail fast。 |
| `upload_filings_from` 的旧文件识别规则可能依赖旧 Fins helper。 | 批量脚本生成 parity 风险。 | Fins owner；CLI-01-S6。 | 在 Fins boundary 建 typed batch plan helper；若无法自洽，降级并登记 deviation。 |
| `--thinking/--no-thinking` 在当前模型 schema 中不是独立布尔开关。 | 旧 CLI 模型选择体验不完全一致。 | Config / Service owner；后续 model profile UX WU。 | 只在当前 model/hint 可明确映射时支持，否则 unsupported。 |
| Fins job cancel 是协作式，部分长事务可能不及时检查 `request_cancel`。 | Ctrl-C 后 terminal 可能延迟。 | Fins runtime owner；现有 ingestion runtime tests。 | CLI 第一次 SIGINT 发 durable cancel，第二次 SIGINT 允许本地退出并打印 job id。 |
| `upload_filing --action delete` 当前是否被 Fins upload runtime 支持未知。 | delete 命令可能执行时报 unsupported。 | Fins owner；CLI-01-S5。 | plan 已说明 "只有当前 upload runtime 支持时放行，否则执行时报 unsupported"。 |

所有 residual risks 都有明确 owner 和 planned handling，无 unowned risk。

## Final Plan Review Conclusion

**结论：pass**

12 个 accepted findings 全部已修复，修复质量高，每个 finding 都有与 `dayu/host/api.py`、`dayu/fins/ingestion_runtime.py`、`dayu/service/host_assembly.py`、`dayu/host/open_host.py` 实际代码的直接对齐证据。Plan fix 未引入新问题，未引入旧实现依赖，未违反架构边界。

Plan 可以安全交给 implementation agent。

## Artifact Path

`docs/reviews/wu-cli-01-plan-rereview-mimo.md`
