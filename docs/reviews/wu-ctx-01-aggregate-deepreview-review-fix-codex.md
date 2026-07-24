# WU-CTX-01 whole-WU aggregate deepreview review fix（AgentCodex）

## 1. 执行边界

- WU base：`5afe71fe`
- accepted tip / 执行时 `HEAD`：`fad15d39067a5822c7c9b8443080542984ee30d4`
- 角色：AgentCodex，只负责 Controller 已裁决 fix gate 的 plan / implement / fix。
- 实现范围：严格限于 `CTRL-AGG-01..09`。
- 未实现 Controller rejected findings；Controller 记录的 deferred findings 为 0。
- 未创建 commit。

本次修复前先核对了 `AGENTS.md`、`docs/host/design.md` §25、Controller
adjudication、两路 aggregate review、accepted plan/amendments 和三个 Slice
artifact 的相关部分。问题动机成立：九项 accepted finding 分别命中 typed contract、
continuation source 状态表达、事务编排可维护性、public lifecycle 组合证据、重复估算、
threshold invariant、派生比例 owner、错误枚举 owner 与 anchor exclusion 测试缺口。
实现没有重新裁决 finding，也没有扩展到 rejected 路径。

## 2. 语义 owner 与修复映射

| Finding | 修复 | Owner / 证据 |
| --- | --- | --- |
| `CTRL-AGG-01` | `_UsageManifestPairing.status/reason` 改为私有 `StrEnum` 闭集；生产分支使用 enum identity，durable JSON 边界显式输出 `.value`。 | usage pairing 的产生与 durable projection 均留在 `dayu.host.engine_ingest`。 |
| `CTRL-AGG-02` | 将 continuation frozen source 拆为 `_CompleteContinuationFrozenSources` 与 `_UnavailableContinuationFrozenSources` 判别联合；complete variant 的字段全部非 optional，删除相关 `cast(str/int, frozen_sources...)`。 | source 恢复仍按 projection → tool schema → policy → request semantics 的既有优先级；`RunnerCallSizingUnavailableReason` 仍是 manifest sizing unavailable 原因 owner。 |
| `CTRL-AGG-03` | 将 `_StartReactiveRecoveryOperation.__call__` 拆成模块级 typed helper：source 校验、candidate 组装、sizing、hard closeout、start identity、truth commit、manifest snapshot 与 result projection。 | 所有写入仍使用同一 `HostTransaction`；顺序保持 manifest → budget fact → `RUN_STARTED` / `ATTEMPT_STARTED`，hard fallback 保持 budget fact → terminal closeout。 |
| `CTRL-AGG-04` | 新增 public `open_host` 集成测试，使用合法 `ToolCallingWorkerFactory` scripted runner，不产生 usage，断言 Run `SUCCEEDED`、存在 `CONTEXT_BUDGET_EVALUATED`、方法为 `conservative_fallback`、原因为 `usage_missing`，且无 `USAGE_REPORTED`。 | 测试未接入真实 provider、未新增 provider 分支、未 monkeypatch anchor resolver。 |
| `CTRL-AGG-05` | steer 首次 conservative sizing 保存 `BudgetEstimate`，anchor 重算复用同一对象，不再对同一 candidate 二次估算。 | `test_steer_hard_continuation_orders_fact_before_new_attempt` 记录 production estimator 调用次数，断言 steer 增量恰为 1。 |
| `CTRL-AGG-06` | 新增 `validate_context_threshold_ordering` 唯一校验 helper；typed `ContextSizingResult`、五阶段 decision matrix 与 durable parser 全部拒绝 `soft >= hard`，错误文本统一为 soft 必须小于 hard。 | `dayu.host.context_budget` 持有 threshold ordering contract；durable parser 调用该 owner，不重写条件。 |
| `CTRL-AGG-07` | 新增 `context_utilization_basis_points`，唯一比例常量 `_UTILIZATION_BASIS_POINTS_SCALE = 10_000` 只存在于 `context_budget.py`；result builders、typed result 与 durable parser 共用该 helper。 | utilization 派生公式由 context budget owner 产生和校验，event parser 只复用。 |
| `CTRL-AGG-08` | 从 `ContextSizingFallbackReason` 删除四个错误 owner 的 `CONTINUATION_*` dead members。 | 四个名字只保留在正确的 `RunnerCallSizingUnavailableReason`；新增 exact enum-set owner test 防止回流。 |
| `CTRL-AGG-09` | 新增 direct resolver 测试：普通 call 后追加更近的 strict compactor manifest/link/usage/completion，断言普通 usage 仍被选择，compactor 整体排除且不形成 orphan barrier。 | fixture 构造合法 `compactor_proposal` manifest，不在 resolver 下游加入测试特例。 |

## 3. 修改文件

Production：

- `dayu/host/admission.py`
- `dayu/host/context_budget.py`
- `dayu/host/context_events.py`
- `dayu/host/engine_ingest.py`

Tests / docs：

- `tests/host/test_context_anchor.py`
- `tests/host/test_context_budget.py`
- `tests/host/test_context_budget_evaluated.py`
- `tests/host/test_public_steer.py`
- `tests/host/test_public_tool_wiring_smoke.py`
- `tests/README.md`
- 本 artifact

