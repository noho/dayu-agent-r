# WU-SEMANTIC-OWNERSHIP-01 R05 Aggregate Validation

## 1. Gate 与 verdict

- umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU。
- internal remediation sub-WU：R05 wait observation/state-machine ownership。
- accepted plan commit：`201eb7f5287fc8e73d05b442e84369e19928236a`。
- accepted S1 commit：`c5af5613b21673864fff072a132ac56a46cc9836`。
- accepted S2 commit：`ff7b0b1825491ee3690a45d56a059c5da00af7aa`。
- Controller verdict：`PASS / READY_FOR_DUAL_AGGREGATE_DEEPREVIEW`。

R05 两个 implementation slices 已分别通过 plan、dual review、fix、full re-review 与 accepted local commit。本 gate 重新验证它们的组合行为、accepted review evolution、R04 config handoff、Engine handshake boundary、retained safety 和 deferred scope；R05 尚未完成，必须经过 AgentMiMo / AgentDS aggregate deepreview、所有 accepted fixes 与 full re-review。

## 2. Aggregate product/test scope

相对 R05 entry base `5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1`，完整 product/test/design/README transaction 为 16 paths：

1. `dayu/host/durable/state.py`
2. `dayu/host/wait_adapter.py`
3. `docs/host/design.md`
4. `tests/host/test_phase7_waiting_integration.py`
5. `tests/host/test_wait_adapter_polling.py`
6. `tests/host/test_wait_observation_runner.py`
7. `tests/host/test_wait_record_state.py`
8. `tests/engine/test_agent_phase3_tool_call.py`
9. `utils/smoke_host_public_awaiting_entrypoint.py`
10. `dayu/host/durable/options.py`
11. `dayu/host/command.py`
12. `dayu/host/open_host.py`
13. `tests/host/test_durable_options.py`
14. `tests/host/test_public_host_admin.py`
15. `dayu/host/README.md`
16. `tests/README.md`

Aggregate product transaction digest：

`41bd8c057cb5ff3d389f909a367a19037a65ae59ffda377cd317b9d1db4eda9a`

`dayu/engine/agent.py`、`dayu/engine/README.md`、`dayu/host/_wait_observation.py`、`dayu/host/waiting.py`、`dayu/host/durable/schema.py`、`dayu/host/dispatch.py`、`dayu/host/engine_ingest.py` 相对 R05 base 均 no diff。

## 3. Aggregate semantic verification

### 3.1 Timeout 与 durable state

- observation timeout 只拥有 transient `ADAPTER_ERROR/wait_observation_timeout` diagnostic、claim release 与既有 backoff；poll Wait/Run 保持 `WAITING`。
- cancelled abandon timeout 保持 `CANCELLED`、释放 claim/backoff，不写 `poll_abandoned_at`。
- `mark_wait_record_poll_abandon_timeout` 与 `_MarkWaitRecordAbandonTimeoutOperation` 在 production/tests 零定义、零调用；schema 无 diff。
- explicit provider lifecycle terminal marker 仍由 Fins/Host typed outcome route 写 `poll_abandoned_at`；authoritative `WaitPollLost` / `ResolveWaitLostOutcome` 保持。

### 3.2 Publication authority 与 public smoke

- `_wait_observation.py` token/generation/lock 仍是唯一 late-result publication authority，no diff。
- S1 owner tests 直接断言 timeout invalidation 后 late result 被 runner 丢弃，不污染下一轮。
- S2 public smoke 不把 runner diagnostics 提升为 Host public contract；它在首轮 late Ready 返回、第二轮 real claim active 且 adapter 尚未返回的 boundary，通过 public Run/outbox + durable Wait facts证明首轮无发布权。
- Controller fresh smoke PASS：handshake `0.001269s < 0.05s`、operation `0.301178s > 0.15s`、首轮 timeout/release/backoff/diagnostic、blocked second claim、最终 `SUCCEEDED` 与 terminal event/outbox exact match 全部成立。

### 3.3 Engine 与 config ownership

- Engine production no diff；新增 regression 在现有 production 上直接证明 executor handshake 返回后，accepted awaiting external operation 可越过 handshake timeout 且不被 Engine timer 取消。
- R04 provider poll/manual/callback typed modes 仍由 `tool_discovery.json` provider config owner；完整 12-field poller runtime policy 仍由 `host_runtime.json` owner；scene/prompt/execution profile 不拥有 poller policy。
- Service 不再 scene/name heuristic 构造默认 policy；旧 helper 与无参 `WaitPollerRuntimePolicy()` 零命中。

### 3.4 Durable construction owner

- R05-S2 review finding 使原 S2 no-production-diff slice合法扩展：`HostDurableStoreOptionsSource` 与 `project_host_durable_store_options(...)` 收敛 command/open-host/smoke 重复 nested policy construction。
- 该扩展已走完整 dual review/fix/re-review，不是未审 allowlist 漂移；durable 下层不 import上层 opener type，所有 construction consumers 共用一个 typed owner。

