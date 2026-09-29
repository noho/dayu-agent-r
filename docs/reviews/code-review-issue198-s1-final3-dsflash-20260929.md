RUNTIME/PROVIDER/MODEL: claude/ds-flash/deepseek-flash[1m]
CANARY=ds-flash-4d0d85f8

# Code Review：#198 S1 final3（ds-flash 备份路，F2/F3 修复后同 SHA 修复性复审）

## Scope 与锁

- Mode: current changes（只审锁定的精确 14 文件 S1 切片；其它 dirty WU 排除，不从其 hunk 反推 S1 语义）
- Workspace: `/Users/leo/workspace/dayu-agent-r`（绝对主工作区）；Branch: `codex/upload-material-oracle`
- HEAD: `47a9cb64e63780deb568a9e2c6fdd0120441cf2f`（审查开始实测一次；本轮未提交、未改动任何被审文件，结束时 `git status --porcelain -- <14 文件>` 仍全部为 ` M`）
- Diff digest：按 `docs/gateflow/issue-198-s1-code-review-f2f3-fix-20260929.md` 记录的有序 14 文件执行 `git diff --binary -- <14 文件> | shasum -a 256` = `f1e1a91557cda273c5d0b77900920381727322a8edea69d6061cda27f0f6bd21`，与任务给定值逐字一致；本轮开始时与全部命令执行完毕后各复算一次，两次一致
- Diff stat: 14 files changed, 2163 insertions(+), 65 deletions(-)
- Included（14 文件白名单，顺序与锁命令一致）：`README.md`、`dayu/cli/output.py`、`dayu/fins/README.md`、`dayu/fins/direct_events.py`、`dayu/fins/ingestion_runtime.py`、`dayu/fins/pipelines/cn_download_workflow.py`、`dayu/fins/pipelines/cn_pipeline.py`、`dayu/service/fins_wait_adapter.py`、`tests/README.md`、`tests/cli/test_output.py`、`tests/fins/test_cn_download_runtime.py`、`tests/fins/test_cn_download_workflow.py`、`tests/fins/test_fins_ingestion_runtime.py`、`tests/service/test_fins_wait_adapter.py`
- Excluded：`dayu/fins/storage/_fs_source_integrity.py`、`tests/fins/test_fins_storage_atomicity.py`（点号元数据独立 WU；F2 用例注入的是**非点号** `foreign-post-repair.bin`，不依赖该 WU 的忽略语义）、`docs/gateflow/*` 队列/序列文档、既有 `docs/reviews/*`。三份 README 各含 1 行点号元数据句，属 adjudication MiMo F5 已登记的分行 staging 事项，本 review 只审其中 S1 句
- 对齐材料（本轮实读）：`AGENTS.md`、accepted plan `docs/gateflow/issue-198-download-failure-projection-plan-20260928.md`（第 41–63 行 S1 正文，含第 57 行同请求重跑要求）、`docs/gateflow/issue-198-s1-implementation-20260929.md`、`docs/gateflow/issue-198-s1-code-review-adjudication-20260928.md`（含 F2/F3 裁决与三次 ds-flash 轮次记录）、`docs/gateflow/issue-198-s1-code-review-f2f3-fix-20260929.md`、上轮同 SHA review `docs/reviews/code-review-issue198-s1-final2-dsflash-20260929.md`、`docs/gateflow/issue-198-s1-cninfo-single-day-evidence-20260929.md`
- Parallel review coverage：无。按任务约束未派发任何子 Agent；全部读码、复跑、证据复核由主 reviewer 完成
- 本轮协议：不执行故意失败的 pytest，不执行无匹配 rg/glob；反例只用静态读码与既有正向测试证明；确需无匹配检索时以 `|| true` 收口并显式标注语义

## 命令与结果披露（全部 exit0）

