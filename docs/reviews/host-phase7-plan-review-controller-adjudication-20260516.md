# Host Phase 7 Plan Review Controller Adjudication - 2026-05-16

## 结论

Controller 裁决：Phase 7 plan 不能直接进入 implementation gate，必须先做 plan fix。

两路 plan review：

- `docs/reviews/host-phase7-plan-review-mimo-20260516.md`：pass-with-risks，提出 1 个高严重度 finding、2 个中严重度 finding、2 个低严重度 finding。
- `docs/reviews/host-phase7-plan-review-ds-20260516.md`：FAIL，提出 3 个高严重度 finding、3 个中严重度 finding，并列出 3 个需要 plan 明确的 open questions。

裁决：接受全部 findings 作为 plan fix scope；不需要回到 design discussion。所有问题都是 plan 规格、测试矩阵、helper
交付物或 slice ownership 不够具体，未推翻 `docs/host/design.md` 的 Phase 7 架构方向。

## Accepted Findings

### PF1 accepted - late result diagnostic 与 wait resolution idempotency 顺序冲突

来源：MiMo-1。

要求：plan 必须明确 late result 对已 `cancelled` / `lost` / terminal wait record 不属于有效 resolution 幂等重放候选。
pipeline 应先读取 wait record status；若状态不可接收新 resolution，则进入 late rejection path，并使用明确的 bounded
diagnostic idempotency 策略。

### PF2 accepted - EngineEvent awaiting / suspended 缺少精确行为矩阵

来源：DS-F1。

要求：plan 必须给出 `(Run.status, Attempt/execution match, accepted refs present, event type)` 行为表。任何
`TOOL_AWAITING` / `RUN_SUSPENDED` EngineEvent 都不得调用 `_close_terminal` 或等价 terminal closeout；匹配 accepted refs
只能 diagnostic / idempotent confirmation；缺失 refs 只能 diagnostic / stale reject，不能创建 wait record 或让 Run 进入
`WAITING`。

### PF3 accepted - WAITING cancel 与现有 cancel 状态机集成锚点不明确

来源：DS-F2。

要求：plan 必须指定 `cancel_run` / `cancel_session_runs` 的 WAITING 分支放入哪个模块和服务路径、调用哪个 durable helper、
CAS 前置条件是什么、是否追加 `ATTEMPT_CANCELLED`、after-commit poller notification 如何表达，以及两条 public cancel 路径如何复用同一核心 helper。

### PF4 accepted - WAITING -> RUNNING transition helper 缺失

来源：DS-F3。

要求：plan 必须新增 Run / Attempt / dispatch transition helper 交付物，例如
`resume_run_from_waiting(...)` 或等价 helper；明确 CAS 前置条件、写入字段、返回类型、事件 refs 与 dispatch record 创建边界。

### PF5 accepted - `TOOL_RESULT_ACCEPTED` wait resolution payload 扩展字段未指定

来源：MiMo-2。

要求：plan 必须列出 wait resolution 场景下 `TOOL_RESULT_ACCEPTED` payload 增量字段，至少包含 `wait_id`、
`resolution_source`、`resolution_kind`、`outcome_digest`、`wait_record_status_before` 与 optional refs；同时区分既有 ordinary
tool result 字段与 wait-specific 字段。

### PF6 accepted - key/ref 长度约束未具体化

来源：MiMo-3。

要求：plan 必须给出 `WaitAdapterKey`、`external_job_id`、`snapshot_id`、provider status ref 等字符串字段的具体长度上限，
并说明约束在 dataclass validation、DDL CHECK 或两者中如何保持一致。

### PF7 accepted - `ToolFactKind.LOST` slice ownership 不明确

来源：MiMo-4。

要求：plan 必须把 `ToolFactKind.LOST` 的新增放入具体 slice 的 exact changes 和 allowed files，避免 P7-S3 需要修改未授权文件。

### PF8 accepted - outcome digest / payload ref 互斥语义需写清

来源：MiMo-5。

要求：plan 必须明确 lost outcome 没有 `payload_ref`，非 lost outcome 没有 `provider_status_ref`，digest 输入覆盖所有非空
typed fields 并包含 `None` sentinel，避免同构 digest。

### PF9 accepted - poller 生命周期与并发模型未指定

来源：DS-F4。

要求：plan 必须明确 Phase 7 第一版 poller 运行模型、启动 / 停止边界、Host handle / transaction 调用约束，以及 restart
恢复与 Phase 11 的关系。

### PF10 accepted - resolved / failed wait different-key 拒绝测试缺失

来源：DS-F5。

要求：plan 必须新增测试：已 `resolved` / `failed` wait record 收到不同 `idempotency_key` 的 `resolve_wait` 时返回
`INVALID_STATE`，且不追加 canonical fact、不创建 Attempt。

### PF11 accepted - late diagnostic idempotency 策略未收敛

来源：DS-F6。

要求：plan 必须直接选择策略。Controller 裁决为：使用独立 `wait_late_rejection` idempotency scope，scope id 为 `wait_id`，
idempotency key 使用 caller key；同 key + same late digest 返回既有 diagnostic refs，同 key + different late digest 返回
idempotency conflict diagnostic / error，不追加无限 diagnostic events。

### PF12 accepted - open questions must be answered in plan

来源：DS open questions。

要求：

- `HostPayloadRef` 移入 `dayu.host.api` 后，plan 必须要求更新 ToolRuntime import。
- `_event_payload.py` 的具体新增 payload helper 归属必须写入 slice exact changes。
- `ResolveWaitRequest.context` 保留，仍作为 mutating request 的 `HostCallContext`。

## Fix Scope

Plan fix agent 只能修改：

- `docs/host/phase7-tool-awaiting-resolve-wait-plan.md`
- `docs/reviews/host-phase7-plan-fix-codex-20260516.md`

不得修改设计真源、总控文档、代码、测试或其它 review artifacts。

## Re-review Gate

Plan fix 完成后，必须由 AgentMiMo 与 AgentDS 做 plan re-review。两路均 PASS 且无 accepted blocking finding 后，controller
才能进入 accepted plan commit gate。
