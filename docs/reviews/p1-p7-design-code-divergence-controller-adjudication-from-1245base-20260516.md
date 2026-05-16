# P1-P7 Design / Code Divergence Controller Adjudication From 1245 Base

日期：2026-05-16

> Superseded note：本 artifact 是按 `1245aeefeeb182a2da833c8577d701a6a71b7065:docs/host/design.md` 字面基线形成的阶段性裁决。随后用户明确决定 `fetch_more` cursor 只存在内存，并要求其余问题按当前 `docs/host/design.md` 的设计目标与最佳实践重新裁决。最终裁决以
> `docs/reviews/p1-p7-design-goals-controller-decision-20260516.md` 与
> `docs/reviews/p1-p7-design-goals-fix-controller-adjudication-20260516.md` 为准。

设计真源：`1245aeefeeb182a2da833c8577d701a6a71b7065:docs/host/design.md`

当前代码：`fix/host-p1-p7-awaiting-production-wiring`

Review artifacts：

- `docs/reviews/p1-p7-design-code-divergence-review-from-1245base-mimo-20260516.md`
- `docs/reviews/p1-p7-design-code-divergence-review-from-1245base-ds-20260516.md`
- `docs/reviews/p1-p7-design-code-divergence-review-from-1245base-codex-20260516.md`

## Verdict

**FAIL。**

三份 review 均确认此前的 `C-P1P7-001` awaiting production wiring 已在当前分支修复，但 Codex 与 DS 分别发现新的设计偏离。Controller 不按投票裁决，而按 `1245aeefeeb182a2da833c8577d701a6a71b7065:docs/host/design.md` 与当前代码证据裁决。

Accepted findings：

- Blocking：0
- High：2
- Medium：3
- Low：1

## Accepted Findings

### CTRL-1245-H1 — `fetch_more` cursor 只存在于内存，偏离 durable descriptor 设计

- 来源：Codex `COD-001`
- 严重性：High
- 设计证据：1245 base design §19 明确要求 `cursor` / `scope_token` 进入 messages 或 EventLog 后必须可恢复到 durable descriptor，且跨 Host restart、Attempt `LOST`、resume、steer 或 replay 后不能依赖旧远端内存。
- 当前代码证据：`dayu/host/tool_runtime.py:1232-1237` docstring 明确“不写 durable cursor 表，不承诺跨进程、跨 restart、跨 recovery 或 replay 可继续补读”；`dayu/host/tool_runtime.py:1263` 使用 `self._cursors` 内存字典；`dayu/host/tool_runtime.py:1358` 仅从该内存字典读取；`dayu/host/tool_runtime.py:1418` 只写入该内存字典。
- 影响：同一进程同一 Attempt 内可用，但 durable accepted tool fact 不能恢复其补读能力；这与 1245 base design 的 Host-governed cursor descriptor 要求冲突。
- Controller disposition：接受为 High，建议当前修复或在进入 PR 前先形成显式设计变更裁决。

### CTRL-1245-H2 — active worker cancel 依赖模块级全局 registry，绕过 composition root 显式注入

- 来源：DS `DS-P1P7-H1`
- 严重性：High
- 设计证据：1245 base design §10.1 运行参数约束要求影响执行、恢复、投影、工具治理或外部通信的运行参数必须有显式接口由调用方传入，不得只能通过模块级全局变量、隐式单例、环境变量或硬编码路径取得。
- 当前代码证据：`dayu/host/dispatch.py:278` 定义 `DEFAULT_ACTIVE_WORKER_REGISTRY = ActiveWorkerRegistry()`；`dayu/host/dispatch.py:281-288` 的 `cancel_active_worker()` 直接访问该全局变量；`dayu/host/command.py:399-410` 和 `dayu/host/command.py:825-835` 的 cancel propagation 使用该全局函数，Host command handle 没有显式持有同一个 injected registry。
- 影响：`HostDispatchScheduler` 虽支持 `active_registry` 注入，但 command path cancel 不随同一 composition root 注入；多 Host handle、测试隔离或未来 supervisor composition 时存在边界倒挂和错误接线风险。
- Controller disposition：接受为 High，建议当前修复。修复方向应让 command handle / admission cancel propagation 使用 composition root 注入的 active worker registry 或明确的 cancel propagation port。

### CTRL-1245-M1 — `resolve_wait` 幂等 digest 包含 `observed_at`，同一 outcome 重试可能误判冲突

- 来源：Codex `COD-002`
- 严重性：Medium
- 设计证据：1245 base design §20 要求 `resolve_wait` 幂等范围为 `(wait_id, idempotency_key)`；同一幂等键 + 同一 outcome 重试返回既有 RunSnapshot / Attempt refs；同一 key + 不同 outcome 才返回 `idempotency_conflict`。
- 当前代码证据：`dayu/host/waiting.py:1093-1100` 的 `_wait_resolution_digest()` 将 `observed_at` 纳入 semantic digest。
- 影响：同一完成结果在真实 retry 时如果重新生成 `observed_at`，会被判断为不同 semantic input，削弱 poll / callback / manual resolve 的稳定重试语义。
- Controller disposition：接受为 Medium，建议当前修复。`observed_at` 应保留为首次 committed event / audit payload，而不是同 outcome 幂等冲突判定的一部分。

