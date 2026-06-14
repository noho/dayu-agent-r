# WU-CLI-01 Plan Review — Adversarial Evidence-Based Review

- **Reviewed target**: `docs/host/wu-cli-01-cli-entrypoint-plan.md`
- **Work unit**: WU-CLI-01 CLI entrypoint integration aligned with dayu-agent CLI
- **Gate**: plan review only
- **Design sources**: `docs/host/design.md`, `docs/engine/design.md`
- **Control doc**: `docs/host/ui-implementation-control.md`
- **Review timestamp**: 2026-06-14T12:57:29+08:00
- **Reviewer**: AgentDS (adversarial plan review)

## Review Scope

Confirmed by controller and user:
- Include: `init`, `prompt`, `interactive`
- Include Fins direct commands: `download`, `upload_filing`, `upload_material`, `upload_filings_from`, `process`, `process_filing`, `process_material`
- Exclude: write workflow, Host management commands (`host`, `sessions`, `runs`, `cancel`, `conv`), Web/GUI/WeChat/render entrypoints

## Assumptions Tested

1. CLI 只通过 Service assembly 与 Host public API 触达 Host（不绕过）。
2. `watch_session_events` 的 live-only 特性能通过 submit-before watcher attach 实现 race-free。
3. Fins direct commands 不伪装成 Host run，通过 approved Service/Fins boundary 并支持 cancel。
4. `compose_submit_followup_request` 当前固定 `runner_spec=None`、`runner_options=None`、`agent_policy=None`，需要新 Service helper 支持 per-run override。
5. `resolve_runtime_locations` 需要 optional explicit config overlay 参数扩展。
6. 旧 CLI 参数面 audit 准确，每个 unsupported flag 都有 intentional deviation 说明。
7. AGENTS 约束（中文 docstring、严格类型、禁止 Any/object、无 raw extra payload、禁止反向依赖、Fins storage 只通过 `dayu.fins.storage`）在 plan 的 implementation slices 中得到遵守。

## Findings

### F01 — 严重 — CancelRunRequest 构造所需 context/client_request_id 未被讨论

- **位置**: Plan 第 287 行「Agent prompt / interactive state machine」第 9 步；第 522 行「Prompt command」Cancel behavior；第 587 行「Interactive command」Cancel behavior
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: Plan 多处写 `cancel_run(reason="cli_sigint")`，但没有说明 `CancelRunRequest` 需要的 `context: HostCallContext` 和 `client_request_id: str` 如何构造。
- **反例/失败场景**: `CancelRunRequest` 的实际签名（`dayu/host/api.py:1867-1895`）要求 `context: HostCallContext`、`client_request_id: str`、`reason: str`、`mode: CancelMode`。若 implementation agent 只传 `reason` 而忽略 `context` 和 `client_request_id`，代码无法通过类型检查或运行时校验。CLI adapter 必须在调用 `cancel_run` 前构造有效的 `HostCallContext`（caller/service/source 等字段），并生成幂等 `client_request_id`。
- **为什么有问题**: Plan 把 `cancel_run` 当成简单的 `(run_id, reason)` 调用，忽略了 Host public API 要求的所有必填字段。这会让 implementation agent 在实现时自行设计 HostCallContext 构造策略和 idempotency key 生成策略，而这些本应在 plan gate 明确。
- **直接证据**:
  - `dayu/host/api.py:3253-3255`: `async def cancel_run(self, run_id: str, request: CancelRunRequest) -> RunSnapshot`
  - `dayu/host/api.py:1867-1895`: `CancelRunRequest` 包含 `context`、`client_request_id`、`reason`、`mode` 四个必填字段
- **影响**: 实施 Agent 在 cancel 路径上自行设计 HostCallContext 来源和 client_request_id 生成策略，可能与其他请求（ensure_session、submit_followup）的 context/id 不一致或重复。
- **建议改法和验证点**:
  1. 在 S2（Service boundary）中明确定义 cancel 相关的 `HostCallContext` 构造规则。
  2. 在 `EntrypointTurnRequest` 或新的 cancel request 中增加 `cancel_context` 和 `cancel_client_request_id` 字段，或规定复用 turn 级 context。
  3. 在 Service helper `cancel_entrypoint_run_and_wait(...)` 的参数中显式接收或构造 `CancelRunRequest` 全字段。
  4. 测试中验证 `CancelRunRequest` 字段完整性。
