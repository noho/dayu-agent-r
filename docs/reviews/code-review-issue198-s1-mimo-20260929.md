RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro[1m]
CANARY=mimo-189b8ac5

# Code Review

## Scope

- Mode: current changes（issue #198 S1 14 文件候选 diff 独立深度审查）
- Branch: `codex/upload-material-oracle`
- Base: HEAD `47a9cb64e63780deb568a9e2c6fdd0120441cf2f`（实测 `git rev-parse HEAD` 一致）
- Diff digest: `git diff --binary -- <14 文件> | shasum -a 256` = `f2766de5d4deb8ebfd922854892e575829d578bbd4faa2e03f38e0351239d448`，与任务给定值一致，未触发停止条件
- Output file: `docs/reviews/code-review-issue198-s1-mimo-20260929.md`
- Included scope（14 文件，1904 insertions / 65 deletions）：
  `README.md`、`dayu/cli/output.py`、`dayu/fins/README.md`、`dayu/fins/direct_events.py`、`dayu/fins/ingestion_runtime.py`、`dayu/fins/pipelines/cn_download_workflow.py`、`dayu/fins/pipelines/cn_pipeline.py`、`dayu/service/fins_wait_adapter.py`、`tests/README.md`、`tests/cli/test_output.py`、`tests/fins/test_cn_download_runtime.py`、`tests/fins/test_cn_download_workflow.py`、`tests/fins/test_fins_ingestion_runtime.py`、`tests/service/test_fins_wait_adapter.py`
- Excluded scope: 主工作树其它脏文件（含 `dayu/fins/storage/_fs_source_integrity.py`、`tests/fins/test_fins_storage_atomicity.py` 等点号元数据独立 WU、docs/gateflow 与 docs/reviews 其它 artifact）不在本审查范围，仅在依赖关系处记录风险
- 对齐材料：`AGENTS.md`、accepted plan `docs/gateflow/issue-198-download-failure-projection-plan-20260928.md`（fix10 现行正文）、实施 artifact `docs/gateflow/issue-198-s1-implementation-20260929.md`、`docs/gateflow/issue-198-s1-code-review-adjudication-20260928.md`
- Parallel review coverage: 无。按任务约束未派发子 Agent，全部走读由主 reviewer 逐路径完成
- 复跑验证（独立执行，非引用总控记录）：
  - `python -m pytest tests/runtime/test_log.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/cli/test_output.py tests/cli/test_fins_commands.py tests/service/test_fins_wait_adapter.py tests/service/test_fins_direct.py -q` → **844 passed, 3 warnings**（edgartools 弃用警告）
  - `python -m pyright dayu/ tests/ utils/` → **0 errors, 0 warnings, 0 informations**

## Findings

