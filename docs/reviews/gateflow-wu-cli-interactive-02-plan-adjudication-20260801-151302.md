# Gateflow Plan Adjudication: `wu-cli-interactive-02-conformance-fixes`

## Gate metadata

- Gate：`plan`
- Work unit：`wu-cli-interactive-02-conformance-fixes`
- Branch：`codex/interactive-oracle`
- PR base：`main`
- Plan artifact：`docs/host/wu-cli-interactive-02-conformance-fixes-plan.md`
- Review target：用户已确认的 F01-F13 冻结语义，以及计划是否可直接生成代码、保持 owner boundary 且不扩大范围。
- Controller：AgentController；本 artifact 是总控裁决，不以任一路 reviewer 输出代替通过结论。

## Scope and changed artifacts

本 gate 只新增计划、两路首轮 plan review、两路 re-review 与本裁决 artifact；没有修改生产代码、测试、registry、oracle 或设计真源。

- Plan：`docs/host/wu-cli-interactive-02-conformance-fixes-plan.md`
- AgentDS 首轮 review：`docs/reviews/plan-review-20260801-143257.md`
- AgentMiMo 首轮 review：`docs/reviews/plan-review-20260801-143623.md`
- AgentMiMo re-review：`docs/reviews/plan-review-20260801-150754.md`
- AgentDS re-review：`docs/reviews/plan-review-20260801-151002.md`

AgentMiMo re-review 的“前置 artifacts”两行把首轮 reviewer 名称写反；文件内容和实际 pane provenance 不受影响。本 artifact 按上述真实映射校正，不回写历史 review。

## Controller decisions

| Finding | Decision | Direct basis | Final status |
|---|---|---|---|
| MiMo-001：F11 未覆盖 reactive terminal writer | `accepted` | `engine_ingest.py` 与 `dispatch.py` 是两类真实 writer；reactive provider await 后的结果事务也缺少 operation-terminal fresh reread | Plan §8 新增窄 `compaction_terminal` owner、两路 writer guard 与反向 barrier tests；closed |
| MiMo-002：非空 draft Ctrl+C 未定义 | `accepted` | 冻结 idle Ctrl+C contract 要求先清 draft，不能隐式登记 exit | Plan §6.5 状态表和 tests 已写死；closed |
| MiMo-003：为 S5 预埋 optional identity | `rejected-with-reason` | S4 guard 只拥有 terminal commit permission；S5 payload owner 才拥有 required identity | 未预埋 nullable 参数或 payload bag；closed by decision |
| MiMo-004：第三次及后续 Ctrl+C 未定义 | `accepted` | canonical waiter 不得被后续 SIGINT 取消 | `exit_after_cancel=true` 后一律 no-op；closed |
| MiMo-005：F13 串线测试不精确 | `accepted` | ordinary、rejected attempt、accepted attempt 必须逐调用绑定 | Plan §9.6 A/B/C 反例已补；closed |
| DS F-01：second Ctrl+C 与 sole QUEUE | `accepted-clarification-only` | F08 graceful cancel 与 F09 durable accepted QUEUE exactly-once 必须组合；无 label fresh Session 不能遗留永久 queued Run | 保持等待 accepted sole QUEUE terminal；不采纳“留给未来 fresh writer”；closed |
| DS F-02：Engine/Host attempt 术语歧义 | `accepted` | compactor Engine request 的 `attempt_id/execution_id=None`，Host attempt number 是外层独立事实 | Plan §9.3 taxonomy、nested identity 与 manifest binding 已补；closed |
| DS F-03：保留 pairwise config claim 操作不精确 | `accepted` | 五条 row 的 config 来源已由 precondition 表达，removed CLI parameter claim 必须删除 | 精确列出 5 条 row，只从两个 claim 数组删除 `parameter:config:default`；closed |
| DS F-04：测试路径可能不存在 | `non-finding` | 路径 inventory 已证明原引用存在 | 删除多余 fallback 说明；closed |
| OQ-01/OQ-02 | `closed-by-code-evidence` | `_resume_interactive_ticker()` 存在；reactive writer 已纳入 F11 | closed |
| PTY/OQ-03 | `allowed-variant` | POSIX 可执行真实 PTY，非 POSIX 只能报告 capability/skip | classified |
| DS re-review N-01：submit client request id 格式 | `non-finding` | 唯一性和 stable owner 是 contract，具体字符串格式是模块私有实施细节 | 不改 plan；classified |

## Re-review adjudication

- AgentMiMo re-review：`PASS`，确认 accepted findings 全部真实关闭，无新增 blocker。
- AgentDS re-review：`PASS`，确认 10 条 controller trace 均有计划落点；唯一 N-01 为非阻断观察。
- Controller 独立复核：共享 compaction terminal CAS、Ctrl+C/QUEUE 状态机、F13 identity taxonomy、五条 registry cleanup 与 Gateflow 自动推进表述均与直接代码和冻结语义一致。
- Decision：`accepted plan pass`。

## Validation

- `git diff --check`：pass。
- 未跟踪 plan 的 `git diff --no-index --check`：无 whitespace error。
- Plan path inventory：77 条；75 条现存，2 条为明确 planned-new：
  - `dayu/host/compaction_terminal.py`
  - `tests/host/test_compaction_terminal.py`
- 意外缺失路径：0。
- F01-F13：全部在 S1-S5 有显式 owner/combined heading；S6 给出集成、docs、registry 与 smoke 闭环。
- 本 gate 未改 Python，因此未运行 pytest、pyright 或 coverage；这些验证从各 implementation slice 起强制执行。

## Docs decision

- 本 gate 只新增计划与 review/adjudication artifacts。
- `docs/host/design.md`、`docs/engine/design.md`、CLI registry/oracle 和各 README 的职责更新已在 S6 明确触发条件，本 gate 不提前写未实现状态。
- 冻结 adjudication controller artifact 不修改。

## Residual risks

- Correctness：无未分类 plan blocker。
- Concurrency/recovery：实现阶段必须用确定性 barrier 证明两路 terminal writer 与 per-Session single-flight；已进入 S4 acceptance criteria。
- Platform：未知终端不能区分 Shift+Enter 时只报告 capability；非 POSIX 不以 pipe 冒充 PTY。
- External provider：行为项 29 的真实成功 compactor identity 仍依赖后续 provider smoke；若凭证/外部服务不可用，必须记录 validation blocker/residual risk，不能用配置推断替代。
- Follow-up calibration：G01-G07 保持后续 CLI calibration gap，不在本 work unit 裁决。

所有 residual risks 均已分类，没有阻止进入 implementation 的风险。

## Completion and next gate

- Completion status：`plan gate pass`。
- Accepted plan commit：本 artifact 与全部 plan/review artifacts 一并提交。
- Next gate：`S1 implementation — F01-F04`。
- Gateflow 必须继续自动推进，不在本普通 gate 停止。
