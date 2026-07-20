# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4-S3 Controller Validation

## Result

`PASS / READY_FOR_DUAL_COMPLETE_CODE_REVIEW / REAL_WINDOWS_PENDING`

## Immutable target

- Entry commit：`5c8c11f88fb0d935ad5730aa7d892ad26a060633`（S2 accepted commit）。
- Exact payload target：`tests/cli/test_init_smoke.py`、`tests/README.md`。
- Payload binary diff SHA-256：`8bba3cd26606dd62552f3ee34a647da749027c62eef737407d6d4c16606886c4`。
- Test file SHA-256：`6748c609664f1e51854d743fd6dd5497069a384aadf7a91604c41a4476ceec30`。
- Tests README SHA-256：`0fa4165bea105738d48788e782e51ad48eadb7aca9ea6a44ddf07e2d795f6aa2`。
- AgentCodex implementation artifact：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s3-implementation-codex.md`，SHA-256 `65afdbcdf18e497032eece068db76f5df864c752526599958198a16d80a355e2`。
- Three-path content manifest SHA-256：`baf08e5c3227a07d1020bfa442ccc879045c6b5d6165bf45b0b3bcdea1e64429`。

Controller 同时锁定并保护既有 dirty inputs：control doc 与 S2 accepted-commit validation artifact。AgentCodex 未改写它们；staged tree 保持为空。

## Owner and behavior verification

Controller 逐行确认：

- `_run_init()` 是 outer real-CLI process failure projection 的唯一 test owner；它用三个 `TemporaryFile(mode="w+b")` anonymous binary handles 与 `Popen[bytes]`，stdin strict UTF-8 write/flush/rewind 后清空 local text/bytes variables，显式 `shell=False`、`close_fds=True`、`text=False`，只调用 `wait()`，没有 `communicate(input=...)`。
- ordinary completion 才读取 stdout/stderr 并 strict UTF-8 decode；typed result 只保留 returncode/stdout/stderr。普通 nonzero 不被重分类为 timeout。
- timeout deadline 后先 poll；仍运行才 kill direct process并做唯一 bounded cleanup wait。cleanup 再 timeout 后恰好一次非阻塞 poll，投影 running/exited；此后没有额外 wait/kill、process-tree 或 job-object 治理。
- failure path 不读取 stdout/stderr；三个 handles 覆盖 child execution 与 cleanup，并在 context unwind 后关闭。
- 唯一 renderer 只投影 category、timeout、deadline returncode、cleanup 与 cleanup returncode；cleanup timeout 才增加 post-timeout process state。`pytest.fail(..., pytrace=False)` 不传播 raw exception frames。
- GitHub Actions canary 只从公开正 ASCII 十进制 `GITHUB_RUN_ID` 经 canonical decimal、31-byte single-NUL domain 与 SHA-256 派生；run id `1` known vector精确匹配 accepted plan。非法/missing workflow id fail closed且不随机 fallback；本地路径仍随机。
- Owner tests锁定 Popen/handle contract、strict UTF-8、ordinary nonzero、四个 timeout/cleanup states、精确 wait/poll/kill 次数、failure-path zero read、raw-probe present/final-projection absent、canary bytes/vector/determinism/shape/fail-closed/local random。
- `tests/README.md` 只更新 accepted test-evidence boundary；没有扩大用户 CLI workflow或 root README 职责。

## Independent validation

Controller 在 `.venv` 下独立运行：

- S1/S2/S3 combined owner tests：`105 passed, 7 skipped, 3 existing edgar deprecation warnings`。
- Full pyright：`0 errors, 0 warnings, 0 informations`。
- Scoped Ruff：`All checks passed!`。
- `git diff --check`：PASS；staged tree empty。

AgentCodex 另运行 final `tests/cli`：`538 passed, 7 skipped`；accepted focused matrix：`200 passed, 7 skipped`；broader Fins：`95 passed`；S2 production owner branch coverage：`93%`。Full Ruff entry/final 均为既有 142-entry exact tuple，SHA-256 `9df493aafef1701c3e2732ee61ea8dfb265d321a435ac12355733c70e245eda5`，新增/扩散为 `0`。

## Scope, security and residuals

- production、S1/S2、workflow、root README、plan/design 与 deferred Issue paths 零 diff。
- S3 diff零命中 `communicate(`、`mkstemp`、`NamedTemporaryFile`、process group/job object、PowerShell、`shell=True` 或 replacement decode。
- 没有读取 GitHub Secrets 或 configured production values，也没有写 canary needle artifact/JUnit property。
- 用户既有 trusted-local Config/Host durable secret 与 Tool Trace/audit no-plaintext 裁决不变；本 slice 只处理测试失败投影。

本地 Darwin 的 Windows nodes按平台跳过，不能关闭 release blocker。真实 Windows R11/R12、dispatch-run lineage 与同一 R12 run 的 log/all-artifact canary scan 保持 `PENDING_RELEASE_BLOCKER`，只能在 S3 accepted commit 并 push 后由 Controller执行。

下一 gate 仅授权 AgentMiMo / AgentDS 对上述 immutable S3 payload、implementation artifact 与本 validation 做并发完整 code review；通过裁决/fix/re-review前不得 accepted commit、push或 dispatch。