`dayu/host/README.md` 已按其更新约束审计。本次没有改变 public API、稳定架构边界或
既有 Host 开发契约，因此不机械更新；`tests/README.md` 已补充新增测试能力。

## 4. 验证

### 4.1 聚焦 owner / integration tests

```bash
source .venv/bin/activate
pytest -q \
  tests/host/test_context_budget.py \
  tests/host/test_context_budget_evaluated.py \
  tests/host/test_context_anchor.py \
  tests/host/test_engine_ingest_mapping.py \
  tests/host/test_public_steer.py \
  tests/host/test_public_tool_wiring_smoke.py
```

结果：`209 passed in 2.18s`。

threshold helper 最后精简后再次执行：

```bash
pytest -q tests/host/test_context_budget.py \
  tests/host/test_context_budget_evaluated.py
```

结果：`63 passed in 0.39s`。

### 4.2 完整 Host tests

最终源码执行：

```bash
source .venv/bin/activate
pytest -q tests/host
```

结果：`2259 passed, 2 skipped, 6 deselected in 53.75s`。

branch coverage 全量运行中曾有一个既有 scheduler timing case 因测试 lane 的
`0.01s` acquire timeout 瞬时失败；日志为 `dispatch.lane_acquire.timed_out`，其余
`2258` 个测试通过。该节点立即单独复跑通过：

```bash
pytest -q \
  tests/host/test_dispatch_scheduler.py::test_scheduler_closes_default_local_proxy_after_terminal_before_late_event
```

结果：`1 passed in 0.34s`；随后上述完整 Host tests 再次全绿。

### 4.3 whole-WU 完整标准 / affected suites

为覆盖 WU base 到最终 working tree 的 Host 与 Service production union，按
`tests/README.md` 的项目标准 suite 一次性执行：

```bash
source .venv/bin/activate
coverage erase
pytest tests/contracts tests/cli tests/documents tests/fins tests/tools \
  tests/host tests/runtime tests/service tests/engine -q \
  --cov=dayu.host --cov=dayu.service --cov-branch --cov-report=
```

结果：`5704 passed, 11 skipped, 6 deselected, 3 warnings in 190.53s`。

3 条 warning 全部来自已安装 `edgar` 包的 deprecated API；6 个 deselected 是默认
pytest 配置排除的 opt-in stress tests。该命令同时覆盖完整 Host、完整 Service 及
Host / Service 的 CLI、Engine、Runtime、Tools、Fins 等标准消费者，不依赖旧 Slice
coverage 数据拼接。

