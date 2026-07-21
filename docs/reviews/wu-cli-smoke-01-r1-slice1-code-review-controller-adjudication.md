# WU-CLI-SMOKE-01-R1 Slice 1 Code Review Controller Adjudication

## Scope

- Gate: Slice 1 code review。
- Base: `929691ea`。
- Review artifacts:
  - `docs/reviews/code-review-20260721-005108.md`（AgentMiMo）。
  - `docs/reviews/code-review-20260721-005320.md`（AgentDS）。
- Implementation artifact: `docs/reviews/wu-cli-smoke-01-r1-slice1-implementation-codex.md`。
- Supplemental control: `docs/phaseflow-umbrella-optimization-control.md`；仅 accepted finding 的 fix batch 适用。

## Motivation / Owner Check

Slice 1 的真实问题仍成立：三类 Engine per-chunk delta 的业务 owner 是 Host transient live contract，而不是 EventLog。当前实现把产生、校验、fanout、slow-consumer、terminal fence 与 public projection 放在 Host owner boundary，并由 Service / CLI 消费 public union；两路审查没有提供 durable owner drift、反向依赖或事务前发布的反例。

本轮 accepted finding 只涉及 `CliThinkingRenderer.close()` 已有语义的 owner-level 测试缺口，不需要修改生产代码或公共 contract。按附加总控归为 Low Risk `test-harness-low`，合并为一个 test-only fix batch。考虑用户指定 AgentMiMo / AgentDS 两路 review 路由，fix 后仍执行双路 narrow re-review，不采用单路优化。

## Decisions

### MiMo review

- `accepted`：review verdict 为 `pass`，未发现实质性问题。其 Host / Service / CLI focused tests、pyright、静态 owner scan 与 `git diff --check` 证据可作为本 gate 的独立通过证据。

### DS-F01 terminal fence / drain TOCTOU

- `rejected-with-reason`。
- finding 描述的 D 虽可能在 terminal 前进入 subscription queue，但 `HostTransientDeltaSubscription.drain_nowait()` 在出队时再次检查 `item.run_id not in self._terminal_run_ids`。`mark_run_terminal(event.run_id)` 在 terminal `yield` 前执行，因此 D 在下一轮 drain 时会被丢弃，不会在 terminal 后交付。
- `_watch_session_events_after()` 的 terminal 分支在最后一次 `drain_nowait()` 返回后到 `mark_run_terminal()` 之间没有 `await`；同一 event loop 的 publisher 不能在该同步区间插入。即使考虑外部并发在该区间 offer，下一轮 drain 的第二道 fence 仍会拒绝 D。
- accepted plan §12.1 的 Slice 2 barrier 仍需证明 terminal linearization 与 readiness 交错，但它是既定 adversarial acceptance，不是当前实现已证实的 correctness defect。

### DS-F02 Service prompt / interactive 集成测试未注入 transient

- `deferred-with-owner`。
- owner 为本 WU Slice 2 的真实 Host → Service → CLI transient / slow-consumer E2E 与 lifecycle validation。Slice 1 已有 Host mixed-stream 测试和 Service reasoning projection 单元测试；当前缺口不要求重复构造另一套 fake-only integration truth。
- Slice 2 必须覆盖 attached mixed stream、thinking callback、terminal/fallback、slow consumer 与无重复 final 输出；不得在 closeout 前遗失该项。

### DS-F03 renderer close 后 record 抑制缺少直接单元测试

- `accepted`。
- `CliThinkingRenderer.close()` 的 owner contract 是关闭后 `record()` 不再输出；当前生产分支存在且命令级测试有间接覆盖，但 `tests/cli/test_thinking_renderer.py` 缺少直接 owner-level 断言。
- fix scope 仅允许在 `tests/cli/test_thinking_renderer.py` 增加直接测试，并写 fix artifact；不得修改生产代码、公共 contract 或进入 Slice 2。

### DS Open Question: terminal-only unbounded queue

- `rejected-with-reason`（已由直接证据关闭，不转 finding）。
- 已终态 cancel 路径不创建 watcher，使用空 queue 且显式 `allow_outbox_terminal_fallback=True`，因此 `_wait_for_terminal()` 直接从 durable Run / Outbox 补读。live 路径的 bounded queue 由 `_WatchAndWaitRuntime` 唯一创建，并先消费 watcher items；queue capacity 不改变 `_wait_for_terminal()` 的 item 语义。两条路径通过是否存在 watcher与 fallback flag 显式分化，没有 owner ambiguity。

## Fix Handoff

- Agent: AgentCodex。
- Allowed production changes: none。
- Allowed test change: `tests/cli/test_thinking_renderer.py`。
- Required artifact: `docs/reviews/wu-cli-smoke-01-r1-slice1-fix-codex.md`。
- Required validation:
  - `source .venv/bin/activate && pytest tests/cli/test_thinking_renderer.py -q`
  - `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py -q`
  - `source .venv/bin/activate && pyright`
  - `git diff --check`
- README decision: test-only direct coverage，不改变测试目录职责、命令或读者工作流，预计无需更新 `tests/README.md`；AgentCodex 仍需先读其更新约束并记录决定。
- Propagation audit: 生产 owner、Host public contract、Service DTO、CLI output contract 均不得变化。
- Baseline residual: none。
- Stop status: fix 完成后停止，等待 AgentMiMo / AgentDS narrow re-review；不得 commit、push、PR 或进入 Slice 2。

## Decision

`fix-required`。当前唯一 accepted finding 为 DS-F03；DS-F02 明确归属 Slice 2，DS-F01 与 open question 已用直接代码证据关闭。
