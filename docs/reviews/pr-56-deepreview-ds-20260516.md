# Code Review — PR #56 Host Phase 7 Tool Awaiting / resolve_wait / Wait Adapter

## Scope

- Mode: PR review
- PR: [#56](https://github.com/noho/dayu-agent-r/pull/56) — Host Phase 7 Tool Awaiting / resolve_wait / Wait Adapter
- Author: Leo Liu (noho)
- Head: feat/host-phase7-tool-awaiting-resolve-wait
- Base: main
- State: OPEN, MERGEABLE
- Commits: 12 (P7-S1 through P7-S5 completion)
- CI checks: no checks configured on this branch
- Output file: docs/reviews/pr-56-deepreview-ds-20260516.md
- Included scope: 15 production files (dayu/host/), 14 test files (tests/host/), 2 doc files (READMEs), 2 design truth files (design.md, implementation-control.md), 1 plan file, ~45 review artifacts (docs/reviews/)
- Excluded scope: Engine/contracts/fins/service/ui/recovery/outbox/audit/tool trace — not modified
- Parallel review coverage: 4 subagents covering (1) public API/contracts/command/waiting, (2) durable layer/schema/state/transition/event payload, (3) adapter/poller/engine-ingest/admission/tool-runtime/run-input, (4) tests/docs

## Findings

### F1-Low — digest 校验不一致：waiting.py 使用弱于 api.py 的校验

- **入口/函数**: `ToolAwaitingAcceptCandidate.__post_init__`
- **文件(行号)**: `dayu/host/waiting.py` 第 236 行
- **输入场景**: 传入合法 sha256 前缀但非十六进制字符集的 digest 值，例如 `sha256:GGGGGGGGggggggggPPPPPPPPppppppppQQQQQQQQqqqqqqqq`。
- **实际分支**: 校验条件 `not value.startswith("sha256:") or len(value) != 71` 只检查前缀和长度，不检查字符是否为 `[0-9a-f]`。
- **预期行为**: 与 `dayu/host/api.py` 中的 `_require_sha256_digest` 函数一致，使用完整正则 `^sha256:[0-9a-f]{64}$` 校验。
- **实际行为**: 非法十六进制字符的 digest 通过校验，可能被持久化并在后续比较中产生不匹配。
- **直接证据**: `waiting.py:236` — `if not value.startswith("sha256:") or len(value) != 71:` vs `api.py:49` — `re.fullmatch(r"^sha256:[0-9a-f]{64}$", value)`。
- **影响**: 低。系统中 digest 均由确定性 sha256 计算产生，不会产生非法字符；但若将来有其他路径构造 digest 或外部传入，弱校验会漏过。
- **建议改法和验证点**: 在 `ToolAwaitingAcceptCandidate.__post_init__` 中复用 `_require_sha256_digest` 或等价正则。
- **修复风险（低）**: 将 `len(value) != 71` 替换为完整正则不影响现有合法 digest。
- **严重程度（低）**: 当前不会触发，但降低防御深度。

### F2-Low — WaitPollLost poll 结果未经测试覆盖

- **入口/函数**: `WaitPoller.poll_once`
- **文件(行号)**: `dayu/host/wait_adapter.py` 第 366-367 行；`tests/host/test_wait_adapter_polling.py`（全文件 219 行）
- **输入场景**: poll adapter 返回 `WaitPollLost`（外部 job 状态不可确认）。
- **实际分支**: `WaitPoller.poll_once()` 正确处理 `WaitPollLost`（第 366-367 行）：构造 `ResolveWaitRequest` 并调用 `resolve_wait`。
- **预期行为**: 测试应覆盖 poll adapter 返回 lost 的路径。
- **实际行为**: `test_wait_adapter_polling.py` 中零条测试覆盖 `WaitPollLost`；`_SequenceAdapter.results` 只用于 `WaitPollReady` 和 `WaitPollNotReady`。
- **直接证据**: `test_wait_adapter_polling.py` 全文 grep `WaitPollLost` 无匹配；`dayu/host/wait_adapter.py:59-68` 定义了 `WaitPollLost` 且第 366-367 行使用它。
- **影响**: 中。poll lost → resolve_wait(lost) → RUN_LOST 的路径在 `test_resolve_wait_command.py` 中以 manual source 被覆盖，但 poller 驱动的 lost 路径缺乏直接集成覆盖。
- **建议改法和验证点**: 在 `test_wait_adapter_polling.py` 新增 `test_poll_adapter_lost_result_resolves_and_closes_run`，用 `WaitPollLost` 结果序列验证。
- **修复风险（低）**: 纯测试新增。
- **严重程度（低）**: poll lost 经 resolve_wait pipeline 的 lost 路径已另有覆盖；此处仅为 poller 调用的端到端缺失。

### F3-Low — resolve_wait 跨文件测试辅助导入

- **入口/函数**: 测试模块级 import
- **文件(行号)**:
  - `tests/host/test_wait_cancel_late_result.py` 第 26-34 行
  - `tests/host/test_wait_adapter_polling.py` 第 30-35 行
  - `tests/host/test_phase7_waiting_integration.py` 第 59-66 行
- **输入场景**: 任一测试文件运行或重构时。
- **实际分支**: 三个测试文件从 `tests.host.test_resolve_wait_command` 导入 `_SeededWaitingRun`, `_options`, `_seed_waiting_run`, `_read_wait`, `_completed_request` 等私有辅助函数。
- **预期行为**: 测试共享辅助应放在 `tests/host/conftest.py` 或 `tests/host/_shared_*.py` 中，避免跨测试模块导入。
- **实际行为**: 测试模块间存在耦合；重命名 `test_resolve_wait_command.py` 或重构其内部辅助会破坏三个其他测试文件。`tests/README.md` 第 137-138 行建议将测试辅助放在 `_fakes.py` / `_factories.py` 中。
- **直接证据**: 三处 import 语句均以 `from tests.host.test_resolve_wait_command import` 开头。
- **影响**: 低。不涉及生产代码正确性，但增加测试维护成本。
- **建议改法和验证点**: 将共享辅助提取到 `tests/host/_resolve_wait_helpers.py`，三个文件从该模块导入。
- **修复风险（低）**: 纯重构，不改变测试语义。
- **严重程度（低）**: 测试架构耦合，非功能缺陷。

### F4-Low — resolve_wait 在 command.py 中绕过 admission service

- **入口/函数**: `resolve_wait`
- **文件(行号)**: `dayu/host/command.py` 第 502-506 行
- **输入场景**: 调用 `resolve_wait(host, wait_id, request)` 时。
- **实际分支**: `resolve_wait` 每次调用都通过 `host._admission_service.event_log_store` 和 `host._admission_service.idempotency_store` 私有属性创建新的 `DefaultHostResolveWaitService` 实例，而 `start_run`/`cancel_run`/`submit_followup` 等其他命令通过 `admission_service` 委托执行。
- **预期行为**: 一致的架构——所有 public command facade 函数应以相同方式委托给 admission 或 resolution service。
- **实际行为**: `resolve_wait` 绕过 admission service，直接访问其内部依赖，自身创建服务实例。这导致每次调用额外对象分配，且 `_admission_service` 是 `HostCommandHandle.__slots__` 中的私有属性。
- **直接证据**: `command.py:503` — `host._admission_service.event_log_store`；`command.py:504` — `host._admission_service.idempotency_store`；`command.py:502` — `service = DefaultHostResolveWaitService(...)`每次调用创建新实例。
- **影响**: 低。功能正确，但架构一致性降低，且依赖私有属性访问。
- **建议改法和验证点**: 将 `DefaultHostResolveWaitService` 预构造并注入到 admission service（或 command handle）中，使 `resolve_wait` 与其他命令保持一致的委托模式。需检查是否破坏现有 `HostCommandHandle` 构造。
- **修复风险（低）**: 结构重构，不改变语义。
- **严重程度（低）**: 架构一致性，非功能缺陷。

### F5-Low — ResolveWaitRequest.outcome isinstance 使用展开元组

- **入口/函数**: `ResolveWaitRequest.__post_init__`
- **文件(行号)**: `dayu/host/api.py` 第 1565-1573 行
- **输入场景**: 将来向 `ResolveWaitOutcome` 联合类型添加新成员时。
- **实际分支**: isinstance 检查硬编码了四种具体类型 `(ResolveWaitCompletedOutcome, ResolveWaitFailedOutcome, ResolveWaitCancelledOutcome, ResolveWaitLostOutcome)`，而非引用 `ResolveWaitOutcome` 类型别名。
- **预期行为**: 使用可从类型别名推断的封闭类型守卫。
- **实际行为**: 如果新增第五个 outcome 类型但忘记更新此元组，运行时会静默接受非法类型，而类型检查和 isinstance 守卫之间产生分歧。
- **直接证据**: `api.py:1565-1573` 硬编码四元组 vs `api.py:522` — `ResolveWaitOutcome: TypeAlias = ResolveWaitCompletedOutcome | ResolveWaitFailedOutcome | ResolveWaitCancelledOutcome | ResolveWaitLostOutcome`。
- **影响**: 低。当前四种 outcome 类型已完成且稳定；仅影响未来扩展。
- **建议改法和验证点**: 将四元组提取为模块级常量 `_RESOLVE_WAIT_OUTCOME_TYPES` 并与 `ResolveWaitOutcome` 类型别名一起更新，或使用 `get_args(ResolveWaitOutcome)`。
- **修复风险（低）**: 行为不变。
- **严重程度（低）**: 维护性，非缺陷。

### F6-Low — resume transition 中 attempt 插入在 Run CAS 之前

- **入口/函数**: `resume_run_from_waiting_in_transaction`
- **文件(行号)**: `dayu/host/durable/run_transition.py` 第 908-922 行
- **输入场景**: resume waiting Run 的事务执行期间。
- **实际分支**: 第 908 行 `insert_attempt` 先于第 909 行 `resume_waiting_run_row` CAS 执行。如果 CAS 失败，第 919 行 `_require_run_mutation_updated` 抛出异常回滚整个事务。
- **预期行为**: 事务内操作顺序不产生外部可见差异。
- **实际行为**: 正确——所有操作在同一 SQLite write transaction 内，CAS 失败触发回滚，attempt 插入不会残留。但操作顺序（insert attempt → CAS run → insert dispatch）在可读性上不如（CAS run → insert attempt → insert dispatch）直观。
- **直接证据**: `run_transition.py:908` — `insert_attempt(transaction, attempt)`；`run_transition.py:909-917` — `run_result = resume_waiting_run_row(...)`；`run_transition.py:919-921` — `_require_run_mutation_updated(...)` 失败时抛出。
- **影响**: 无。事务保证原子性。
- **建议改法和验证点**: 可选将 attempt 插入移至 CAS 成功后，或添加注释说明顺序意图。
- **修复风险（低）**: 纯排序调整，事务内无区别。
- **严重程度（低）**: 可读性，非缺陷。

### F7-Info — `await_kind` 列缺少 DDL CHECK 约束

- **文件(行号)**: `dayu/host/durable/schema.py` 第 477 行
- 与 `resume_policy` 列（有 `CHECK (resume_policy IN ('poll','callback','manual'))`）不同，`await_kind` 列没有受控词汇表约束。代码验证（`state.py:4214`）仅检查非空文本。这反映 `await_kind` 来自 `ToolAwaitSpec`，由工具而非 Host 控制值空间；但应在 schema 或注释中记录此设计决策。
- **严重程度**: 信息性。

### F8-Info — `_resolve_outcome_json` 使用独立 `if` 而非 `if/elif` 链

- **文件(行号)**: `dayu/host/waiting.py` 第 1486-1509 行
- 四个独立 `if` 语句处理 `ResolveWaitOutcome` 联合类型的每个成员，最终 `raise TypeError` 看起来像死代码。`if/elif/elif/elif/else` 链或 `match/case` 能更清晰地表达穷尽性意图。
- **严重程度**: 信息性。

## Open Questions

1. **WaitLateRejectionReason.IDEMPOTENCY_CONFLICT 未使用**：`waiting.py` 中定义但从未作为 rejection reason 使用——idempotency conflict 以 `HostApiError` 形式抛出，不走 late diagnostic 路径。这是有意预留还是遗漏？

## Residual Risk

- **CI 未配置**：此分支无 CI checks，所有验证依赖手工运行。建议在 merge 前配置 CI（或确认 merge 后的 main 分支 CI 会触发）。
- **WaitPollLost test gap**（F2）：poll adapter lost → resolve_wait → RUN_LOST 路径在 poller 层无直接测试。`test_resolve_wait_command.py` 中以 manual source 覆盖了 lost 路径，但 poller 驱动的 lost 路径缺乏集成覆盖。
- **Cross-test import coupling**（F3）：三个测试文件依赖 `test_resolve_wait_command.py` 的私有辅助，后续重构可能破坏。
- **Callback 路径未落地**：`WaitResolutionSource.CALLBACK` 在代码中可用，但无 HTTP callback endpoint、authentication 或重放防护。
- **Poller 无后台调度循环**：`WaitPoller` 仅有 `poll_once()` 单轮入口，无退避、in-flight fencing 或错误重试。
- **Engine matching-ref 校验**：Engine 公共事件不携带 Host accepted wait refs，当前只能做 diagnostic/idempotent confirmation。
- 以上残余风险均有明确 deferred owner（后续 phase/adapter hardening work unit），不构成 PR 阻塞项。

## Verdict

**PASS — 建议在 merge 前处理 F2（WaitPollLost test gap）和 F3（cross-test import coupling）。**

PR #56 正确实现了 Host Phase 7 的完整功能集：

- Typed `ResolveWaitRequest` 替代 weak `outcome_ref`，`observed_at` 强制 UTC-aware
- Wait record durable table 含完整 CHECK 约束、索引与 CAS helpers
- ToolRuntime awaiting accept 在单个事务内原子写入 `TOOL_AWAITING` + `RUN_WAITING` + `ATTEMPT_SUSPENDED` + wait record
- `resolve_wait` 支持 completed/cancelled resume、failed/lost closeout，幂等 scope `(wait_id, idempotency_key)`
- `WAITING` cancel 复用同一 transition，session-scope 与 single-run cancel 无漂移
- Late result diagnostic 使用独立 `wait_late_rejection` 幂等 scope，同 key 同 digest 不重复写
- WaitPoller 交易外调用 adapter，ready/lost 通过 `resolve_wait` 提交，cancelled 只 abandon
- Engine `TOOL_AWAITING`/`RUN_SUSPENDED` 仅 diagnostic confirmation，不创建 wait state，不失败 Run
- RunInputBuilder resume 路径从 EventLog canonical facts 重建 accepted wait/tool fact system message
- 设计真源（design.md, implementation-control.md）未修改
- 无边界越位或反向依赖

8 个 findings 中：0 个严重/高，0 个中，6 个低，2 个信息性。无 blocking finding。

验证通过：389 tests passed, 0 pyright errors, `git diff --check` clean。
