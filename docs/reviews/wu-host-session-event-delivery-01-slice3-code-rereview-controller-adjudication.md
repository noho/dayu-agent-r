# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 3 Code Re-Review Controller Adjudication

## 输入与结论

- AgentMiMo：`docs/reviews/wu-host-session-event-delivery-01-slice3-code-rereview-mimo.md`
- AgentDS：`docs/reviews/wu-host-session-event-delivery-01-slice3-code-rereview-ds.md`
- Fix：`docs/reviews/wu-host-session-event-delivery-01-slice3-fix-codex.md`
- Accepted base：`b33bb80b`

两路原 reviewers 均确认 `S3-CR-F01 CLOSED`、`S3-CR-F02 CLOSED`、0 new material correctness finding。Controller接受两项关闭结论，但不能把 AgentDS 明确记录的 remaining duplicate projection作为后续 cleanup residual，因为它直接命中根 `AGENTS.md` 的硬约束。

## Prior findings

### S3-CR-F01

- 裁决：`closed`
- `_fail_recovering_run` 的 UPDATED 分支现在从 same-transaction exact result产生 `wake_queue_promotion=True` notice。
- runtime test在 callback内先用独立 SQLite connection读取 committed Run/EventLog join，再用 typed transaction核对 stable ref；CAS_LOST/INVALID_STATE为零notice。

### S3-CR-F02

- 裁决：`closed-as-originally-scoped`
- 四个 `RunTransitionResult` consumer已删除本地同名helper并复用 durable owner helper。
- 但本轮全局扫描发现第五份同语义 projection；见 `S3-RR-F01`。原 finding 的局部修复成立，不代表整个 shared semantic已闭合。

## New finding adjudication

### S3-RR-F01 waiting 仍复制 exact Run/Event → notice 投影

- 来源：AgentDS re-review residual risk；Controller按仓库硬约束重新分类。
- 严重度：maintainability / semantic-owner hard constraint
- 裁决：`accepted-current-fix`
- 直接证据：`dayu/host/waiting.py::_terminal_notice_from_wait_transition` 与 `dayu/host/durable/run_transition.py::terminal_notice_from_transition` 都执行相同的 `run/run_event`存在性、stable terminal id/sequence、Session、Run identity校验并构造 `TerminalPostCommitNotice`；差异仅是输入 dataclass类型。
- Root cause：第一次 F02 的 static test只枚举四个同名 `RunTransitionResult` consumers，按函数名而不是按业务语义扫描，未覆盖 `WaitResolutionTransitionResult` 的同义实现。
- 约束：根 `AGENTS.md` 要求多个消费者复用同一 source of truth / projection helper，并明确“重复逻辑必须抽取”；因此不得推迟为 cleanup residual。
- 修复边界：由 AgentCodex在 durable owner提供一个使用直接 typed `RunRow | None` 与 exact `EventLogRow | None` 输入的唯一 projection helper（直接参数优先于为此新增 Protocol），五个 consumer都直接复用；删除 waiting 的 pure projection helper。`_terminal_notice_from_terminal_wait_snapshot` 可保留其 terminal confirmation/replay职责，但只能把确认结果交给 shared helper，不再复制校验/构造。
- 测试要求：owner/static test覆盖 waiting在内的五个 consumer，禁止本地wrapper/alias/re-export；owner behavior test覆盖 missing/inconsistent exact row；waiting replay/failed/lost/expiry与producer manifest/flag/post-commit时点保持。

## Decision

`fix-required`

下一 gate=`code-rereview-fix-slice-3`。只由AgentCodex修复 `S3-RR-F01`，随后原AgentMiMo与AgentDS再次并行执行 `$deepreview` narrow re-review。不得修改README、control之外的Controller artifacts、public export、Engine boundary或其它Slice 3语义。
