# WU-CLI-SESSION-01 Plan Review

## Review Meta

- **Review Target**: `docs/host/host-issues/wu-cli-session-01-cli-session-management-plan.md`
- **Work Unit**: WU-CLI-SESSION-01, GitHub Issue #145
- **Design Sources**: `docs/host/design.md`, `docs/engine/design.md`
- **Control Doc**: `docs/host/issues-implementation-control.md`
- **Review Type**: Adversarial plan review (planreview)
- **Review Date**: 2026-06-16

## Scope Summary

Plan proposes:
1. Add Host public `list_sessions` API returning `SessionListItem` / `ListSessionsResult`
2. Delete obsolete `interactive --new-session` flag
3. Implement CLI `session list` / `session resume` / `session purge` commands, all based on Host truth
4. CLI `resume` = submit new prompt/interactive turn on existing Host Session; not Host wait-resume, not recover old Agent/Runner/Attempt
5. 6 implementation slices (S1-S6)

## Assumptions Tested

| # | Assumption | Evidence | Verdict |
|---|-----------|----------|---------|
| A1 | `host_sessions` durable row already contains `created_at` / `closed_at` | Verified: `SessionRow` has `created_at: str`, `closed_at: str \| None` (ISO strings) at `dayu/host/durable/state.py:177-192` | **Confirmed** — but stored as `str`, not `datetime` |
| A2 | `session_snapshot_from_rows(...)` is reusable for list conversion | Verified: at `dayu/host/durable/state.py:4327-4349`, uses transaction to query active_run_id + queued_run_ids per session | **Partial** — works but each call triggers 2 extra queries |
| A3 | `purge_session` already enforces CLOSED + terminal Runs precondition | Verified: `dayu/host/command.py:814-877` returns `INVALID_STATE` with message "purge_session requires a closed Session with terminal Runs" | **Confirmed** |
| A4 | `ParsedCliArgs.new_session: bool` is the obsolete field to delete | Verified: `dayu/cli/arg_parsing.py:101`, default `False` at line 207 | **Confirmed** |
| A5 | CLI `interactive` has `args.new_session` branch creating process-temporary Session | Verified: `dayu/cli/commands/interactive.py:279-285`, creates `bind_slot=True` process session | **Confirmed** |
| A6 | `prompt_slot_key` / `interactive_slot_key` helpers at `host_context.py` are reusable for resume-by-label | Verified: `dayu/cli/host_context.py:83-105` | **Confirmed** |
| A7 | No existing `list_sessions` in Host public API, `Host` Protocol, or `_PublicHostHandle` | Verified: grep confirms zero matches across `api.py`, `open_host.py`, `read_api.py`, `__init__.py` | **Confirmed** |
| A8 | `HostApiErrorCode` includes INVALID_STATE, CONFLICT, IDEMPOTENCY_CONFLICT, NOT_FOUND | Verified: `dayu/host/api.py:1187-1196` | **Confirmed** |

---

## Findings

### F-01 [高] SessionListItem.created_at/closed_at 的 datetime 类型与 durable SessionRow 的 str 类型之间存在未说明的转换 gap

- **位置**: 第 6 节"公共契约 / Schema / 状态机变更" — `SessionListItem` dataclass 定义
- **问题类型**: 契约缺失
- **当前写法**: Plan 定义 `created_at: datetime`（timezone-aware UTC）、`closed_at: datetime | None`，并在第 6 节直接代码证据中声称 `host_sessions` row 已包含 `created_at` / `closed_at`
- **反例/失败场景**: `dayu/host/durable/state.py:177-192` 中 `SessionRow.created_at` 是 `str`（ISO format timestamp string），`SessionRow.closed_at` 也是 `str | None`。`session_snapshot_from_rows(...)` 当前并不访问这两个字段——因为 `SessionSnapshot` 没有时间戳字段。implementation agent 需要在 durable read helper 中引入 `datetime.fromisoformat()` 或等价解析，但 plan 未说明：
  - 解析失败（malformed ISO string）时的行为——raise 还是 fallback？
  - 时区处理：`SessionRow` 当前使用 `datetime.now(UTC).isoformat()` 写入，但 durable schema 不强制校验；若未来有非 UTC 时间戳写入，`datetime` 类型无法表达 offset-naive vs offset-aware 的不一致