- **修复风险**: 低。只需在 Service helper contract 中补充字段，不改变 Host API。
- **严重程度**: 严重
- **推荐裁决**: accepted — 必须在 implementation 前补充

### F02 — 高 — ReadOutboxTerminalItemsRequest 的 cursor 管理缺口

- **位置**: Plan 第 282-285 行「Agent prompt / interactive state machine」第 7 步 outbox fallback；S2 第 435-436 行
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: Plan 说「调用 public `read_outbox_terminal_items(...)` 查找同一 `run_id` 的 terminal item」，但没有说明 `ReadOutboxTerminalItemsRequest` 需要的 `after: OutboxTerminalCursor`（含 `event_sequence: int`）如何获取。
- **反例/失败场景**: `ReadOutboxTerminalItemsRequest`（`dayu/host/api.py:2746-2771`）要求 `after: OutboxTerminalCursor`，其 `event_sequence` 是「调用方已经处理的 terminal EventLog sequence 水位」。但 plan 的 fallback 场景是 live watcher 未能产出 terminal —— 此时 Service 可能没有任何已处理的 terminal event_sequence。若传 0 或随意值，可能读到不该读的历史 terminal 或漏掉本 run 的 terminal。`OutboxTerminalItemsBatch` 还返回 `projection_status`（CAUGHT_UP/LAGGED/FAILED），plan 没有说明如何处理 LAGGED 或 FAILED 状态下的重试或报错。
- **为什么有问题**: Cursor 是 outbox read 的核心参数，缺失管理策略意味着 implementation agent 必须自行设计 cursor 的生命周期（初始值、如何从 watcher 事件提取、如何在多次 poll 间推进）。这属于 plan 不可直接实施的缺口。
- **直接证据**:
  - `dayu/host/api.py:2746-2751`: `ReadOutboxTerminalItemsRequest` 包含 `after: OutboxTerminalCursor` 和 `seen_terminal_event_ids: tuple[str, ...]`
  - `dayu/host/api.py:2603-2623`: `OutboxTerminalCursor` 含 `event_sequence: int`
  - `dayu/host/api.py:2816-2836`: `OutboxTerminalItemsBatch` 含 `projection_status`、`has_more` 等字段
- **影响**: 实施 Agent 自行设计 cursor 策略，可能导致 outbox read 永远读不到正确的 terminal item、读到旧 terminal、或在 projection lagged 时错误地认为 terminal 丢失。
- **建议改法和验证点**:
  1. 在 S2 中明确 outbox cursor 管理策略：
     - 初始 cursor 从 watcher 已消费的最后一个 `HostEvent.event_sequence` 派生（即使该 event 不是 terminal）。
     - 若 watcher 完全未产出任何事件，初始 cursor 使用 `event_sequence=0`。
  2. 明确 `projection_status` 处理：CAUGHT_UP 且无匹配 terminal 为 contract violation；LAGGED 时按 poll interval 重试 get_run + read_outbox；FAILED 时升级为 Service error。
  3. 测试中覆盖 projection_status 所有状态路径。
- **修复风险**: 低-中。需要在 Service helper 中增加 cursor 追踪状态，但不改变 Host API。
- **严重程度**: 高
- **推荐裁决**: accepted — 必须在 implementation 前补充

### F03 — 高 — HostCallContext 构造策略未定义

- **位置**: Plan 全文，尤其是 `EntrypointTurnRequest` 定义（第 413-421 行）和 Host public API 调用点列表（第 224-234 行）
- **问题类型**: 契约缺失 / 架构边界
- **当前写法**: Plan 提到 Host public API 调用点（`ensure_session`、`create_session`、`submit_followup`、`cancel_run` 等）但没有说明 CLI adapter 如何构造这些调用所需的 `HostCallContext`。`EntrypointTurnRequest` 包含 `context: HostCallContext` 但没有说明 `caller`、`service`、`source` 等字段的来源和取值规则。
- **反例/失败场景**: `HostCallContext`（`dayu/host/api.py` 中定义）包含 `caller`、`service`、`source` 和 `metadata` 字段。这些字段需要由 CLI adapter 在每次 Host 调用时构造。若 plan 不定义 construction rule，implementation agent 可能：
  - 在 CLI 命令中硬编码 caller/service 字符串。
  - 为每次 Host 调用创建不一致的 context。
  - 无法区分 prompt 命令和 interactive 命令的调用来源。
  - 未来 Web/GUI 复用 Service helper 时无法传入正确的调用上下文。
