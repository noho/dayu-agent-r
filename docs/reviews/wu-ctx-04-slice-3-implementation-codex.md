# WU-CTX-04 Slice 3 implementation report（AgentCodex）

status: complete

work unit: WU-CTX-04

slices completed: 3/3

- Slice 1：accepted baseline commit `eda1d70e`；本轮未修改。
- Slice 2：accepted baseline commit `4ca0810b`；本轮以精确 HEAD
  `4ca0810b27eded188e4f9aae54756a871eb371ed` 为起点。
- Slice 3：按 accepted plan 与 Controller 的
  `resume-with-narrow-test-only-amendment` 完成 implementation、README 与 8.4-8.7 验证。

## resume history（保留）

### 初始 blocker

本 artifact 初始状态为 `blocked`，当时 Slice 3 尚未开始 production 实现。直接证据是原 tests
allowlist 遗漏了 required strict contract 的现有消费者：

- `tests/host/test_dispatch_scheduler.py` 直接调用无 `session_id` 的
  `ActiveWorkerRegistry.register(...)`、直接构造无 `session_id` 的
  `ActiveCancelMessage(...)`，并覆盖 / 调用待删除的 workspace-wide
  `tick_active_cancel_watchdog(...)` 与无 target `wake_active_cancel_watchdog()`。
- `tests/host/test_admission_multiprocess.py` 的 admission fake 额外保留无 target watchdog wake
  接口、计数和零调用断言，仍表达待删除的全局 wake shape。
- production 若为了原 allowlist 保留默认 / optional `session_id`、从 `run_id` 猜 Session、旧入口
  overload、wrapper 或 workspace-wide compatibility path，会直接违反 exact identity、stale grep 与
  “无兼容逻辑”约束。

初始 blocker 因而判断：问题真实存在，正确 owner 与目标状态机没有歧义，冲突只在 tests scope；
不能用 production fallback 规避。原 blocking questions 是要求 scope owner 至少把
`tests/host/test_dispatch_scheduler.py` 纳入机械迁移；否则 strict exact changes 与 full
pytest / pyright 无法同时满足。初始报告同时明确未修改 production、tests、README、design、control、
plan 或 review artifacts，且当时未运行 completion validation。

### Controller amendment

Controller 在
`docs/reviews/wu-ctx-04-slice-3-scope-amendment-controller.md` 裁决：

- decision：`resume-with-narrow-test-only-amendment`。
- blocking open questions：None。
- 原 allowed tests 仅追加 `tests/host/test_dispatch_scheduler.py` 与
  `tests/host/test_admission_multiprocess.py`。
- 追加文件只允许 required `session_id` / exact identity 构造迁移、obsolete global tick/wake
  迁移或死接口删除、以及必然失效的 qualified-name/signature 断言同步；不得漂移其它测试行为。
- 禁止 production default、optional `session_id`、overload、alias、wrapper、loose parsing、全局
  compatibility path或第二套 cancel semantic owner。

本次恢复严格按该 amendment 执行，没有继续扩大 allowlist。全量回归一度发现
`test_terminal_post_commit.py` 的 terminal producer 闭集失败；实现没有修改该 allowlist 外测试，
而是把 exact owner target 的写事务重验接回原 `_tick_active_cancel_watchdog` 唯一 terminal producer，
从 production root cause 消除了第二调用点。该测试随后和全量回归一起通过。

## changed files

### Production

- `dayu/host/durable/state.py`
- `dayu/host/durable/run_transition.py`
- `dayu/host/dispatch.py`
- `dayu/host/command.py`
- `dayu/host/open_host.py`

### Tests

- `tests/host/test_active_cancel_dispatch.py`
- `tests/host/test_public_session_attachment.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_state_schema.py`
- `tests/host/test_run_attempt_transitions.py`
- `tests/host/test_dispatch_scheduler.py`（Controller amendment）
- `tests/host/test_admission_multiprocess.py`（Controller amendment）

### README / implementation artifact

- `README.md`
- `dayu/README.md`
- `dayu/host/README.md`
- `dayu/config/README.md`
- `dayu/service/README.md`
- `tests/README.md`
- `docs/reviews/wu-ctx-04-slice-3-implementation-codex.md`（本文件）

`docs/host/issues-implementation-control.md` 的既存 Controller 修改未被本 implementation 触碰；
scope amendment artifact 也未修改。未修改 design、control、accepted plan 或 review artifacts，未
commit / push。