| 命令 | 结果 |
| --- | --- |
| `git rev-parse HEAD` | `47a9cb64e63780deb568a9e2c6fdd0120441cf2f`，exit0 |
| 14 文件 `git diff --binary` + `shasum -a 256`（开始时、收尾时各一次） | 两次均为 `f1e1a915…f6bd21`，exit0 |
| `git diff --stat -- <14 文件>` | 14 files changed, 2163 insertions(+), 65 deletions(-)，exit0 |
| `git diff --check -- <14 文件>` | 无输出，exit0 |
| `pytest -k post_repair_abort_then_same_request tests/fins/test_cn_download_runtime.py -q` | `2 passed, 38 deselected, 3 warnings`（edgartools 第三方弃用），exit0 |
| 受影响八文件 suite（`tests/runtime/test_log.py`、`tests/fins/test_fins_ingestion_runtime.py`、`tests/fins/test_cn_download_workflow.py`、`tests/fins/test_cn_download_runtime.py`、`tests/cli/test_output.py`、`tests/cli/test_fins_commands.py`、`tests/service/test_fins_wait_adapter.py`、`tests/service/test_fins_direct.py`） | `846 passed, 3 warnings`，exit0 |
| `python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations`，exit0 |
| `stat` 14 文件 mtime | `cn_pipeline.py` 19:08:03、`test_cn_download_runtime.py` 19:09:43，其余 09:53–10:24，exit0 |
| `rg -n "_CN_TERMINAL_INTEGRITY_FAILED" dayu/ tests/ \|\| true` | 无匹配；语义：旧重复常量已从产品与测试代码彻底移除（`\|\| true` 只为保持命令 exit0），exit0 |
| `rg -n "CnDownloadIntegrityAbort\|_INTEGRITY_FAILED_STATUS" dayu/ --glob '*.py'` | 仅 workflow 定义/产出与 `cn_pipeline.py:59/60/1387/1472` 消费，exit0 |
| `rg -n "integrity_failed" dayu/ tests/` | 产品仅 `cn_download_workflow.py:54/558` + `cn_pipeline.py:59/1472`；测试为独立字面量钉点（`test_cn_download_workflow.py:2775/2879`、`test_cn_download_runtime.py:861/877`），exit0 |
| `rg -n "issue198-foreign-root\|baseline.log" <typed-failure.stdout/.stderr> \|\| echo no-match` | 无匹配，输出 `leak_check: no foreign basename or log path in typed-failure streams (rg no-match)`，exit0 |
| 7 个留档 CLI 原始流的 `shasum -a 256` | 与证据文档逐字一致（见下节），exit0 |
| `rg -n "classification=\|reason_code=\|retry_hint=" typed-failure.stderr`、`rg -n "discovered=" baseline.stdout`、`rg -n "provider_page_total" 两个探针 stdout`、`head -c 600 readback.stdout` | 内容实读见下节，exit0 |

除上表外本轮无其它 shell 命令；无任何非零退出，无需披露的异常命令。

## F2 复核：同请求恢复（真实 FS + 真实 adapter/runtime）

**被测用例**：`tests/fins/test_cn_download_runtime.py:1677` 起（direct/job 参数化到 `:1873`）。

**独立读码结论（逐句读产品代码，不读断言转述）**

1. 真实链：`_build_runtime_with_cn_hk_adapters` 装配真实 `FsSourceDocumentRepository`/`FsBatchingRepository` 与生产 `CnDownloadAdapter`；discovery/transport/converter 是确定性 fake（外部 provider，允许）。`request`（`:1697`）在中止帧与重跑帧共用同一对象。
2. 中止帧确为 post-repair 路径：preflight 首次枚举在 `cn_download_workflow.py:261`，注入点（`:1785`）只在第 2 次真实枚举前写外来文件，该次即 `:397` 的 post-repair 枚举；抛出的是真实 storage typed `SourceIntegrityPreflightError`（非测试伪造），经 `:403` typed catch 转 `_integrity_abort`（`:533`）。
3. 中止帧与计划第 51 行计数口径一致：`filings` 只含已确认的首候选终态行（`:1706-1708` 修好的来源），未开始的第二候选不计数、不造行；测试断言 `discovered=downloaded=1`、`failed=0`、`len(calls)==2`、`downloaded_sources==["cn-runtime-a1"]`、第二候选 identity 目录不存在、公司 meta 与 PDF 旧字节保持。
4. 重跑只清除唯一外来文件（`:1836`），同一 request 再走 `runtime.download` / `runtime.start_download`；direct 真实行序 `[(首候选,"skipped"), (第二候选,"downloaded")]`、job `written_document_ids==[second_id]`，计数 `(1,1,0,0)`，`downloaded_sources==["cn-runtime-b2"]`，两份来源 meta 可由仓储读回、真实枚举均 `COMPLETE`。`skipped` 只可能来自单 filing 的真实 per-document `COMPLETE` 分类，`downloaded` 行的 locator 必须经 `source_repository.get_source_document_locator` 成功（`cn_pipeline.py:1565-1581`），因此“已处理”声明受 storage owner 强制，测试未在测试侧重算 counts/IDs。
5. 无重复行/重复计数（本轮新增静态核对）：单 filing 流在 Phase B typed 中止时**不先产出** `FILING_FAILED` 行结果，因此 `:344-357` 的补行不会与循环内的 `filings.append` 叠加。既有正向用例 `test_cn_phase_b_real_preflight_aborts_with_confirmed_prior_filing`（`tests/fins/test_cn_download_workflow.py:2689` 起）断言 rows 恰为 `["downloaded","failed"]` 两行、`FILING_FAILED` 事件恰 1 次、`commit_calls==2/rollback_calls==1`，与该推断互证。
6. abort 快照通过 runtime 身份校验（本轮新增推断链）：`ingestion_runtime.py` 的 `_execute_download_request` 在 adapter 边界对 `FinsSourceDownloadAdapterFailure.persisted_summary` 执行 `_bounded_download_summary`（`:8057`，实为精确类型断言并原样返回实例）与 `_validate_download_summary_request_identity`（`:8077`），失败会以 ValueError 投影为 EXECUTION 且无 reason；direct 中止帧断言 `reason_code is UNSAFE_PUBLICATION` 成立 ⟹ 该 summary 已通过身份校验，且下游消费的是同一实例（不存在“验证一份、消费另一份”）。
7. 反证方式说明：本轮协议禁止故意失败测试，故未复跑注入反证；上轮 `code-review-issue198-s1-final2-dsflash-20260929.md` 中两次注入（COMPLETE 一律降级、重跑阶段把首候选改为 REPAIR_REQUIRED）的证据按总控“内容可用旁证”口径参考，本轮以静态读码 + 既有正向用例复核同一承重点（`:1866` 传输调用断言仍是该用例的承重项）。