- **为什么有问题**: `HostCallContext` 是 Host 调用的公共契约字段，跨所有 Host 命令一致。CLI 作为 UI adapter 必须能构造它，但 Service helper 不应内置 CLI-specific caller identity。Plan 需要在 Service 边界定义 context 构造规则而非留给 CLI 自行填充。
- **直接证据**:
  - `dayu/host/api.py:1935-1967`: `SubmitFollowupRequest` 要求 `context: HostCallContext`
  - `dayu/host/api.py:1867-1881`: `CancelRunRequest` 要求 `context: HostCallContext`
  - `dayu/host/api.py:1674-1702`: `EnsureSessionRequest` 不直接要 context 但 `create_session` 要
  - `dayu/host/api.py:1705-1754`: `CreateSessionRequest` 要求 `context: HostCallContext`
- **影响**: 实施 Agent 自行设计 context 策略，可能与后续 Web/GUI entrypoint 的 context 不兼容；Service helper 的"可复用"目标被削弱。
- **建议改法和验证点**:
  1. 在 `EntrypointRuntimeRequest`（S2）中增加 `caller_identity: str` 字段（如 `"cli"`）。
  2. 在 Service helper 内部统一构造 `HostCallContext(caller=..., service="entrypoint_runtime", source=caller_identity, metadata=())`。
  3. 确保 CLI 和未来 Web/GUI 都通过同一个 `caller_identity` 参数区分来源。
  4. 测试中验证不同入口的 HostCallContext 一致性。
- **修复风险**: 低。只需在 Service dataclass 中增加一个字段，不影响 Host API。
- **严重程度**: 高
- **推荐裁决**: accepted — 必须在 implementation 前补充

### F04 — 中 — compose_submit_followup_request 扩展策略不明确

- **位置**: Plan 第 199 行「可复用 Service boundary」第 3 条；第 422-424 行 S2 allowed changes
- **问题类型**: 不可直接实施 / 架构边界
- **当前写法**: Plan 说「让 `compose_submit_followup_request(...)` 或新增 sibling helper 支持 typed per-run `RunnerCallOptions` / `AgentPolicy` override」。但没有明确选择：是修改现有函数签名增加 override 参数，还是新增独立 helper function。两种选择对现有调用方（如 `utils/smoke_host_public_multiturn.py`）的影响不同。
- **反例/失败场景**:
  - 若修改现有 `compose_submit_followup_request` 增加参数，现有 smoke 脚本调用点需要同步更新，但 smoke 脚本的修改不在本 WU scope 内。
  - 若新增 sibling helper，两个函数之间可能出现重复逻辑或不一致的默认值行为。
  - 当前 `compose_submit_followup_request`（`dayu/service/host_assembly.py:437-474`）硬编码 `runner_spec=None, runner_options=None, agent_policy=None`。新 helper 需要从 `ServiceOpenHostAssemblyResult.ordinary_selection` 和 `agent_policy_config` 中提取值并合并 per-run override。
- **为什么有问题**: Plan 对同一个关键决策给出二选一，implementation agent 必须自行判断。二选一的风险不对称：改现有函数影响外部调用方，新增函数有重复逻辑风险。Plan gate 应该做出明确选择。
- **直接证据**:
  - `dayu/service/host_assembly.py:437-474`: `compose_submit_followup_request` 当前固定传 `None`
  - Plan 第 88 行：`compose_submit_followup_request(...)` 当前把 `runner_spec`、`runner_options`、`agent_policy` 固定为 `None`
- **影响**: 实施 Agent 选择不当会导致 smoke 脚本 break 或 Service helper 过度设计。中风险，因为两种路径都可以后续修正。
- **建议改法和验证点**:
  1. 明确选择：新增 `compose_submit_followup_request_with_overrides(...)` sibling helper，保留原函数给不需要 override 的调用方。
  2. 新 helper 签名显式接收 `ordinary_selection`、`agent_policy_config` 和 `EntrypointRunOverrides`，内部调用原函数后 `replace(...)` 覆盖 runner_options 和 agent_policy。
  3. 验证 smoke 脚本调用不受影响。
- **修复风险**: 低。
- **严重程度**: 中
- **推荐裁决**: accepted — 必须在 implementation 前明确选择

### F05 — 中 — FinsDirectCommandService 方法签名与实际 FinsIngestionRuntime API 之间的映射未细化

