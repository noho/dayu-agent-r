# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 3 Code Review Fix（AgentCodex）

## 结论

`READY_FOR_CODE_REREVIEW`

- Gate：`code-review-fix-slice-3`
- Accepted base：`b33bb80b`
- 修复范围：仅 `S3-CR-F01`、`S3-CR-F02`
- 角色边界：AgentCodex accepted finding fix
- 未更新 control doc、README、两份 reviewer artifacts或既有 implementation artifact；未 commit、push、创建或修改 PR。

## 第一性原理与 owner 裁决

两项 accepted findings 均成立，且严重性判断准确：

1. `S3-CR-F01` 不是单纯低延迟优化。`_fail_recovering_run(...)` 已在同一 write transaction 中把 Run 从 `RECOVERING` 收口为 `FAILED` 并释放 active slot；若返回 `terminal_notice=None`，本 opener 的 terminal delivery watermark与 queued promotion barrier都不会消费这个已提交事实。因此 root cause 是 terminal producer丢弃了 transition owner 已返回的 exact `run_event`，不是 watcher、coordinator或 durable reconcile 缺陷。
2. `S3-CR-F02` 不是可延期的风格问题。`RunTransitionResult.run_event + Run stable terminal ref -> TerminalPostCommitNotice` 是单一投影语义；四个 producer 模块各自实现后已经出现参数名、错误文本与分支形态漂移。唯一正确 owner 是 `dayu.host.durable.run_transition`，直接消费者只负责传入本 transaction 的 promotion flag。

两项修复都不需要 schema、public API、Engine contract、coordinator状态机、producer manifest或 README 范围扩张。

## S3-CR-F01 修复证据

### Root cause

`dayu/host/engine_ingest.py::EngineEventIngestor._fail_recovering_run` 的 `StateMutationStatus.UPDATED` 分支已拿到 `fail_recovering_run_in_transaction(...)` 返回的 same-transaction `RunTransitionResult.run_event`，却硬编码 `terminal_notice=None`。两个上游 context-compaction/recovery caller只会继续传播该值，导致最终 `_finish_ingest(...)` 跳过 `TerminalPostCommitPort.notify_terminal_post_commit(...)`。

### Diff

- `dayu/host/engine_ingest.py`
  - `UPDATED` 分支改为直接调用 owner helper：
    `terminal_notice_from_transition(result, wake_queue_promotion=True)`。
  - helper只消费当前 transaction result；没有 latest/max/readback、第二 transaction、Run status猜测或日志解析。
  - `CAS_LOST`、`INVALID_STATE`及其它非 `UPDATED` 结果仍返回 rejected、`terminal_notice=None`，不会伪造 notice。

### Owner/runtime tests

- `tests/host/test_engine_ingest_mapping.py::test_reactive_fallback_over_budget_fails_closed_without_lost`
  - 走真实 context compaction -> `RUN_RECOVERING` -> fallback over hard budget -> `RUN_FAILED` 路径。
  - recording port在 callback 内断言 production runner 已无 active transaction；随后用独立 SQLite connection读取已提交 Run/EventLog join，再开启 typed read transaction读取 stable Run与exact event row。
  - 断言 `_finish_ingest` 交给端口的对象就是 `EngineIngestResult.terminal_notice`；notice、Run与EventLog row的 Session、sequence及Run identity一致；`wake_queue_promotion=True`；callback恰好一次。
- `tests/host/test_engine_ingest_mapping.py::test_reactive_fail_closed_propagates_recovering_fail_rejection`
  - 参数化覆盖 `CAS_LOST` 与 `INVALID_STATE`。
  - 两种结果都断言 `terminal_notice is None`、port notices为空、`RUN_FAILED` row为零。

## S3-CR-F02 修复证据

### Root cause

`admission.py`、`engine_ingest.py`、`recovery.py`、`dispatch.py` 各自定义 `_terminal_notice_from_transition(...)`，重复校验同一个 owner contract，且 dispatch 已漂移为 `should_wake_queue_promotion` 参数名与合并错误分支。重复实现使相同 terminal fact 在不同 producer 中可能得到不一致投影。

### Diff

- `dayu/host/durable/run_transition.py`
  - 新增唯一 typed `terminal_notice_from_transition(...)`。
  - required 输入只有 `RunTransitionResult` 与严格 bool `wake_queue_promotion`。
  - 直接校验 `run_event` 存在，以及 Run stable `terminal_event_id/terminal_event_sequence`、Session id、Run id与 exact row完全一致。
  - 返回 Host-private `TerminalPostCommitNotice`；不读取 store、不注册 callback、不 public package export。
  - 完整中文 docstring明确参数、返回值与 `HostDurableError`。
- `dayu/host/admission.py`、`dayu/host/engine_ingest.py`、`dayu/host/recovery.py`、`dayu/host/dispatch.py`
  - 直接 import并复用同一 owner helper。
  - 删除四份本地 helper，不保留 wrapper、alias或 re-export。
  - 所有原 producer flag与最外层 post-commit notify时点保持不变。

