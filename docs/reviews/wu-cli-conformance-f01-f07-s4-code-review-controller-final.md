# WU-CLI-CONFORMANCE-F01-F07 S4/F04 Code Review — Controller Final Adjudication

## Gate 元数据

- Work unit：`WU-CLI-CONFORMANCE-F01-F07`
- Slice：`S4 / F04`
- Gate：`code re-review -> accepted slice commit`
- Entry HEAD：`25400fba`
- 状态：`PASS`

## Evidence 与 final states

- MiMo re-review：`docs/reviews/wu-cli-conformance-f01-f07-s4-code-rereview-mimo.md`，PASS。
- DS re-review：`docs/reviews/wu-cli-conformance-f01-f07-s4-code-rereview-ds.md`，PASS。
- Fix：`docs/reviews/wu-cli-conformance-f01-f07-s4-fix-codex.md`。

| Finding | Final state |
|---|---|
| close失败后重复close/docstring不一致 | `已修复`：terminal/take-clear在await前，异常原样传播，后续no-op。 |
| refresh close失败后的stale current/double-close | `已修复`：await前take-clear，失败不open，下一次显式mutation fresh open。 |
| close/open failure tests | `已修复`：exactly-once attempt、异常identity、no-premature-open、open retry全部锁定。 |
| enum `is`建议 | `证据失效`：typed schema boundary拒绝裸字符串，CLI保持identity匹配，不做loose parsing。 |

总控已核对修订代码、五个新增failure/typed tests、两路re-review与209项focused test / full pyright证据。F04核心contract保持：mode immutable、READ_ONLY拒绝留REPL/draft/history且零Run、下一mutation fresh attach、同语义稳定request id、RW后恰好一个Run与一次ack。

真实双CLI进程/PTY调度风险已分类给S8。没有unclassified residual risk或blocking open question。本gate通过；下一入口为`S4 accepted slice commit`，之后进入`S5/F05 implementation`。

## Artifact path

`docs/reviews/wu-cli-conformance-f01-f07-s4-code-review-controller-final.md`
