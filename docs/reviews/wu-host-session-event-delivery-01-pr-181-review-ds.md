# PR Review — WU-HOST-SESSION-EVENT-DELIVERY-01 PR #181

## 审查身份

- **Reviewer**：AgentDS（独立 PR review，未读取 AgentMiMo 任何 review artifact）
- **审查日期**：2026-07-22 03:52 UTC+8
- **Mode**：PR Review Mode — 独立 adversarial correctness/stability/maintainability/ownership review
- **Deepreview skill**：完整遵循 `$deepreview --pr 181`

## Scope

- **Repository**：noho/dayu-agent-r
- **PR**：#181
- **Title**：feat(host): own session event delivery with bounded mailboxes
- **Author**：noho (Leo Liu)
- **Head branch**：`phaseflow/wu-host-session-event-delivery-01`
- **Base branch**：`main`
- **Reviewed remote HEAD**：`6e20767daf7b65bcd9761202972aa15e6fd66397`
- **PR State**：OPEN, DRAFT
- **Mergeable**：MERGEABLE
- **URL**：https://github.com/noho/dayu-agent-r/pull/181
- **Changed files**：154（gh pr diff）；PR metadata `files` 字段因 GitHub API 100 文件上限截断
- **Additions/Deletions**：19,645 / 2,429
- **Included scope**：全部 production/config/README/test/utils/smoke 文件（83 个代码/test 文件 + 规划/review/裁决 artifact）
- **Excluded scope**：`docs/host/issues-implementation-control.md` 本地 Controller-owned uncommitted 改动（指令排除）
- **Base documents read**：AGENTS.md、docs/host/design.md（scan）、docs/engine/design.md、plan（docs/host/wu-host-session-event-delivery-01-plan.md）、goal confirmation、Controller aggregate adjudication
- **AgentMiMo artifacts**：未读取，保持独立

## Verification Results

### 独立验证矩阵

| 验证项 | PR Body 声明 | 独立验证结果 |
|---|---|---|
| affected suites | 3443 passed, 9 skipped, 6 deselected | **3443 passed, 9 skipped, 6 deselected** ✅ |
| stress tests | 6 passed | **6 passed** ✅ |
| pyright | 0 errors | **0 errors, 0 warnings** ✅ |
| `git diff --check` | passed | **无输出** ✅ |
| transient_delta.py cov | 92% | **92%** (target ≥80%) ✅ |
| open_host.py cov | 84% | **84%** (target ≥80%) ✅ |
| terminal_post_commit.py cov | 95% | **95%** (target ≥80%) ✅ |
| entrypoint_runtime.py cov | 86% | **86%** (target ≥80%) ✅ |

### 专项 Scan 结果

| Scan | 预期 | 结果 |
|---|---|---|
| 旧 delivery 语义残留 (`_TRANSIENT_WATCH_BUFFER_CAPACITY` 等) | 空 | **空** ✅ |
| `dayu.runtime` 反向依赖 | 空 | **空**（仅 docstring 提及规则）✅ |
| `dayu/engine` delivery contract 泄漏 | 空 | **空** ✅ |
| `wake_queue_promotion` 调用点 | 仅 coordinator/scheduler bridge/ordinary paths | **5 处**，全部是授权调用方 ✅ |
| `hasattr`/`getattr` 在新代码中 | 空 | **空** ✅ |
| `cast()` 在 entrypoint_runtime | 空 | **空** ✅ |
| 旧 Service relay symbols | 空 | **空**（`_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY`、`_WatcherFailure` 等全部删除）✅ |
| 全部 `watch_session_events(...)` caller | 显式 `await` | **全部显式 `await`** ✅ |
| 生成/临时 artifact | 空 | **空** ✅ |
| merge conflicts | 无 | **MERGEABLE** ✅ |

## Findings

### 未发现实质性问题

经过完整 adversarial correctness/stability/maintainability/ownership review，未发现 material finding。

以下逐项记录各审查维度的独立结论与直接代码证据：

---

#### 1. Public async attach 与 successful-return boundary — PASS

**证据链**：

