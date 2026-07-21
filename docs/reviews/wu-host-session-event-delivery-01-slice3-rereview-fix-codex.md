# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 3 Re-Review Fix（AgentCodex）

## 结论

`READY_FOR_NARROW_CODE_REREVIEW`

- Gate：`code-rereview-fix-slice-3`
- Accepted base：`b33bb80b`
- 修复范围：仅 accepted `S3-RR-F01`
- 角色边界：AgentCodex accepted finding fix
- 未修改 control doc、reviewer artifacts、README、public export、Engine boundary 或其它 Slice 3 语义；未 commit、push 或创建/修改 PR。

## 第一性原理与 owner 裁决

`S3-RR-F01` 成立，且不能降级为后续 cleanup。被对外承诺的业务语义不是
`RunTransitionResult` 或 `WaitResolutionTransitionResult` 各自如何包装字段，而是同一对 durable
stable `RunRow` 与 exact `EventLogRow` 如何校验并投影为 Host-private
`TerminalPostCommitNotice`。此前 `run_transition.py::terminal_notice_from_transition` 与
`waiting.py::_terminal_notice_from_wait_transition` 都负责缺失校验、stable terminal ref、Session、Run identity
一致性校验和 notice 构造，仅上游 dataclass 不同，因此存在两个同语义 owner，直接违反根 `AGENTS.md` 的唯一 owner 与重复逻辑约束。

唯一正确 owner 继续位于 `dayu.host.durable.run_transition`。直接输入采用朴素 typed rows，不新增 Protocol：

```python
project_terminal_notice_from_exact_run_event(
    run: RunRow | None,
    exact_run_event: EventLogRow | None,
    *,
    wake_queue_promotion: bool,
) -> TerminalPostCommitNotice
```

该名称明确表达“投影动作”与“exact Run/Event 输入”。五个 consumer 只负责传入 same-transaction 或 terminal confirmation
返回的 rows，以及本 producer 已冻结的 promotion flag；owner 不读取 store、不做 latest/max/readback、不注册 callback。

## 修复内容

### Durable owner

- `dayu/host/durable/run_transition.py`
  - 删除 `terminal_notice_from_transition(...)`。
  - 新增唯一 `project_terminal_notice_from_exact_run_event(...)`，直接接收 `RunRow | None`、
    `EventLogRow | None` 与严格 bool flag。
  - owner fail-closed 覆盖 Run row 或 exact event row 缺失，以及 terminal event id/sequence、Session id、Run id 任一不一致。
  - notice 仍只携带 exact Session、terminal event sequence 与原始 promotion flag；无 schema/public contract 变化。

### 五个直接 consumer

- `dayu/host/admission.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/recovery.py`
- `dayu/host/dispatch.py`
- `dayu/host/waiting.py`

五个模块均直接 import/call durable owner helper，并显式传入 transition/confirmation 的 `.run` 与 `.run_event`；没有本地
wrapper、alias、re-export 或 `TerminalPostCommitNotice(...)` 构造。

`waiting.py::_terminal_notice_from_wait_transition` 已删除。
`_terminal_notice_from_terminal_wait_snapshot` 保留 terminal wait 状态确认与 replay 职责，但 confirmation 完成后只把
`confirmation.run`、`confirmation.run_event` 传给 shared owner helper，不再构造临时 waiting transition，也不再复制投影校验。

所有既有 producer flags 保持：waiting 首次 failed/lost/expiry 为 `True`，terminal confirmation/replay 为 `False`；其它
admission、engine ingest、recovery、dispatch 调用点的 bool 值未改变。producer manifest、最外层 post-commit notify 时点、
waiting replay/failed/lost/expiry 状态机以及 Host-private/no Engine boundary 均未改变。

## 测试变更

- `tests/host/test_run_attempt_transitions.py`
  - owner 行为改为直接输入 exact rows。
  - 覆盖 Run row 缺失、exact event row 缺失。
  - 覆盖 terminal event id、terminal event sequence、Session id、Run id 四类不一致并 fail-closed。
  - 保持真实 terminal transaction 产生 exact event、commit return 后投影 notice 的路径。
