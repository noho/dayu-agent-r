# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-RW Fresh Windows Evidence Controller Adjudication

## Verdict

`REMOTE_PARTIAL_PASS / ACCEPTED_TEST_ORACLE_FINDING=1 / PLAN_CORRECTION_REQUIRED`

本轮仍属于既有 `WU-SEMANTIC-OWNERSHIP-01` umbrella WU 的 AR-F07 WIN4 real-Windows remediation continuation，不创建新 WU。

## Locked Run Identity

| Gate | Dispatch-returned run id | Workflow | Path | Event | Ref | Head SHA | Identity |
| --- | ---: | --- | --- | --- | --- | --- | --- |
| R11 | `29709987970` | `R11 upload script Windows gate` | `.github/workflows/r11-upload-script-windows.yml` | `workflow_dispatch` | `phaseflow/host-issues-control` | `b11eb95c8312e085755b81c630e9c359220d3ff1` | PASS |
| R12 | `29709993229` | `R12 init Windows gate` | `.github/workflows/r12-init-windows.yml` | `workflow_dispatch` | `phaseflow/host-issues-control` | `b11eb95c8312e085755b81c630e9c359220d3ff1` | PASS |

两个 run id均直接来自各自 dispatch response URL，不是按时间、最近run、artifact名或workflow summary反推。

## R12 Security Gate

在读取任何R12 failure content前，Controller完成以下顺序：

1. 验证R12 metadata tuple完整匹配上表；
2. 下载同一run的完整workflow logs与唯一artifact `r12-init-windows-29709993229`；
3. 依据final plan §2.3文字在进程内独立验证known vector并派生run-specific non-secret test canary；
4. 对下载zip与解压后的完整logs/artifacts共 `19` files做recursive exact-value scan。

结果：`match_category=test_canary / status=PASS / matches=0`。Canary没有回显或落盘；没有读取、请求或扫描GitHub Secrets/configured production values。

R12 artifact zip SHA-256为 `61d9511461eb619b5b0c7ea90b6d7db4b545d7799b6709c198953f613dbc0151`，logs zip SHA-256为 `0d9e1aa9fc5925e60dca7d7b1765d7a434657ead3c1f5f9024d2ac5c51a6b20c`。Required `init-pytest-junit.xml`、`r11-pytest-junit.xml`、`source-hashes.json`、`versions.txt`与`environment-names.txt`均存在。

## Positive Evidence

- R12 init gate: `9 passed / 9`，包括真实redirected stdin secret owner消费、setx round-trip、registry exact cleanup与其余filesystem/init nodes。`WIN4-RW-F02`得到真实Windows positive closure evidence。
- R11 capability step: PASS。
- Standalone R11: non-POSIX run key、adversarial argv与parser action均PASS；真实upload进程在失败断言前已经 `execution.returncode == 0`。
- R12 embedded R11: adversarial argv PASS；真实upload同样在失败断言前完成process exit、company meta、唯一filing id、snapshot identity/source kind与nonempty descriptors。
- Standalone R11 artifact保留generated script、recorder oracle、source input、published company/source tree、JUnit/stdout/stderr；artifact zip SHA-256 `238d0fb901da6e28366c0737d0ac161e551b374cf231c9c545696b32b471a489`，logs zip SHA-256 `d7fe339ad8762a3dc14272e35f17823a374d5652a9200d75cfe3578dc168451c`。

## Accepted Finding

### WIN4-RW-RF01 — test consumer错误拥有Fins primary-document选择

- Severity: HIGH（remote release-gate blocker；不是production upload defect）
- Owner: `tests/cli/test_upload_filings_from_command.py::test_windows_generated_script_runs_real_cli_into_temp_storage`
- Exact failure: standalone R11为 `3 passed, 1 failed`；R12 embedded R11为 `1 passed, 1 failed`。两处唯一失败均是 `assert snapshot.primary_filename == source_path.name`。
- Direct owner evidence: 同一published source meta明确包含原始HTML与Docling JSON两个descriptor，并由Fins upload owner把 `primary_document`设为生成的 `_docling.json`。`dayu/fins/pipelines/docling_upload_service.py`选择并发布该primary；`FsSourceDocumentRepository.read_source_snapshot()`只投影Fins持久化owner truth。真实artifact中原始HTML与Docling JSON均存在且各自hash完整。
- Root cause: amended plan §13.2.1错误把“本次原始source已发布”与“Fins选择哪个descriptor为primary”合并。CLI test只应消费public snapshot，不应把raw source basename强加为Fins primary。
- Required correction: 保留snapshot identity/source kind/nonempty descriptors与“primary精确命中descriptor”断言；把raw source publication证明改为public descriptor中exact source basename唯一存在且其public SHA-256等于本次fixture bytes SHA-256。不得硬编码Docling filename为新expected primary，不得读取raw meta/private path，不得修改Fins production/storage contract。

## Finding Ledger

| Finding | Status | Fix boundary |
| --- | --- | --- |
| `WIN4-RW-RF01` | ACCEPTED / OPEN | plan correction，然后one-test implementation/review/fix/re-review |
| `WIN4-RW-F02` | POSITIVE REMOTE EVIDENCE / closure pending clean aggregate rerun | no code action |
| R12 canary | PASS | no code action |
| R11/R12 overall | FAIL | 由RF01传播；不得复用为final closure |

没有production Fins defect、secret leak、unified authorization需求、deferred issue实现或新的产品裁决问题。

## Next Gate

AgentCodex只修正final plan中WIN4-RW-S1 success oracle：删除source basename必须等于primary的错误所有权，加入public source descriptor exact name/hash证明，并更新remote matrix/negative cases/stop conditions与completion wording。先经双路完整plan review、fix、re-review和accepted plan commit，再实现one-test fix。未经review不得直接改test。
