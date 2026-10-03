# UM-O12-F01 plan fix5：PR4 findings 收口记录

- RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol
- CANARY=gpt-6-sol-f20ee392
- 工作区：`/private/tmp/dayu-upload-o12`；读码 HEAD：`8d8d494fbbce0052372fb1b42097c9f7222cfa28`。
- 修订对象：`docs/gateflow/upload-material-o12-company-plan-20260929.md`（fix5 SHA-256 `48e0598bd8c949e7257b6fd6c6a03adbdca31b0def2d680d4b0cea93f7ed5e60`）；本文件仅记录计划修订与直接代码证据，不是实施、测试通过、总控裁决或下一 gate 放行。
- 依据：`docs/gateflow/upload-material-o12-plan-review-adjudication-20260929.md` 最新“第四修订版双路复审与待修清单”；Kimi `docs/reviews/plan-review-20260929-094058-o12-rereview4-kimi.md`；MiMo `docs/reviews/plan-review-20260929-094433-o12-rereview4-mimo.md`。既有评审与总控裁决未修改。

## 动机与 owner 核对

四项 finding 均由当前 HEAD 的直接路径支撑，属于计划契约缺口，严重性按总控登记为 F1 中、F2/F3/F4 低。修复范围只在 plan 文字和未来实施白名单/验证矩阵，不新增已接受 O34/O13 之外的产品行为。公司名称 freshness 的 owner 仍是 `resolve_upload_company_meta_decision`；material 同版快照及 guarded comparison 归 storage；公开失败原因归 `upload_failure.py`；CLI 只渲染已给出的 reason；job terminal 归 upload runtime 的 job catch。

| 登记项 | 当前 owner 直接证据 | fix5 对计划的修订 | 未来回归锚点 |
| --- | --- | --- | --- |
| O12-PR4-F1 | `dayu/fins/upload_failure.py:264-271` 将 `CompanyMetaConcurrentUpdateError` 全局归 `STORAGE_IO`；`dayu/fins/domain/company_meta_contract.py:221-252` 的 merge 可抛该异常，filing/material 均用公司提交；`dayu/fins/pipelines/filing_upload_publication.py` 用相同公司决策。 | 在 failure owner 定义 material 专属语境映射入口：material 的该异常和 storage guarded conflict 使用 material `source_publication_conflict` 构造器，filing 的共享 mapper 分支、`storage_io` code/message 保持原样；typed `FinsUploadFailureError.failure` 优先；两市场 workflow、direct、job 消费同源 reason。不可全局改共享异常分支。 | material 公司 merge 抛该异常仍为 `storage/source_publication_conflict`；filing 公司 merge 同异常仍为 `storage/storage_io` 及原 message/retry_hint；alias 双冲突仍为 `ticker_alias_conflict`。`test_upload_failure.py` 与 `test_filing_upload_publication.py` 双端锁定。 |
| O12-PR4-F2 | `dayu/cli/commands/fins.py:204-207` 的 `FinsUploadPrevalidationError` catch 把日志和错误行都写死为 `upload_filing`，而同函数其它 usage catch 已使用 `args.command_name`。 | CLI catch 的日志命令名和 `dayu-cli ...:` 前缀均取 `args.command_name`；保留 `exc.failure.message` 与 `EXIT_FAILURE`，不在 CLI 重判 integrity。 | `tests/cli/test_fins_commands.py` hermetic 覆盖 material UNSAFE/可信 REPAIR_REQUIRED 的实际 `upload_material`、stdout/stderr、exit；filing 名称回归；真实 CLI 补跑记录双流与退出。 |
| O12-PR4-F3 | `dayu/fins/ingestion_runtime.py:5052` 的 upload job 泛异常调用 `_save_failed_from_exception`，同函数也由 download job `:4913/:4960` 调用，`:5986-6004` 只存 message；upload 正常失败 `:5024-5028` 已存 typed 双摘要。 | typed 构造与同一 terminal 保存放在 `_run_upload_job` 的异常收口；按 filing/material 语境从 failure owner 取得 reason，`failure_summary` 和 `result_summary.failure` 同源。共享 message-only `_save_failed_from_exception` 保留给 preprocess/download，download 不引入 upload failure code。 | upload job 异常双摘要 `kind/code/message/retry_hint` 相等，direct/observation 同源；download job 泛异常的 message-only/空摘要及 terminal disposition 不漂移。post-commit 不确定性单列，不由摘要计数推断 manifest。 |
| O12-PR4-F4 | `rg` 核对旧 `stage_company_meta_for_upload` 只有 SEC/CN material 两处生产调用、`upload_company_meta.py` 的函数/导出及两处测试引用；其专属 `_load_existing_company_meta` 与 `Sequence` import 亦会失用。 | 将 `dayu/fins/pipelines/upload_company_meta.py` 加入未来实施白名单，删旧函数、导出及失用私有 helper/import；`test_company_identity_storage_contract.py` 与 `test_sec_pipeline_upload_filing_stream.py` 改用纯 decision + `stage_upload_company_meta_decision` 或仓储直写夹具，不保留旧读/判/写 wrapper。 | 全仓 `rg` 无旧 helper 引用；跨进程 alias 冲突与非法 alias 零写两条 owner 行为继续成立。 |

