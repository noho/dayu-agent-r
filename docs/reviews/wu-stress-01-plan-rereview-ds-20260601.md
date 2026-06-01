# WU-STRESS-01 Plan Re-review — AgentDS

## Gate

plan-re-review

## Reviewed Targets

- 修订后 plan: `docs/host/wu-stress-01-host-production-stress-suite-plan.md`
- Controller adjudication: `docs/reviews/wu-stress-01-plan-controller-adjudication-20260601.md`
- 原 DS review: `docs/reviews/wu-stress-01-plan-review-ds-20260601.md`

## Design Source

`docs/host/design.md`

## Control Source

`docs/host/host-core-followup-implementation-control.md`

## Conclusion

PASS — 9/9 ADJ items fixed, 0 remaining findings, 0 blocking.

修订后 plan 已完整处理 ADJ-01 到 ADJ-09 全部裁决项。原 DS review 中 F-01 到 F-05 分别由 ADJ-05、ADJ-08、ADJ-06、ADJ-02、ADJ-09 覆盖并修复。修订未引入新问题；plan 满足 design_doc 设计目标、总控文档验收信号和 CLAUDE.md 约束；未要求修改 Host public contract、durable schema、EventLog、recovery 状态机或 scheduler 生产行为；slices 可独立验证、prerequisites/stable output 清晰、可 code-generation-ready 推进 implementation gate。

## Per-finding Re-review Status

### ADJ-01: failure_boundary 类型收窄 → FIXED

**要求**: 把 `failure_boundary: str | None` 改成封闭诊断类型。

**修订证据**: Plan 第 151-164 行定义 `StressFailureBoundary = Literal["durable", "scheduler", "watch", "watch_reconnect", "liveness", "recovery", "projection", "active_cleanup", "scheduler_close", "worker_accept", "unknown"]`。第 182 行 `failure_boundary: StressFailureBoundary | None`。第 633 行 slice 5 failure paths 中再次确认必须使用 `StressFailureBoundary` 封闭类型。`Literal` 与 `| None` 均为 Python 3.11 可用语法。

**验证**: 通过。封闭类型禁止裸 `str` 扩散，覆盖了 stress suite 全部可定位边界。

---

### ADJ-02: helper/docstring 约束显式写入 plan → FIXED

**要求**: 所有新增模块级函数、class、dataclass 都有完整中文 docstring；lag diagnostic helper 必须声明 fresh short read transaction 与 point-in-time diagnostic 语义。

**修订证据**: Plan 新增第 4 节（第 194-209 行）"新增 helper 的 docstring、类型和 diagnostic 语义"，要求：(a) 完整中文 docstring 覆盖参数/返回值/异常；(b) 所有函数必须有完整参数类型和返回值类型，禁止 `Any`/`object`/裸 `dict`/`list`；(c) lag diagnostic helper docstring 中必须声明 fresh short read transaction 读取 point-in-time diagnostic，不表达 watcher replay truth。

**验证**: 通过。覆盖了原 DS F-04 的 lag 语义缺失和 AGENTMIMO F2 的 docstring 边界问题。

---

### ADJ-03: StressTerminalObservation 消费场景 → FIXED

**要求**: 明确消费路径或要求不创建该类型。

**修订证据**: Plan 第 186-192 行明确：(a) `StressTerminalObservation` 只能在实现需要 terminal 去重或 watch lag 计算时创建；(b) 消费路径固定为 `terminal_duplicate_count()`、`terminal_dedupe_ok()`、`watch_lag_samples()`；(c) 若实现用局部 tuple/dict-free typed helper 完成同等工作且无上述消费路径，"则不得创建 `StressTerminalObservation`，避免死设计或 god bag"。

**验证**: 通过。既保留了设计灵活性，又设定了明确的 delete-if-unused 阀门。

---

### ADJ-04: stress worker factory 边界具体化 → FIXED

**要求**: 说明新增 factory 与既有 recovery helper 的增量职责，优先复用。

**修订证据**: Plan 第 5 节（第 212-227 行）重写为：(a) 明确 "优先复用 `run_blocking_owner_process`、`AsyncControlledFinalAnswerWorkerFactory`、accepted marker、process terminate、owner stale fault injection、event type count、attempt count 等既有能力"；(b) 新增职责限定为 final/fail/blocking/stream exception/clean EOF/handle close count/cancel count/accepted snapshot count/per-run scripted behavior；(c) 规定 "不得复制 `recovery_support.py` 中已有多进程 owner / marker / stale liveness 逻辑的大段实现"；(d) 若只需语义微调，应写薄 wrapper 并说明复用关系。

**验证**: 通过。增量职责列表具体、可审查，复用边界清晰。

---

### ADJ-05: pytest addopts / CI / marker 验证补足 → FIXED

**要求**: Slice 1 validation 加入 CI pytest 命令检查、`pytest --markers` 和默认收集/deselect 行为验证。

**修订证据**: Plan Slice 1 Tests/validation（第 278-305 行）新增：(a) `pytest --markers` 检查 stress 和 timeout marker 均可见；(b) `pytest --collect-only` 默认与 `-o addopts=""` 双路径对比；(c) CI pytest 调用检查命令 `rg -n "pytest|python -m pytest|uv run pytest"` 覆盖 `.github/**`、`pyproject.toml`、`tox.ini`、`noxfile.py`、`Makefile`；(d) implementation report 必须记录发现的 pytest 调用及 addopts 影响评估；(e) failure path 增加 "pytest --markers 缺少 timeout" 停止条件。