- `dayu/host/api.py:1195-1233`：`watch_session_events` 是 `async def`，返回 `HostSessionEventIterator` Protocol。
- `dayu/host/open_host.py:1195-1234`：factory 内先 `reserve()`（零分配，仅计数检查），再 `await durable_actor.call(...)` 完成 cursor transaction，然后在同 owner-loop 临界段（无 `await`）内 `attach()` 创建 subscription/mailbox、构造 `_HostSessionEventIterator`、注册 fanout。任一失败按已分配逆序清理并幂等 `release()`。
- `dayu/host/api.py:3622-3651`：`HostSessionEventIterator` Protocol 精确声明 `__aiter__`、`__anext__`、`aclose`。
- 所有 40+ caller（production/test/utils）均使用 `await`。

**无 pending cursor future、done callback、lazy first-anext attach。** ✅

---

#### 2. Host sole delivery owner 与 item-only 512 — PASS

**证据链**：

- `dayu/host/api.py:1081-1115`：`HostSessionEventDeliveryPolicy` 仅两个 required 正整数字段，无默认值、无 byte/heap 字段。
- `dayu/config/host_runtime.json:22-23`：packaged `"transient_mailbox_max_items": 512, "max_subscriptions_per_session": 4`。
- `dayu/host/transient_delta.py:479-486`：`retained_items = len(self._mailbox) + (1 if self._in_flight is not None else 0)`，严格按 item 计数。
- `dayu/host/transient_delta.py:643-668`：`_offer()` 使用 `prospective_retained_items = self.retained_items + 1 > cap` 做 overflow 判定；overflow 后立即从 fanout 移除，不把 overflow event 入队。
- `dayu/service/entrypoint_runtime.py`：旧 relay symbols（`_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY`、`_WatcherFailure`、`_WatchAndWaitRuntime.queue/drain_task`、`_drain_host_events`）全部删除，无第二个 event buffer。

**无 byte/heap 字段、无 Service relay、无 batch drain。** ✅

---

#### 3. Typed errors、metrics 与确定性 overflow — PASS

**证据链**：

- `dayu/host/api.py:1378-1379`：`DELIVERY_INTERRUPTED` 和 `RESOURCE_EXHAUSTED` 加入 `HostApiErrorCode`。
- `dayu/host/api.py:1417-1443`：`HostSessionEventDeliveryReason.TRANSIENT_MAILBOX_OVERFLOW` 单一成员；`HostSessionEventDeliveryDetail` 只含 `reason`。
- `dayu/host/api.py:1446-1472`：`HostSessionEventAdmissionReason.SESSION_SUBSCRIPTION_LIMIT_REACHED` 单一成员；`HostSessionEventAdmissionDetail` 只含 `reason`。
- `dayu/host/api.py:1503-1507`：`HostApiErrorDetail` union 包含三者：`HostSessionEventDeliveryDetail | HostSessionEventAdmissionDetail | HostUnavailableDetail`。
- `dayu/host/transient_delta.py:43-91`：低基数 logging 只使用封闭 `_DeliveryLogEvent`/`_DeliveryLogOutcome`/`_DeliveryLogReason` enum，不含 identity、payload、item count 或 capacity dimension。
- `dayu/host/open_host.py:1289-1298`：overflow 路径先交付已接受 mailbox prefix，prefix 耗尽后下一次 `anext()` 才抛 typed `HostApiError(code=DELIVERY_INTERRUPTED)`，不丢失已接受事件。

**No availability-mapped overflow, no capacity dimension fields.** ✅

---

#### 4. Durable causal fence、bounded merge 与跨 opener correctness — PASS

**证据链**：

