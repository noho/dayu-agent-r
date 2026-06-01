# WU-STRESS-01 Plan Review — AgentDS

## Gate

plan-review

## Reviewed Target

`docs/host/wu-stress-01-host-production-stress-suite-plan.md`

## Design Source

`docs/host/design.md`

## Control Source

`docs/host/host-core-followup-implementation-control.md`

## Code Inspection Artifact

`docs/reviews/wu-stress-01-discussion-code-inspection-20260601.md`

## Conclusion

PASS — 5 findings, 0 blocking.

Plan 满足 design_doc 设计目标和 WU-STRESS-01 全部 success signal；未过度设计；未要求修改 Host public contract、durable schema、EventLog、recovery 状态机或 scheduler 生产行为；watch reconnect 语义未越界；pytest marker/addopts 默认排除策略不会破坏常规测试；slices 可独立验证、file ownership 清晰；测试为 deterministic，无不可控 sleep 或外部服务依赖；满足 CLAUDE.md 中文 docstring、强类型、禁止 Any/object 约束。

## Findings

### F-01-未修复-LOW-addopts 全局副作用未充分评估

Plan 在 `pyproject.toml` 新增 `addopts = "-m 'not stress'"`。当前 `pyproject.toml:136-137` 无 `addopts` 配置，因此该变更是对全局 pytest 默认行为的修改。

**证据**：当前 `tests/README.md` 中所有命令（例如 `pytest tests/host -q`）均未携带 `-m` 参数。新增全局 `addopts` 后，这些命令的行为变为 `pytest -m 'not stress' tests/host -q`。虽然当前无任何 test 标记 `stress`，默认命令行为不变，但以下风险未被 plan 覆盖：

- 若未来有人在非 stress test 上误标记 `@pytest.mark.stress`，会被静默排除。
- 若现有 CI 脚本或 Makefile 中已有 `-m` 参数，将与 `addopts` 产生合并行为（pytest 的 marker 合并规则是与逻辑），可能导致意外 deselect。
- Plan 未检查项目中是否存在 `conftest.py` 的 `pytest_collection_modifyitems` 或其它 hook 可能与 `-m` 交互。

**建议**：在 Slice 1 validation 中增加 `pytest tests/host -q --collect-only` 验证默认收集不减少已有测试数量；或增加 `pytest --markers` 检查确认 marker 注册无误。

**controller 裁决**：非阻塞。当前无 `stress` marker 冲突，默认行为不变。实现时做一次全量 collect-only 对比即可关闭此风险。

---

### F-02-未修复-LOW-Slice 4 close cleanup 间接验证链未具体化

Plan Slice 4 对 scheduler close 后 "no active task" 的验证采用间接证据链："如直接使用 public opener无法访问 private scheduler，则通过 handle close count、lane reacquire、reopen no spurious recovery、EventLog terminal counts 间接证明"。

**证据**：`dayu/host/dispatch.py` 的 `HostDispatchScheduler` 内部状态（`_active_tasks`、lane controller、dispatch drain）不通过 public API 暴露。design_doc 明确 "scheduler / wakeup / dispatch control API：Service 不得调用 scheduler wakeup、读取 dispatch row 或控制 dispatch"（design.md:991）。Plan 的 stop condition（"如果 close cleanup 只能通过新增 production accessor 证明，停止"）正确保护了边界。

但间接证明链存在以下模糊点：

- "handle close count"：handle 指 `DeterministicStressWorkerFactory` 记录的 worker handle close count，还是 `ActiveWorkerRegistry` 的 handle？前者是测试层记录，可验证；后者是生产对象。
- "lane reacquire" 用 `timeout_seconds=0` 验证 capacity 可用，但 lane 是 `dayu.runtime` 层中立组件，不是 Host scheduler 内部状态。lane capacity 恢复不等价于 scheduler internal task cleanup 完成。
- Plan 未给出具体的断言伪代码或最小验证步骤。

**建议**：在 Slice 4 实现前，补一段伪代码级别的验证链：先 close Host，再通过 `InspectableStressWorkerFactory` 确认所有 released handle close count == accepted count，再 reopen 确认无 spurious recovery event，最后通过 lane immediate acquire 确认 capacity 释放。

