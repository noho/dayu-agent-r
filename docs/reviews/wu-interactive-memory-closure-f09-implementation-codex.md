# Interactive Conversation Memory closure F09：implementation artifact

## Gate identity

- Work unit：Interactive Conversation Memory closure F08–F10。
- Gate：implementation slice F09。
- Accepted plan：`docs/reviews/wu-interactive-memory-closure-f08-f10-plan-codex.md`。
- Implementation base / accepted F08 checkpoint：`47b6a2af`。
- 分支：`codex/interactive-oracle`。
- Artifact path：`docs/reviews/wu-interactive-memory-closure-f09-implementation-codex.md`。
- Completion status：`implementation-pass`；下一 gate 为 F09 code review。
- Git 边界：本 gate 未 commit、未 push，也未执行远端操作。

## 动机、直接证据与 owner 判定

F09 的问题真实存在，严重性判断成立。实施前代码在
`DurableCompactorProposalManifestRecorder.record_compactor_proposal_manifest`
同一 write transaction 中已经写出 manifest descriptor，hot payload 也携带该
manifest ref/digest，但 canonical `EventLogAppendRequest.payload_ref` 与
`payload_digest` 被显式写为 `None`。Tool Trace projector 因而机械投影 null，public
formal resolver 的严格 row/hot equality check 正确地 fail closed；根因不是 resolver
过严，也不是 private Tool Trace storage 缺少 compactor 特例。

唯一语义 owner 是 compactor proposal manifest recorder 的 canonical manifest / EventLog
producer boundary。修复只在该 owner 中完成：EventLog row、hot payload、manifest
descriptor 与独立 compactor input projection descriptor 都从同一 transaction 已写出的
descriptor 派生。没有修改 durable/tool_trace resolver、projector、fail-closed identity
条件、private SQLite schema/query 或其它下游消费者。

首轮 public formal resolver owner test 还给出第二条直接证据：补齐 row descriptor 后，
resolver 已通过 row/hot identity 校验，但 canonical compactor manifest 缺少 formal
resolver 已有 contract 所需的 manifest-level projection descriptor，因而报
`runner-call manifest has no projection artifact ref`。Accepted plan 明确要求 formal
resolver 可恢复独立 compactor input projection，且禁止修改 resolver，因此同一 producer
现在把已持久化 projection descriptor 的 ref/digest/size 写入 manifest 与 hot atoms；不
二次计算 projection，不把 manifest descriptor 与 projection descriptor 混用。

## Scope 与改动

本 slice 只修改以下 approved paths：

- `dayu/host/compaction_operation.py`
- `tests/host/test_tool_trace_queries.py`
- `tests/host/test_dispatch_scheduler.py`
- 本 implementation artifact

生产改动：

1. canonical EventLog row 的 `payload_ref` 直接使用
   `manifest_descriptor.payload_ref`，`payload_digest` 使用同一 canonical manifest 的
   `manifest_digest`。
2. canonical manifest 增加已写入 compactor input projection descriptor 的
   ref/digest/size；hot payload 使用完全相同的 projection descriptor atoms，并继续携带
   同源 manifest ref/digest 与完整既有 hot body。
3. manifest body 只计算一次；manifest digest 只从该 body 计算一次。projection 与
   manifest descriptor 仍是两个独立 descriptor。

测试改动：

1. dispatcher integration helper 走真实 scheduler → durable recorder → EventLog → Tool
   Trace catch-up → public `read_runner_call_reconstruction_signals_by_run` → public
   `resolve_runner_call_projection_from_signal` 链路。
2. helper 对每个 compactor call 逐项断言 EventLog row、hot manifest ref/digest、Tool
   Trace signal、resolved manifest、独立 projection payload、operation id、attempt
   number、compactor Engine run id、effective provider/model 与 successful response
   identity 同源。
3. 覆盖单 attempt successful compact、invalid → repair → successful，以及四个 invalid
   attempts 耗尽后进入既有 dispatch fallback；最后一种路径每次 runner call 都有成功
   response identity，避免用 provider exception 代替 invalid/repair contract。
4. 原先依赖 `sqlite_payload_object` 的 compactor manifest 断言已改成 public formal
   resolver；private SQLite 不再是通过条件。原 post-compact ordinary call sizing 断言也
   通过同一个 public formal resolver 保留。