### Owner/static tests

- `tests/host/test_run_attempt_transitions.py::test_terminal_closeout_appends_concrete_terminal_events`
  - 用真实 terminal transition result在 commit return 后投影 notice。
  - 断言 exact sequence/stable Run ref/Session一致与 promotion flag原样保留。
  - 精确覆盖 missing `run_event` 与 inconsistent stable sequence 的 fail-closed错误。
- `tests/host/test_terminal_post_commit.py::test_terminal_notice_projection_has_single_durable_owner`
  - AST断言 owner模块恰好一个 `terminal_notice_from_transition` 定义。
  - AST断言四个 consumer都从 owner模块直接 import，且不存在本地同名/旧私有 helper定义。

## 验证证据

所有命令均在 `source .venv/bin/activate` 后执行。

### Targeted与 focused tests

- F01/F02 最终 targeted：`5 passed in 0.42s`。
- 三个 owner/runtime/static test文件完整执行：`157 passed in 1.70s`。
- producer manifest、direct promotion、optional/default/rebind与single-owner静态节点：`4 passed in 0.53s`。
- dual-opener目标节点：`1 passed in 0.62s`。
- 完整 `tests/host/test_watch_session_events.py`：`18 passed in 1.77s`。
- 原 S3 focused gate：`407 passed in 6.91s`。

### 完整 Host suite与单文件 coverage

命令：

```bash
pytest tests/host -q --cov=dayu.host \
  --cov-report=json:workspace/tmp/wu-host-session-event-delivery-01-s3-fix-host-coverage.json \
  --cov-report=term
```

结果：`2067 passed, 2 skipped, 6 deselected in 69.81s`，总覆盖率 `91%`。

| S3 modified production file | Covered lines / statements | Coverage |
|---|---:|---:|
| `dayu/host/admission.py` | 962 / 1058 | 91% |
| `dayu/host/command.py` | 367 / 416 | 88% |
| `dayu/host/dispatch.py` | 1174 / 1292 | 91% |
| `dayu/host/durable/run_transition.py` | 1302 / 1397 | 93% |
| `dayu/host/engine_ingest.py` | 1283 / 1416 | 91% |
| `dayu/host/open_host.py` | 638 / 726 | 88% |
| `dayu/host/recovery.py` | 246 / 268 | 92% |
| `dayu/host/terminal_post_commit.py` | 20 / 21 | 95% |
| `dayu/host/waiting.py` | 547 / 618 | 89% |

全部 S3 modified production文件均达到 `>=80%`。

### Type、diff与 boundary scans

- 完整 `pyright`：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过；新增未跟踪 test/artifact另以 `git diff --no-index --check` 检查，无 whitespace error。
- terminal producer AST manifest：21 个 producer闭集精确通过，`_fail_recovering_run` row保持在 manifest中。
- ordinary direct promotion allowlist：仍精确为5处；terminal producer没有 direct promotion。
- single projection owner scan：仅 `run_transition.py` 定义 helper；四个 producer仅 direct import/call。
- optional/default port：production constructor/producer参数无 optional/default terminal port；广义文本扫描唯一命中仍是 `dispatch.py` inert scheduler在 construction-only bind 前的私有未绑定状态字段。该既有状态只由 required accessor与一次性 binder消费，没有 optional producer contract、临时 no-op、setter或runtime rebind，本修复未改变该已接受构造不变量。
- Engine boundary：`dayu/engine` 对 `TerminalPostCommit`、`terminal_post_commit`、`session_event_delivery` 零命中。
- runtime reverse dependency：锚定真实 import语句扫描零命中；`dayu.runtime` 未反向 import Engine/Host/Service/UI/Fins。
- scope：本 fix只改5个 production owner/consumer、3个 authorized Host tests与本 artifact；完整 Slice 3 production/test diff仍位于 accepted S3 allowlist。Controller-owned control doc保持既有 dirty状态且未写入；两份 reviewer artifacts未修改。

## README audit

- `dayu/host/README.md`：terminal coordinator与transition projection owner变化命中其 Host current-contract职责。
- `tests/README.md`：新增 owner/static/runtime regression evidence命中测试分层说明职责。
- `dayu/README.md`：本 fix没有改变既有 `UI -> Service -> Host -> Engine` 分层或 public边界。
- accepted plan与本 gate明确把 README实际同步留给 S4；本 fix仅完成审计，没有修改任何 README。

## Finding状态与 residual risks

| Finding | 状态 | 证据 |
|---|---|---|
| `S3-CR-F01` | 已修复 | success path exact notice + post-commit runtime propagation；CAS-lost/rejected零notice |
| `S3-CR-F02` | 已修复 | durable owner唯一helper + 四consumer direct import + owner/static tests |

- 当前 accepted fix没有未分类 residual risk或 uncovered correctness path。
- Service exact-five、CLI callback execution domain、旧 Service relay删除与 README实际更新继续由已批准 S4拥有；本 gate未实施或冒充完成。

`READY_FOR_CODE_REREVIEW`
