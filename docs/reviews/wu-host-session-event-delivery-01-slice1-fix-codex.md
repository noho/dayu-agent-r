# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 1 Code Review Fix

## Gate metadata

- Work unit：`WU-HOST-SESSION-EVENT-DELIVERY-01`
- Gate：`code-review-fix-slice-1`
- Accepted finding：仅 `DS-F02`
- Accepted plan base：`33af05fa`
- 实施 owner：AgentCodex
- 完成状态：`READY_FOR_REREVIEW`
- Artifact path：`docs/reviews/wu-host-session-event-delivery-01-slice1-fix-codex.md`

## Scope

本 gate 只修复 `HostTransientDeltaSubscription` 的 watcher-local single-pop terminal fence，并补 owner-contract test。未处理 Controller rejected 的 `DS-F01`、`DS-F03`、`DS-F04`，未进入 Slice 2 或后续 slice，未修改 Controller-owned `docs/host/issues-implementation-control.md`、adjudication artifact 或 reviewer artifacts，也未 commit。

本 gate 新增或修改的文件：

- `dayu/host/transient_delta.py`
- `tests/host/test_transient_delta.py`
- `docs/reviews/wu-host-session-event-delivery-01-slice1-fix-codex.md`

## First-principles judgment and root cause

问题真实存在，并且是 terminal delivery correctness finding，不是未来误用风险：

1. accepted base 的 `drain_nowait()` 在 owner boundary 丢弃 `run_id` 已进入 `_terminal_run_ids` 的 mailbox item；当前 `pop_next_nowait()` 改成直接 `popleft()` 后丢失了该 fence。
2. `_PublicHostHandle._watch_session_events_after()` 在 mailbox 暂时为空后会 await durable actor read。await 期间，同 Run transient 可以先通过 `_offer()` 进入 mailbox。
3. durable read 返回后，iterator 会 mark 并 yield 同 Run terminal；`_offer()` 只能拒绝 mark 之后的新 publish，不能处理 mark 之前已经接受的 mailbox item。
4. 下一次 `anext()` 因而会把该 stale item 直接转成 in-flight 并错误交付。

语义 owner 是 `HostTransientDeltaSubscription`：它同时拥有 mailbox、唯一 in-flight、watcher-local terminal fence、retained item 计数与 readiness。修复若放在 `open_host` iterator 或 Service consumer，会形成下游补偿并使多个消费者重复解释 terminal fence，因此不能接受。

## Fix

`HostTransientDeltaSubscription.pop_next_nowait()` 现在在 single-pop owner boundary 内：

- 从 mailbox 头部逐项检查 watcher-local terminal fence；
- 命中 terminal Run 的 stale item 直接释放，绝不写入 `_in_flight`；
- 首个有效 item 才执行 mailbox 到唯一 in-flight 的 transfer，因此有效 transfer 前后 retained item 数保持不变；
- mailbox 没有有效项时返回 `None`；
- 返回前统一按剩余 mailbox、overflow 与 closed owner state 刷新 level-triggered readiness。

该扫描最多处理当前 policy 已有界的 retained prefix，不引入 batch 返回、额外 retained copy、兼容分支、下游 fallback 或 Slice 2 causal fence。

## Deterministic owner-contract test

新增 `test_single_pop_filters_prequeued_terminal_stale_item`，覆盖两个确定性场景：

1. mailbox 预存 Run A stale item，后面还有 Run B item；mark Run A terminal 后，single-pop 直接返回 Run B。断言 Run A 不被交付，Run B 是唯一 in-flight，`retained_items` 从 2 变为 1，mailbox readiness 已清除，release 后计数为 0。
2. mailbox 只预存一个同 Run stale item；mark terminal 后，single-pop 返回 `None`。断言 stale 未成为 in-flight，`retained_items` 变为 0，readiness 不再保持 set。

红灯证据：只加入测试、尚未修复时，精确 node 失败并显示实际返回 `run-1`、预期 `run-2`。实施 owner 修复后同一 node 通过。

## Validation

- 红灯复现：`pytest tests/host/test_transient_delta.py::test_single_pop_filters_prequeued_terminal_stale_item -q` → `1 failed`，实际错误交付 `run-1`。
- 修复后精确 node：同一命令 → `1 passed`。
- 受影响 focused tests：`pytest tests/host/test_transient_delta.py tests/host/test_watch_session_events.py -q` → `29 passed`。
- S1 focused gate：plan S1 的 9 个 focused files → `318 passed, 3 warnings`；warnings 均为第三方 `edgar` deprecation warning。
- 单文件 coverage：`pytest tests/host/test_transient_delta.py tests/host/test_watch_session_events.py --cov=dayu.host.transient_delta --cov-report=term-missing --cov-fail-under=80 -q` → `29 passed`，`dayu/host/transient_delta.py` 为 `92.09%`。
- 完整类型检查：`python -m pyright dayu/ tests/ utils/` → `0 errors, 0 warnings, 0 informations`。
- Whitespace gate：`git diff --check` → exit 0。

所有 Python 验证均在 `source .venv/bin/activate` 后运行。

## README audit

- `dayu/host/README.md` 已明确承诺 watcher-local terminal fence：terminal 后不再交付同 Run late delta；本修复恢复该既有 contract，没有新增或改变 public API、policy、分层或用户可见流程，因此无需修改。
- `tests/README.md` 已把 terminal fence 和 `test_transient_delta.py` deterministic owner barriers 纳入当前测试职责摘要；新增测试属于既有测试层级和 contract 的补强，因此无需修改。
- 本修复不触发根 README、`dayu/README.md` 或其它 README 的内容变化。

## Finding status and residual risks

- `DS-F02`：`已修复`，等待 AgentMiMo 与 AgentDS 独立 re-review。
- 新增 residual risk：无。single-pop stale 扫描受现有 retained item policy 上界约束，不改变 overflow、reservation、detach 或 async attach 状态机。
- Slice 2—4 的既定工作仍由 accepted plan 对应 slice owner 覆盖；本 gate 未实施、提前评审或重分类这些后续范围。
- Controller rejected findings 保持 `rejected-with-reason`，本 gate 未改动相关代码。