- **位置**: Plan CLI-01-S5 第 625-632 行；Plan 第 99 行代码证据
- **问题类型**: 契约缺失
- **当前写法**: Plan 给 `FinsDirectCommandService` 列出 `start_upload_filing(...)` 和 `start_upload_material(...)` 两个方法，但没有说明它们如何在内部映射到 `FinsIngestionRuntime.start_upload(FinsUploadRequest)`。`start_upload` 接受 union type `FinsUploadFilingRequest | FinsUploadMaterialRequest`，而非两个独立方法。
- **反例/失败场景**: Implementation agent 可能在 `FinsDirectCommandService` 中寻找不存在的 `runtime.start_upload_filing(...)` 方法，或者绕过 typed request 直接把 CLI args 传入。
- **为什么有问题**: Service 层的方法命名暗示 Fins runtime 有对应的独立方法，但实际只有一个联合方法。这不是设计错误，但 plan 的表述不够精确，容易让 implementation agent 误解调用路径。
- **直接证据**:
  - `dayu/fins/ingestion_runtime.py:419`: `FinsUploadRequest = FinsUploadFilingRequest | FinsUploadMaterialRequest`
  - `dayu/fins/ingestion_runtime.py:1528-1530`: `def start_upload(self, request: FinsUploadRequest, ...) -> FinsIngestionJobStart`
  - Plan 第 629 行：`start_upload_filing(...)` 和 `start_upload_material(...)` 作为独立方法
- **影响**: 实施 Agent 可能浪费时间寻找不存在的方法；或反向依赖 CLI 自行构造 request。
- **建议改法和验证点**:
  1. 在 S5 中明确 `FinsDirectCommandService.start_upload_filing(...)` 内部构造 `FinsUploadFilingRequest`，调用 `runtime.start_upload(FinsUploadFilingRequest(...))`。
  2. 同样，`start_upload_material(...)` 内部构造 `FinsUploadMaterialRequest`，调用 `runtime.start_upload(FinsUploadMaterialRequest(...))`。
  3. 把这两个 Service 方法标注为 convenience wrapper，注明底层调用 `FinsIngestionRuntime.start_upload`。
- **修复风险**: 低。
- **严重程度**: 中
- **推荐裁决**: accepted — implementation 前在 plan 或 S5 描述中补充映射关系

### F06 — 中 — Interactive 第二轮及之后的 watcher attach 策略不清晰

- **位置**: Plan 第 594 行「Interactive」Tests / validation：「每一轮都在 submit 前 attach watcher；第二轮不得复用上一轮已关闭或已消费完的 terminal wait state」
- **问题类型**: 状态机漏洞
- **当前写法**: Plan 正确地提出每一轮都需要 pre-submit watcher attach，但没有说明：
  1. 第一轮 watcher 在 terminal 后是否关闭/丢弃。
  2. 第二轮如何创建新的 watcher iterator。
  3. 同一个 `session_id` 上多个 watcher iterator 的生命周期管理 —— Host 是否允许同一 session 同时存在多个 active watcher（即使之前的已消费完但未显式 close）。
- **反例/失败场景**: 若第一轮 watcher async iterator 未被正确关闭（`aclose()`），Host 内部可能持有该 session 的 watcher 引用。第二轮创建新 watcher 时可能与旧 watcher 的 cursor 或内部状态冲突。或者，若 Host 允许同一 session 多个 watcher，则第二轮 watcher 可能收到第一轮残留的历史事件，需要通过 `event_sequence` 去重。
- **为什么有问题**: Plan 说「第二轮不得复用上一轮已关闭或已消费完的 terminal wait state」但没有给出具体机制保证这一点。Implementation agent 需要自行管理 watcher 生命周期，可能出错。
- **直接证据**:
  - `dayu/host/api.py:3337-3346`: `watch_session_events` 返回 `AsyncIterator[HostEvent]`，docstring 说「创建 Session live HostEvent 订阅」
  - Host design doc 关于 `watch_session_events` 的详细描述需要进一步查看 `open_host.py` 实现
- **影响**: 多轮 interactive 对话中 watcher 泄漏或事件重复消费，可能导致第二轮永远收不到 terminal 或错误消费第一轮的旧事件。
- **建议改法和验证点**:
  1. 在 Service helper `submit_entrypoint_turn_and_wait(...)` 中明确：每次调用创建新的 watcher iterator，terminal 后显式关闭（`aclose()` 或等价清理）。
  2. 在 Service 内部用 `event_sequence`（从已消费事件中记录最大值）作为去重依据，确保第二轮不被第一轮残留事件干扰。
  3. 在 interactive 测试中验证两轮间 watcher 独立性和事件去重。
