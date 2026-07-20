# WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4 Fresh Windows Corrected Evidence Controller Adjudication

## Verdict

`REMOTE_PASS / AR-F07-WIN-REMOTE_CLOSED / AR-F07_CLOSED / PR_REVIEW_NEXT`

本裁决属于 `WU-SEMANTIC-OWNERSHIP-01` umbrella WU 的 AR-F07 WIN4 remediation continuation，不是新 WU，也不创建新的 sub-WU。

## Locked run identity

| Gate | Dispatch-returned run id | Workflow | Path | Event | Ref | Head SHA | Attempt | Conclusion |
|---|---:|---|---|---|---|---|---:|---|
| R11 | `29713519099` | `R11 upload script Windows gate` | `.github/workflows/r11-upload-script-windows.yml` | `workflow_dispatch` | `phaseflow/host-issues-control` | `701dacc05d42f079b9f8e414aa54807714217d0c` | 1 | success |
| R12 | `29713522620` | `R12 init Windows gate` | `.github/workflows/r12-init-windows.yml` | `workflow_dispatch` | `phaseflow/host-issues-control` | `701dacc05d42f079b9f8e414aa54807714217d0c` | 1 | success |

两个 run id 均直接取自各自 `gh workflow run` dispatch response URL。Controller 没有按时间、最近 run、workflow summary 或 artifact 名反推 run id；下载、metadata、job、log 与 artifact 查询均锁定上述 exact ids。

## R12 pre-content security gate

在读取任何 R12 evidence 内容前，Controller 依序完成：

1. metadata tuple 精确匹配 workflow name/path、event、ref、accepted head SHA 与 attempt；
2. 下载同一 R12 run 的完整 logs ZIP 与 API 列出的唯一 artifact `r12-init-windows-29713522620`；
3. 独立验证冻结 domain 为 31 bytes、single trailing NUL，且 public run-id `1` known vector 匹配；
4. 仅在进程内派生本 run 的 test canary，对两个 archive raw bytes、18 个 uncompressed entries 及当时 171 个相关 review/control evidence 文件做 exact-value scan。

结果：`match_category=test_canary / status=PASS / matches=0`。实际 canary 未打印、未写文件、未进入命令输出或本 artifact；未读取、请求、导出或扫描 GitHub Secrets/configured production values。写入本 artifact 与 control 更新后，Controller 对相同两个 archives、18 entries 及更新后的 172 个相关 review/control evidence files 再次扫描，仍为零命中。

## R11 evidence

- workflow/job/全部 steps：success；JUnit `4 tests / 0 failures / 0 errors / 0 skipped`，四个 exact nodes 全部 passed。
- artifact id/name/size：`8449629852` / `r11-windows-upload-script-29713519099` / `478211` bytes；artifact ZIP SHA-256 `a0041dcc9e9dc9513e6bde4f36c17cdd5dd56c6f6a8f74cf2c26633b5d457f5a`；logs ZIP SHA-256 `9ab285531fcfdce8a0c7c0d5491484af8037d9fc49dd7bce7eaf5923522dba8d`。
- JUnit/stdout/stderr SHA-256：`938e4b4b55fb33a52d7f04d805398d6464271587f3da9c3f9725b016853831df` / `4229d6cb52bed5dc221dd5f5cc90f8ee8ead18ba73d963e4745e06f60f919cfd` / empty-file `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。
- generated script SHA-256 `c1ae92232d69e91cfaa269a068abd39bbc295a7c426f715515e92f887be01d9d` 与 oracle 精确一致；recorder oracle 恰有一行；`cmd.exe /d /c`、company-name supplied 与 result contract 均通过。
- runner 内 `source_artifact_count` actual/oracle 为 `7/7`，由 workflow step fail-closed 比较并成功；downloaded public portfolio 有 5 个非隐藏文件且 required recorder/script/oracle/JUnit/stdout/stderr 均存在。现有 upload action 默认不上传 storage hidden identity files，该已知 packaging 边界不承担业务成功语义。
- public storage contract：`source_kind=filing`；`primary_filename=2024FY_AAPL_Annual_Report_docling.json` 在 descriptors 中 exact membership 为 1；raw source basename `2024FY_AAPL_Annual_Report.htm` exact membership 为 1，其 public SHA-256 与同一 Windows artifact source bytes及 published raw file均为 `7473d33d2b53e02753e0f52f82ac57f72a653e0d3cdd513e25f95d34943a96e6`。没有把 raw source 强制为 primary。

## R12 evidence

- workflow/job/全部 steps：success；init JUnit `9/9 passed`，embedded R11 JUnit `2/2 passed`，均为 0 failures / 0 errors / 0 skipped。
- artifact id/name/size：`8449652016` / `r12-init-windows-29713522620` / `1976` bytes；artifact ZIP SHA-256 `c605b70b73ef2432e792a70a85af8b88fea7cc5fde03cd5a0736d282db170909`；logs ZIP SHA-256 `de34da019ce1441ef338da9ba344bb0bfd198dd99c889c2e9926a2a5dc202d31`。
- init JUnit、embedded R11 JUnit、source hashes SHA-256 分别为 `98099010d486faa3a02121e3586554c0ff3ac2aaf19559f7e4dc8cdf2e843a15`、`d5967263b8ac0f6fb5f57d70ba2645c0a4fe8c6515c1d7e8e04e5cd37f4a5c17`、`32a798ddf16db9f91f651243853302f65c35a672d73a1986b9ad7cc9bc8d2b06`。
- required five files全部存在；`environment-names.txt` 只含六个配置名、不含值，SHA-256 `79188cd5efabfb10a52600169ce5198610190dcb10baf24271d4f828dc338763`。
- `source-hashes.json` 的五个 Windows checkout source hashes 均与 accepted HEAD 对应文件的 CRLF worktree bytes 精确匹配；本地 LF blob hash不同是 checkout line-ending projection，不是 lineage mismatch。
- real redirected stdin、setx round-trip/exact cleanup、junction/symlink/identity-drift/rollback/race gates全部由 exact JUnit nodes通过。Tool execution handshake timeout、Issue 142/151/175/177/178 与统一 authorization 均未被本 gate 实施。

## Controller closure

`AR-F07-WIN-REMOTE` 的唯一 open evidence residual 已由 fresh same-head R11/R12 关闭。先前 RF01 是 test consumer ownership defect；修正后同一 product behavior 在 standalone 与 embedded real Windows gates均通过。没有 production Fins defect、secret leak、统一 authorization需求或新的产品裁决问题。

Gemini 低 budget 仍按用户裁决为 `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`，与本 Windows gate 无关。

## Next gate

只授权 Controller 形成 exact remote-evidence accepted commit并做 post-commit scope/cleanliness validation。之后 push，进入 draft PR 179 双路完整 review；不得 merge、mark ready、删除分支或直接 final closeout。