**结论**：F2 在真实 owner 链上成立，未发现伪造公共结果、测试侧重算或把上次未处理候选计为已处理；中止帧与重跑帧的计数、行序、字节与完整性证据自洽。

## F3 复核：唯一状态真源与依赖方向

- 全仓静态核对：生产代码 `integrity_failed` 字面量只存在于 `cn_download_workflow.py:54`（`_INTEGRITY_FAILED_STATUS` 定义）与 `:558`（产出快照）；`cn_pipeline.py:59` 同向导入该私有常量、`:1472` 只做相等校验。旧 `_CN_TERMINAL_INTEGRITY_FAILED` 在 `dayu/` 与 `tests/` 均无匹配（见命令表，`|| true` 仅为保持 exit0）。
- 依赖方向：`cn_pipeline.py:58-62` 从 `cn_download_workflow` 导入的是既有方向的三个符号（本次新增的只有私有状态常量）；`rg "CnDownloadIntegrityAbort|_INTEGRITY_FAILED_STATUS" dayu/` 显示反向无导入、无循环；未新增兼容 re-export / wrapper。
- 异常层级（本轮显式核对）：`SourceIntegrityPreflightError` 与 `SourceIntegrityRevisionConflictError` 均直接继承 `RuntimeError`（`dayu/fins/storage/source_integrity.py:191/211`），互不为子类，因此 `cn_download_workflow.py:344` 的单 filing `except SourceIntegrityPreflightError` 不会误吞 mid-filing revision conflict（该路径仍由宽 `except Exception` 投影为 `filing_execution_failed`，与 `test_cn_mid_filing_revision_conflict_injection_remains_ordinary_failure` 的独立断言一致）；`_classify_direct_error` 的 `isinstance(exc, OSError | SourceIntegrityPreflightError)` 同理不会把 revision conflict 归入 STORAGE。
- 严格性未回退：`_summary_from_pipeline_result`（`:1444-1447`）仍只接受 `ok/cancelled`，`_summary_from_integrity_abort`（`:1471-1473`）只接受该私有状态，二者共用 `_project_cn_pipeline_summary`（`:1477`）纯投影；`test_cn_integrity_snapshot_has_separate_strict_projection_entry`（`tests/fins/test_cn_download_runtime.py:839`）用独立字面量双向拒绝（普通入口拒 `integrity_failed`、失败入口拒 `ok`、坏 row 仍抛）。

**结论**：F3 修复在 owner boundary 上成立，同一状态事实只有一处定义，消费方未复制字面量，也未引入反向依赖。

## 旧 finding 无回退核对