- **为什么有问题**: Plan 声称 durable row 已就绪，但实际上行级存储格式（str）与公共契约类型（datetime）之间存在转换 gap。若 implementation agent 自行决定转换策略（例如静默 drop malformed timestamp），会导致 review 返工
- **直接证据**: `dayu/host/durable/state.py:177-192` SessionRow 定义；`dayu/host/api.py:2227-2263` SessionSnapshot 不含时间戳字段
- **影响**: 实施 Agent 需自行设计转换契约 → review 发现不一致 → 返工；或静默吞错 → 隐藏 bug
- **建议改法和验证点**:
  1. 在 plan 第 6 节补充：`read_api.list_sessions` 在转换 `SessionRow -> SessionListItem` 时使用 `datetime.fromisoformat()` 解析 `created_at`/`closed_at`，malformed timestamp raise `HostApiError`（不可恢复）
  2. 明确 `SessionListItem` 的 datetime 字段为 timezone-aware UTC，与当前 `SessionRow` 写入路径一致
  3. 若 reviewer 认为 public contract surface 过大，按 plan 第 12 节 open question fallback：从 public dataclass 移除时间戳，CLI 展示使用 raw ISO string
  4. 验证：`test_list_sessions` 覆盖 malformed timestamp 行 → HostApiError
- **修复风险**: 低
- **严重程度**: 高

---

### F-02 [中] SessionListItem 与 SessionSnapshot 的字段不对称——对 Host API 消费者造成困惑

- **位置**: 第 6 节"公共契约 / Schema / 状态机变更" — `SessionListItem` 与既有 `SessionSnapshot`
- **问题类型**: 契约缺失 / 过度设计
- **当前写法**: `SessionListItem` 包含 `created_at` / `closed_at`，而 `SessionSnapshot`（通过 `get_session` 返回）不包含这些字段
- **反例/失败场景**: Service / CLI 通过 `get_session(session_id)` 获取单个 Session 时看不到时间戳，但通过 `list_sessions()` 却能看到。这种不对称性意味着：
  - Service 若需要展示 Session 时间戳，必须始终调用 `list_sessions()` 而非 `get_session()`
  - 新增时间戳仅对 list 路径开放，暗示这是一个"列表专属展示字段"而非 Session 公共事实——但如果时间戳是 durable truth，任何 read path 都应可访问
- **为什么有问题**: 公共 read contract 族不一致。若时间戳是 Host truth（它确实是 durable row 中的列），应该同时加入 `SessionSnapshot`，或明确说明 `SessionListItem` 是 CLI display model 而非 host truth contract。Plan 当前将它定义为 Host public dataclass，位置在 `dayu/host/api.py`，暗示这是 Service-facing truth
- **直接证据**: `dayu/host/api.py:2227-2263` `SessionSnapshot` 字段不含 `created_at`/`closed_at`
- **影响**: 后续 Service 消费者困惑 → 需要在 plan review 阶段裁决，而非留给 implementation agent
- **建议改法和验证点**:
  1. 推荐：将 `created_at`/`closed_at` 同步加入 `SessionSnapshot`（这是最小的设计修正，因为字段已在 durable row 中），`SessionListItem` 复用同一组字段
  2. 备选：明确 `SessionListItem` 是 CLI 专用 display contract，放入 `dayu/cli/` 而非 `dayu/host/api.py`，并移除 Host public contract 中的时间戳字段
  3. 备选：保持当前 plan 但添加注释说明 `SessionSnapshot` 后续 WU 补齐时间戳
  4. 验证：`test_package_exports` 确认两个 dataclass 的时间戳字段一致性
- **修复风险**: 低（推荐方案：在 SessionSnapshot 上加两个字段，follow get_session 已有 pattern）
- **严重程度**: 中

---

### F-03 [中] Slice S5 "抽取可复用内部执行 core" 欠规格——contract shape 未定义