- **修复风险**: 低-中。增加 watcher 生命周期管理逻辑。
- **严重程度**: 中
- **推荐裁决**: accepted — implementation 前在 S2 中补充 watcher 生命周期说明

### F07 — 中 — `EntrypointRunOverrides` 缺少 `max_duplicate_tool_calls` 字段

- **位置**: Plan 第 406-412 行 `EntrypointRunOverrides` 定义
- **问题类型**: 契约缺失
- **当前写法**: Plan 声明 `--max-duplicate-tool-calls`、`--duplicate-tool-hint-prompt` 为 intentional deviation（第 146 行），不在 `EntrypointRunOverrides` 中包含。这是正确的 intentional deviation 决策。
- **反例/失败场景**: 无 —— 这个 finding 实际上不是问题。让我撤回...

实际上，让我重新考虑。Plan 第 146 行明确说这些 flags 当前无 Host public per-run typed contract，作为 intentional deviation。这是正确的。这不是 finding。

### F07（修正）— 中 — `resolve_runtime_locations` 扩展参数的层中立性需要验证

- **位置**: Plan 第 199 行；第 391 行 S2 allowed changes
- **问题类型**: 架构边界
- **当前写法**: Plan 要给 `resolve_runtime_locations(...)` 增加 keyword-only `explicit_config_overlay_dir: Path | None = None`。当为 `None` 时保持当前 `workspace/config` 行为。
- **反例/失败场景**: 当前函数签名 `resolve_runtime_locations(*, project_root: Path, package_config_root: Path)`。增加 `explicit_config_overlay_dir` 参数后，当用户传入显式路径时，函数直接使用该路径而不检查 `workspace/config` 是否存在。但函数内部的 `_resolve_prompt_asset_root` 和 `_resolve_scene_manifest_root` 仍然使用 `config_overlay_dir`。如果 `explicit_config_overlay_dir` 指向一个不存在的目录，prompt/scene manifest 会 fallback 到 package 默认值 —— 这可能不是用户期望的行为（用户显式指定了 config 目录就应该能用）。
- **为什么有问题**: 这个参数扩展本身合理，但需要明确：
  1. 当 `explicit_config_overlay_dir` 指向不存在的目录时，是报错还是静默 fallback？
  2. 当前 `resolve_runtime_locations` 对不存在的 `workspace/config` 静默返回 `None`；对显式传入的路径是否应有不同行为？
- **直接证据**: `dayu/runtime/location.py:32-62`: 当前实现
- **影响**: 用户用 `--config /wrong/path` 时可能静默使用包默认配置，而不是报错。
- **建议改法和验证点**:
  1. 明确：`explicit_config_overlay_dir` 非 `None` 但目录不存在时应抛出 `RuntimeLocationError`，而不是静默 fallback。
  2. 在 S2 测试中覆盖显式路径不存在时的错误路径。
- **修复风险**: 低。
- **严重程度**: 中
- **推荐裁决**: accepted — 在 plan 或 S2 中补充 explicit config 路径的行为契约

### F08 — 低 — prompt command `--ticker` slot key 与当前 `prompt.json` manifest 自洽性未验证

- **位置**: Plan 第 497 行 S3：「`--ticker` 写入 scene context slot，字段名必须与当前 `prompt.json` manifest 自洽」
- **问题类型**: 不可直接实施 / open question 未收敛
- **当前写法**: Plan 要求字段名与 manifest 自洽，但没有给出当前 `prompt.json` manifest 中 `context_slots` 的实际定义。Implementation agent 需要自己去读 manifest 确定 slot key。
- **反例/失败场景**: 若 `prompt.json` manifest 的 `context_slots` 定义的是 `ticker` 但 CLI 传的是 `stock_ticker`，Service assembly 阶段的 `ScenePrepare` 会因为 required slot 未满足而失败。Plan 没有给出这个 slot key，implementation agent 可能猜错。
- **为什么有问题**: Plan 中直接引用 `prompt.json` manifest 但没有提供其实际 content。这不是设计问题，但 plan 应该包含 manifest 中 context_slots 的具体 key（如 `ticker`），避免 implementation agent 需要自行探查。
- **直接证据**: Plan 第 96 行提到 `dayu/config/prompts/manifests/` 现有 `prompt.json`、`interactive.json`
- **影响**: 低 —— implementation agent 只需读一下 manifest 文件就能确定 key。但如果 manifest 未来变化，CLI slot key 需要同步更新。
- **建议改法和验证点**:
  1. 在 plan 中补充当前 `prompt.json` manifest 的 `context_slots` 定义。
  2. 在 S3 测试中使用真实的 `prompt.json` manifest 做 ScenePrepare 集成验证。