## public contract / schema / state machine

- `ActiveCancelMessage.session_id` 与 `ActiveWorkerRegistry.register(session_id=...)` 均为 required
  参数；没有 default、optional shape、overload、wrapper 或兼容入口。registry 保存并稳定排序返回
  exact `(session_id, run_id, attempt_id, execution_id)` snapshot，cancel 必须四元 identity 全等。
- `dayu.host.durable.state` 成为 exact Run / current Attempt / execution / dispatch owner SQL join 的
  owner，定义 `AttemptExecutionIdentity` 与 `OwnedAttemptCancelCandidate`。查询只接受有界、唯一
  identity tuple；empty tuple 直接返回；不按 Run / Attempt terminal status 过滤，stale current
  Attempt、execution、dispatch owner、缺 record 或缺 cancel link 只过滤不误配。
- `dayu.host.durable.run_transition` 继续独占 `CANCEL_REQUESTED` canonical fact 语义，投影
  `OwnedAttemptCancelTarget(identity, cancel_request_event_id)`。linked event 必须精确匹配 event id、
  canonical class/type、Session/Run、Run-scoped identity、inline payload、完整 body digest 与当前
  producer exact six-field payload；缺行、错链、非法 enum/type/digest 一律抛 durable invariant error。
- caller fast path 按 message 中 required Session id 传播，并只把目标 Session 放入 watchdog queue；
  删除 public workspace-wide tick、无 target wake 与 periodic global cancelling scan/query。
- execution-owner scheduler 每个 dispatch poll interval 快照本地 worker identities，只读取
  `owner_host_instance_id` 与四元 identity 精确匹配的 durable cancel target，transaction 外传播
  token / hook，再在写事务内重验 exact target并复用原 accepted-cancel watchdog transition。即使
  caller watchdog 已把 Run 置为 terminal，cancel link仍可读取并完成物理传播；owner reconcile不
  获得 attachment、新 Attempt、promotion 或 takeover 权限。
- 空 local registry 是严格空集合，直接返回全零 typed reconciliation summary，不开启无意义 durable
  read；这避免短 poll interval 下空事务占用调度窗口，并有 owner-level 测试锁定。
- durable schema、table、index、public cancel mode 与 terminal state machine均未改变；没有第二套
  cancel closeout owner。

## tests / direct evidence

- registry 测试断言 stable exact identity snapshot、wrong Session miss且 token/hook 不变、required
  Session cancel message 与 `cancel_all` 精确传播。
- strict durable query 覆盖 terminal status 后仍返回 exact target、wrong owner / stale execution / stale
  current Attempt过滤、duplicate identity拒绝，以及 missing linked row、wrong class/type/Session/Run、
  non-Run-scoped event、payload ref、body digest、payload exact-key shape等 fail-closed 矩阵。
- public 双 opener 回归使用真实 durable state：A 启动 delayed worker后 detach，B fresh RW 通过同一
  public cancel API接受取消，A execution-owner one-shot reconcile精确调用本地 token / hook并把 Run
  收口为 `CANCELLED`；B registry miss不影响 durable acceptance。
- amendment 文件只做机械迁移：dispatch scheduler fixtures / fakes / calls 改为 required Session target；
  admission multiprocess 删除不属于 admission contract 的 obsolete extra watchdog fake，业务断言不变。
- 第一次 full regression 暴露新增 direct transition producer；改为复用原唯一 producer后，未修改
  `tests/host/test_terminal_post_commit.py` 即通过。
- 第一次 coverage run暴露 10ms lane deadline 下 empty registry仍开 durable read 的时序竞争；生产
  空集快路径与对应测试落地后，未放宽 timeout，coverage测试面和最终 full regression均通过。

## validation

所有命令均在仓库根目录、`source .venv/bin/activate` 后执行。

- 8.4 exact focused command：`325 passed`，3 个第三方 deprecation warnings。
- Controller amendment 两文件：`110 passed`。
- 8.5 final full regression：`5590 passed, 11 skipped, 6 deselected`，3 个第三方
  `edgar` deprecation warnings；无失败。