- **位置**: 第 9 节 Slice S5 — "为 prompt / interactive 抽出可复用的内部执行 core"
- **问题类型**: 切片过粗 / 不可直接实施
- **当前写法**: "为 prompt / interactive 抽出可复用的内部执行 core，使调用方可以传入已选定 `session_id`，同时复用 scene/runtime assembly、submit、watcher、outbox fallback、SIGINT cancel 逻辑。不复制 submit/watch/cancel 大段逻辑；如果必须抽取，优先抽到 CLI command 层私有 helper，保持 UI adapter 边界"
- **反例/失败场景**: implementation agent 拿到该 slice 后需要自行设计：
  - 抽取的 core 函数签名是什么？接受什么参数？返回什么？
  - "复用 scene/runtime assembly" 具体指什么——当前 `_ensure_prompt_session` 和 `_ensure_interactive_session` 的装配路径不同，它们的公共部分是什么？
  - 抽取后是否需要修改 `prompt.py` 和 `interactive.py` 中已有函数？这会不会让 S5 的回滚范围超出预期？
  - 如果抽取失败（"跨模块导入大量私有状态"），plan 只说"先重构出小的 CLI-internal helper"，但没有给出最小可验收的 helper contract
- **为什么有问题**: Slice S5 是 6 个 slice 中最复杂的（跨 prompt/interactive/session 三个命令模块），但 plan 对核心设计决策（抽取 contract）的描述最少。implementation agent 可能过度抽取（引入不必要的 abstraction layer）或抽取不足（复制代码）
- **直接证据**: Plan Slice S5 精确变更段（line 506-516）未定义 core function 参数、返回值、异常契约
- **影响**: 实施 Agent 需重新设计 → review 可能要求重写 → 返工；或抽取错误 → 引入不必要耦合
- **建议改法和验证点**:
  1. 在 plan 中补充最小 core contract sketch：函数名、关键参数（`session_id`, `Host handle`, `args`）、返回值类型、异常传播契约
  2. 明确该 core 不应该是新的 abstraction layer——只做参数转发和 lifecycle 编排
  3. 定义"停止条件"触发时的 fallback 行为：如果抽取需要在 prompt.py 和 interactive.py 中做过多改动，允许 S5 内联实现（在 `session.py` 中直接调用 `_ensure_prompt_session` + `submit_followup` 等现有 helper）
  4. 验证：S5 实现后 `prompt.py` / `interactive.py` 原有测试零改动或仅有参数注入改动
- **修复风险**: 中
- **严重程度**: 中

---

### F-04 [中] label 反解算法未定义——带特殊字符的 label 存在解析歧义

- **位置**: 第 7 节 CLI 命令面设计 — `session list` 的 LABEL 列 + 第 8 节 Session 身份模型
- **问题类型**: 契约缺失 / 状态机漏洞
- **当前写法**: "LABEL：从 `cli.prompt.<label>` 或 `cli.interactive.<label>` 反解；anonymous 显示 `-`"。Plan 说 slot_key 格式为 `cli.prompt.<name>` / `cli.interactive.<name>`
- **反例/失败场景**:
  1. 用户 label 包含 `.`（例如 `proj.v1`）：`cli.prompt.proj.v1` 的 strip 前缀 `cli.prompt.` 后得到 `proj.v1`——正确。但若未来 slot_key 格式发生变化（例如引入子命名空间），反向解析将不可靠
  2. 反向解析依赖 slot_key 前缀的字符串操作，但 plan 没有定义：
     - 如果 slot_key 不以 `cli.prompt.` 或 `cli.interactive.` 开头，显示什么？（plan 用 `other` 兜底，但没有说明 `other` 何时会出现）
     - `other` slot 的 `KIND` 显示什么 label？原始 slot_key？`-`？
  3. `Kind` 枚举值在 S3 中定义为 `prompt` / `interactive`，但 slot 反向解析如果同时匹配 `cli.prompt.` 和 `cli.interactive.`（不可能，因为前缀不同），模糊时谁优先？——这不是真问题，但说明算法未形式化