| 已接受项（来源轮次） | 本轮独立证据 | 状态 |
| --- | --- | --- |
| MiMo F1 / 单 filing typed preflight 保真 | `cn_download_workflow.py:344-369` typed catch；`test_cn_phase_b_real_preflight_aborts_with_confirmed_prior_filing` | 无回退 |
| MiMo F2 / 公共 enum 双向全集 | `tests/fins/test_fins_ingestion_runtime.py` 新增用例断言键/值集合分别等于两个 enum 全集且 `.value` 一致（`:6157` 起） | 无回退 |
| MiMo F3 / CLI `reason_code=` | `dayu/cli/output.py:486/493`；`tests/cli/test_output.py` 同时钉 `reason_code="unsafe_publication"` 与文档行 `reason="来源暂时不可用"` | 无回退 |
| Kimi F1 / MiMo F4 / `reason_code=None` 占位 | `tests/cli/test_output.py` 新增 EXECUTION 帧断言 `classification="execution"`、`reason_code="-"` | 无回退 |
| Kimi F1 / typed 零候选 direct+job 同源 | `ingestion_runtime.py:4351`（direct）与 `:5013` 附近（job）均用 `_empty_download_summary_from_request(FAILED)`；`test_initial_typed_download_job_saves_structured_zero_summary_and_safe_message` 断言与 direct 同一消息 | 无回退 |
| Kimi F2 / 私有 adapter failure 与单点 unwrap | `FinsSourceDownloadAdapterFailure`（`:587`）持有 `cause`；`_download_exception_cause`（`:6916` 附近）在 `_classify_direct_error` 与 `_download_public_failure_from_exception` 各解一次，无 `__cause__` 遍历/字符串解析 | 无回退 |
| Kimi F3 / 纯投影 helper 抽取 | `cn_pipeline.py:1477-1518`，两入口先验 status 再复用 | 无回退 |
| Kimi F4 / wait `scope_note` 逐字 | `fins_wait_adapter.py:592` 常量、`:618` 投影；测试用独立字面量逐字断言字段名与值 | 无回退 |
| MiMo 第四/七次 / `FinsResultSummary` 放宽与负例 | `direct_events.py:677-690`：FAILURE 仅拒绝 `CANCELLED` disposition；`test_failed_operation_accepts_only_valid_processed_document_dispositions` 覆盖 FAILED/PARTIAL_FAILURE/SUCCEEDED 正例与缺 failure、SUCCESS 混用、CANCELLED disposition 负例 | 无回退 |
| K-F1 / fresh ticker 非空 company intent | `test_initial_company_commit_real_preswap_preflight_keeps_zero_request_summary` 真实 `commit_batch→_validate_complete_source_tree` | 无回退 |
| MiMo 第七次 F2 / typed job 二次保存 WARN 固定标识 | `ingestion_runtime.py` `_save_typed_download_failure` 只 `_LOGGER.warning("fins.download.typed_failed_record_save_failed")`；测试断言无 `exc_info`/`error_type`/类名/秘密且 record 仍 `RUNNING`、摘要 `{}` | 无回退 |
| MiMo code review F1 / revision conflict runtime 投影 | `test_cn_post_repair_real_second_source_revision_conflict_preserves_public_summary`（direct/job） | 无回退 |
| ds-flash F2（上轮）/ 同请求重跑 | 本文件 F2 段 | **已修复** |
| ds-flash L1（上轮）/ 双处私有常量 | 本文件 F3 段 | **已修复** |
| 旧测试未被弱化（本轮新增核对） | `git diff -U0`：`tests/fins/test_cn_download_runtime.py` 全文件仅删除 1 行（`from dataclasses import dataclass, field` 的行内改名），`cn_pipeline.py` 仅删除旧 import 与旧调用形状；无既有断言被删除或放宽 | 无回退 |
| 取消控制流保持 | 受影响八文件 suite 全绿（846 passed），无 test 被 skip 或 deselected 于常规运行 | 无回退 |

## CLI 三日证据复核（只读复算，不改留档）

7 个原始流 SHA-256 现场复算与证据文档逐字一致：单日探针 `f5c31806…`、三天探针 `b5a0c53d…`、baseline stdout `8cee933d…`、baseline stderr `e3b0c442…`（空文件）、typed-failure stdout `0804026d…`、typed-failure stderr `5349d095…`、readback stdout `b4980068…`。

内容实读：