- **修复风险**: 低。
- **严重程度**: 低
- **推荐裁决**: accepted — implementation 前补充 manifest slot key 引用

### F09 — 低 — `init --reset` 的数据安全边界描述可以更精确

- **位置**: Plan 第 762-763 行 S7
- **问题类型**: 契约缺失
- **当前写法**: `--reset` 只删除本项目当前 init 拥有的 workspace config / `.dayu` runtime dirs；禁止删除用户财报数据，除非有专门参数和确认流程。本 WU 不新增该危险能力。
- **反例/失败场景**: Plan 说「禁止删除用户财报数据」但没有定义「用户财报数据」的路径白名单。Implementation agent 需要判断哪些目录属于财报数据（`workspace/fins` 下的内容？还是用户指定的其他路径？）。如果 `workspace/fins` 在 `.dayu` runtime dirs 之外，它是安全的；但如果 `.dayu` 和 `workspace/fins` 有重叠或 implementation agent 误解了清理范围，可能意外删除数据。
- **为什么有问题**: 数据删除是高风险操作。Plan 表述为 policy 声明而非可验证的路径约束。Implementation agent 需要自行确定清理范围。
- **直接证据**: Plan 第 762-763 行
- **影响**: 低 —— `workspace/fins` 通常在 `workspace/` 下，与 `workspace/config` 和 `.dayu` 显式分离。但表述不够精确。
- **建议改法和验证点**:
  1. 在 S7 中明确定义 `--reset` 的清理路径白名单：`workspace/config/` 和 `<project_root>/.dayu/`（或等价 runtime dir），并显式排除 `workspace/fins/`。
  2. 在 `init` 命令中硬编码目录名白名单，不做模式匹配。
  3. 测试中验证 reset 不触碰 Fins data fixture。
- **修复风险**: 低。
- **严重程度**: 低
- **推荐裁决**: accepted — implementation 前在 S7 中明确路径白名单

### F10 — 低 — 部分旧 CLI 参数审计中 `--debug-sse` 等的 intentional deviation 归类可能有歧义

- **位置**: Plan 第 146 行
- **问题类型**: 范围漂移 / open question 未收敛
- **当前写法**: `--debug-sse`、`--debug-tool-delta`、`--debug-sse-sample-rate`、`--debug-sse-throttle-sec`、`--enable-tool-trace`、`--tool-trace-dir`、`--max-duplicate-tool-calls`、`--duplicate-tool-hint-prompt` 当前无 Host public per-run typed contract，作为 intentional deviation，不做静默忽略。
- **反例/失败场景**: 「不做静默忽略」的具体行为是什么？Plan 在 Success Signal 中说 unsupported flags 应该「fail fast」，但第 146 行只说「不做静默忽略」，没有明确是报错还是警告后继续。对比其他 intentional deviation（如 `--infer`、`--ci`）plan 明确说「执行时报 unsupported」。这里的不一致可能让 implementation agent 困惑。
- **为什么有问题**: 同一类处理策略（unsupported flag）在 plan 中有不同表述，implementation agent 需要自行判断是报错、警告还是忽略。Plan 应统一表述为：解析保留但执行时报 `unsupported` 错误并 exit 2。
- **直接证据**: Plan 第 146 行 vs 第 144 行（`--infer` 明确 `unsupported`）vs 第 162 行（`--ci` 明确 `unsupported`）
- **影响**: 低 —— implementation agent 大概率按 fail fast 处理。但表述不一致可能导致个别 flag 被静默忽略。
- **建议改法和验证点**: 将第 146 行的表述与 `--infer`/`--ci` 统一为：「解析保留，但执行时报 `unsupported` 并 exit 2，不做静默忽略」。
- **修复风险**: 低。
- **严重程度**: 低
- **推荐裁决**: accepted — 统一表述即可

## Open Questions