- **为什么有问题**: Label 反解是 CLI display 核心逻辑——如果算法不可靠，用户看到错误的 label 会误解 Session 归属。Plan 将反向解析实现完全交给 S3，但 S3 的描述只说"增加从 `SessionListItem.slot` 反解 CLI display kind/label 的 helper"，没有具体算法
- **直接证据**: Plan S3 精确变更段（line 419-426）只说"增加 label kind enum 或受限字符串常量"和"增加 label -> slot ref helper"，没有反向解析伪代码或边界条件
- **影响**: 实施 Agent 自行实现 → 可能与 plan 意图不一致 → review 返工
- **建议改法和验证点**:
  1. 在 plan S3 补充 label 反向解析规则：
     - `slot_key` 以 `cli.prompt.` 开头 → `KIND=prompt`, `LABEL=slot_key[len("cli.prompt."):]`
     - `slot_key` 以 `cli.interactive.` 开头 → `KIND=interactive`, `LABEL=slot_key[len("cli.interactive."):]`
     - `slot is None` → `KIND=anonymous`, `LABEL=-`
     - 其它 → `KIND=other`, `LABEL=<slot_key>`
  2. 验证：覆盖 label 包含 `.`、空 label、极长 label、非 CLI slot 的 Session
- **修复风险**: 低
- **严重程度**: 中

---

### F-05 [中] purge by label 的 resolve-then-purge 两步操作缺乏 TOCTOU 说明

- **位置**: 第 7 节 — `session purge --label` + 第 9 节 Slice S4
- **问题类型**: 并发恢复风险
- **当前写法**: "purge by label 先用 `list_sessions` resolve slot，再调用 Host `purge_session`"
- **反例/失败场景**:
  1. CLI 通过 `list_sessions()` 找到 `session_id=A` 对应 label `foo`
  2. 在 `list_sessions()` 返回后、`purge_session(A)` 调用前，另一个 CLI 进程 purges session A
  3. `purge_session(A)` 收到 `CONFLICT`（already purged）→ CLI exit 1，stderr "已被其它请求 purge"
  4. 但用户命令行指定的是 `--label foo --kind prompt`，stderr 如果只报 `session_id` 不报 label，用户需要再跑一次 `session list` 确认——UX 不够好

  同样场景也适用于 resume by label：`list_sessions()` 后 Session 被并发 close，resume 的 `submit_followup` 收到 INVALID_STATE
- **为什么有问题**: TOCTOU 本身由 Host truth 正确兜底（不会误 purge/resume）。但 plan 没有：
  1. 明确说明这个 TOCTOU 窗口存在且由 Host 兜底
  2. 要求在 CLI 错误输出中包含用户原始输入（label name + kind），而不仅仅是 Host 返回的 session_id
  3. 测试覆盖这个并发场景
- **直接证据**: Plan S4 测试段（line 476-482）只有 "purge by label 先用 `list_sessions` resolve slot，再调用 Host `purge_session`"，无 TOCTOU 说明
- **影响**: 并发 CLI 使用场景下错误信息不够诊断 → 用户困惑；测试不覆盖 → 未来重构可能打破 Host 兜底假设
- **建议改法和验证点**:
  1. Plan 第 7 节补充：TOCTOU 窗口由 Host `purge_session` / `submit_followup` 的 pre-condition check 在 durable transaction 内原子兜底；CLI 的错误输出必须同时包含用户指定的 label + kind 和 Host 返回的 session_id + error
  2. 测试：fake Host `list_sessions` 返回 session A，然后 `purge_session(A)` 抛出 `CONFLICT` → 验证 stderr 包含 label 信息
  3. 不必在 CLI 做 CAS 或加锁——让 Host 做最终 truth 是正确的分层设计
- **修复风险**: 低
- **严重程度**: 中

---

### F-06 [低] `list_sessions()` 使用 `session_snapshot_from_rows` 对每个 session 触发 2 次额外 SQL 查询