**controller 裁决**：非阻塞。Plan 的 stop condition 已兜底。实现时若无法构造可信间接证明，应停止并报告。

---

### F-03-未修复-LOW-缺少 pytest-timeout 依赖检查

Plan 要求所有 stress tests 使用 `@pytest.mark.timeout(...)`（Implementation Decisions 第 5 条），但未检查 `pytest-timeout` 是否已在 `pyproject.toml` 的 dependencies 或 optional-dependencies 中声明。

**证据**：`@pytest.mark.timeout` 由 `pytest-timeout` 插件提供，不是 pytest 内置 marker。若未安装，stress tests 将因 unknown marker 报 warning 或跳过 timeout 行为，导致 stress test 可能无限挂起。

**建议**：在 Slice 1 实施前确认 `pytest-timeout` 已可用；若未在 `pyproject.toml` 声明，应在 Slice 1 中新增为 test dependency。

**controller 裁决**：非阻塞。实现时若 `pytest-timeout` 不可用，应添加到 `pyproject.toml` 的 test 依赖组。

---

### F-04-未修复-INFO-Slice 3 lag 计算的数据源语义应明确

Plan 定义 `compute_watch_lag(latest_sequence, last_seen_sequence) -> int`，其中 `latest_sequence` 来自 `read_latest_event_sequence(root_path)`。

**证据**：design_doc 要求 "需要 fresh durable truth 的 public read、scheduler、recovery 和 governance decision 必须开启新的短 read / write transaction；不得复用长 read transaction、read model、projection lag、memory snapshot 或 watch cache 作为治理真源"（design.md:753）。Lag 计算是诊断用途，不是治理真源，不违反此约束。但 plan 未在 `compute_watch_lag` 或 `read_latest_event_sequence` 的语义中明确说明：

- `latest_sequence` 必须来自新的短 read transaction，不能复用 watcher 内部缓存的 cursor。
- lag 是 point-in-time diagnostic snapshot，不保证线性一致性。

**建议**：在 `stress_support.py` 的 `compute_watch_lag` docstring 中声明数据源语义。

**controller 裁决**：非阻塞。属于实现细节，由 CLAUDE.md 中文 docstring 约束自然覆盖。

---

### F-05-未修复-INFO-Slice 3 "consumer cancel 不改变 active run 状态" 验证路径未指定

Plan Slice 3 断言 "consumer cancel 不改变 active run 状态、不新增 EventLog"。该断言语义正确（对齐 design_doc watch 取消只关闭订阅的语义），但 plan 未指定验证机制。

**证据**：design_doc 明确 "提前停止消费时，由调用方 cancel consumer task 或在返回对象支持 `aclose()` 时显式 `aclose()`，这只关闭本次 watch 订阅，不写 EventLog、不 cancel Run、不影响其它 watcher"（design.md:950）。Plan 应指定：是使用 `get_run` 确认 consumer cancel 前后 Run status 不变，还是使用 EventLog count helper 确认无新增 row。

**建议**：在 Slice 3 expected assertions 中增加具体验证步骤描述。

**controller 裁决**：非阻塞。实现时可自然选择 `get_run` + EventLog count 组合验证。

---

## Open Questions / Residual Risk

1. **addopts 与 CI 交互**：若项目存在未在 plan 中引用的 CI 配置文件（如 `.github/workflows` 中的 pytest 命令），新增 `addopts` 可能改变 CI 行为。实现前应检查 CI 配置。
2. **pytest-timeout 可用性**：若 `pytest-timeout` 未安装且未在 Slice 1 中处理，stress tests 可能无限挂起。
3. **Slice 4 close cleanup 间接证明的可构造性**：若实现时发现无法通过 public API + test helper 构造可信的 close cleanup 证明链，将触发 stop condition。这不是 plan 缺陷，但属于 residual implementation risk。

## Controller Decision Status

- [ ] Reviewed
- [ ] Findings accepted / rejected / deferred
- [ ] Plan approved for implementation gate
- [ ] Plan requires revision before implementation

## Artifact Path

`docs/reviews/wu-stress-01-plan-review-ds-20260601.md`