### 4.4 全量 pyright

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
```

最终结果：`0 errors, 0 warnings, 0 informations`。

### 4.5 whole-WU production Python union branch coverage

gate allowlist 直接由最终 working tree 执行以下命令生成：

```bash
git diff --name-status 5afe71fe -- 'dayu/**/*.py'
```

结果为 25 个现存 production Python 文件，全部状态为 `M` 或 `A`，没有删除后无法
执行的模块。精确 union allowlist 为：

```text
M	dayu/host/__init__.py
M	dayu/host/_runner_call_manifest.py
M	dayu/host/accepted_result_projection.py
M	dayu/host/admission.py
M	dayu/host/api.py
M	dayu/host/command.py
M	dayu/host/compact_payload.py
M	dayu/host/compaction_operation.py
A	dayu/host/context_anchor.py
M	dayu/host/context_budget.py
M	dayu/host/context_events.py
M	dayu/host/context_fallback.py
M	dayu/host/dispatch.py
M	dayu/host/durable/run_transition.py
M	dayu/host/durable/schema.py
M	dayu/host/durable/state.py
M	dayu/host/engine_ingest.py
M	dayu/host/lifecycle_events.py
M	dayu/host/memory.py
M	dayu/host/open_host.py
M	dayu/host/read_api.py
M	dayu/host/recovery.py
M	dayu/host/run_input.py
M	dayu/host/waiting.py
M	dayu/service/entrypoint_runtime.py
```

以下逐文件数据来自 §4.3 对最终 working tree 的同一次 branch-enabled coverage
run：

| 文件 | Statements | Miss | Branch | Partial | Coverage |
| --- | ---: | ---: | ---: | ---: | ---: |
| `dayu/host/__init__.py` | 10 | 0 | 0 | 0 | 100% |
| `dayu/host/_runner_call_manifest.py` | 561 | 58 | 206 | 55 | 85% |
| `dayu/host/accepted_result_projection.py` | 278 | 13 | 108 | 9 | 93% |
| `dayu/host/admission.py` | 1203 | 119 | 334 | 87 | 86% |
| `dayu/host/api.py` | 1380 | 91 | 344 | 85 | 90% |
| `dayu/host/command.py` | 420 | 50 | 58 | 9 | 88% |
| `dayu/host/compact_payload.py` | 235 | 21 | 72 | 16 | 87% |
| `dayu/host/compaction_operation.py` | 497 | 30 | 100 | 21 | 91% |
| `dayu/host/context_anchor.py` | 433 | 52 | 186 | 46 | 84% |
| `dayu/host/context_budget.py` | 509 | 56 | 192 | 56 | 84% |
| `dayu/host/context_events.py` | 540 | 61 | 162 | 38 | 84% |
| `dayu/host/context_fallback.py` | 310 | 29 | 108 | 27 | 87% |
| `dayu/host/dispatch.py` | 1581 | 180 | 422 | 113 | 85% |
| `dayu/host/durable/run_transition.py` | 1417 | 109 | 312 | 101 | 88% |
| `dayu/host/durable/schema.py` | 353 | 10 | 48 | 11 | 95% |
| `dayu/host/durable/state.py` | 1388 | 163 | 334 | 97 | 83% |
| `dayu/host/engine_ingest.py` | 1721 | 182 | 512 | 119 | 85% |
| `dayu/host/lifecycle_events.py` | 147 | 5 | 12 | 2 | 96% |
| `dayu/host/memory.py` | 934 | 72 | 218 | 63 | 88% |
| `dayu/host/open_host.py` | 759 | 83 | 124 | 23 | 86% |
| `dayu/host/read_api.py` | 528 | 44 | 154 | 25 | 90% |
| `dayu/host/recovery.py` | 329 | 35 | 116 | 31 | 84% |
| `dayu/host/run_input.py` | 1913 | 248 | 730 | 189 | 82% |
| `dayu/host/waiting.py` | 654 | 75 | 202 | 62 | 83% |
| `dayu/service/entrypoint_runtime.py` | 877 | 109 | 298 | 72 | 83% |
| **whole-WU union 合计** | **18977** | **1895** | **5352** | **1357** | **86%** |

此外，对 allowlist 中每个文件独立执行：

```bash
coverage report --include="$union_file" --fail-under=80
```

25 次均返回成功；最低为 `dayu/host/run_input.py` 的 82%，不存在需补测试或声明
blocker 的文件。accepted Slice coverage 只作为历史补充，本节当前 working tree 的统一
运行才是本 gate 的最终 coverage 证据。

### 4.6 diff / stale / allowlist / README audit

- `git diff --check`：通过，无输出。
- stale pairing / cast audit：旧 `_USAGE_PAIRING_STATUS_*`、
  `_USAGE_PAIRING_REASON_*`、相关 `cast(str/int, frozen_sources...)` 均无命中。
- threshold stale audit：旧 `must not exceed` / `thresholds are out of order`
  文本在三个 owner 文件中无命中。
- basis-point owner audit：`dayu/host/**/*.py` 中 `10_000` 仅命中
  `dayu/host/context_budget.py` 的单一私有常量。
- continuation owner audit：四个 `CONTINUATION_*_UNAVAILABLE` 名字只存在于
  `_runner_call_manifest.py` 的 `RunnerCallSizingUnavailableReason` 及其
  `engine_ingest.py` producer/consumer。
- steer 静态审计：`_create_steer_attempt_result` 中
  `estimate_prepared_runner_call_candidate(...)` 仅一次。
- README audit：仅 `tests/README.md` 需要并已更新；新增条目使用稳定能力标题
  `context budget / anchor integration`，不含 WU、aggregate 或 fix gate 过程措辞；
  `dayu/host/README.md` 无 diff。
- 未修改两路 aggregate review、Controller adjudication 或
  `docs/host/issues-implementation-control.md`。

执行前已有且全程保护的 Controller dirty docs 状态：

```text
 M docs/host/issues-implementation-control.md
?? docs/reviews/code-review-20260724-073108.md
?? docs/reviews/code-review-20260724-074017.md
?? docs/reviews/wu-ctx-01-aggregate-deepreview-controller-adjudication.md
```

结束时内容 SHA-256 分别为：

```text
8c3a8b0e09b8afc44e40362935b34caf9d1b9f9489a65bf8bc822a4c3baef0b4  docs/host/issues-implementation-control.md
dc30504267cc0eca7772b6bcf2171454a8f9e284022556bfb3f9fec40ccbe8b5  docs/reviews/code-review-20260724-073108.md
c5087c47704f208a8b711d6c14ace7c5cd458068f38155510781a96bfee71b6f  docs/reviews/code-review-20260724-074017.md
771d8ea3db500071b0457fe9a0b29db3be3c1f92df0c602171ac4d553094adb3  docs/reviews/wu-ctx-01-aggregate-deepreview-controller-adjudication.md
```

## 5. Residual risk / 未覆盖项

- 默认 pytest 配置排除了 6 个 stress tests；本 gate 未显式运行 opt-in production
  stress suite。完整 Host suite与项目标准 suite 均已全绿。
- public no-usage 组合测试使用合法 scripted runner，按 Controller 要求没有调用真实
  provider；真实 provider 的 usage 上报差异仍由既有 provider smoke / matrix 覆盖。
- Controller 明确保留的 long-session performance 风险不属于本 fix gate，本次没有引入
  新的预计算、缓存或后台治理机制。
- 未实现任何 rejected finding，包括 kind-classifier 抽象、额外 barrier/cartesian
  矩阵、默认 fallback reason 移除、floor/int 调整或旧 API 注释修订。