- **位置**: 第 6 节 — Durable 读取 helper `read_all_sessions_with_slots` + `read_api.list_sessions`
- **问题类型**: 非最优方案
- **当前写法**: Plan 说 `read_api.list_sessions` "在 read transaction 中把每行转成 `SessionListItem`。可复用 `session_snapshot_from_rows(...)` 以保持 active / queued / cursor 语义同源"
- **反例/失败场景**: `session_snapshot_from_rows` (`dayu/host/durable/state.py:4327-4349`) 对每个 session 调用 `_read_active_run_id(transaction, session_id)` 和 `_read_queued_run_ids(transaction, session_id)`——各一次 SQL 查询。N 个 session = 1（主查询）+ 2N 次额外查询。对于 500 个 session，这是 1001 次 SQLite 查询
- **为什么有问题**: Plan 承认 "第一版不做 pagination"，但不承认 per-session 查询放大。如果 workspace 中有几百个 Session，`session list` 会明显变慢，且全部在同一 read transaction 内——SQLite 读锁持有时间变长
- **直接证据**: `dayu/host/durable/state.py:4327-4349` session_snapshot_from_rows 实现
- **影响**: Performance degradation for moderate-to-large session counts；not a correctness issue
- **建议改法和验证点**:
  1. 在 durable helper 中做 batch query：一条 SQL 查询所有 session 的 active_run_id + queued_run_ids（JOIN + GROUP BY）
  2. 或在 plan 中明确标注该性能边界，并记录为 deferred risk（Section 12 已有 "List 规模" 条目，但未提 per-session query amplification）
  3. 测试：100-session fixture 下 `list_sessions()` 耗时 < 100ms
- **修复风险**: 低
- **严重程度**: 低

---

### F-07 [低] `list_sessions()` 在 Host Protocol 中无 request 参数——缺少最小诊断上下文

- **位置**: 第 6 节 — `Host` Protocol 增加 `async def list_sessions(self) -> ListSessionsResult`
- **问题类型**: 契约缺失
- **当前写法**: `list_sessions()` 无任何参数。Plan 说这是"有意的最小设计"，不需要 request/query/filter
- **反例/失败场景**: 其他 Host public read API（`get_session(session_id)`、`get_run(run_id)`）都不需要 request 参数——这是读操作的一致模式。但 `list_sessions` 与其他读操作不同：它可能被多个 CLI 进程高频调用（每次 `session list` 都是一次），如果 Host 未来需要在 audit log 中记录 list 访问（非必需但可能），没有 `client_request_id` 或 actor 信息将无法关联
- **为什么有问题**: 这不是当前功能需求，但 plan 可以将 `list_sessions` 设计为 `async def list_sessions(self, request: ListSessionsRequest)` 并在 `ListSessionsRequest` 中只放 `client_request_id`，保持与其他 mutating request 的 envelope 一致性。Plan 当前的极简设计（零参数）也可以成立——但需要明确说明这是读操作的一致模式
- **直接证据**: `dayu/host/api.py:3143-3152` `get_session(self, session_id: str)` — 也无 request 参数，说明读操作确实不需要 request envelope
- **影响**: 低——当前设计中不影响功能正确性
- **建议改法和验证点**: 保持当前设计，在 plan 中加一句："`list_sessions()` 沿用 `get_session` / `get_run` 的只读零参数模式，不引入 request envelope"
- **修复风险**: 无
- **严重程度**: 低

---

### F-08 [低] 测试计划缺少并发 purge → list_sessions 一致性验证

- **位置**: 第 9 节 Slice S1 + 第 10 节测试/验证命令
- **问题类型**: 测试缺口
- **当前写法**: Slice S1 测试包含 `test_list_sessions_excludes_purged_session`、`test_list_sessions_returns_open_closed_and_anonymous_labeled_sessions`
- **反例/失败场景**: 测试使用 fake/mock Host，但真实场景下：
  - 一个 read transaction 内 `list_sessions()` 正在遍历 sessions，另一个 write transaction 并发 purge 了一个 session
  - SQLite WAL 模式下，read transaction 看到的是事务开始时的快照——purge 后的 session 仍可能在 list 结果中（若 purge commit 在 read 开始之后）
  - 这是 SQLite 的预期行为（snapshot isolation），不是 bug——但 plan 和测试没有确认这个行为是可接受的
- **为什么有问题**: Mock 测试不会暴露 SQLite 并发语义。若 implementation agent 假设 list 结果保证排除已 purge session（plan 确实声称 "已 purge Session 不出现在 list 中"），但并发场景下不一定成立
- **直接证据**: Plan 第 6 节 Durable helper 段："已 purge Session 已从 `host_sessions` 删除，因此自然不会出现在结果中"——这在无并发时正确，但在 read transaction 与 purge write transaction 并发时，取决于 SQLite 的 snapshot isolation
- **影响**: 极低概率下的暂时性不一致——list 可能短暂显示刚被 purge 的 session。但这不影响正确性（因为 `get_session` / `purge_session` 仍由 Host truth 兜底）
- **建议改法和验证点**:
  1. 在 plan 标注：list 结果中的"已 purge 不出现在结果中"指事务开始时的快照，并发 purge 可能在当前事务不可见——这是 SQLite WAL snapshot isolation 的正确行为
  2. 可选：添加一个并发测试（使用真实 SQLite）验证此行为