- 8.5 full pyright：`0 errors, 0 warnings, 0 informations`。
- targeted ruff（全部 Slice 3 modified Python files）：`All checks passed!`。
- `git diff --check`：通过。
- 8.6 coverage test surface：`3539 passed, 9 skipped, 6 deselected`，无失败。
- 8.6 相对 baseline `974f9e1686f6e26f96830cd3478edc9d0d686c45` 的 21 个 modified
  production Python files逐文件 `--fail-under=80` 全部通过：
  - `dayu/cli/session_execution.py` 81%；`dayu/host/__init__.py` 100%；
    `dayu/host/api.py` 94%；`dayu/host/command.py` 88%；
    `dayu/host/compact_pipeline.py` 94%；`dayu/host/compaction_operation.py` 94%；
    `dayu/host/context_events.py` 90%；`dayu/host/context_policy.py` 94%；
    `dayu/host/dispatch.py` 90%；`dayu/host/durable/event_log.py` 91%；
    `dayu/host/durable/run_transition.py` 93%；`dayu/host/durable/state.py` 88%；
    `dayu/host/engine_ingest.py` 91%；`dayu/host/open_host.py` 89%；
    `dayu/host/proactive_compaction.py` 86%；`dayu/host/recovery.py` 92%；
    `dayu/host/session_attachment.py` 88%；`dayu/runtime/__init__.py` 100%；
    `dayu/runtime/config_loader.py` 96%；`dayu/runtime/native_mutex.py` 92%；
    `dayu/service/host_assembly.py` 95%。
- 8.7 三组 invariant grep均无输出并以预期状态 1 退出：
  - `StartupRecovery|read_non_terminal_runs\(|read_cancelling_runs\(` 在 `dayu tests` 零命中。
  - 删除的 proactive operation count字段 / 常量 / reason在 `dayu tests README.md` 零命中。
  - `dayu/runtime/native_mutex.py` 对 Engine / Host / Service / UI / Fins 的反向 import零命中。

## README / docs

- 根 `README.md`：只写用户可见行为；两个 CLI 进程选同一 Session 时后进入者为 typed read-only，
  需要先正常退出旧 owner并等待关闭，再 fresh `session resume`，原 RO会话不自动升级。
- `dayu/README.md`：明确 UI / CLI 持有 attachment、Service watcher只负责 subscription，Host拥有
  access truth；补充 layer-neutral strict-native mutex边界与跨 opener exact cancel路径。
- `dayu/host/README.md`：更新 Host public attachment contract、mutation gate、target recovery、
  scheduler new-work eligibility、execution-owner cancel reconcile、唯一 watchdog terminal owner和
  proactive single-operation语义。
- `dayu/config/README.md`：明确 operator可配置的是 reactive operation上限与单 operation semantic
  proposal attempt budget；proactive启动没有独立次数配置。
- `dayu/service/README.md`：把 watcher表述统一为 event subscription；明确 Service不调用、缓存或从
  watcher / snapshot推断 attachment access truth。
- `tests/README.md`：记录 same/different Session、target recovery、native mutex、incomplete proactive
  operation与 cross-opener exact cancel的测试层级和 focused命令，并消除 watcher/attachment混称。
- `docs/host/design.md`、`docs/host/issues-implementation-control.md`、accepted plan、scope amendment与
  review artifacts：按 owner / 禁止项未修改。

## blocking questions

None。Controller amendment 已消除 tests scope blocker，implementation没有出现新的 ownership、schema、
state machine或权限裁决缺口。

## residual risks

- **环境残余风险（已有明确验证 owner）**：本机为 macOS，只实际执行 POSIX native mutex backend；
  Windows `msvcrt.locking` 路径仍由受支持 Windows Python 3.11 CI执行同一 native mutex测试。unsupported
  与未知 errno继续 fail closed。
- **已接受的运行时延迟边界**：无 IPC / proxy / notification 时，跨 opener cancel物理传播最多等待
  一个 `dispatch_poll_interval_seconds`；caller durable acceptance与 target watchdog不依赖该轮询。
- **已有外部执行边界**：本地 token / hook已精确传播不等于远端 provider或第三方 job物理
  exactly-once停止；迟到结果仍由 Host identity / terminal fence拒绝。
- **fresh-schema边界**：本 WU按 accepted plan不兼容旧 DB / workspace config；若将来要求升级，必须
  由独立 migration WU拥有，不能回填本 Slice的兼容 parser或wrapper。

无未分类风险，无需用户补充裁决。