- `dayu/host/transient_delta.py:218-281`：`ValidatedTransientDeltaCandidate` 携带 `durable_causal_fence_event_sequence`，来自同一 validation transaction 的 Attempt `started_event_sequence`。
- `dayu/host/transient_delta.py:284-311`：`HostTransientDeltaMailboxEntry` 包含 event + fence，二者合计按一个 retained item 计数。
- `dayu/host/open_host.py:1342-1358`：head fence 未达时不 pop，按 page 追 durable catch-up；head 达到 fence 后 pop 并 yield transient entry。
- `dayu/host/open_host.py:1300-1321`：current terminal fence 最大一个，逐次交付 mailbox head same-Run prefix，首个 different-Run entry 原位保留，terminal yield 后下一次 `anext()` 才交付 B。
- `dayu/host/open_host.py:1360-1372`：mailbox 空 + 无 local notice 时，由 bounded reconciliation interval（`_SESSION_EVENT_RECONCILIATION_INTERVAL_SECONDS = 0.02`，Host-internal 常量，不进入 public policy）驱动每次最多一页 durable read，持续调用中的后续 timeout 才允许下一页。
- `tests/host/test_watch_session_events.py`：双 opener 测试在 `test_watch_session_events.py` 内使用两个独立 `open_host` context + 共享 DB/lane DB，不依赖外部 fixture。

**不建立第三 sequence domain，不持久化 fence。** ✅

---

#### 5. Local TerminalPostCommitPort 与 producer completeness — PASS

**证据链**：

- `dayu/host/terminal_post_commit.py:14-66`：`TerminalPostCommitNotice` 严格三个字段（session_id、terminal_event_sequence、wake_queue_promotion），`TerminalPostCommitPort` 同步 local-only Protocol，不 public export。
- `dayu/host/durable/run_transition.py`：`RunTransitionResult` 增加 required `run_event: EventLogRow | None`。
- `dayu/host/admission.py`、`dayu/host/waiting.py`、`dayu/host/engine_ingest.py`、`dayu/host/recovery.py`、`dayu/host/dispatch.py`：terminal producer 内无直接 `wake_queue_promotion` 旁路 — 对 `dayu/host` 全仓 scan 确认 5 处剩余调用全部属于 coordinator（`open_host.py:447`）、scheduler bridge（`open_host.py:585,587`）、ordinary non-terminal admission（`admission.py:4692`）和 recovery accepted/queued promotion（`recovery.py:361`）。
- `dayu/host/open_host.py:1426-1545`：Host close 顺序为 health gate → wait_poller → durable_actor.stop_and_drain → scheduler.close → coordinator.close → delivery_hub.close → projection → actor handle/executor → store。scheduler-owned producer 全部 stop 后才 close coordinator/port，之后才 close delivery owner。

**AST manifest、runtime fakes、local A/B barriers 均在 `tests/host/test_terminal_post_commit.py` 覆盖。** ✅

---

#### 6. Service exact-five sole consumer 与 CLI/UI execution domain — PASS

**证据链**：

- `dayu/service/entrypoint_runtime.py:501-560`：exact-five closed union（`_TargetTerminal`、`_DeliveryInterrupted`、`_IteratorEnded`、`_CallbackFailed`、`_IteratorFailed`），每个携带 `target_generation`。
- `dayu/service/entrypoint_runtime.py:563-737`：`_ServiceObservationState` 实现 capacity-one first-commit slot，状态机：`ATTACHED_UNBOUND → CONSUMING(g) → RESULT_READY(g) → (ack) → ATTACHED_UNBOUND`；`request_stop()` 对空 slot 赢得仲裁。
- `dayu/service/entrypoint_runtime.py:1347`：只有 `DELIVERY_INTERRUPTED` 进入 `get_run/Outbox` durable recovery，其它 iterator failure 不伪装成 Host outage。
- `dayu/cli/runtime_display.py:137-355`：`RuntimeDisplayController` 每个 instance 创建私有 `ThreadPoolExecutor(max_workers=1)`，实现 `EntrypointCallbackExecutionPort`，通过 `async serial gate` + `loop.run_in_executor(explicit_executor, ...)` 串行执行 callback/renderer。不设置为 event-loop default executor，不与 Host/`dayu.runtime`/其它 Session 共享。
- `dayu/cli/session_execution.py`：caller lifecycle owner，唯一 `finally` close flow 先标记 closing → 等待当前 callback 完成 → 串行提交 renderer close → shutdown executor。

**无 Service event-copy relay、无 task exception side channel。** ✅

