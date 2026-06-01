# WU-STRESS-01 Plan Review — AgentMiMo

## Gate

- **Gate**: plan review
- **Reviewer**: AgentMiMo
- **Date**: 2026-06-01

## Reviewed target

`docs/host/wu-stress-01-host-production-stress-suite-plan.md`

## Design source

- `docs/host/design.md` — Host 设计真源
- `docs/host/host-core-followup-implementation-control.md` — follow-up 实施总控
- `docs/reviews/wu-stress-01-discussion-code-inspection-20260601.md` — 代码核对 artifact

## Conclusion

**PASS** — 无 blocking finding。计划满足 design doc 设计目标和 WU-STRESS-01 验收信号，未越界修改 Host public contract / durable schema / EventLog / recovery 状态机 / scheduler 生产行为，slices code-generation-ready 且可独立验证。

## Findings

### F1-未修复-次要-failure_boundary 应使用 Literal 类型而非 str

**位置**: plan §3 结构化摘要，`failure_boundary: str | None`

**问题**: AGENTS.md 要求禁止无类型参数/返回值。`failure_boundary` 的合法值已固定为 `durable` / `scheduler` / `watch` / `liveness` / `recovery` / `projection` / `active_cleanup` / `unknown` 八个枚举值，但类型声明为 `str | None`。按 AGENTS.md 强类型约束，应使用 `Literal[...]` 或 `Enum` 替代裸 `str`，让 pyright 能在调用侧检查拼写。

**建议**: 改为 `failure_boundary: Literal["durable", "scheduler", "watch", "liveness", "recovery", "projection", "active_cleanup", "unknown"] | None`。

**是否 blocking**: 否。实现 agent 可自行修正，不影响 slice 结构。

### F2-未修复-次要-helper 函数 docstring 要求未显式覆盖所有新增函数

**位置**: plan §3、各 slice Exact changes

**问题**: AGENTS.md 要求"函数必须提供完整中文 docstring，至少包含参数、返回值、异常"。计划只对 `HostStressSummary` 和 `summary_to_json` 显式要求 docstring，但 `assert_summary_ok`、`terminal_duplicate_count`、`watch_lag`、`build_stress_open_host_options`、`consume_terminals`、`close_host_event_iterator`、`read_latest_event_sequence`、`compute_watch_lag`、`wait_all_runs_terminal`、`read_host_instances`、`verify_lane_released` 等新增 helper 均未显式声明 docstring 要求。

**建议**: 在 §3 或 slice 1 的 Exact changes 中补充一句："所有新增模块级函数和 dataclass 均须提供完整中文 docstring，符合 AGENTS.md 编码硬约束。"

**是否 blocking**: 否。AGENTS.md 是全局约束，实现 agent 应自动遵守。

### F3-未修复-次要-StressTerminalObservation 未被任何 slice 使用

**位置**: plan slice 1 Exact changes

**问题**: `StressTerminalObservation` dataclass（记录 `run_id`、`event_id`、`event_sequence`、terminal kind/status）在 slice 1 中定义，但在 slice 2-5 的 Exact changes、Expected assertions 和 Validation command 中均未被引用。它是死设计元素，如果实现时确实不需要，应删除以避免 god bag 倾向。

**建议**: 实现时若无消费方，不创建该 dataclass；或在 plan 中标注其具体消费场景。

**是否 blocking**: 否。实现 agent 可自行判断是否需要。

### F4-未修复-次要-与 recovery_support 现有 worker factory 的职责边界未显式区分

**位置**: plan slice 1、slice 4 Exact changes

**问题**: `tests/host/recovery_support.py` 已提供四个 worker factory / handle 类：`BlockingFinalAnswerHandle`、`BlockingFinalAnswerWorkerFactory`、`AsyncControlledFinalAnswerHandle`、`AsyncControlledFinalAnswerWorkerFactory`。计划新增 `DeterministicStressWorkerFactory`（slice 1）和 `InspectableStressWorkerFactory`（slice 4），但未显式说明与已有 factory 的职责差异。计划声称"复用 `tests.host.recovery_support`，不要复制大段逻辑"，但新增 factory 的边界语义不清晰。

**建议**: 在 Exact changes 中补充一句说明新 factory 相对于已有 factory 的增量能力（例如：`DeterministicStressWorkerFactory` 支持 stream exception / clean EOF 模式；`InspectableStressWorkerFactory` 增加 accepted snapshot / handle close count / cancel count 诊断）。若增量能力可通过扩展现有 factory 实现，优先扩展而非新建。

**是否 blocking**: 否。实现 agent 可在实现时决定合并或区分。

### F5-未修复-观察-pytest addopts 覆盖策略有已知 gotcha

**位置**: plan §Contract / Schema / State-machine / Public-interface Changes

**问题**: 默认 `addopts = "-m 'not stress'"` 配合显式 `pytest -o addopts="" -m stress` 的策略有一个已知 gotcha：若用户直接运行 `pytest -m stress` 而不加 `-o addopts=""`，将选中 0 个测试。计划已明确记录此行为并提供正确命令，但该策略不是 pytest 的标准模式，可能造成新开发者困惑。

**建议**: 无需修改。计划已正确文档化此行为。实现时可考虑在 `tests/README.md` 中用醒目注释说明。

**是否 blocking**: 否。

### F6-未修复-观察-首次引入 @pytest.mark.timeout

**位置**: plan §Implementation Decisions §5

**问题**: `pytest-timeout>=2.1.0` 已是 `pyproject.toml` 依赖（第 82 行），但当前整个测试代码库中无任何 `@pytest.mark.timeout` 用法。计划要求所有 stress tests 使用 `@pytest.mark.timeout(...)`，这是首次引入该 marker。

**建议**: 无需修改。依赖已存在，引入用法合理。

**是否 blocking**: 否。

### F7-未修复-观察-slice 间依赖 handoff 隐式

**位置**: plan §Implementation Slices

**问题**: 五个 slice 之间存在隐式依赖：slice 2-5 依赖 slice 1 的 helper；slice 4 声称复用 slice 2 的 crash helper；slice 5 组合所有 slice。计划未显式声明 slice 间 contract handoff。按总控文档的 slice 切分原则，"好的 slice 应当有明确输入、输出、non-goals、allowed files / modules、验证命令和后续 slice 可依赖的稳定交付物"。

**建议**: 无需修改。各 slice 的 Allowed files 和 Expected assertions 已足够隐式表达依赖。实现 agent 按顺序实施即可。

**是否 blocking**: 否。

## Open questions / residual risk

无。计划的 Blocking Questions For Controller 已声明当前无 blocking questions，watch reconnect 语义已正确定义为"重新 attach 后观察后续 terminal"而非"回放断开窗口"，与 design doc 的 `watch_session_events` 无 cursor 参数约束一致。

## Controller decision status placeholder

待 controller review 后填写。

## Artifact path

`docs/reviews/wu-stress-01-plan-review-mimo-20260601.md`