### CTRL-1245-M2 — 缺少 `TOOL_TERMINAL_RESULT` event type

- 来源：DS `DS-P1P7-M1`
- 严重性：Medium
- 设计证据：1245 base design §13.2 列出 `TOOL_TERMINAL_RESULT`，§20 同时要求 wait resolution append tool terminal / result canonical fact。
- 当前代码证据：`dayu/host/durable/run_transition.py` 与 `dayu/host/waiting.py` 当前 wait resolution 使用 `TOOL_RESULT_ACCEPTED`；`TOOL_TERMINAL_RESULT` 字符串在 `dayu/host` 中不存在。
- 影响：EventLog event_type 无法直接区分普通工具 accepted result 与等待完成后的 terminal tool result。该偏离主要影响 audit / trace taxonomy 和后续 projection 接线。
- Controller disposition：接受为 Medium，但修复前需要先确认设计口径：是新增独立 event type，还是正式更新设计说明 `TOOL_RESULT_ACCEPTED` 覆盖 terminal path。

### CTRL-1245-M3 — 缺少 `FOLLOWUP_QUEUED` event type

- 来源：DS `DS-P1P7-M2`
- 严重性：Medium
- 设计证据：1245 base design §13.2 列出 `FOLLOWUP_QUEUED`，并在 control event binding 中说明 `FOLLOWUP_QUEUED` 的 `run_id` 是 queued / created Run。
- 当前代码证据：当前 follow-up queue path 由 `USER_INPUT_ACCEPTED` + `RUN_ACCEPTED` / `RUN_QUEUED` 组合表达；`FOLLOWUP_QUEUED` 字符串在 `dayu/host` 中不存在。
- 影响：EventLog event_type 无法直接区分 start queued Run 与 submit_followup queue 产生的 queued Run，影响 follow-up queue 的审计与 projection 解释。
- Controller disposition：接受为 Medium，但修复前需要先确认设计口径：是新增独立 event type，还是正式更新设计说明现有事件组合等价。

### CTRL-1245-L1 — `cancel_run` docstring 对 WAITING cancel 描述已过期

- 来源：MiMo `DIVERGE-001` 的反向证据
- 严重性：Low
- 设计证据：1245 base design §20 要求 `WAITING` cancel 标记 active wait record cancelled，并拒绝迟到 poll / callback canonical fact。
- 当前代码证据：`dayu/host/admission.py` 当前 `RunStatus.WAITING` 分支调用 `_cancel_waiting()`，说明生产逻辑已实现；但 `dayu/host/command.py:364-371` 和 `dayu/host/command.py:424-431` docstring 仍描述 `WAITING` cancel 由 Phase 7 负责。
- 影响：代码注释与当前实现不一致，容易误导后续 review；不影响生产行为。
- Controller disposition：接受为 Low 文档清理，不阻塞。

## Rejected / Deferred Observations

### REJ-1245-1 — MiMo `cancel_run on WAITING` 未实现

Controller 拒绝该 finding 的主结论。当前 `dayu/host/admission.py` 已在 `RunStatus.WAITING` 分支调用 `_cancel_waiting()`，生产行为不是拒绝 WAITING cancel。保留为 `CTRL-1245-L1` docstring stale。

### REJ-1245-2 — `retry_run` / `replay_run` 未实现

Controller 将 DS `DS-P1P7-M3` 归为后续 phase non-goal。1245 base design 覆盖完整终态能力，但当前 review 明确范围是已实施 P1-P7；retry / replay 属后续 phase，不作为当前偏离阻塞项。

### REJ-1245-3 — recovery、steer、context compaction、guidance 相关事件未实现

Controller 将 DS `DS-P1P7-M4` 归为后续 phase non-goal。当前 P1-P7 不要求这些后续治理路径落地。

### REJ-1245-4 — C-P1P7-001 awaiting production wiring

三方均确认此前 awaiting production wiring 缺口已在当前分支修复。该 finding 保留在历史 artifact 中，不再作为当前 blocking finding。

## Next Gate

当前 review gate 不通过。进入 PR 或继续宣称 P1-P7 与 1245 base design 一致前，需要至少处理以下事项：

1. 修复 `CTRL-1245-H1` fetch_more durable cursor descriptor 偏离，或正式形成设计变更裁决。
2. 修复 `CTRL-1245-H2` active worker registry composition root 偏离。
3. 修复 `CTRL-1245-M1` resolve_wait 幂等 digest。
4. 对 `CTRL-1245-M2` / `CTRL-1245-M3` 做设计口径裁决；若维持 1245 base design，则补齐 event type 或等价 audit/projection 解释。
5. 清理 `CTRL-1245-L1` docstring stale。
