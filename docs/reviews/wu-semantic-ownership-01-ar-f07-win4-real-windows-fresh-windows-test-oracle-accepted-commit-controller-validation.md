# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-RW-RF01 Accepted Implementation Commit — Controller Validation

## Commit identity and verdict

- Timestamp：`2026-07-20T10:17:02+0800`。
- Commit：`329068411a1669730c0a5ec4ed3bde0b0ed9b8e5`。
- Subject：`test: accept AR-F07 WIN4 upload oracle fix`。
- Parent：`39926eb85aa25441f5209a128a3c971f451b5b25`。
- Tree：`3a78bca50dcc15defec7754cf3b14dca9a95bb1e`。
- Exact changed paths：`12`。
- Sorted path-list SHA-256：`0ec98b1177b9a7251ff76b8293e6dab8a25ab30966c1e703555f609f3198fe72`。
- Verdict：`PASS / LOCAL_SUB_WU_ACCEPTED / AGGREGATE_DEEPREVIEW_REQUIRED / REAL_WINDOWS_PENDING`。

## Scope and post-commit validation

Commit exact scope为：一个 target test file、control以及本 RF01 implementation/review/fix/re-review完整 evidence链。没有
`dayu/` production、其它 test、README、design或workflow delta。相对 parent的target code diff保持 frozen
binary/full-index SHA-256 `fcecb15cc3f09707077a6cf016ac28b960fb13013f1dcda92d4db092734f2169`。

Post-commit Controller fresh验证：

- worktree clean；staged tree empty；`git diff --check`通过；
- target test file：`20 passed, 2 skipped, 3 warnings`；
- commit path set、parent、tree、subject与sorted path digest exact match；
- local ledger accepted/open/new/backflow/blocker均为 `0`。

macOS的两个 skips仍是platform事实，不能关闭真实 Windows gate。API key/header trusted-local与 Tool Trace/audit明文禁止、既有
security mechanisms、no-unified-authorization与deferred Issues范围均未改变。

## Aggregate boundary and next gate

最后一个内部 remediation sub-WU的本地 implementation/review链至此 accepted，但 umbrella仍未完成。下一 gate必须从
aggregate base `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9` 到 accepted head
`329068411a1669730c0a5ec4ed3bde0b0ed9b8e5` 完整审查组合行为。该范围的 product/test/README payload仍为六个路径：

- `README.md`；
- `dayu/cli/commands/init.py`；
- `tests/README.md`；
- `tests/cli/test_init_command.py`；
- `tests/cli/test_prompt_command.py`；
- `tests/cli/test_upload_filings_from_command.py`。

Aggregate deepreview必须重新覆盖 old WIN4 S1/S2、RF01 test correction、真实 workflow契约、trusted-local secret与non-disclosure、
Fins public snapshot owner、security/deferred边界和全部 review backflow。只有aggregate review/fix/re-review accepted后，才可push并
dispatch fresh R11/R12；当前不得直接进入 remote、PR review或 closeout。