5. 新增 EventLog row descriptor 与 hot manifest identity 人为不一致的反例，继续断言
   `HostDurableError: tool trace row and runner-call hot identity mismatch`。

## README decision

实施前已读取 `dayu/host/README.md` 的 `Agent更新约束【必须遵守】` 与
`tests/README.md` 开篇写作边界，判定均不更新：

- Host README 只记录稳定开发契约、架构边界和当前关键机制。F09 修复既有 canonical
  EventLog → Tool Trace formal reconstruction contract 的 producer identity，不新增公共
  API、状态机、分层关系或稳定职责。
- tests README 只记录测试分层、运行方式与维护约定。F09 只扩展既有 Host owner / integration
  coverage，不新增测试层级、命令类别或维护规则。
- 精确 slice allowlist 也不授权修改 README；因此不以机械同步扩大 scope。

## Validation

所有 Python 命令均在 `source .venv/bin/activate` 后执行。

- 四条关键路径初检：single success、invalid→repair→success、invalid exhausted→fallback、
  row/hot mismatch，`4 passed`。
- F09 focused suite：
  `pytest tests/host/test_tool_trace_queries.py tests/host/test_dispatch_scheduler.py -q`，
  最终 `149 passed`。
- 相关 owner suites：
  `pytest tests/host/test_compaction_operation.py tests/host/test_proactive_compaction_operation.py tests/host/test_tool_trace_projection.py -q`，
  `81 passed`。
- focused + owner coverage run：上述五个 test files 合计 `230 passed`；
  `dayu/host/compaction_operation.py` 为 `634 statements / 108 missed / 83%`，达到单文件
  `>=80%` 目标。
- 受影响范围 pyright：三个修改 Python files，
  `0 errors, 0 warnings, 0 informations`。
- 全量 `python -m pyright`：`0 errors, 0 warnings, 0 informations`。
- Ruff lint：三个修改 Python files，`All checks passed`。
- Ruff format：production 与 dispatcher test 整文件 `--check` 均通过；Tool Trace 新增测试
  block 经 range format 产生，随后撤回 formatter 对既有未触及 baseline 的机械重排，未把
  unrelated formatting 纳入 slice。
- compileall：三个修改 Python files 通过。
- `git diff --check` 通过。
- implementation base `47b6a2af` 到本 gate 的 path diff 在加入本 artifact 后精确等于四个
  approved paths。
- 未修改 `dayu/host/durable/tool_trace.py` 或任何 resolver/projector/private SQLite owner。
- 按用户约束未运行五条正式 CLI scenarios。

## Frozen baseline verification

implementation 前与最终验证时的三份 baseline SHA-256 均匹配 accepted-plan checkpoint：

- `docs/cli_ci_oracles.json`：
  `da04923193a04c0e33eca9c60e0d8eb919b74963b2c2f4170954be2f07261201`
- `docs/cli_ci_scenarios.json`：
  `7c991d14ebc79f9f8e8c66d9eb94c10156c5a36eecd3bb11df24ed18cbca2093`
- `docs/reviews/wu-interactive-memory-closure-f08-f10.md`：
  `95a09543fc7f1a2a09f99dbe2c2c014e71ac22f2c386dc5364f6a1a2d14b1b08`

只读 frozen evidence 也未改变：

- `workspace/tmp/interactive-memory-observed-behavior.md`：
  `ad64315116c3940d9b0e7354c9e2a38aeff75fa179af723a82e696ff55658263`
- `workspace/tmp/interactive-memory-report-freeze.json`：
  `7ba64926a22406f086a417ee269313a3b07dbc05b480463ff535007f72198f5b`

## Residual risks 与 uncovered areas

- 真实 provider/model/response identity 的最终跨进程 CLI evidence 仍由后续正式
  `interactive.g06.tool-trace-formal` readiness stage 拥有；分类为
  `covered by later approved evidence stage`。本 slice 已用 public formal resolver 的可重复
  integration contract 覆盖同一 identity 链，但按计划不运行正式场景。
- 历史已写入 null row descriptor 的 EventLog 不做兼容读取或 migration；分类为 accepted
  non-goal / fresh current contract。没有 resolver fallback、loose parsing 或 compactor
  private-table 特例。
- 五条正式 CLI scenarios 全部未覆盖，统一分类为
  `covered by later approved evidence stage`。

没有 blocking open question，也没有未分类 residual risk。
