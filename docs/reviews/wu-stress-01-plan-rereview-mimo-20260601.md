# WU-STRESS-01 Plan Re-Review — AgentMiMo

## Gate

- **Gate**: plan re-review
- **Reviewer**: AgentMiMo
- **Date**: 2026-06-01

## Reviewed target

`docs/host/wu-stress-01-host-production-stress-suite-plan.md`（修订版）

## Reference artifacts

- `docs/reviews/wu-stress-01-plan-controller-adjudication-20260601.md` — controller 裁决
- `docs/reviews/wu-stress-01-plan-review-mimo-20260601.md` — 原 review

## Conclusion

**PASS** — ADJ-01 到 ADJ-09 全部被修订后 plan 正确修复，无 residual blocking finding。

## Per-finding re-review status

### ADJ-01 — failure_boundary 类型收窄：FIXED

**裁决要求**: 把 `failure_boundary: str | None` 改成封闭诊断类型要求。

**修订后 plan 证据**:

- §3（第 149-167 行）新增 `StressFailureBoundary = Literal[...]`，包含 11 个封闭值：`durable` / `scheduler` / `watch` / `watch_reconnect` / `liveness` / `recovery` / `projection` / `active_cleanup` / `scheduler_close` / `worker_accept` / `unknown`。
- 明确声明"不得使用裸字符串扩散"和"failure_boundary 必须是 StressFailureBoundary | None 或等价封闭枚举类型，不得是 str | None"。
- Slice 5 Failure paths（第 633 行）重复约束："必须使用 StressFailureBoundary 封闭类型"。
- Python 3.11 语法兼容性已声明。

**状态**: FIXED。类型已收窄为封闭 Literal，pyright 可在调用侧检查拼写。

### ADJ-02 — helper docstring 约束显式化：FIXED

**裁决要求**: 所有新增模块级函数、class、dataclass 都有完整中文 docstring；lag diagnostic helper 必须声明 fresh short read transaction 与 point-in-time diagnostic 语义。

**修订后 plan 证据**:

- §4（第 194-209 行）新增独立小节"新增 helper 的 docstring、类型和 diagnostic 语义"，明确要求：
  - 所有新增模块级函数、class、dataclass 都必须有完整中文 docstring。
  - 至少包含参数含义、返回值、可能抛出的异常、测试 helper 边界说明。
  - 禁止 `Any`、`object`、裸 `dict` / `list` 注解和无类型签名。
- lag diagnostic helper（第 205-209 行）明确要求 docstring 声明：
  - "每次读取 latest sequence、session terminal sequence 或 EventLog count 时，都通过 fresh short read transaction 获取 point-in-time diagnostic"。
  - "该读取只用于测试诊断和 lag 估算，不表达 watcher replay truth"。
  - "不得复用长事务快照计算'最终 lag'"。

**状态**: FIXED。docstring 和 diagnostic 语义约束已显式覆盖所有新增 helper。

### ADJ-03 — StressTerminalObservation 消费场景：FIXED

**裁决要求**: 明确消费路径，或要求实现时不创建该类型。

**修订后 plan 证据**:

- §3（第 186-192 行）明确列出三个消费路径：
  - `terminal_duplicate_count(observations: Sequence[StressTerminalObservation]) -> int`
  - `terminal_dedupe_ok(observations: Sequence[StressTerminalObservation]) -> bool`
  - `watch_lag_samples(...)` 或等价 lag helper 读取 observation 中的 `event_sequence` / `run_id`
- 同时声明："如果实现最终直接用局部 tuple / dict-free typed helper 完成去重和 lag 计算，而没有上述消费路径，则不得创建 StressTerminalObservation，避免死设计或 god bag。"

**状态**: FIXED。消费路径已明确，且提供了"不创建"的退出条件。

### ADJ-04 — stress worker factory 边界具体化：FIXED

**裁决要求**: 说明新增 stress factory 与既有 recovery helper 的增量职责，优先复用既有 helper。

**修订后 plan 证据**:

- §5（第 211-227 行）新增独立小节，明确：
  - "优先复用 run_blocking_owner_process、AsyncControlledFinalAnswerWorkerFactory、accepted marker、process terminate、owner stale fault injection、event type count、attempt count 等既有能力"。
  - "只有在现有 helper 不能覆盖 stress 诊断时才新增类型"。
  - 新增职责只限于：stream exception、clean EOF、handle close/cancel count、accepted snapshot count、per-run scripted worker 行为选择。
  - "不得复制 recovery_support.py 中已有多进程 owner / marker / stale liveness 逻辑的大段实现。若只需要语义微调，应写薄 wrapper，并在 wrapper docstring 中说明复用关系和增量职责"。
- Slice 4 Prerequisites（第 470 行）要求："InspectableStressWorkerFactory 的增量职责已确认不能由 recovery_support 现有 helper 满足"。

**状态**: FIXED。增量职责边界清晰，复用优先原则已明确。

### ADJ-05 — pytest addopts / CI / marker 验证补足：FIXED

**裁决要求**: 在 Slice 1 validation 加入 CI pytest 命令检查、`pytest --markers` 和默认收集 / deselect 行为验证。

**修订后 plan 证据**:

- Slice 1 Tests / validation（第 278-286 行）新增：
  - `pytest --markers` 验证 marker 可见。
  - `pytest --collect-only tests/host/test_host_production_stress.py -q` 验证默认排除。
  - `pytest -o addopts="" --collect-only ...` 验证覆盖后可收集。
