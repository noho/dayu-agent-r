# WU-SEMANTIC-OWNERSHIP-01 / R06-S3 Controller validation

## 结论

`PASS / READY_FOR_DUAL_COMPLETE_CUMULATIVE_CODE_REVIEW`

本 gate 只接受 R06-S3 implementation 进入完整累计 R06（S1+S2+S3）双路 code review；它不接受 R06、不创建中间 commit，也不授权 R07、Issue 142/151/175/177/178、统一 tool authorization、push 或 PR。

AgentCodex implementation artifact 为 `docs/reviews/wu-semantic-ownership-01-r06-s3-implementation-codex.md`。Controller validation finding `R06-S3-CV-F01` 已修复并关闭。

## 独立 owner / scope 复核

Controller 直接检查了 accepted plan §7.3 的 production/test/README 闭集与关键调用图，确认：

- `DefaultFinsRuntime.create`、`CnPipeline`、`SecPipeline` 和 standalone 6-K reconcile 四个真实 composition root 均实例化 `FsBatchingRepository`，并让 batching/source/blob/processed/company/maintenance wrappers 共享同一 repository set/core；
- production mutation 使用 required keyword `batch=`，54 个 production mutation call 与 129 个 test mutation call 的 AST 审计均为 `missing_explicit_batch_keyword=0`；callback 在 invocation-time 接收 caller token，没有 ContextVar、task/thread identity、auto batch 或 source lifecycle facade；
- CN、SEC、Docling producer 均在 batch 外准备下载/转换输入，在短 transaction 内 blob-first 写入并只发布一次 complete source；company、filing、maintenance 和每个 Docling document 的 publication unit 分离；
- rebuild 与 6-K source 更新和既有 processed reprocess marker 使用同一 token；SEC 6-K 不从 published read 猜测尚未提交的 staging source，而从当前有界下载 payload 选择 primary 后再发布；
- commit 前异常/取消只回滚一次；commit 调用开始后 caller 不再二次 rollback；
- production acknowledgement/false-completion producer 扫描为 0。两处显式 `ingest_complete=False` 仅存在于 storage validator negative tests，保留为 owner-level rejection 证据，没有用字面量改写美化扫描；
- README 只更新 `dayu/fins/README.md` 与 `tests/README.md` 的 current contract；根 README、`dayu/README.md` 与设计真源无职责内变化；
- path containment、symlink/escape 拒绝、DNS/peer 校验、resource budgets、atomic replace/fsync、writer/recovery fencing、publication lock、minimal journal 与 crash recovery 均保留；没有实施统一 tool authorization 或 deferred ISSUE。

## Controller validation finding

### R06-S3-CV-F01 — preprocess completion 缺失分支缺少直接测试

初次复核发现 `FinsIngestionRuntime._select_preprocess_documents` 在 S3 最终 scan 中从缺省完成收紧为只接受 `meta.get("ingest_complete") is True`，但当时没有直接覆盖字段缺失分支。finding 成立：storage validator 拥有新 publication 完整性，preprocess selection 仍独立拥有进入预处理集合的资格语义。

AgentCodex 只在 allowlist 内的 `tests/fins/test_fins_ingestion_runtime.py` 增加 owner-level test：两个 source 先经真实 shared-core repository 完整发布，随后测试只损坏其中一个 published meta，删除 `ingest_complete`；直接调用 selection owner 后，返回集合只保留显式完成 source。测试没有启动 mutation transaction、没有放宽 storage validator、没有引入 fake/compatibility shim。

Controller 独立重跑该测试：`1 passed, 3 warnings`。`R06-S3-CV-F01` 关闭。

## 独立验证

Controller 在激活 `.venv` 后独立执行并通过：

| Validation | Result |
| --- | --- |
| R06-S1 focused | `134 passed, 64 deselected, 3 warnings` |
| R06-S2 exact focused | `91 passed, 144 deselected, 3 warnings` |
| R06-S3 13-file matrix + coverage | `319 passed, 1 skipped, 3 warnings` |
| Fins + combined acceptance | `723 passed, 1 skipped, 3 warnings` |
| fresh recovery / concurrent-reader smoke | Agent implementation evidence `10 passed, 97 deselected`；S1 focused 同时覆盖完整 recovery/lock owner matrix |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| cumulative changed Python Ruff | `All checks passed!` |
| full Ruff fingerprint | base `162`、current `152`、`current-only=0`、`base-only=10`；十项均为 accepted plan §10 的 changed-owner 旧 finding 清理 |
| mutation AST scan | production `54`、tests `129`、missing explicit batch `0` |
| production ambient / ack / false-completion scans | `0` |
| `git diff --check` | 通过 |
| staged paths | `0` |

三条 warning 均来自 `edgar` 依赖的既有 deprecation warning；唯一 skip 是可选 Docling integration 环境门控。

## 逐文件 coverage

Controller 用完整 S3 matrix 重新生成 coverage JSON，22 个实际 changed production 文件的 statement line coverage 全部 `>=80%`。最低值为：

- `sec_download_state.py`：119/148，80.41%；
- `cn_download_rebuild.py`：132/164，80.49%；
- `sec_6k_primary_document_repair.py`：148/181，81.77%；
- `cn_download_workflow.py`：195/238，81.93%；
- `sec_download_persistence.py`：100/122，81.97%。

受 `R06-S3-CV-F01` 影响的 `ingestion_runtime.py` 为 1526/1690，90.30%；其余文件范围为 84.05%–100%。没有用 overall、omit、pragma 或 mock-only delegation 代替单文件检查。

## Residual 与下一 gate

R06-S3 当前 correctness residual 为 0；`R06-S3-CV-F01` 已关闭。full Ruff 剩余 152 项逐字段复现 accepted base 且不命中累计 changed paths，不是本 gate 新增或扩散。

下一 gate 仅为 AgentMiMo / AgentDS 对完整累计 S1+S2+S3 tree 的并发 complete code review。所有 accepted review findings 必须交回 AgentCodex 修复并完成双路 re-review 后，R06 complete final tree 才可进入单一 accepted local commit。
