# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-C Plan Fix

## Artifact Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 R3-C`
- Gate: `plan fix`
- Fix owner: `AgentCodex`
- Date: `2026-07-12`
- Status: `pass`
- Plan artifact: `docs/host/wu-semantic-ownership-01-round3-r3-c-fins-storage-atomicity-plan.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-plan-review-controller-adjudication.md`
- Implementation authorization: none；本次只修订plan并记录fix，不修改production code、tests、README、control docs或commit。

## Controller Finding Disposition

| Finding | Status | Plan fix |
| --- | --- | --- |
| `R3-C-PF-01` | fixed | 明确`commit_cn_filing_source_document()`只能在caller-owned active document batch内stage final meta与processed marker；fast-skip与normal-convert call site都不得产生第二个commit owner，并要求同token顺序证明。 |
| `R3-C-PF-02` | fixed | 明确caller只回滚commit前operation exception/cancellation；`commit_batch()`调用开始即把token生命周期交给storage，commit failure只传播、不做invalid-token rollback。 |
| `R3-C-PF-03` | fixed | 写明active-batch `try/finally`、`commit_started`所有权切换、operation/cancellation rollback、双重错误chain及active token期间零yield/await；加入同步`CancelledError`注入断言。 |
| `R3-C-PF-04` | fixed | 把`SWAPPED_TARGET`恢复定义为明确行为反转：`COMMITTED`前删除new target并恢复backup；加入swap与`COMMITTED`之间crash state测试。 |
| `R3-C-PF-05` | fixed | 固定双重错误传播形状：原commit error是primary，rollback error位于`__cause__`，primary带note，journal/backup/staging证据保留；测试按异常对象身份检查两者。 |
| `R3-C-PF-06` | fixed | 确认`DownloadedReportAsset` owner是`dayu/fins/pipelines/cn_download_models.py`；要求全`dayu/fins`与`tests`扫描type、constructor、`.pdf_path`、keyword、fixture、annotation及位置解包。 |
| `R3-C-PF-07` | fixed | 指定owner-level journal/rename helper或按phase/path monkeypatch的failure injection seam；禁止call-count-only mock，并要求真实filesystem state断言。 |
| `R3-C-PF-08` | fixed | 固定snapshot三个字段及`created_at: datetime`；Host复用durable parser，并新增具体`WaitAdapterSnapshotProjectionError`路径，使非法durable token/timestamp在adapter调用前fail closed。 |
| `R3-C-PF-09` | fixed | 把`S1 -> S2 -> S3`改为mandatory串行依赖；禁止S1/S2留下TODO/compatibility过渡；README/docs只在全部production与tests land且slice review accepted后同步。 |
| `R3-C-PF-10` | fixed | 明确包括`COMMITTED`在内的所有journal写入复用atomic JSON + file fsync + parent-directory sync；明确upload acknowledgement在显式batch内只stage、不nested commit。 |

未修复finding数量：`0`。

## Changed Sections In Plan

1. `Artifact Metadata`
   - gate更新为`plan fix`，加入plan-review controller adjudication真源。
2. `Contract And State-Machine Decisions`
   - 扩充batch journal durability、`SWAPPED_TARGET`恢复反转、commit+rollback异常传播。
   - 固定S2 caller token/`try/finally`/cancel contract、CN/HK final-stage helper的caller-batch前置条件，以及upload acknowledgement显式batch行为。
   - 确认`DownloadedReportAsset` type owner与完整影响扫描。
   - 固定Host snapshot字段、timestamp parser、resume-token validation和projection error/backoff路径。
3. `S1 — Storage Identity, Commit Point, And Local Durability`
   - 新增`Per-phase failure injection strategy`，补齐crash state、双错误、journal directory sync断言。
4. `S2 — Single-Document Ingestion Atomicity And Temp-Less CN/HK Assets`
   - 补齐caller-owned batch、token交接、active-batch cancel、两个CN/HK call site和acknowledgement的验证要求。
   - 扩大`DownloadedReportAsset` scan到全`dayu/fins`和`tests`。
5. `S3 — Host Adapter Snapshot And Service-Owned Fins Wait Glue`
   - 把S1/S2前置关系改为mandatory，新增Host projection fail-closed contract和测试断言。
   - 文档同步明确延后到三个production slice及其tests全部land之后。
6. `Slice Count Justification`、`Review And Validation Route`、`Final production-high validation`、`README / Documentation Decisions`
   - 统一强制顺序、全仓asset scan与最终doc sync时点。
7. `Plan Gate Decision`
   - next gate改为MiMo/DS plan re-review。

`Tool-Security Deferred Items`及四类排除项保持存在；本fix没有把upload allowlist/user-file authority、URL/TLS/redirect/SSRF provenance、remote byte budget或LLM-facing security schema变化加入任何实施slice。

## Validation

执行的plan-only检查：

```bash
rg -n '^## Tool-Security Deferred Items$' docs/host/wu-semantic-ownership-01-round3-r3-c-fins-storage-atomicity-plan.md
```

结果：`523:## Tool-Security Deferred Items`。

```bash
rg -n -o 'R3-C-PF-(01|02|03|04|05|06|07|08|09|10)' docs/host/wu-semantic-ownership-01-round3-r3-c-fins-storage-atomicity-plan.md
```

结果：十个marker均存在；首次直接命中分别为PF-10 `:157`、PF-04 `:161`、PF-05 `:162`、PF-02 `:189`、PF-03 `:190`、PF-01 `:191`、PF-06 `:197`、PF-08 `:214`、PF-07 `:253`、PF-09 `:386`。

```bash
git diff --check
```

结果：通过，无whitespace error。由于两个目标artifact当前均为untracked，另以`git diff --no-index --check /dev/null <artifact>`逐文件检查新增文件内容；无whitespace diagnostic（命令因存在预期新增diff返回`1`）。

未运行production tests或pyright：本gate只修改Markdown plan/review artifact，且用户明确禁止实现production code/tests。

## Blocking Questions

无。当前scope item的semantic owner均已在plan中明确；未触发blocked stop condition。

## Fix Gate Decision

- status: `pass`
- fixed findings: `10 / 10`
- remaining unfixed findings: `0`
- blocking questions: `0`
- next gate: MiMo/DS plan re-review
