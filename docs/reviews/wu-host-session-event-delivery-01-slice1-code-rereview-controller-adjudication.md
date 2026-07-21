# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 1 Code Re-Review Controller Adjudication

## Scope

- Gate: `code-rereview-slice-1`
- Accepted finding: `DS-F02`
- Base: accepted plan amendment commit `33af05fa`
- AgentCodex fix: `docs/reviews/wu-host-session-event-delivery-01-slice1-fix-codex.md`
- AgentMiMo original-review continuity artifact: `docs/reviews/wu-host-session-event-delivery-01-slice1-code-rereview-mimo.md`
- AgentDS original-review continuity artifact: `docs/reviews/wu-host-session-event-delivery-01-slice1-code-rereview-ds.md`
- AgentMiMo `$deepreview` artifact: `docs/reviews/code-review-20260721-210025.md`
- AgentDS `$deepreview` artifact: `docs/reviews/code-review-20260721-210135.md`

两路 reviewer 独立执行；Controller 不以多数票替代 finding 裁决。由于 Claude CLI 的 skill invocation 使用 `/deepreview`，两路在完成定向预检后均实际执行 `/deepreview --base 33af05fa`；只有上述 skill-driven artifacts 与原 reviewer continuity artifacts 共同作为本 gate evidence。

## Accepted finding closure

### DS-F02 terminal fence single-pop regression

Decision: `closed`。

两路均以当前代码和 deterministic test 独立确认：

1. `HostTransientDeltaSubscription.pop_next_nowait()` 在 mailbox owner boundary 逐项跳过 `run_id in _terminal_run_ids` 的 stale item。
2. stale item 只从 mailbox 释放，不写入 `_in_flight`；首个有效 item 才执行 mailbox → unique in-flight transfer。
3. stale-only 路径返回 `None`；stale + other-Run 路径返回后续有效 item。
4. stale drop、valid transfer、release、overflow 与 close 的 retained/readiness accounting 保持一致。
5. `test_single_pop_filters_prequeued_terminal_stale_item` 在修复前稳定失败、修复后通过，覆盖上述两条路径；S1 focused gate 为 `318 passed`，`transient_delta.py` coverage `92.09%`，完整 pyright `0 errors`。

修复位于正确语义 owner，不是 iterator、Service 或 UI 下游补偿，且未提前引入 Slice 2 causal fence。

## New findings adjudication

- AgentMiMo: 0 material finding，0 open question。
- AgentDS: 0 new material finding。
- AgentDS skill artifact 重复列出原 `DS-F04` 20ms Host-internal poll constant 注释建议。Decision: `rejected-with-reason-maintained`。该常量存在于 accepted base，符合 plan 的 private bounded constant contract；仍无 CPU regression 或错误 latency 的直接证据，推测性注释不是 correctness fix。
- AgentDS 关于大量 Session CPU 与 S1 relay 256/Host mailbox 512 的 open questions。Decision: 分别维持 `closed-no-current-action` 与 `closed-by-accepted-slice-sequencing`；后者由 Slice 4 删除 relay 的 accepted scope 收口。

## Residual observations adjudication

- S2 causal fence、S3 coordinator close ordering、S4 relay/exact-five/UI executor 均已由 accepted four-slice plan 指定 owner/destination，不是 Slice 1 遗留缺陷。
- 多处显式 `512/4` fixtures 继续作为无 hidden fallback 的独立 contract assertions，不抽取生产默认常量。
- 合并的 factory cancellation/close/allocation failure test 仅是组织建议；没有共享状态掩盖失败的代码证据，不创建修复。
- 任意第三方 callback 无限阻塞的物理终止边界是 accepted design constraint；Slice 4 仍须完成必要的 Service/UI execution-domain isolation。
- AgentDS `$deepreview` scope summary 把 README 数量记为 5 并提及未修改的 `dayu/service/README.md`；direct `git diff --name-only 33af05fa` 显示实际 modified README 为 4 个。该 artifact metadata 误差不影响其逐文件代码结论、finding closure 或验证结果，不构成 code finding；Controller 以 git diff 为权威范围证据。

## Gate decision

Decision: `pass`。

- `DS-F02`: closed。
- New material findings: 0。
- Blocking open questions: `None`。
- Validation evidence: S1 focused `318 passed`；affected Host/runtime/Service suites `2851 passed, 1 skipped, 6 deselected`；`transient_delta.py` coverage `92.09%`；完整 pyright `0 errors`；`git diff --check` pass。
- Next gate: Controller 创建 Slice 1 accepted commit，然后进入 `implementation-slice-2`，派发 AgentCodex。