## Kimi OQ 的最小形状

1. `MaterialUploadAdmission` 含必需的规范化 request、canonical ticker、双 ID、resolved action、同版 observed state、公司 typed decision、`file_selection: FinsUploadMaterialFiles`。静态校验一次构造且校验 selection；delete 为空，upsert 保序；后续 `prepare_upload` 消费原对象。`dayu/fins/upload_format_contract.py:455-523` 已有该不可变 selection，SEC/CN 当前在 `UPLOAD_STARTED` 前各自重建，故 carry 能消除重复选择而不发明新角色语义。
2. `FinsUploadRunner`、production runner、SEC/CN/HK facade 与底层 material workflow 的执行签名必传 `MaterialUploadAdmission`。runtime 三入口给它；独立公开 raw 入口在首事件前调用共享 initial helper 得到它，再调用同一必传执行链。无 `None`、raw kwargs 双签名或执行中补读。`dayu/fins/ingestion_runtime.py:4714-4748` 当前 material 只返回 normalized raw request；SEC/CN 的后置读/判点在 `sec_upload_workflow.py:475-525`、`cn_pipeline.py:1091-1141`，所以这个边界需要显式迁移。
3. storage 公共协议 `repository_protocols.py` 定义一个 `MaterialUploadPublishedStateConflictError`；company/source 两种 batch-scoped expected-state 比较由 storage core 在 ticker publication guard 内抛此 typed 异常，facade 透传，Fins material 映射为既有 public `source_publication_conflict`。该异常不承载 raw meta/path/string reason，也不用既有只代表公司 merge 的 `CompanyMetaConcurrentUpdateError` 充当 source 漂移类型。现有 `_fs_storage_infra.py` 持有 batch/guard/commit，`repository_protocols.py` 已是 typed storage contract owner。

## 已接受边界与待验证项

- O34：合法公司先独立 company batch commit；转换失败/取消或材料 guarded conflict 后公司事实可留。材料 manifest 与 source 同一材料 batch 成功提交后才报告材料 `ok`；post-commit 释放异常不倒推零发布。
- O13：COMPLETE tombstone 保留全量可信 meta/revision；相同指纹恢复保留旧 ID/版本，不同指纹按既有规则递增；两者保留首次时间并清删除态。版本计算 owner 仍为 `docling_upload_service.py:_resolve_document_version`。
- O05/O16 静态拒绝先于状态读，O14/O15 目标状态条件先于公司缺名；本次未实施这些 work unit。
- 计划修订待同新版 Kimi/MiMo 双路有效 re-review。此轮未改产品代码、测试或 README，未运行产品 pytest/pyright；未来实施 gate 依 plan 环境预检及 15 文件测试/pyright/逐文件 coverage。此处的测试条目是验收要求，不能称已通过。

## 本次文本验证

- 文本/白名单脚本核对四项 finding、三个 typed 形状、换行与尾随空白、未来实施白名单去重/存在性：通过；共 31 个未来实施路径，其中三个明确标为新增，旧 helper owner 文件与两处迁移测试均在表内。计划 SHA 与本记录所列一致。
- `git diff --check`：exit 0；目标两份文档当前未跟踪，故此命令只检查 tracked diff。文本脚本已单独检查这两份未跟踪文档的尾随空白与换行。`git diff --name-only` 与 cached 结果均空，未修改 tracked 产品文件。
- 首次文本/白名单脚本：exit 1，原因是 plan 首页把四项编号合写、脚本要求逐项出现；已在各修订段落加逐项标签并重跑 exit 0。首次工具编排 JavaScript 亦因括号语法错误未执行任何内层命令；随后重新调用成功。
