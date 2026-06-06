# WU-TOOLS-01 Final Closeout Controller

## 结论

WU-TOOLS-01 本地 final closeout 通过。Fins / Web / Doc tools migration with shared document foundations 的 S1-S6 与 external blocker reconciliation 已接受；当前没有无 owner / destination 的 open residual risk。

本 closeout 不声明 GitHub PR gate 已通过，也不关闭 GitHub Issue #82 / #97 / #98。当前分支仍需按用户授权进入 draft PR gate。PR merge 后，默认后续入口是 WU-TOOLS-01-F01；若用户优先恢复 broad Host validation，则先进入 WU-CM-01-F04。

GitHub issue status comments:

- #82：https://github.com/noho/dayu-agent-r/issues/82#issuecomment-4637480828
- #97：https://github.com/noho/dayu-agent-r/issues/97#issuecomment-4637480886
- #98：https://github.com/noho/dayu-agent-r/issues/98#issuecomment-4637480924

## Scope

- Work unit：WU-TOOLS-01。
- 状态：local final closeout / PR-ready closeout。
- 设计真源：`docs/host/design.md`、`docs/engine/design.md`。
- 总控真源：`docs/host/issues-implementation-control.md`。

## Accepted Local Delivery

- Accepted plan commit：`f6658fb4`。
- Slice S1 shared document foundations accepted commit：`07e3b7f9`。
- Slice S2 tool adapter and typed provider config accepted commit：`20cd553c`。
- Slice S3 Doc tools provider accepted commit：`2d46fee8`。
- Slice S4 Fins storage and read tools provider accepted commit：`6a0bc255`。
- Slice S5 Web tools provider accepted commit：`0b4dcd81`。
- Slice S6 combined discovery / ToolRuntime acceptance accepted commit：`36d66569`。
- External blocker reconciliation accepted commit：`ac036cbc`。
- Fins ingestion follow-up control commit：`746f7db9`。
- Host compactor seam residual plan clarification commit：`8dddea7d`。

## Residual Risk Closeout

| ID | Closeout decision | Owner / destination |
|---|---|---|
| WU-ENG-02-S3-R1 | transferred-to-issue | WU-OBS-00B / GitHub Issue #119 under #70 analyzer |
| WU-TOOLS-01-S4-R1 | deferred-with-owner | WU-TOOLS-01-F01 |
| WU-TOOLS-01-S5-R2 | deferred-with-owner | WU-TOOLS-01-F02 then WU-TOOLS-01-F03 / GitHub Issue #120 |
| WU-TOOLS-01-S1-R1 | deferred-with-owner | WU-TOOLS-01-F04/F05 and WU-TOOLS-01-F06/F07 / GitHub Issues #121 and #122 |
| WU-TOOLS-01-S1-R2 | deferred-with-owner | WU-TOOLS-01-F08 |
| WU-TOOLS-01-S6-R1 | deferred-with-owner | WU-CM-01-F04 before broad Host validation |

No active residual is left in `open` state. Closed residuals from earlier gates remain documented in their review / reconciliation artifacts and are not re-added to the active residual table.

## Follow-up Work Units

- WU-TOOLS-01-F01：build the shared Fins service/runtime foundation, then expose independent read / download / preprocess providers through the current ToolRuntime / awaiting contract; CLI and tool download / process must call the same runtime logic.
- WU-TOOLS-01-F02：migrate the OLD Web CI diagnostics pipeline.
- WU-TOOLS-01-F03：generate explicit Web smoke from the migrated diagnostics pipeline.
- WU-TOOLS-01-F04：migrate SEC/Fins CI pipeline.
- WU-TOOLS-01-F05：generate SEC/Fins CI smoke.
- WU-TOOLS-01-F06：migrate CN/HK Docling CI pipeline.
- WU-TOOLS-01-F07：generate CN/HK Docling smoke.
- WU-TOOLS-01-F08：rename the documents processor registry away from the misleading OLD `engine` ownership name.
- WU-TOOLS-01-F09：migrate upload ingestion into the shared Fins service/runtime foundation and add an independent upload ingestion tool provider.
- WU-CM-01-F04：migrate proactive scheduler tests to the current manifest-producing compact contract.
- WU-OBS-00B：decide whether usage observation projection needs correlation fields in analyzer scope.

For all Fins ingestion follow-ups, ticker / market normalization must call `dayu/fins/ticker_normalization.py` as the only source of truth. No CLI, tool adapter, CI runner, smoke runner or pipeline selector may recreate ticker parsing, market inference, exchange inference or company id generation logic.

## Validation Status

The accepted slice artifacts record focused test and pyright validation. This closeout step made documentation-only control updates; no production code, test code, schema or README behavior changed.

Final local checks for this closeout must verify:

- `git diff --check` passes.
- Residual risk table has no `open` item without owner / destination.
- WU-TOOLS-01 row and current status point to PR-ready closeout and executable follow-up entry points.

## Next Entry Point

Open the WU-TOOLS-01 draft PR from branch `phaseflow/wu-tools-01` with deferred residuals tracked in the control doc and GitHub Issues #119-#122. After PR merge, enter WU-TOOLS-01-F01 by default. If broad Host validation must be restored before tool follow-ups, enter WU-CM-01-F04 first.