---

#### 7. Config、assembly、callers 与 README — PASS

**证据链**：

- `dayu/runtime/config_loader.py:524-529`：`SessionEventDeliveryPolicyConfig` 两个 required 正整数字段，strict exact-field parser。
- `dayu/service/host_assembly.py`：assembly 一对一构造 `HostSessionEventDeliveryPolicy(transient_mailbox_max_items=..., max_subscriptions_per_session=...)`。
- `dayu/host/__init__.py`：package export 包含全部新 public symbols。
- README trigger audit：`dayu/host/README.md`、`dayu/service/README.md`、`dayu/config/README.md`、`dayu/README.md`、`tests/README.md` 均更新；根 `README.md` 未不必要修改。
- 全部 production/test/utils caller 已更新为 `await watch_session_events(...)`。

**No missing constructor, no default fallback. No unused old symbols. No compatibility shim.** ✅

---

## Open Questions

1. **GitHub Actions CI 不完整**：仅 2 个 Windows checks 处于 pending 状态（`windows-init-transaction`、`windows-upload-script`），无 macOS/Linux CI 运行。PR body 未提及 CI gap。非 blocking（本 reviewer 已在本地独立验证全部 tests/pyright/scans），但应在 ready-for-review 前确认 CI 配置。

2. **PR body 中的 "aggregate deepreview ... PASS"**：该声明来自 pre-PR gate（Controller adjudication 对 commit `035d0035` 的裁决），而非本 PR review。PR body 将其放在 Validation 节可能被误读为 PR review 已通过。非 blocking，但建议在 PR body 中明确标注该 aggregate deepreview 的时间点和 scope，与本 PR review 区分。

3. **`docs/host/design.md` 变更**：该文件超出 256KB 限制，本 reviewer 未能完整走读其变更。对关键 section 的 scan 显示变更与 plan 一致（Host 拥有 Session Event Delivery、Service sole consumer、CLI execution domain 等），但未覆盖完整 diff。建议其他 reviewer 补读。

## Residual Risk

1. **未覆盖的 defensive code 分支**：各核心文件未覆盖行集中在防御性 TypeError/ValueError validation、close error logging 和 operator diagnostic 分支（如 `open_host.py` close error 级联路径 line 1435-1545）。这些路径在正常 operation 下不可达，但极端 double-failure 场景下的行为由 code structure 保证（close_error 聚合、首个 error 优先），tests 无法在不注入 mock failure 的前提下覆盖。risk 低。

2. **跨平台行为差异**：Windows CI pending；`ThreadPoolExecutor` 和 `asyncio` 在 Windows 上的 behavior（特别是 ProactorEventLoop 下的 `run_in_executor` 取消语义）未经本 reviewer 验证。risk 低（CLI display 执行域隔离不依赖 Windows-specific 行为）。

3. **`docs/host/design.md` 部分覆盖**：因文件大小限制未完整走读，见 Open Questions #3。

## Conclusion

**Verdict：PASS — 0 material findings**

经过独立的 adversarial correctness、stability、maintainability 和 semantic ownership 审查，本 PR 的实现与 plan、design、AGENTS.md 约束一致：

- Host 成为 Session Event Delivery 唯一 owner，删除 Service event-copy relay
- async attach successful-return 是真实 activation boundary
- item-only 512 mailbox + 4 subscription cap 精确生效
- typed errors/metrics 使用 closed enum，不含 identity/payload/capacity dimension
- causal fence、bounded merge、cross-opener reconciliation 有确定性 test barrier 证明
- terminal producer completeness 经 AST manifest + runtime fake + promotion bypass scan 三重验证
- Service exact-five capacity-one state machine 与 cleanup precedence 完整
- CLI 执行域由 UI 层显式拥有，与 Host/runtime default executor 隔离
- 全部 tests/pyright/coverage/scans 独立验证通过

无 material finding 需要 AgentCodex fix/re-review loop。

## Artifact Path

`docs/reviews/wu-host-session-event-delivery-01-pr-181-review-ds.md`

---

READY_FOR_CONTROLLER
