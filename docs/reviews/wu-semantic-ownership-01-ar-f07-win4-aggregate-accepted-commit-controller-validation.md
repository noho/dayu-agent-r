# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4 Aggregate Accepted Commit Controller Validation

## Result

`PASS / EXACT_SCOPE_ACCEPTED_AGGREGATE_EVIDENCE_COMMIT / READY_FOR_PUSH_AND_REAL_WINDOWS_DISPATCH`

## Commit identity

- Commit：`e0bbf2ae14a92f9069c8440d0443341c1b1d812a`（`docs: accept AR-F07 WIN4 aggregate evidence`）。
- Parent：`d9a9edacfe610038e77c770ba43b63c0f613b549`（S3 accepted commit）。
- Tree：`403b78586dc60cf78f4e32245b7713fd39822122`。
- Exact changed paths：`10`。
- Sorted changed-path list SHA-256：
  `5c29f62f4f03b78d1eebb28ffbe9321c514770a126fee494ffd8f144338d62e0`。

## Scope validation

提交内容精确为control doc、S3 post-commit validation以及aggregate initial reviews、Controller adjudication、
zero-change fix/validation、双路complete re-review和final Controller adjudication。没有production、test、README、
workflow、design或accepted plan变更。

提交前staged exact manifest为10 paths且`git diff --cached --check`通过；提交后working tree与staged tree均为空，
`git diff --check`和`git diff --cached --check`通过。

## Ledger and next gate

- Aggregate material finding：`0`。
- Accepted/open finding：`0`。
- Accepted chain backflow：`0`。
- Local blocker：`0`。
- Real Windows residual：`PENDING_RELEASE_BLOCKER`。

下一 gate由Controller把包含本validation和control状态的exact evidence commit完成后，非强制push当前branch到remote
`github`，再分别dispatch新的R11与R12 Windows workflow。R12必须使用dispatch response返回的唯一run id锁定
workflow/event/branch/ref/head SHA并独立重算run-specific canary；该值不得出现在命令、review artifact、control doc、
Tool Trace、audit或公开日志中。Standalone R11不消费该canary，只按自身无secret-input与artifact integrity验收。