### 1-未修复-中-revision conflict typed 中止的 Fins runtime 投影缺少计划要求的回归锁定
- **入口/函数**: `CnDownloadAdapter.download`（`dayu/fins/pipelines/cn_pipeline.py:1342`）抛出的 `FinsSourceDownloadAdapterFailure(cause=SourceIntegrityRevisionConflictError, persisted_summary=…)`，经 `FinsIngestionRuntime._run_direct_stream_producer`（`dayu/fins/ingestion_runtime.py:4338`）与 `_run_download_job` → `_save_typed_download_failure`（`dayu/fins/ingestion_runtime.py:4994`）投影为公共失败。
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:6986-6992`（`_download_public_failure_from_exception` 的 EXECUTION 兜底分支）、`dayu/fins/ingestion_runtime.py:4994-5035`（job typed catch）；对照 accepted plan `docs/gateflow/issue-198-download-failure-projection-plan-20260928.md:57` 的测试分工“私有 adapter failure 另断言其原 cause 身份不变、preflight 四值仍由 Fins 同一映射投影、**revision conflict 沿既有分类**、非 typed 不获 reason”。
- **输入场景**: repair 已确认发布后，post-repair 分类返回 `SelectedSourceRepairRequired`，workflow 显式抛 `SourceIntegrityRevisionConflictError`（`dayu/fins/pipelines/cn_download_workflow.py:402`）并以已确认 filings 快照构造 `CnDownloadIntegrityAbort`；adapter 将其包为 `FinsSourceDownloadAdapterFailure` 后，direct/job 需把它投影为既有 `EXECUTION` 分类、`reason_code=None` 且保留已确认文档摘要。
- **实际分支**: 代码走读确认当前实现正确——`_download_exception_cause` 单点解包后，`SourceIntegrityRevisionConflictError` 既非 `FinsDownloadProviderError` 也非 `SourceIntegrityPreflightError`/`OSError`，落入 `ingestion_runtime.py:6986` 的 EXECUTION 兜底；`_save_typed_download_failure`/producer 均消费 `exc.persisted_summary` 保快照。但该组合（EXECUTION + 无 reason_code + 守恒摘要）在 runtime 层**没有任何测试锁定**。
- **预期行为**: 按 accepted plan S1 测试分工，direct 与 job 两个入口都要断言 revision conflict 沿既有 EXECUTION 分类、不获公开 reason、快照计数守恒。
- **实际行为**: 全部 runtime 层 typed 测试（`tests/fins/test_cn_download_runtime.py` 的 `test_initial_company_commit_real_preswap_preflight_keeps_zero_request_summary`、`test_cn_real_phase_b_abort_keeps_published_document_in_result_and_job`、`test_hk_real_commit_preflight_uses_same_partial_failure_route`、`test_cn_post_repair_real_preflight_has_successful_document_scope_and_failed_operation`、`test_cn_real_initial_whole_kind_preflight_uses_request_zero_summary`，及 `tests/fins/test_fins_ingestion_runtime.py` 的四 reason 参数化）只覆盖 `SourceIntegrityPreflightError`（均为 `UNSAFE_PUBLICATION` 或四值 reason）。唯一触及 revision conflict 的 `tests/fins/test_cn_download_workflow.py:3114 test_cn_post_repair_real_second_selected_source_conflict_preserves_first_row` 只断言 workflow 层 `abort.cause is SourceIntegrityRevisionConflictError` 与 rows 保留，不经 `CnDownloadAdapter → FinsSourceDownloadAdapterFailure → FinsIngestionRuntime` 的 direct/job 投影。全仓 grep 确认没有任何测试构造 `FinsSourceDownloadAdapterFailure` 或断言该 cause 的公共分类。wait 测试中 `revision_failure`（`tests/service/test_fins_wait_adapter.py:523-531`）只是手工构造 EXECUTION JSON 形状，不覆盖异常→分类映射。
- **直接证据**: `grep -rn "SourceIntegrityRevisionConflictError|revision" tests/fins/test_fins_ingestion_runtime.py tests/fins/test_cn_download_runtime.py` 零命中；`grep -rn "FinsSourceDownloadAdapterFailure" tests/` 仅命中 wait 测试函数名。`ingestion_runtime.py:6986-6992` 兜底分支与 `:4344`/`:5022-5028` 的 `persisted_summary` 消费点是该语义的唯一 owner 路径。
- **影响**: 当前行为正确，但回归面裸奔。后续重构若在 `_download_public_failure_from_exception` 给 revision conflict 私造新 public reason（计划明令“不能借守恒修复私造新 public reason”），或在 job 保存路径丢弃 `persisted_summary` 回退零摘要，现有 844 测试全绿而语义已破——这正是 AGENTS.md“测试必须断言 owner 级 contract 行为”的失效面。
- **建议改法和验证点**: 在 `tests/fins/test_cn_download_runtime.py` 仿照 `test_cn_post_repair_real_preflight_has_successful_document_scope_and_failed_operation` 增加 direct/job 参数化：真实仓储跑出已确认 repair filing 后触发 post-repair revision conflict，断言 RESULT/job record 为 `FinsErrorKind.EXECUTION`、`failure.reason_code is None`、`terminal_disposition="succeeded"`、`written_document_ids` 保留、job `failure_summary.message` 为既有 EXECUTION 安全消息。
- **修复风险（低/中/高）**: 低——纯补测，不改产品代码。
- **严重程度（低/中/高/严重）**: 中

## 声称行为逐条反证（基于直接代码证据）

| 声称行为 | 结论 | 直接证据 |
| --- | --- | --- |
| whole-kind 首候选前 typed 分类 | 成立 | `cn_download_workflow.py:260` 初始 `classify_source_integrity_preflight` 位于 per-candidate try 之外，typed 裸透传不构造 abort/filing 行；`test_cn_real_initial_whole_kind_preflight_uses_request_zero_summary`（direct/job）断言零候选 `FAILED` 请求级摘要、`reason_code=UNSAFE_PUBLICATION`、下载未启动 |
| 循环前 company pre-swap typed（K-F1） | 成立 | `cn_download_workflow.py:282-289` 无 repair 时的 `_publish_cn_company_after_repair` 不包 typed catch，裸透传。`test_initial_company_commit_real_preswap_preflight_keeps_zero_request_summary` 在**真实** `FsBatchingRepository.commit_batch` 内断言 `state.company_meta_intent is not None`（真实 company intent 已 stage）后才注入 staging stray，委托真实 `core._validate_complete_source_tree`（`_fs_storage_infra.py:558-559`，注释明确“完整性校验只读 transaction staging，必须先于 publication guard”）抛真实 typed；`validation_visits == [True]` 证明真实校验被经过，`all(not path.exists() for path in target_ticker_dir)` 证明物理 swap 未发生（pre-swap durable 边界），direct/job 均为请求级零摘要。注入仅制造受控损坏，未伪造 typed 或 classifier 返回值 |
| Phase A/B 单文档 typed 分类 | 成立 | `cn_download_filing_workflow.py:172-173`（Phase A UNSAFE）、`:602-603`（Phase B staged UNSAFE，`finally` 回滚）原样抛出；workflow `cn_download_workflow.py:344-369` 先于普通 `except Exception` 捕获，当前候选记一行 `failed`（通用 `source_integrity_preflight` 类别，不复制四值 reason），发 `FILING_FAILED`，以冻结 `filings` 快照抛 `CnDownloadIntegrityAbort`，不发 `PIPELINE_COMPLETED`、不进 `project_cn_filing_failure` |
| post-repair typed 分类 | 成立 | `cn_download_workflow.py:395-415` catch 同时覆盖 classifier 调用与 `SelectedSourceRepairRequired → SourceIntegrityRevisionConflictError` 显式检查（满足“不得只包住 classifier”）；`:422-441` company 调用点单独 catch preflight，且共享函数 `_publish_cn_company_after_repair` 内部无 catch（满足“catch 只能放在后者的调用点”） |
| 之前已发布 filing 计数守恒 | 成立 | `_integrity_abort`（`cn_download_workflow.py:521-568`）只从已确认 `filings` 真源冻结快照；`_summary_from_integrity_abort` → `_project_cn_pipeline_summary`（`cn_pipeline.py:1474-1515`）复用唯一纯投影，`from_document_rows` 机械派生 counts/terminal，`FinsDownloadResultSummary.__post_init__`（`download_contract.py:373-404`）交叉校验 `discovered=sum(rows)=sum(counts)`。Phase B 中止 `discovered=2/downloaded=1/failed=1/partial_failure`、post-repair 保持 `1/1/0/succeeded` 文档快照 + 操作 `FAILURE`，direct/job 断言同源；未开始候选不计数不造行 |
| job failed record | 成立 | `_run_download_job` catch 序（unsupported → typed → generic，`ingestion_runtime.py:4992-4997`）；`_save_typed_download_failure` 复用 terminal 幂等读取，消息取 `FinsPublicFailure.safe_message`（与 direct 同源），摘要为同一已验证 `persisted_summary.to_json_summary()` 或 `_empty_download_summary_from_request(…, FAILED)`；零摘要用例断言 `record.result_summary == expected.to_json_summary()` 而非 `{}` |
| direct 单 RESULT | 成立 | producer 异常路径只经 `_emit_direct_result` 发一个 FAILURE RESULT（`ingestion_runtime.py:4364-4379`），成功/no-source 路径各自 return；异常快照不另发终态；四组 direct/job 参数化测试均断言 `len(results) == 1` |
| LLM wait / CLI reason_code | 成立 | 唯一映射 `_SOURCE_INTEGRITY_PUBLIC_REASONS`（`ingestion_runtime.py:6904-6910`）+ 测试断言键全集=storage enum 全集、值全集=公共 enum 全集、成对 `.value` 相等；`FinsPublicFailure.to_json_value` 与 CLI `_print_download_failure`（`dayu/cli/output.py:483-497`）取同一 `.value`，None → `"-"`（`_EMPTY_CELL`）；文档行 `reason=` 保持自由文本；wait `_failure_message`（`fins_wait_adapter.py:595-626`）同帧携带 download/failure/`scope_note`（逐字常量 `_DOWNLOAD_FAILURE_SCOPE_MESSAGE`），缺 download 的 typed 失败帧拒绝生成 |
| 二次失败与日志安全 | 成立 | `_save_typed_download_failure` 二次读写失败仅 `_LOGGER.warning("fins.download.typed_failed_record_save_failed")`（固定标识，无 `error_type`/`exc_info`/动态异常信息，满足 fix10 合同）；`test_typed_download_job_second_save_failure_logs_only_fixed_event` 以含秘密路径的自定义异常注入，断言日志无类名/秘密/路径/traceback，job record 不虚称已保存 |
| `FinsResultSummary` 放宽边界 | 成立 | `direct_events.py:677-690` 仅允许 FAILURE 携带 `FAILED/PARTIAL_FAILURE/SUCCEEDED` 文档终态，仍拒绝 CANCELLED 混用、无 failure 的 FAILURE download、SUCCESS 携带 FAILED/CANCELLED；与 plan fix6 F2 一致 |
| mid-filing revision conflict 残余 | 与计划一致 | `test_cn_mid_filing_revision_conflict_injection_remains_ordinary_failure` 把 workflow 宽 catch → `filing_execution_failed` 行 + 继续候选固定为已知残余，归属 `fins-download-storage-sibling-errors`，未冒充 S1 typed 保真 |

## CLI 证据边界独立评价

- 计划要求的窄日期 baseline（`--start 2025-03-28 --end 2025-03-28`）**验收前提未满足**：退出 0 但 `discovered=0`，`portfolio/000333/filings/` 未产生，故“确实选中至少一个候选并建立真实 published filing”的前置不成立。实施 artifact 如实登记为 validation gap，未冒充通过。本审查不将该 exact 命令记为通过。
- 宽日期（`2024-01-01..2026-12-31`）双流验证与窄日期走**同一生产代码路径**（同 CLI 入口、同 CN workflow、同 whole-kind preflight、同 typed 投影）：baseline 建立 3 份带 identity/meta 的真实 published filing 后放置 root stray，重跑得到预期退出 1、`classification="storage" reason_code="unsafe_publication"`、修复提示，stderr/log 无原始异常/URL/token/路径泄漏。作为 typed storage 失败投影与脱敏边界的行为证据成立；但它只证明“该日期窗口有候选”的路径行为，**不能替代**窄窗口 baseline 那条验收。
- 残余：若总控要求窄窗口正式验收，须先确认 000333 在 2025-03-28 的可用 filing 日期后补跑，不得把零发现写成成功；这是 provider 候选可用性问题，不是产品代码缺陷。

## 结论

**fail（按停止条件：存在真实未修复 finding）**——但失败面精确限定如下，不含行为错误：

1. Finding 1（中）：revision conflict typed 中止的 runtime 层投影缺计划明文要求的回归锁定，属真实未修复 finding，须由总控裁决（accepted → 补测 follow-up，或 rejected-with-reason）。
2. 窄日期 CLI baseline 验收未证明（validation gap），不冒充 exact 命令通过。
3. 发布事实本身可证明：whole-kind / 循环前 company pre-swap（K-F1 真实 company intent + 真实 `_validate_complete_source_tree` pre-swap 路径成立）/ Phase A/B / post-repair / company commit typed 分类、已发布 filing 计数守恒、job failed record、direct 单 RESULT、LLM wait/CLI reason_code、二次失败日志安全均与 accepted plan 同源一致；844 passed 与 pyright 0 已独立复跑属实。

## Open Questions

- 无（revision conflict 投影缺口已上升为 Finding 1，非开放问题）。

## Residual Risk

- generic 异常（post-repair company commit 的 ValueError/OSError、physical swap/restore 及 rollback 双失败、postcommit）在已确认文档后仍可能回退零摘要——plan 明示残余，归 `fins-download-indeterminate-publication-state`，S1 不宣称覆盖。
- 844-passed 运行基线是混合工作树（含点号元数据独立 WU 的未提交 `_fs_source_integrity.py` 等）；14 文件测试全部使用非点号 stray（`undeclared.bin`、`foreign-*.bin`），不依赖该 WU 的点号忽略行为，耦合风险低，但“仅含 14 文件 diff 的纯净树”未单独重跑。
- 三份 README 的 #198 句与点号元数据 WU 句在同一 diff hunk 相邻；PR gate 仍须按 plan 要求用 patch 编辑按行拆分 stage 并核对 staged patch，本审查不代做。
- 新测试大量触达私有符号（`core._validate_complete_source_tree`、`storage._fs_identity._identity_directory_path`、`ingestion_runtime._empty_download_summary_from_request`、`cn_pipeline._summary_from_*`）；plan 明文授权 identity owner 导入与 spy 配方，不算违规，但对后续重构敏感。
- coverage 插桩下两个取消时序测试失败（实施 artifact 已如实记录，普通 suite 通过）；插桩敏感性独立于 S1 语义。
- `tests/fins/test_fins_direct.py` 仅作回归验证未改动；S2（安全 operator 调用栈）与本 diff 无关，未实施。