- **修复风险**: 低
- **严重程度**: 低

---

### F-09 [低] `interactive_process_slot_key` 删除后 host_context 导出清理不完整

- **位置**: 第 9 节 Slice S2 — "若 `interactive_process_slot_key(...)` 无其它用途，删除该 helper 与测试引用"
- **问题类型**: 范围漂移（minor）
- **当前写法**: "若...无其它用途，删除"——条件判断留给 implementation agent
- **反例/失败场景**: `dayu/cli/host_context.py:366-378` 的 `__all__` 中包含 `interactive_process_slot_key`。若删除该函数但未更新 `__all__`，会导致 import * 问题（虽然代码不应使用 import *）。更实质的问题是：plan 未确认 `interactive_process_slot_key` 是否在测试中有直接引用
- **为什么有问题**: Plan 给 implementation agent 留了一个条件判断（"若无其它用途"），但 agent 的上下文可能不知道所有引用点
- **直接证据**: `dayu/cli/host_context.py:107` 定义 `interactive_process_slot_key`，`dayu/cli/host_context.py:372` 在 `__all__` 中导出
- **影响**: Minor — 遗漏会导致 pyright 报 `__all__` 未定义符号，但会被 pyright 捕获
- **建议改法和验证点**: Plan S2 精确变更中加入："同时从 `host_context.__all__` 中移除 `interactive_process_slot_key`"
- **修复风险**: 无
- **严重程度**: 低

---

## Architecture Boundary Review

逐层检查 UI → Service → Host → Engine 分层：

| 检查项 | 结果 | 证据 |
|--------|------|------|
| CLI 不绕过 Host 读取 durable internals | **PASS** | Plan 明确 CLI 通过 `open_host(...)` + Host public API 操作 |
| `list_sessions` 不写入 EventLog | **PASS** | 只读 API，进入 `read_api.py`，不进入 command path |
| `purge` 不绕过 Host `purge_session` 前置条件 | **PASS** | CLI 映射 Host INVALID_STATE → stderr + exit 1，不自动 close/cancel |
| `resume` 不恢复旧 Agent/Runner/Attempt | **PASS** | 明确只是提交新 prompt/interactive turn |
| Engine 不拥有 Session 生命周期 | **PASS** | CLI resume 只是在已有 Host Session 上 submit_followup，Engine 保持 run-scoped |
| 禁止反向依赖 | **PASS** | 无新增反向依赖；`dayu.host` 不 import `dayu.cli` |
| Service 层不暴露 | **PASS** | 当前 CLI 直接调用 Host public API（正确——CLI 是 UI adapter，Service 是中间层，current design 约定 CLI 可直接 open_host） |

## Best-Practice Review

| 检查项 | 结果 |
|--------|------|
| 中文 docstring | **PASS** — Plan 要求 "中文 docstring 完整说明参数、返回值、异常" |
| 严格类型 | **PASS** — Plan 明确 "禁止 Any、object、裸 dict/list 签名" |
| 禁止兼容 wrapper | **PASS** — Plan S2 停止条件明确禁止保留兼容 flag |
| 禁止过度设计 | **PASS** — Plan 第 13 节专门论证 "为什么该方案没有过度设计" |
| 测试覆盖率 ≥ 80% | **CONDITIONAL** — Plan 要求新增模块 ≥ 80%，但未说明如何度量（`--cov` 命令） |
| pyright 0 errors | **PASS** — 明确验证命令 |

## Overengineering Review

| 检查项 | 结果 |
|--------|------|
| 无 pagination/filter DSL | **PASS** — Plan 明确拒绝，认为属于过度设计 |
| 无 `get_session_by_label` | **PASS** — 复用 `list_sessions()` |
| 无 CLI JSON output | **PASS** — 只在有需要时添加 |
| 无交互式 purge 确认 | **PASS** — 强制 `--yes` flag |

## Overcoupling Review