## 4. Controller aggregate validation

所有 Python 命令均在 `.venv` 激活后运行。

| Gate | Result |
|---|---|
| R05 ten-file functional aggregate | `360 passed, 3` 个第三方 edgar deprecation warnings |
| fresh public awaiting smoke | PASS，11 phases 完成 |
| durable projection owner + public admin focused | `11 passed` |
| R05 S1 changed-owner coverage session | `1839 passed, 2 skipped, 5 deselected`；`state.py 83%`、`wait_adapter.py 86%`；两个逐文件 `--fail-under=80` PASS |
| R05 S2 changed-production coverage session | `1840 passed, 1 skipped, 5 deselected`；`command.py 88%`、`open_host.py 85%`、`durable/options.py 100%`；三个逐文件 `--fail-under=80` PASS |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| changed Python Ruff | `All checks passed!` |
| full Ruff registry | R05 fixed base `167` → accepted S1 `165` → aggregate `162` |
| `git diff --check` / working tree | PASS / clean before this artifact |
| scheduler deterministic residual probe | `1 passed`，仍以预期 `HostApiError` 为直接证据 |

Full Ruff baseline→aggregate 精确 diff 只删除五条 touched-file F401：

- S1：`durable/state.py` unused `TERMINAL_RUN_STATUS_VALUES`；`test_phase7_waiting_integration.py` unused `UTC`。
- S2：`command.py` unused `AttemptStatus` 与 `read_run_by_id`；`test_public_host_admin.py` unused `create_host_command_handle`。

其它 residual 六元组不变；无新 rule/location/message，无 `noqa`、ignore 或 config 变更。

## 5. Accepted evolution from original plan

两项 original plan text 已被后续直接证据和完整 review 裁决 supersede，aggregate review 必须按最终 accepted chain 审查，不能倒逼恢复较弱设计：

1. 原 smoke handoff 写 runner `dropped_count`；S2 initial review确认这要求穿透 `_HostHandle._wait_poller`。Controller accepted finding 后改成 blocked-second-observation 的 public/durable owner facts，内部 counter 仅留 S1 owner test。
2. 原 Ruff residual 预期 `165` 只包含 S1 两条删除；S2 accepted review fix实际触及 command/admin test 并删除三条同文件旧 F401，aggregate registry 因此为 `162`，精确等于 fixed base `167 - 5`。

S2 original “Engine production no diff”仍成立；durable construction helper change 是 code-review accepted finding 的窄 Host owner fix，不修改 Engine wait semantics。

## 6. Source、propagation、security 与 deferred audit

- timeout terminal-only primitive 删除 guard PASS；typed LOST/explicit lifecycle terminal保留。
- token/fence、claim/backoff、config owner、private diagnostics、duplicate durable helper、Engine no-diff scans PASS。
- R05 product added lines 对 unified authorization/permission framework、callback transport、process isolation、Issue 175 零新增语义。
- cancellation、claim CAS、capacity、close-drain、filesystem/durable storage safety 无删除或放宽。
- scheduler close / terminal promotion coordination仍可确定性复现，未修、未隐藏、未 waive、未归 Issue 175。
- cancelled abandon 长期 retry 的终止证据仍归 future Host durable evidence policy；不得从 timeout 猜 LOST。

## 7. README decision

- `docs/host/design.md` 与 `dayu/host/README.md` 准确记录当前 wait contract；不写未来 policy 或实现过程。
- `tests/README.md` 已同步 owner tests 与 aggregate public smoke 边界。
- Engine README 既有 handshake timeout 说明已足够，no diff。
- 根 README、`dayu/README.md` 无用户工作流/分层变化，no diff。

## 8. Residual ledger 与下一 gate

| Residual | Owner / destination | Aggregate status |
|---|---|---|
| scheduler close / terminal promotion coordination | independent Host scheduler/lifecycle owner；需显式后续裁决 | retained，非 R05 fix |
| cancelled abandon 持续 timeout 的 durable terminal evidence | future Host durable evidence policy | retained，非 timeout 猜测 |
| Issue 175 process isolation | existing Issue 175 | deferred |
| callback / unified authorization / R06+ | later remediation/issue owner | deferred |

没有 aggregate validation blocker 或未分类 residual。

下一 gate：AgentMiMo / AgentDS 并发 R05 aggregate deepreview。必须覆盖全部 16-path combination、完整 plan/review evolution、S1/S2 accepted finding ledger、semantic owner drift、overcoupling、retained safety 和 deferred scope。任何 accepted finding 必须交 AgentCodex 修复并双路 full aggregate re-review；不能直接把 R05 标记完成。
