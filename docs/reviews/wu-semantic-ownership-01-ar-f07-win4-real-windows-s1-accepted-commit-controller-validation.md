# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4-RW-S1 Accepted Commit Controller Validation

## Result

`PASS / ACCEPTED_COMMIT_VALIDATED / S2_IMPLEMENTATION_AUTHORIZED / REAL_WINDOWS_PENDING`

## Commit identity

- Commit：`9eeb467ab45ca945882234026ef95301cd5b609d`（`test: accept AR-F07 WIN4 real-Windows S1 remediation`）。
- Parent：`8fafe9bad4828c83fa6cf80a1dc2199fe78472d9`。
- Tree：`98079423de68a22b5798e7d1733602f87f2b2ed3`。
- Exact path count：12。
- Sorted path-list SHA-256：`b988a469221b779f7d47a1bd0de3ebae4bdb19af07902561f2ab3f37c4214989`。
- Committed payload SHA-256：`71855b783ae1191ed764c69c938f2ca29d0c51ae575f501a431e33615ebb4d3d`。

## Exact accepted paths

1. `docs/host/issues-implementation-control.md`
2. `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s1-code-rereview-controller-adjudication.md`
3. `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s1-code-rereview-ds.md`
4. `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s1-code-rereview-mimo.md`
5. `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s1-code-review-controller-adjudication.md`
6. `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s1-code-review-ds.md`
7. `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s1-code-review-fix-codex.md`
8. `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s1-code-review-fix-controller-validation.md`
9. `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s1-code-review-mimo.md`
10. `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s1-controller-validation.md`
11. `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-s1-implementation-codex.md`
12. `tests/cli/test_upload_filings_from_command.py`

无其它product/test/README/workflow/design/plan路径进入提交。

## Fresh validation

- Target test：`20 passed, 2 skipped, 3 warnings`。
- Public repository owner nodes：`3 passed, 3 warnings`。
- Full pyright：`0 errors, 0 warnings, 0 informations`。
- Staged `git diff --check`：PASS。
- Post-commit working tree：clean。
- Post-commit staged tree：clean。
- Committed path count/digest、parent、tree与payload SHA均与提交前锁定值一致。

一次Controller输入的诊断命令使用了不存在的两个测试文件路径并以pytest usage error退出；它没有修改仓库状态，随后已用
implementation artifact列明的三个exact public repository owner nodes重跑并得到上述`3 passed`。该诊断失误不属于产品、测试或
review finding。

## Authorization boundary

只授权WIN4-RW-S2 implementation：由CLI input owner在TTY下继续使用隐藏输入，在redirected stdin下提示到stderr并读取恰好一行，
统一收敛TTY `EOFError`与redirected empty string，保留`KeyboardInterrupt`传播，并只条件移除一个LF及其紧邻CR。允许修改范围严格为
`dayu/cli/commands/init.py`、`tests/cli/test_init_command.py`、根`README.md`、`tests/README.md`及S2 evidence。不得进入aggregate、push、
remote dispatch或PR review；不得引入统一secret/authorization infrastructure或实现任何deferred Issue。
