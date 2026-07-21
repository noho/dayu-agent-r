# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 2 Code Review Controller Adjudication

## Scope

- Gate: `code-review-slice-2`
- Base: accepted Slice 1 commit `64383186`
- Implementation artifact: `docs/reviews/wu-host-session-event-delivery-01-slice2-implementation-codex.md`
- AgentMiMo `/deepreview` artifact: `docs/reviews/code-review-20260721-221210.md`
- AgentDS `/deepreview` artifact: `docs/reviews/code-review-20260721-221029.md`

两路 reviewer 独立执行；AgentDS 首次 invocation 未产出 artifact，因此不计入 gate evidence，清理上下文后的完整重跑才作为有效审查。Controller 不以多数票替代 finding 裁决，也不亲自实施或 review。

## Review conclusions

- AgentMiMo: `PASS`，0 material finding，0 blocking open question。
- AgentDS: `PASS`；列出 F1/F2/F3 三项观察，并在补齐的 Gate Conclusion 中明确三项均非 material、均不阻塞 Slice 2。

两路均确认 causal fence 来自同一 validation transaction 的 `Attempt.started_event_sequence`，逐订阅 mailbox entry 独立，retained accounting 保持 mailbox + unique in-flight，head 在 cursor 追平 fence 前不会 pop，durable page cursor 只按已处理边界推进，same-Run prefix / terminal / different-Run barrier、overflow prefix 后立即 typed error、每 timeout 最多一页、Host close 即时 EOF 与双 opener independent-context barrier 均成立。

## AgentDS findings adjudication

### DS-F1 同一 durable page 内多个 non-PROGRESS event 缺少独立测试

Decision: `not-accepted-as-slice-2-defect; carried-as-slice-3-directed-test-input`。

直接代码证据和 reviewer 走读均表明当前单槽状态机会逐一处理 terminal，不存在已证明的丢失、合并或交换顺序缺陷；accepted Slice 2 completion conditions 也未把该特定组合列为 blocking barrier。因此不创建 Slice 2 fix gate。另一方面，本 WU acceptance 明确要求完整 terminal producer static/runtime barriers，Slice 3 正是 terminal producer/coordinator 接线闭环；派发 Slice 3 时必须把“同一 durable page 内至少两个 non-PROGRESS event，且各有对应 transient handoff”的 deterministic regression 纳入实现验证，最终 aggregate deepreview 再检查其闭环。该归属不是 residual WU，也不得推迟到本 WU 之外。

### DS-F2 删除 `_terminal_run_ids` 后缺少 mailbox 层 post-terminal fallback

Decision: `rejected-with-reason`。

accepted plan 明确要求删除 subscription terminal run-id set；post-terminal transient candidate 的语义 owner 是 `EngineEventIngestor` 的同一 durable validation transaction，而不是 subscription、iterator 或测试 helper。通过测试 helper 绕过 durable validation 后再要求 mailbox 拒绝，会把 owner contract 错放到下游并重新引入从 event 顺序反推 terminal 的补偿逻辑，违反设计与仓库 AGENTS.md。当前无直接代码证据证明 owner validation 存在竞态缺口，不恢复 `_terminal_run_ids`，也不新增绕过 owner 的伪端到端测试。Slice 3 的 terminal producer static/runtime barriers仍须从真实 owner path 验证 terminal 提交后不会产生 transient candidate。

### DS-F3 `pending_durable_page_next_cursor` 初始赋值不被消费

Decision: `rejected-nonmaterial`。

guard 证明该初始值在首次 page read 前没有执行路径会读取；没有 correctness、stability、maintainability 或类型错误证据。使用任意 sentinel 反而会引入额外无效状态。当前保持最小实现，不为纯 dead store 印象创建 fix gate；若后续 owner-level 状态机抽取自然删除该赋值，可随所属 slice 一并验证。

## Residual observations adjudication

- AgentMiMo 记录的 global EventLog scan 后按 session 过滤是 accepted base 的既有 read contract，Slice 2 未改变；无当前 regression 证据，不扩张本 slice。
- local terminal watermark 的 producer/coordinator wiring 明确属于 Slice 3；Slice 2 只建立 owner state/hook，双 opener correctness 不依赖 local hook。该项是下一 slice 的 accepted scope，不是未归属 residual。
- merge loop 复杂度是 aggregate deepreview 的 maintainability 观察点；当前 coverage、deterministic barriers 与完整类型检查均已通过，不以推测性重构替代已验证实现。
- F1 指定的 multi-terminal single-page regression 与 F2 指定的真实 owner-path terminal barrier必须在 Slice 3 内闭环，不创建新的 residual WU。

## Validation evidence

- AgentCodex implementation gate: focused `159 passed`；affected suites `3410 passed, 8 skipped, 6 deselected`；stress `6 passed`；`engine_ingest.py` / `transient_delta.py` / `open_host.py` production single-file coverage `84.28%`–`92.00%`；完整 pyright `0 errors`；diff/source/scope audits pass。
- AgentDS independent rerun: focused `151 passed`；affected suites `3410 passed, 8 skipped, 6 deselected`；stress `6 passed`；`transient_delta.py` coverage `92.00%`；`open_host.py` coverage `84.28%`；pyright `0 errors`。
- Controller acceptance check: `git diff --check` pass；Slice 2 changed-file scope与 implementation artifact一致。

## Gate decision

Decision: `pass`。

- Accepted current Slice 2 findings: 0。
- Material findings remaining: 0。
- Blocking open questions: `None`。
- Next gate: Controller 创建 Slice 2 accepted commit，然后进入 `implementation-slice-3`，把 DS-F1 multi-terminal regression 与真实 owner-path post-terminal barrier作为显式派发约束交给 AgentCodex。