- 单日探针 JSON：`provider_page_total=0`、`raw=[]`、`selected=[]`；三天探针 JSON：`provider_page_total=2`，两条均为 `2025-03-28`（摘要 `1222951198` + 全文 `1222951181`），产品只选中全文。
- baseline stdout 第 236 行：`discovered=1 downloaded=1 skipped=0 rejected=0 failed=0 omitted=0`。
- typed-failure stderr 第 3 行：`classification="storage" source="cninfo" transport="-" reason_code="unsafe_publication" retry_hint="请检查并修复工作区来源状态后重试；重复下载不会自行修复。"`；外来文件名与日志路径在两个流中均无匹配。
- readback stdout：唯一 ID `fil_cn_95d26c810c326725ece2cc478a6a4c012fe1c9ce`、`integrity.status="complete"`、`reasons=[]`，并有真实公司/来源 meta。

界限判断（与上轮一致，不因本轮复算而放宽）：该证据走同一条 CLI + whole-kind typed + 公共投影路径，足以证明 S1 的 typed 失败投影与 reason 显示；它**不是**计划第 57 行那条单日命令，`fins-cninfo-single-day-discovery-window` 仍是独立 work unit。本沙箱无外网，无法独立重跑真实 provider，只能复核留档原始流。

## Findings

无阻断项。F2/F3 修复成立，未发现新的 correctness defect。以下为按既有格式登记的低级/信息项，均不阻断 S1 code gate：

### N1（low, info；中止帧行数断言依赖契约蕴含而非显式断言）— 沿用上轮

- 位置：`tests/fins/test_cn_download_runtime.py:1817`（只索引 `document_rows[0]`）。
- 本轮复核依据：`FinsDownloadPublicSummary.__post_init__`（`direct_events.py:441-442`）强制 `len(rows) + omitted == discovered`；该帧 `discovered == 1` 且 `:1815` 断言 `downloaded_count == 1`，故行数恰为 1、`omitted == 0`。反例不可达。
- 建议（不阻断）：补 `document_rows == (…)` 全量断言以提升可读性。

### N2（low；job 持久摘要无逐项文档行）— 沿用上轮

- 位置：`dayu/fins/download_contract.py:491-521`（`to_json_summary` 只给 counts + `written_document_ids`（有界 10）+ `omitted_written_document_count`）。
- 真实可达反例：无（不是缺陷）。job 侧 skip 由 `skipped_count=1`、`:1866` 传输只调用第二候选、两份真实来源 `COMPLETE` 联合证明；direct 侧另有逐项行。F2/F3 fix 记录已如实声明该边界。

### N3（low；README 句与其它 WU 行同 hunk）— 沿用上轮

- 位置：`README.md:322-323`、`dayu/fins/README.md:598-599`、`tests/README.md:24-25`。
- 影响与修法：本 14 文件 SHA 内因此各含 1 行非 S1 内容；staging 时须按行拆分（不能用 `git add -p s` 拆相邻新增行），提交前核对 staged patch 只含 S1 句。

### N4（info，新；`cn_download_workflow.__all__` 未声明被跨模块消费的 `CnDownloadIntegrityAbort`）

- 位置：`dayu/fins/pipelines/cn_download_workflow.py:1014`（`__all__ = ["run_cn_download_stream_impl"]`）与 `:59`（类定义）、`:54`（私有状态常量）。
- 现状：同包 `cn_pipeline.py:59-60` 跨模块导入 `CnDownloadIntegrityAbort` 与 `_INTEGRITY_FAILED_STATUS`，两个测试模块也按模块属性访问该异常；`__all__` 只影响 `from … import *`，仓库内无 `import *` 用法，故**无运行时影响**，仅声明与真实跨模块契约不一致。
- 说明：F3 裁决明确选择“同向导入私有状态常量、不扩公共合同”的最小改法，本条不构成对该裁决的反对；若后续要求私有跨模块契约显式化，可在 `__all__` 中列出该异常类型（私有常量按既有惯例可不列）。

### N5（info，新；`CnDownloadIntegrityAbort` 的 message 对 revision conflict 场景为 preflight 文案）

- 位置：`dayu/fins/pipelines/cn_download_workflow.py:59-79`：构造函数无条件 `super().__init__(_INTEGRITY_PREFLIGHT_MESSAGE)`，而其 `cause` 允许 `SourceIntegrityRevisionConflictError`。
- 影响面（本轮静态核对）：全仓唯一 catch 点在 `cn_pipeline.py:1387`，它只用 `exc.cause` 重新包装为 `FinsSourceDownloadAdapterFailure`，abort 的 message 不进入 public RESULT、job record、CLI/wait JSON 或日志；`_download_exception_cause` 只读 `cause` 属性。因此**当前无消费者投影该文案**，不构成 LLM-facing/公开语义泄漏。
- 风险：属未来面向；若新增处理器直接渲染 `str(abort)`，会把 revision conflict 误述为 preflight 失败。建议（不阻断）：message 改为两类原因中立的“下载来源完整性中止”或按 `cause` 分派。