1. **`HostCallContext` 字段语义确认**：`HostCallContext` 的 `caller`、`service`、`source` 字段的取值是否有项目级约定？如 `caller="cli"`、`service="entrypoint_runtime"`、`source="dayu-cli"`？需要与 Host 设计真源确认是否存在 caller identity 的命名约束或保留前缀。

2. **同一 session 多个 watcher 共存**：Host 是否允许同一 session 上同时存在多个 active `watch_session_events` iterator？如果允许，它们的 cursor 是否独立？如果 interactive 每轮创建新 watcher 而旧 watcher 未显式 `aclose()`，Host 如何处理？建议在 S2 实现前通过 Host API 源码或 Host 设计 doc 确认。

3. **`EntrypointRunTerminalResult` 中 `source` 字段值**：Plan 第 286 行说 terminal 来源为 `live_event` 或 `outbox_read`。是否还有第三种情况 —— watcher 不产出 terminal 但 `get_run` 显示终态且 outbox 也查不到（plan 第 285 行说这是 contract violation）？如果是，建议增加 `source=contract_violation` 状态而不是直接抛异常，以便调用方记录诊断信息。

## Residual Risks

| Risk | Impact | Owner / Destination | Planned Handling |
| --- | --- | --- | --- |
| `cancel_run` 的 `CancelRunRequest.mode` 当前只允许 `graceful`，不支持 force-cancel。 | 用户第二次 SIGINT 后本地退出，但远端 run 可能仍在 graceful cancel 阶段运行。 | Host owner；后续 Host cancel mode 扩展。 | Plan 已指出第二次 SIGINT 本地退出并打印 run id。风险可接受。 |
| Interactive REPL 中的输入态/运行态边界检测依赖 `asyncio` event loop 集成。 | 在 `asyncio.run()` 的单次调用中混合 REPL 输入（同步阻塞）和 async event loop 可能复杂。 | CLI owner；CLI-01-S4。 | Plan 选择 `asyncio.run` 做 async/sync 边界，实现需仔细处理 input() 阻塞与 event loop 的关系。 |
| `upload_filings_from` 的旧文件识别规则能否从当前 Fins domain 自洽迁移。 | 批量脚本生成 parity 风险。 | Fins owner；CLI-01-S6。 | Plan 已有 stop condition 和降级策略。 |
| Plan 的 `EntrypointRuntimeRequest` 缺少 `env` 字段和 `host_runtime` override，这些在 `ServiceOpenHostAssemblyRequest` 中存在。 | Service helper 可能无法向 `compose_open_host_options` 传递必要的 env/secrets 和 host_runtime override。 | Service owner；S2。 | `EntrypointRuntimeRequest` 已包含 `env: Mapping[str, str]`；但 `host_runtime_id` override 在 `ServiceAssemblyOverrides` 中已有。风险低。 |
| Plan 未讨论 workspace root 自动检测（当前目录向上查找 `workspace/config` 或 `.dayu` marker）。 | `--base` 未指定时 CLI 行为未定义。 | CLI owner；CLI-01-S3/S4。 | 旧 CLI 默认 `./workspace`；plan 应明确默认行为。 |

## Final Plan Review Conclusion

**结论**: **pass-with-risks**

Plan 的架构方向正确：CLI 作为 UI adapter，prompt/interactive 通过 ConfigLoader → ScenePrepare → ToolsDiscovery → Service assembly → Host public API 触达 Host，Fins direct commands 通过 approved Service/Fins boundary。关键架构边界（不导入 Engine 内部、不绕过 Host public API、不直接读 Fins storage）得到遵守。7 个 implementation slices 按依赖顺序排列合理，每个 slice 有明确的 allowed files、tests、completion signal 和 stop condition。

**阻塞性问题（3 个，必须在 implementation 前解决）**：
- F01: `CancelRunRequest` 的 `context`/`client_request_id` 构造策略未定义
- F02: `ReadOutboxTerminalItemsRequest` 的 cursor 管理未定义
- F03: `HostCallContext` 的构造策略未定义

**非阻塞性问题（7 个，建议在 implementation 前或期间解决）**：
- F04-F10: 见上文 findings

**无架构级阻断**：Plan 没有违反分层边界、没有反向依赖、没有让 CLI 直接操作 Engine/Fins storage。旧 CLI 审计完整，intentional deviation 记录清晰。

Plan 在补充 F01-F03 后即可安全交给 implementation agent。