| 检查项 | 结果 |
|--------|------|
| SessionListItem 在 `dayu/host/api.py` 与 SessionSnapshot 同层 | **PASS** — 属于同一公共命名空间 |
| CLI session 命令不依赖 prompt/interactive 内部实现 | **RISK** — Slice S5 边界模糊，见 F-03 |
| list_sessions 不依赖 projection | **PASS** — 直接从 durable truth 读取 |
| Host public API 与 CLI 测试不耦合 | **PASS** — CLI 测试使用 fake Host |

## AGENTS.md / CLAUDE.md Compliance

| 规则 | 结果 |
|------|------|
| 中文 docstring | **PASS** |
| 禁止 `Any`/`object`/无类型签名 | **PASS** |
| 禁止兼容 wrapper | **PASS** |
| 禁止反向依赖 | **PASS** |
| LLM-facing 文本自足 | **PASS** — plan 明确"LLM-facing prompt 不暴露 Host 内部治理术语" |
| 禁止魔法数字/字符串 | **PASS** |
| 分层架构 UI→Service→Host→Engine | **PASS** |

---

## Open Questions

1. **`SessionListItem.created_at`/`closed_at` 最终类型**: Plan 第 12 节自己提出 "如果 reviewer 认为该 contract surface 过大，fallback 是从 public dataclass 移除时间戳"。建议在 plan fix 阶段裁决。见 **F-01**、**F-02**

2. **Closed Session resume exit code**: Plan 推荐 `2`（用户选择了不可用目标），但标注了 "最终实现必须测试并固定"。这是 implementation 阶段的 trivial decision，不阻塞 plan

3. **List 规模**: Plan 明确第一版不做 pagination，属于显式 defer。不阻塞 plan

4. **Resume by label uses list_sessions**: Plan 第 12 节标注不新增 `get_session_by_label` —— 在真实非 CLI 调用方需要前不过度设计。此为正确决策，见 **F-05** TOCTOU 标注

---

## Residual Risks

| ID | 风险 | 严重度 | 跟踪去向 |
|----|------|--------|----------|
| R1 | 大量 Session 场景下 `list_sessions` 性能不足 | 低 | Follow-up issue — 增加 pagination / filter |
| R2 | `list_sessions` 与并发 purge 的 snapshot isolation 行为 | 低 | Host design doc — 标注 SQLite WAL read transaction 语义 |
| R3 | Slice S5 core extraction 设计欠规格 | 中 | 见 F-03 — plan fix 阶段定义最小 contract |
| R4 | `SessionListItem` 与 `SessionSnapshot` 时间戳字段一致性 | 中 | 见 F-02 — plan fix 阶段裁决 |

---

## Conclusion

**PASS-WITH-RISKS**

本 plan 的动机成立、架构边界正确、分层清晰、与 Host 设计真源对齐。6 个 slice 按依赖顺序排布合理（S1 Host API → S2 删除过时 flag → S3 CLI helper → S4 list/purge → S5 resume → S6 文档），S1-S4 已达到 code-generation-ready 标准。

主要风险集中在：
- **F-01/F-02**（高/中）：`SessionListItem` 时间戳字段的类型转换 gap 及与 `SessionSnapshot` 的不一致性——plan 自身已将时间戳纳入 open question，建议 plan fix 阶段裁决
- **F-03**（中）：Slice S5 core extraction 欠规格——可能迫使 implementation agent 在 S5 重新设计
- **F-04/F-05**（中）：label 反解算法未形式化 + purge-by-label TOCTOU 未说明

无 blocking 级 finding。所有中等及以上 finding 均可通过 plan amendment 修复，不改变方案核心路径。Engine 不变、Host 状态机不变、无 schema migration、无不安全数据删除——结构性安全性良好。

---

## Completion Report

1. **Review artifact path**: `docs/reviews/plan-review-wu-cli-session-01-ds-20260616.md`
2. **Conclusion**: **PASS-WITH-RISKS**
3. **Findings count by severity**:
   - 高: 1 (F-01)
   - 中: 4 (F-02, F-03, F-04, F-05)
   - 低: 4 (F-06, F-07, F-08, F-09)
4. **Blocking open questions**: 无 — 所有 open questions 均可由 plan amendment 解决，不要求重新设计或回退