## Residual Risk

- **旧快照不可逐字复算**：`86aa9a2b…` → `f1e1a915…` 的逐字 delta 无留档（未提交、无 stash）；本轮以 fix 记录 + adjudication 自述 + 文件 mtime（仅 `cn_pipeline.py` 19:08:03、`test_cn_download_runtime.py` 19:09:43 落在 19 时段）佐证“本轮只改这两处 + 记录”，非逐字证明。
- **混合工作树**：846 passed / pyright 均在含点号元数据独立 WU dirty 文件的树上运行；S1 新用例注入非点号条目、不依赖该 WU 行为，但纯 14 文件树未单独复跑（与前几轮相同的残余）。
- **调用计数耦合**：多候选用例把“post-repair 前恰两次 `list_source_integrity`”“`len(calls)==2`”锁为合同，未来 owner 调整枚举次数需同步更新注入点（有意的回归锁）。
- **测试调用 storage 私有成员**（`_identity_directory_path`、`_FILING_IDENTITY_NAMESPACE`、`_resolve_active_batch`、仓储实例方法 monkeypatch）：adjudication 已允许（不重算哈希、委托真源），对 storage 内部重构敏感。
- **typed job 二次保存失败后 record 停在 RUNNING**：accepted plan 明确选择“WARN 只诊断、不虚称已保存、不以 `{}` 覆盖原摘要”，测试按此断言 `RUNNING` + `{}`；该边界由计划接受，本 review 只登记未另加修复要求。
- **未覆盖的独立 WU 仍成立**：单日 CNInfo 发现窗口、mid-filing revision conflict 分类（`fins-download-storage-sibling-errors`）、company commit 其它失败（`fins-download-indeterminate-publication-state`）、raw 诊断审计（`fins-other-raw-diagnostics-audit`）均未被本切片声称修复；本 review 未复验 S2、未做真实网络验证。
- **本轮未复跑注入反证**（协议禁止故意失败测试）：F2 的敏感性证据沿用上轮已披露记录与既有正向用例的承重断言，不等同于本轮新做的注入实验。

## 结论

**pass-with-risks**（无阻断项；F2/F3 修复在真实 owner 链上成立，未发现新的 correctness finding）

1. 锁一致：HEAD `47a9cb64…`，14 文件 diff SHA-256 `f1e1a915…f6bd21` 开始与收尾各复算一次、逐字一致；未跨版本混审，未触碰其它 dirty WU，未修改产品/测试/README/plan/adjudication/旧 review。
2. F2 成立：真实 FS 仓储 + 真实 workflow/adapter/runtime 的 direct/job 两入口，同一 request 在清除唯一外来 mutation 后重跑；首候选按真实 per-document `COMPLETE` skip（无传输）、第二候选 `downloaded`（恰一次传输）、计数 `discovered=2/downloaded=1/skipped=1/rejected=failed=0`、durable 字节/meta/COMPLETE 三重读回；中止帧未处理候选不计数也不造行、无重复行、abort 快照通过 runtime 身份校验。
3. F3 成立：`integrity_failed` 唯一真源在 `cn_download_workflow.py:54`，`cn_pipeline.py` 同向消费；旧重复常量在 `dayu/` 与 `tests/` 已无匹配；两异常类型互不继承使 typed catch 不误吞 revision conflict；普通/失败两入口的严格 status 校验未放宽。
4. 旧 finding 无回退：汇聚清单逐条有当前代码/测试证据，本轮以 `git diff -U0` 证明旧测试断言零删除；受影响八文件 846 passed、pyright `0/0/0`、`git diff --check` 均本轮独立复跑通过；七日 CLI 证据 7 个原始流哈希与内容逐字复核一致，其证明界限如实保持（不替代计划单日命令）。
5. 未决/残余：N1–N5 与 Residual Risk 各条；S2、单日发现窗口、sibling 分类等独立 WU 未被本切片声称完成。

## 回传

CANARY=ds-flash-4d0d85f8

Artifact 绝对路径：`/Users/leo/workspace/dayu-agent-r/docs/reviews/code-review-issue198-s1-final3-dsflash-20260929.md`