- Slice 1 Expected assertions（第 290-296 行）新增：
  - `pytest --markers` 输出必须包含 `stress` 和 `timeout` marker。
  - CI / 常规 pytest 命令检查必须覆盖 `.github/**`、`pyproject.toml`、`tox.ini`、`noxfile.py`、`Makefile`；建议用 `rg` 检查。
  - implementation report 必须记录发现的 pytest 调用及是否受 addopts 影响。
  - 两条 collect-only 命令的 collected / deselected / selected 摘要必须记录。
- Slice 1 Failure paths（第 301-304 行）新增：
  - `pytest --markers` 缺少 `timeout`：必须停止修复环境。
  - 覆盖 addopts 的 collect-only 无法收集完整 stress tests。
- Validation Matrix（第 647-651 行）同步新增 `pytest --markers` 和两条 collect-only 命令。

**状态**: FIXED。CI 检查、marker 验证和 collect-only 行为验证已全面覆盖。

### ADJ-06 — pytest-timeout 可用性写清：FIXED

**裁决要求**: 写明依赖已存在，并在 Slice 1 验证 marker 可用。

**修订后 plan 证据**:

- Contract section（第 123 行）新增："pytest-timeout>=2.1.0 已在 pyproject.toml test optional dependency 中存在；implementation 不应新增依赖，只需验证 pytest --markers 中存在 timeout marker。"
- Slice 1 Prerequisites（第 248 行）："当前仓库 test optional dependency 已包含 pytest-timeout>=2.1.0；implementation 只验证 marker 可用，不新增依赖。"
- Slice 1 Expected assertions（第 290 行）："timeout marker 来自已存在的 pytest-timeout dependency，不需要新增依赖。"
- Slice 1 Failure paths（第 301 行）："pytest --markers 缺少 timeout：说明测试环境没有安装已声明的 pytest-timeout，必须停止修复环境。"

**状态**: FIXED。依赖存在性和验证要求已显式声明。

### ADJ-07 — slice 依赖 handoff 显式化：FIXED

**裁决要求**: 在每个 slice 写明 prerequisites / stable output。

**修订后 plan 证据**:

- 每个 slice（Slice 1-5）均已新增：
  - **Prerequisites** 小节：声明前置 slice 完成状态和可复用的 helper / 交付物。
  - **Stable output for next slices** 小节：声明本 slice 产出的、后续 slice 可依赖的稳定交付物。
- 例如 Slice 2 Prerequisites（第 327-331 行）声明依赖 Slice 1 的 summary、failure boundary、option builder、worker/handle。
- 例如 Slice 4 Prerequisites（第 465-470 行）声明依赖 Slice 1、Slice 2 crash helper、Slice 3 terminal dedupe helper，并要求确认 InspectableStressWorkerFactory 增量职责。
- Slice 5 Prerequisites（第 573-577 行）声明依赖 Slice 1-4 全部完成。

**状态**: FIXED。slice 间依赖和交付物已显式声明。

### ADJ-08 — Slice 4 close cleanup 间接证明链具体化：FIXED

**裁决要求**: 增加伪代码级验证链。

**修订后 plan 证据**:

- Slice 4 新增"Close cleanup indirect proof chain"小节（第 507-542 行），包含：
  - 完整伪代码：从 factory 创建、host 打开、submit active + queued run、cancel queued、close host，到 reopen 后验证。
  - 四个断言步骤：
    1. `factory.total_cancel_count >= 1` — 证明 scheduler close 已向 active worker 传播取消。
    2. `factory.total_close_count == factory.accepted_handle_count` — 证明所有 handle 已 close。
    3. `verify_lane_immediate_acquire(...)` — 证明 close 后没有遗留 lane claim。
    4. `after_terminal_counts == expected_no_duplicate_increment(...)` — 证明 close/reopen 没有重复 terminal。
    5. `count_event_type(tmp_path, "RUN_RECOVERING") == expected_recovery_count_from_intentional_crash_only` — 证明 clean close 未被误判为 stale orphan。
  - 证明链含义解释。

**状态**: FIXED。伪代码级验证链已具体、可审查、可执行。

### ADJ-09 — Slice 3 consumer cancel 验证机制具体化：FIXED

**裁决要求**: 在 Slice 3 expected assertions 中加入具体验证机制。

**修订后 plan 证据**:

- Slice 3 Expected assertions（第 427-431 行）新增四步验证：
  1. "cancel consumer 前用 fresh short read transaction 读取 EventLog count，记为 before_cancel_event_count"。
  2. "cancel consumer 后立即用 await host.get_run(active_run_id) 验证 active run 仍为 RUNNING 或原预期非终态，且 worker handle 未收到 cancel"。
  3. "再用 fresh short read transaction 读取 EventLog count，断言 after_cancel_event_count == before_cancel_event_count"。
  4. "释放对应 worker 后，再通过 public get_run 或 watcher 验证 run 正常 terminal"。

**状态**: FIXED。consumer cancel 验证机制已具体到 get_run + EventLog count 前后对比。

## Residual risks / open questions

无新发现。原 review 的 F5（addopts gotcha，已文档化）、F6（首次引入 @pytest.mark.timeout，依赖已存在）和 F7（slice 依赖隐式，现已显式化）均为观察项，已在修订中解决或确认无需修改。

## Artifact path

`docs/reviews/wu-stress-01-plan-rereview-mimo-20260601.md`