**验证**: 通过。覆盖了原 DS F-01 的 CI 交互风险和 AGENTMIMO F5 的 marker 验证缺口。

---

### ADJ-06: pytest-timeout 可用性写清 → FIXED

**要求**: 写明依赖已存在，Slice 1 验证 marker 可用。

**修订证据**: Plan 第 123 行明确 "`pytest-timeout>=2.1.0` 已在 `pyproject.toml` test optional dependency 中存在；implementation 不应新增依赖，只需验证 `pytest --markers` 中存在 `timeout` marker"。第 231-232 行重复确认。第 248 行 Slice 1 prerequisites 中再次注明 "已包含 `pytest-timeout>=2.1.0`；implementation 只验证 marker 可用，不新增依赖"。第 301 行 failure path 中要求 "pytest --markers 缺少 timeout：说明测试环境没有安装已声明的 pytest-timeout，必须停止修复环境"。

**验证**: 通过。覆盖了原 DS F-03 和 AGENTMIMO F6。

---

### ADJ-07: slice 依赖 handoff 显式化 → FIXED

**要求**: 每个 slice 写明 prerequisites / stable output。

**修订证据**: 修订后每个 slice 均包含两个新章节：
- **Prerequisites**: Slice 1（第 245 行）、Slice 2（第 327 行）、Slice 3（第 394 行）、Slice 4（第 465 行）、Slice 5（第 573 行）。
- **Stable output for next slices**: Slice 1（第 306 行）、Slice 2（第 364 行）、Slice 3（第 435 行）、Slice 4（第 544 行）、Slice 5（第 614 行）。

依赖链清晰：Slice 2/3/4/5 均依赖 Slice 1 的 marker/summary/option builder；Slice 4 依赖 Slice 2 的 crash/recovery helper；Slice 3/4/5 依赖各自的 terminal dedupe/lag helper；Slice 5 聚合 Slice 1-4 全部 output。

**验证**: 通过。每个 slice 的输入、输出、前置条件均可独立验证。

---

### ADJ-08: Slice 4 close cleanup 间接证明链具体化 → FIXED

**要求**: 增加伪代码级验证链。

**修订证据**: Plan 第 507-542 行新增 "Close cleanup indirect proof chain" 章节，包含：(a) 完整 Python 伪代码（34 行）展示 handle close/cancel count、lane immediate acquire、reopen no spurious recovery、terminal/EventLog no duplicate 四步验证；(b) 每步验证含义的逐一解释（第 537-542 行）：handle count 证明 cancel 传播、reopen 无额外 recovery 证明 clean close 未误判、lane acquire 证明 capacity 释放、EventLog count 证明无重复 closeout。

**验证**: 通过。伪代码级证明链具体、可审查、可执行。覆盖了原 DS F-02。

---

### ADJ-09: Slice 3 consumer cancel 验证机制具体化 → FIXED

**要求**: 在 Slice 3 expected assertions 中加入具体验证机制。

**修订证据**: Plan 第 427-432 行将 consumer cancel 验证改写为四步机制：(a) cancel 前用 fresh short read transaction 读取 EventLog count 记为 `before_cancel_event_count`；(b) cancel 后立即 `await host.get_run(active_run_id)` 验证 active run 仍为 `RUNNING` 且 worker handle 未收到 cancel；(c) 再用 fresh short read transaction 读取 EventLog count，断言 `after_cancel_event_count == before_cancel_event_count`；(d) 释放 worker 后通过 `get_run` 或 watcher 验证 run 正常 terminal。

**验证**: 通过。验证机制使用 public API (`get_run`) + durable diagnostic (EventLog count fresh read)，不依赖 scheduler internals。覆盖了原 DS F-05。

---

## Residual Risks / Open Questions

1. **Slice 4 close cleanup proof 的可构造性**: 伪代码级证明链已具体化，但实际实现时仍需确认 `InspectableStressWorkerFactory` 的 handle close/cancel 计数与 `ActiveWorkerRegistry` 的交互是否可直接观测。Plan 的 stop condition（"如果 close cleanup 只能通过新增 production accessor 证明，停止"）已兜底。非 plan 缺陷，属于 implementation risk。
2. **CI pytest 调用检查**: Plan 要求 implementation agent 用 `rg` 搜索 CI 配置中的 pytest 调用。若仓库无 CI 配置文件，implementation report 需记录 "未发现对应 CI pytest 配置"。该 risk 已由 ADJ-05 从 review finding 转为 plan requirement，不再属于 unaddressed gap。
3. **StressTerminalObservation 最终存在性**: Plan 给出了明确的 delete-if-unused 规则。若实现阶段发现无需该类型，应删除；若保留，必须有消费路径。该风险已由 ADJ-03 从 review finding 转为 plan requirement。

## Controller Decision Status

- [x] Reviewed
- [x] All ADJ-01 through ADJ-09 verified as FIXED
- [x] Plan approved for implementation gate — no blocking findings remain

## Artifact Path

`docs/reviews/wu-stress-01-plan-rereview-ds-20260601.md`
