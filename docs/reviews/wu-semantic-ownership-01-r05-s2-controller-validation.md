# WU-SEMANTIC-OWNERSHIP-01 R05-S2 Controller Validation

## 1. Gate 与 verdict

- umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU、feature 或 issue。
- slice：accepted-plan R05-S2 Engine no-diff regression / public smoke / README acceptance。
- transition HEAD：`e077c708`。
- AgentCodex artifact：`docs/reviews/wu-semantic-ownership-01-r05-s2-implementation-codex.md`。
- Controller verdict：`PASS / READY_FOR_DUAL_COMPLETE_CODE_REVIEW`。

S2 没有创建第二个 production transaction。当前 diff 只包含 Engine regression test、public awaiting smoke、Host README、tests README 与 implementation artifact；`dayu/engine/agent.py`、Engine README、S1 七路径、control、scheduler owners与其它 README均 no diff。

## 2. Controller 独立功能验证

### 2.1 Fresh public smoke

Controller 使用新的 workspace 独立运行：

```text
python utils/smoke_host_public_awaiting_entrypoint.py \
  --workspace-root workspace/tmp/r05-controller-public-awaiting
```

结果 exit 0。关键直接证据：

```text
typed provider modes: poll/manual/callback
packaged policy: 12 fields exact snapshot
test effective: handshake=0.05, observation=0.15, operation=0.30,
                backoff=0.60, quantum=0.005, margin=0.03
handshake elapsed=0.001000 < 0.05
first observation: Run=WAITING, Wait=WAITING, claim released,
                   ADAPTER_ERROR/wait_observation_timeout, terminal outbox=0
operation measured=0.300124
all four timing inequalities=true
late Ready dropped_count=1, Run still WAITING, terminal outbox=0
second observation after real due -> public RunSnapshot SUCCEEDED
terminal event/outbox exact match
worker accept count=2, poll observation count=2
all 11 named phases complete
```

该 smoke 保持 packaged `ConfigLoader -> provider discovery -> Service composition -> open_host -> submit/wait -> durable poller -> public terminal/outbox` 主链，无网络、无 credential、无 private resolve 或 durable mutation。

### 2.2 Tests

Controller 独立结果：

| matrix | result |
|---|---|
| Engine full `test_agent_phase3_tool_call.py` | `48 passed` |
| R04 config/Fins/Service exact owner nodes | `35 passed, 3 warnings` |
| ten-file R05 aggregate | `360 passed, 3 warnings` |

warnings 均来自 `.venv` edgar deprecation，不在 R05 source/propagation path。

Agent 另已通过计划 §7.2 exact Engine nodes `7 passed`，并在只新增 test、`agent.py` no diff 时让新 accepted-awaiting regression 首次即绿。

## 3. Coverage、type、lint 与 diff

- full pyright：Controller `0 errors, 0 warnings, 0 informations`。
- changed Python Ruff：Controller `All checks passed!`。
- full Ruff machine-readable registry：fixed base `167`、accepted S1 `165`、current S2 `165`；Controller `cmp` 确认 current 与 accepted S1 JSON完全一致。
- Host changed-owner coverage：Controller 对当前 `.coverage` 逐文件复核 `durable/state.py=83%`、`wait_adapter.py=86%`，两个 `--fail-under=80` PASS。Agent 的完整 measurement 为 `1831 passed, 1 skipped, 5 deselected`，只保留 accepted 两个 ignore。
- Engine coverage JSON branch-aware combined：`77.626459%`，显示 `78%`；statement coverage 为 `597/742=80.458221%`。accepted plan 中“agent.py=80%”对应 statement coverage，而 branch-aware exact command如实显示78%。`agent.py` 在 fixed base / S1 / S2 均 no diff，因此不是新增 changed-production coverage debt；不得把78伪装成80，review必须继续核对此解释。
- `git diff --check`：PASS。

相对 transition HEAD `e077c708` 的 tracked diff精确为：

1. `dayu/host/README.md`
2. `tests/README.md`
3. `tests/engine/test_agent_phase3_tool_call.py`
4. `utils/smoke_host_public_awaiting_entrypoint.py`

另有唯一 untracked implementation artifact。无 staged path。

## 4. Source、owner 与安全复核

- Engine handshake budget只在 executor 返回前读取/使用；accepted `ToolAwaitingOutcome` 后没有 timer ownership。`agent.py` no diff。
- S1 timeout-only terminal primitive/wrapper 零定义、零调用；Host state/wait adapter相对 S1 accepted commit no diff。
- token/generation publication fence、claim CAS、release/backoff、typed LOST、explicit lifecycle terminal marker、安全/containment/capacity/close-drain全部保持原 owner。
- smoke 的唯一 fixed-duration sleep 是被测独立 external operation；state waits按0.005秒 quantum重新读取 owner state，不以 sleep 推断业务事实。
- smoke 没有 `hasattr/getattr`、monkeypatch、`.resolve_wait(...)`、无参 `WaitPollerRuntimePolicy()` 或 `poll_next_observe_at` mutation。
- production added-lines 对 authorization、permission、callback transport、process isolation、process-backed/subprocess、Issue 175 零命中。
- scheduler deterministic probe仍 `1 passed`（以预期 `HostApiError` 为通过条件）；scheduler residual未修、未隐藏、未 waive、未归 Issue 175。

## 5. README decision

- Host README只补当前 Waiting 稳定 contract：poll timeout/abandon timeout非终态、late publication无 authority、typed outcome拥有终态。
- tests README纠正旧 stuck-poll/abandon-marker测试描述，并登记 Engine regression与 public smoke覆盖。
- Engine README已有 handshake timeout边界，`agent.py` no diff，保持 no diff。
- 根 README / `dayu/README.md` 无用户入口、工作流、分层或装配变化，保持 no diff。

## 6. Code review 必须重点挑战

Validation通过不等于 code acceptance。两路完整 code review必须特别挑战：

1. smoke 从1295行增至2195行（本 slice约 `+1094/-97`）是否仍是满足 plan十项契约的最小可维护实现，是否形成 God script/helper或可合并的重复逻辑；
2. `_WaitPollerDiagnosticsHost` 通过 private `_wait_poller` 只读 runner dropped count，以及 `_durable_options(...)` 打开独立 read transaction，是否是 plan要求 diagnostics的必要 owner-level证据，还是不当私有耦合/重复 options projection；
3. smoke是否真的保持 public 主链，local worker/adapter只替代外部依赖，未 self-implement Host timeout/backoff/terminal语义；
4. timing关系、event顺序与单一 deadline是否可能在慢CI产生 false pass/false fail；
5. Engine fake operation是否真实证明 handshake timer不拥有 accepted operation，而不是只证明 fake task没有显式取消；
6. test/smoke docstring、类型、cleanup、thread/task leak、Host close以及失败路径诊断是否完整；
7. README 文案是否只描述 current production contract，没有实施过程、未来 policy或内部治理术语漂移；
8. Engine 78% branch-aware / 80.458% statement解释是否忠实符合 plan与项目 coverage要求；
9. retained safety、scheduler residual与 deferred scope是否被 smoke/test间接弱化或掩盖。

## 7. 下一 gate

下一 gate：AgentMiMo / AgentDS 并发双路完整 R05-S2 code review。Reviewer只能写各自 artifact；任何 accepted finding必须由 AgentCodex全部修复并经双路完整 re-review后才能 accepted local commit。

R05 aggregate、scheduler fix、Issue 175、callback、统一 authorization、R06-R12、push与PR仍未授权。