- `tests/host/test_terminal_post_commit.py`
  - static owner consumer 闭集由四个扩为 admission、engine_ingest、recovery、dispatch、waiting 五个。
  - 冻结 owner helper 名称、两个直接 typed row 参数与 keyword-only bool 参数。
  - 每个 consumer 必须 direct import（无 import alias）并直接调用 owner。
  - 禁止旧 transition/wait helper、本地 helper alias 与本地 `TerminalPostCommitNotice(...)` 构造。

## 验证证据

所有 Python 命令均在 `source .venv/bin/activate` 后执行。

### Targeted、waiting 与 S3 focused

- owner/static + owner behavior + `test_wait_callback.py` + `test_wait_expiry_closeout.py` +
  `test_wait_cancel_late_result.py`：`23 passed in 1.19s`。
- 最终 owner/static 与 owner behavior 节点：`2 passed in 0.46s`。
- producer manifest、direct promotion allowlist、single owner、optional/default source 节点：`4 passed in 0.60s`。
- static AST annotation 完成严格类型收窄后的最终 single-owner 节点：`1 passed in 0.44s`。
- 完整 S3 focused gate：`407 passed in 6.92s`。
- 完整 Host suite天然再次覆盖 resolve wait replay/failed/lost/expiry 与全部 waiting tests。

### 完整 Host suite与单文件 coverage

命令：

```bash
pytest tests/host -q --cov=dayu.host \
  --cov-report=json:workspace/tmp/wu-host-session-event-delivery-01-s3-rereview-fix-host-coverage.json \
  --cov-report=term
```

结果：`2067 passed, 2 skipped, 6 deselected in 70.14s`，总覆盖率 `91%`。

| Slice 3 modified production file | Covered / statements | Coverage |
|---|---:|---:|
| `dayu/host/admission.py` | 967 / 1063 | 91% |
| `dayu/host/command.py` | 367 / 416 | 88% |
| `dayu/host/dispatch.py` | 1173 / 1290 | 91% |
| `dayu/host/durable/run_transition.py` | 1300 / 1395 | 93% |
| `dayu/host/engine_ingest.py` | 1285 / 1418 | 91% |
| `dayu/host/open_host.py` | 638 / 726 | 88% |
| `dayu/host/recovery.py` | 246 / 268 | 92% |
| `dayu/host/terminal_post_commit.py` | 20 / 21 | 95% |
| `dayu/host/waiting.py` | 540 / 609 | 89% |

全部 modified production 单文件均达到 `>=80%`。

### Type、diff、source、boundary 与 scope scans

- 完整 `pyright`：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过；新增未跟踪 test/artifact另执行 no-index whitespace check。
- production 旧 `terminal_notice_from_transition` 与 `_terminal_notice_from_wait_transition`：零命中。
- `TerminalPostCommitNotice(...)` production 构造：仅 durable owner helper 一处。
- 五个 consumer：全部 direct import/call新 owner helper；static AST gate通过。
- terminal producer manifest仍为冻结的 21 个 producer闭集；ordinary direct promotion allowlist仍精确为 5 处。
- Engine boundary：`dayu/engine` 对 `TerminalPostCommit`、`terminal_post_commit`、`session_event_delivery` 零命中。
- runtime reverse dependency：锚定真实 import语句扫描零命中。
- scope：本 fix只修改 durable owner、五个 consumer、两个 owner/static tests，并新增本 artifact。既有 Controller-owned
  control doc和 reviewer artifacts保持原 dirty/untracked状态且未写入；README未修改。

## README 决策

用户明确禁止本 gate 修改 README；本修复也未改变 public API、分层、用户工作流或已冻结 S3 terminal delivery contract，
因此只记录审计，不修改 README。

## Finding 状态与 residual risks

| Finding | 状态 | 证据 |
|---|---|---|
| `S3-RR-F01` | 已修复 | 唯一 exact Run/Event durable owner；五 consumer direct call；waiting 本地投影删除；owner/static、waiting、focused、full Host、coverage、pyright与边界扫描通过 |

- 当前 finding 无未分类 residual correctness 或 semantic-owner risk。
- Service exact-five、CLI callback execution domain、旧 Service relay 删除与 README 最终同步仍属于已批准 S4，本 gate未实施或冒充完成。
- 下一入口：由原 AgentMiMo 与 AgentDS 对 `S3-RR-F01` 执行 narrow code re-review。

`READY_FOR_NARROW_CODE_REREVIEW`
