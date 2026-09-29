RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro[1m]
CANARY=mimo-aa24b3b3

# Issue #198 S1 final2 code review（MiMo 同版深审）

## 范围、锁与对齐材料

- Mode: 当前未提交改动的精确 14 文件 S1 候选（issue #198 S1，F2/F3 修复后的快照）；任务标签 `issue198-s1-final2-mimo-20260929-01`；独立 `$deepreview`，未派发子 Agent。
- 工作区：`/Users/leo/workspace/dayu-agent-r`，分支 `codex/upload-material-oracle`。
- HEAD 锁：`git rev-parse HEAD` = `47a9cb64e63780deb568a9e2c6fdd0120441cf2f`，与任务给定值逐字一致；审查结束前复核，未漂移。
- Diff 锁：按 `docs/gateflow/issue-198-s1-code-review-f2f3-fix-20260929.md` 的 14 文件顺序与命令 `git diff --binary -- <14 文件> | shasum -a 256` = `f1e1a91557cda273c5d0b77900920381727322a8edea69d6061cda27f0f6bd21`，与任务给定值逐字一致；审查结束前复核，未漂移。`git diff --check -- <14 文件>` 退出 0。
- 14 文件（锁内顺序）：`README.md`、`dayu/cli/output.py`、`dayu/fins/README.md`、`dayu/fins/direct_events.py`、`dayu/fins/ingestion_runtime.py`、`dayu/fins/pipelines/cn_download_workflow.py`、`dayu/fins/pipelines/cn_pipeline.py`、`dayu/service/fins_wait_adapter.py`、`tests/README.md`、`tests/cli/test_output.py`、`tests/fins/test_cn_download_runtime.py`、`tests/fins/test_cn_download_workflow.py`、`tests/fins/test_fins_ingestion_runtime.py`、`tests/service/test_fins_wait_adapter.py`。
- 排除 scope：其它 WU dirty 文件（`dayu/fins/storage/_fs_source_integrity.py`、`tests/fins/test_fins_storage_atomicity.py`、`docs/gateflow/*` 其它序列/证据文档、`docs/reviews/*` 既有 artifact、`docs/upload_material_oracle_*`）完全排除，不计入本快照、不从其 hunk 反推 S1 语义。三份 README diff 各含另一 WU 的点号元数据句子（同 hunk 相邻），本审查只审 S1 句，分行 staging 事项保持既有裁决（MiMo F5）。
- 对齐材料（均实读）：`AGENTS.md`；accepted plan `docs/gateflow/issue-198-download-failure-projection-plan-20260928.md`（含 fix8/9/10 与 S1 正文）；`docs/gateflow/issue-198-s1-implementation-20260929.md`、`issue-198-s1-implementation-20260928.md`；`docs/gateflow/issue-198-s1-code-review-adjudication-20260928.md` 全文（含 F1~F5、F01/F02、fix4/fix5 边界、K-F1、code review F1 与 ds-flash F2/F3 裁决）；F1 fix `issue-198-s1-code-review-f1-fix-20260929.md`；F2/F3 fix `issue-198-s1-code-review-f2f3-fix-20260929.md`；既往 ds-flash review `docs/reviews/code-review-20260929-190212.md`；CLI 三日证据 `issue-198-s1-cninfo-single-day-evidence-20260929.md`。
- 本次为同版双路 final2 深审的 MiMo 路；不宣布 S1 code gate 通过，结论只对本快照内容成立。

## 独立验证（本轮实跑，非引用他人记录）

| 命令（`source .venv/bin/activate` 后） | exit | 结果 |
| --- | ---: | --- |
| `python -m pytest tests/fins/test_cn_download_runtime.py -k "post_repair_abort_then_same_request" -q` | 0 | `2 passed, 38 deselected, 3 warnings`（edgartools 第三方弃用警告） |
| `python -m pytest tests/runtime/test_log.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/cli/test_output.py tests/cli/test_fins_commands.py tests/service/test_fins_wait_adapter.py tests/service/test_fins_direct.py -q` | 0 | `846 passed, 3 warnings` |
| `python -m pyright dayu/ tests/ utils/` | 0 | `0 errors, 0 warnings, 0 informations` |
| 覆盖率（plan 命令，`COVERAGE_FILE=$TMPDIR/...`，排除 2 项插桩敏感取消用例）→ `coverage report` | 0 | `613 passed, 2 deselected`；`output.py` 81%、`direct_events.py` 84%、`ingestion_runtime.py` 87%、`cn_download_workflow.py` 92%、`cn_pipeline.py` 92%、`fins_wait_adapter.py` 92%，均 ≥80% |
| `git diff --check -- <14 文件>` | 0 | 无空白错误 |

全部探索/验证 shell 命令自身退出 0；无预期外非零命令，无用非零探测冒充证据。

## F2 对抗性审查：真实同仓中止 → 清 mutation → 同请求重跑

对象：`tests/fins/test_cn_download_runtime.py:1677` `test_cn_post_repair_abort_then_same_request_skips_complete_source_and_downloads_next`（direct/job 参数化）。逐项核验结论如下，未发现阻断缺陷。

1. **真实链，非手造结果**：`_build_runtime_with_cn_hk_adapters(tmp_path)` 一次构建，全程同一 runtime、同一真实 FS 仓储；direct 走 `runtime.download(request)` 事件流、job 走 `runtime.start_download(request)`，中间是真实 `CnDownloadAdapter → CnPipeline → run_cn_download_stream_impl → 单 filing workflow → FsSourceDocumentRepository`。provider discovery/transport 是确定性 fake，与 plan 配方一致。测试从事件/job record 消费真实投影，无手造 `FinsResultSummary`/`FinsPublicFailure`，无从进度事件回填摘要。
2. **中止帧事实**：首候选先真实发布（`start_download` 成功，取 `written_document_ids[0]`），再损坏其 PDF 触发真实 repair；`inject_post_repair` 在第 2 次真实 `list_source_integrity`（post-repair 分类枚举）前向 `filings/` 根写入非点号外来文件，真实 classifier 抛 typed。断言 `len(calls) == 2` 锁定注入点恰为 post-repair 枚举；direct 恰一 RESULT、`status=FAILURE`、`terminal_disposition=SUCCEEDED`、`discovered=downloaded=1`、`failed=0`、`document_rows[0].document_id == document_id`、`failure.reason_code is UNSAFE_PUBLICATION`；job `status=FAILED`、同 counts、`written_document_ids == [document_id]`、`failure_summary["message"] == "本地来源完整性预检失败"`。第二候选 `not second_target.exists()`、传输仅 `["cn-runtime-a1"]`（repair 重下），首候选 PDF 字节与 company meta 旧值不变。与 plan 计数口径逐条相符：post-repair 已处理 filing 保留唯一终态行、`failed_count=0`、row 机械派生 `SUCCEEDED`、请求级 RESULT 仍 `FAILURE`、job record 仍 `FAILED`。
3. **重跑帧事实**：只删除外来 mutation，以**同一 request 对象**、同仓重跑。direct 行序 `[(document_id,"skipped"), (second_id,"downloaded")]`；job `written_document_ids == [second_id]`；两者 `discovered=2`、`(downloaded,skipped,rejected,failed)==(1,1,0,0)`；传输仅 `["cn-runtime-b2"]`（首候选完整来源 skip，无传输）；首候选 PDF 仍原字节；两份 `get_source_meta` 可读回；真实 `list_source_integrity` 两份均 `COMPLETE`。中止帧未处理的第二候选只在重跑计入，未被伪称已处理；重跑无上一轮 failed 行残留（rows 恰两条）。
4. **ID 真源**：`second_id` 取自 `dayu.fins.pipelines.cn_form_utils.build_cn_filing_ids`，与生产 `resolve_cn_download_ids` 对 fresh、非 HK 绑定、非 period-corrected 候选的分配路径同一函数（`cn_download_identity.py` 对 CN 直接返回该分配）；测试未重算哈希、未硬写 `id-...`。行断言以该 ID 与生产派生逐字对照，任何漂移都会失败关闭，不是空断言。fresh 前提由 `assert not second_target.exists()` 与无 published meta 保证。
5. **失败投影同源**：abort 帧 `failure`/`failure_summary` 来自 runtime 唯一映射 `_download_public_failure_from_exception`（`safe_message="本地来源完整性预检失败"`，job message 与之逐字一致）；`reason_code` 非空在 `FinsPublicFailure.__post_init__` 强制 `kind=STORAGE`，与 `_classify_direct_error` 的 `OSError | SourceIntegrityPreflightError → STORAGE` 一致。
6. **脆弱点（有意回归锁，非缺陷）**：`len(calls) == 2` 把 `list_source_integrity` 调用次数锁为合同；`build_cn_filing_ids` 与 `replace(first_candidate,...)` 的 `amended/identity_period` 前提由行断言运行时验证。与 ds-flash review 既列 call-count/注入点耦合同类。

## F3 对抗性审查：私有状态真源与依赖方向

- 修复内容：`cn_pipeline.py` 删除重复常量 `_CN_TERMINAL_INTEGRITY_FAILED`，改为同向导入 `cn_download_workflow._INTEGRITY_FAILED_STATUS`（生产侧 `"integrity_failed"` 现仅 `cn_download_workflow.py:54` 一处定义；产生点 `:558`、消费点 `cn_pipeline.py:1472`）。与 ds-flash L1 及总控 F3 裁决（「pipeline 侧复用 workflow 常量，避免跨层反向依赖」）一致。
- 依赖方向：`cn_pipeline.py` 原已导入 `run_cn_download_stream_impl` 与 `CnDownloadIntegrityAbort`，本次常量导入同向；实测 `cn_download_workflow.py` 不 import `cn_pipeline`/`ingestion_runtime`，`ingestion_runtime.py` 不引用两者，无反向依赖、无兼容 re-export、无公开合同变化。
- 状态语义仍单 owner：workflow 产生 `integrity_failed` 快照并以私有 `CnDownloadIntegrityAbort` 携带，pipeline 双入口封闭校验（`_summary_from_pipeline_result` 仅 `ok/cancelled`，`_summary_from_integrity_abort` 仅 `integrity_failed`）后共用纯投影 `_project_cn_pipeline_summary`；`test_cn_integrity_snapshot_has_separate_strict_projection_entry` 以独立字面量固定双入口互斥与坏 row 拒绝，测试未读生产常量，符合 owner 级断言要求。F3 成立，无回退。

## 旧 F1~F21 修复无回退核验（对照裁决链逐项）

| 历史裁决项 | 当前快照状态 | 本轮直接证据 |
| --- | --- | --- |
| MiMo F1 typed preflight 被宽 except 吞成普通失败 | 无回退 | `cn_download_workflow.py` 单 filing `except SourceIntegrityPreflightError` 先于 `except Exception`；mid-filing revision conflict 仍走普通失败并继续循环（残余归属不变，`test_cn_mid_filing_revision_conflict_injection_remains_ordinary_failure` 在） |
| MiMo F2 enum 双向全集断言 | 无回退 | `test_fins_ingestion_runtime.py:6148-6151` 键全集=storage enum、值全集=public enum、成对 `.value` 相等 |
| MiMo F3 CLI `reason_code=` 标签 | 无回退 | `dayu/cli/output.py:486-493` 失败详情 `reason_code=`；文档行 `reason=` 语义未动（`_download_document_line` 未改） |
| Kimi F1/MiMo F4 `None -> "-"` 占位 | 无回退 | `output.py` `_EMPTY_CELL` 占位；`test_output.py` EXECUTION 用例断言 `classification="execution"` 与 `reason_code="-"`，storage 用例保留 |
| MiMo F5 README 相邻句按行 staging | 状态延续 | 三份 README 的 S1 句自足、点号句独立；同 hunk 按行 stage 仍是 commit gate 待办，非本快照缺陷 |
| Kimi F01 job 空摘要 `{}` | 无回退 | `_save_typed_download_failure` 以 `summary.to_json_summary()` 保存；`test_initial_typed_download_job_saves_structured_zero_summary_and_safe_message` 断言结构化零摘要与安全消息 |
| Kimi F02 post-repair typed 归零 | 无回退 | post-repair 分类块（含显式 revision conflict 检查）与 post-repair `_publish_cn_company_after_repair` 调用点各有 typed catch → `_integrity_abort`；workflow 测试断言 cause/rows/无 `PIPELINE_COMPLETED` |
| Kimi OQ1/MiMo F1 fresh Phase B 目标目录配方 | 无回退 | `_identity_directory_path` + `_FILING_IDENTITY_NAMESPACE` 私有 helper 取未发布目标，真实 classifier/rollback 断言仍在（`test_cn_real_phase_b_abort_keeps_published_document_in_result_and_job`） |
| MiMo F1 后置窗口守恒（fix5 缩窄后） | 无回退 | 只对可证明路径（post-repair 分类块、company pre-swap typed）收口；非 typed/物理不确定面仍留 `fins-download-indeterminate-publication-state`，无泛 `except Exception` 保留快照 |
| Sol fix4 RESULT owner 放宽 | 无回退 | `FinsResultSummary.__post_init__` 仅拒 `FAILURE + CANCELLED`，允许 `FAILED/PARTIAL_FAILURE/SUCCEEDED`；不按 kind/reason 放宽；成功/取消混用、无 failure 仍拒 |
| OQ1 typed pre-swap + cleanup 双失败链 | 无回退 | `test_cn_post_repair_company_preswap_typed_spy_preserves_snapshot_and_chain` 断言 `abort.cause is preflight_error`、`abort.cause.__cause__ is cleanup_error`，未断言 cleanup 成功 |
| OQ2 wait `scope_note` 逐字 | 无回退 | `_DOWNLOAD_FAILURE_SCOPE_MESSAGE` + 测试独立字面量逐字断言字段与值；revision conflict 帧同 scope_note |
| MiMo F3 wait 失败帧缺 download 拒绝 | 无回退 | `_failure_message` 拒绝 `download=None` 的失败帧；跨操作 dataclass 仍允许（`replace(result, download=None)` 负例在） |
| MiMo F4 job 二次保存不逃逸 + 固定 WARN | 无回退 | `_save_typed_download_failure` 内 try/except → `_LOGGER.warning("fins.download.typed_failed_record_save_failed")`；测试断言 `exc_info is None`、无 `error_type`/类名/路径/秘密、record 仍 `RUNNING`、`result_summary == {}` 不虚称终态 |
| 第五次复审 F1 零候选同源 | 无回退 | direct catch 与 job typed catch 对裸 typed 均用 `_empty_download_summary_from_request(..., terminal_disposition=FAILED)`；`test_cn_real_initial_whole_kind_preflight_uses_request_zero_summary`、`test_initial_company_commit_real_preswap_preflight_keeps_zero_request_summary` 各 direct/job 在 |
| 第五次复审 F2 私有 adapter failure 单点 unwrap | 无回退 | `FinsSourceDownloadAdapterFailure` 定义于 `ingestion_runtime.py`，持原 cause + 已验证 summary（TypeError 限 typed cause）；`_download_exception_cause` 为唯一 unwrap 实现，direct/job 不遍历 `__cause__`、不解析字符串 |
| 第五次复审 F3 纯投影 helper 抽取 | 无回退 | `_project_cn_pipeline_summary` 单一纯投影，双入口共用；未伪 `ok`、未放宽正常入口 |
| K-F1 fresh ticker 非空 company intent + 真实 `commit_batch → _validate_complete_source_tree` | 无回退（既有覆盖） | `test_initial_company_commit_real_preswap_preflight_keeps_zero_request_summary` 注入前断言 `company_meta_intent is not None`、真实校验路径计数、target 未建、`discovered=0` 零摘要 |
| code review F1 revision conflict direct/job owner 测试 | 无回退 | `test_cn_post_repair_real_second_source_revision_conflict_preserves_public_summary` 在（EXECUTION、`reason_code=None`、守恒行/ID/计数、job 安全文案） |
| code review F2（ds-flash）同请求重跑回归 | **本轮重点，已修复** | 见上 F2 专节；focused 2 passed |
| code review F3（ds-flash）私有状态真源收敛 | **本轮重点，已修复** | 见上 F3 专节 |
| ds-flash L1~L4 风格项 | L1 已由 F3 收口；L2/L3/L4 仍为纯风格 | L4 实测仍在：`tests/service/test_fins_wait_adapter.py:422` 顶层函数间空行 1 行（black/E302 期望 2）；仓库 gate 不跑 ruff，不阻断 |

补充核验：`_bounded_download_summary` 实为 contract 类型确认并返回同一实例，`_execute_download_request` 对私有 failure「验证后仍抛原异常」不存在「验证拷贝、消费原对象」缝隙；`download_contract` 的 `written_document_ids` 由 typed rows 唯一派生，测试侧重算不存在。测试未见 fake 公共 RESULT 充端到端证据。

## CLI 三日证据界限（如实保留）

- 计划指定的 **单日** `2025-03-28..2025-03-28` 真实 baseline 仍未满足：provider 第一页 `totalRecordNum=0`，`discovered=0`，该条验收**未通过**，已登记独立 WU `fins-cninfo-single-day-discovery-window`（`issue-198-s1-cninfo-single-day-evidence-20260929.md`）。本审查不把它改写成通过。
- 三天窗口 `2025-03-27..2025-03-29` 的真实 CLI baseline/typed 失败/读回与宽窗口证据走同一生产调用链（同 CLI、同 whole-kind preflight、同公共投影），可作为 S1 typed 失败投影路径的行为证据，但属**方法替代**，不冒作原单日命令通过，也不属本 14 文件快照的改动。
- 14 文件候选内无任何文本宣称单日命令通过；`tests/README.md`/根 `README.md` 的 S1 句未越界描述 CLI 日期验收。

## Findings

无阻断 finding。以下为非阻断观察项，按行号/证据/预期-实际/建议登记：

### N1（low，记录精度；不阻断）：F2 新测试实为替换旧 post-repair runtime 用例，fix 记录未披露

- 位置：`tests/fins/test_cn_download_runtime.py:1677` 与 `docs/gateflow/issue-198-s1-code-review-f2f3-fix-20260929.md`「F2 真实恢复回归」节。
- 证据：86aa9a2b 快照存在 `test_cn_post_repair_real_preflight_has_successful_document_scope_and_failed_operation`（ds-flash review 穷举列出），当前树中该用例名已消失，其位置由 F2 新用例占据；numstat 佐证（`test_cn_download_runtime.py` 净 +852/-1，全局 +2163，与「新增 199 行测试 + 移除约百行旧用例」自洽）。fix 记录把 F2 描述为纯新增回归，未记录替换。
- 预期/实际：预期「补回归」时保留或转移旧用例断言语义并如实记录；实际断言语义并集保留（成功文档作用域 + 失败操作 = 新用例中止帧 `terminal_disposition=SUCCEEDED` + `status=FAILURE` + counts/rows/durable 字节/company 旧值，且 Phase B/whole-kind/wait 测试另行覆盖 reason/安全文案/投影细节），仅记录精度不足。
- 修法：后续 fix/closeout 记录补一句「替换原 post-repair runtime 用例，断言并集保留」；无需改测试或产品代码。

### N2（low，风格延续；不阻断）：顶层函数间空行回退

- 位置：`tests/service/test_fins_wait_adapter.py:422`（两顶层测试函数间仅 1 空行）。
- 证据/预期/实际：即 ds-flash L4；black/E302 期望 2 空行，当前 1。仓库 gate 只跑 pytest+pyright，无 lint 阻断。
- 修法：下次触碰该文件时按 black 恢复；不单开修复轮。

### N3（residual，plan 已声明；不阻断）：typed job 一次投影构造在非逃逸 try 之外

- 位置：`dayu/fins/ingestion_runtime.py` `_save_typed_download_failure`（`failure = _download_public_failure_from_exception(...)` 与 `summary.to_json_summary()` 在 try 外）。
- 预期/实际：plan 的不逃逸承诺只覆盖「二次读取/保存失败」；若一次投影构造自身再抛，会逃出 `_run_download_job`，与 plan 风险段「二次投影失败归 `fins-direct-projection-failsafe`」一致，属已声明残余而非新缺陷。
- 修法：维持既定归属，不在 S1 扩兜底。

## Residual Risk（沿既有分类，无新增未分类风险）

- **单日 CNInfo 发现缺口**：`fins-cninfo-single-day-discovery-window`，独立 WU；三日/宽窗口仅为替代证据。
- **不确定发布状态**：`fins-download-indeterminate-publication-state`（precommit ValueError/OSError、post-commit release、physical swap/rollback 双失败）——S1 不宣称覆盖，泛异常零摘要是明确残余缺陷。
- **sibling 分类**：mid-filing `SourceIntegrityRevisionConflictError` 与 `SourceIntegrityRepairBlockedError` 仍 EXECUTION 兜底，归 `fins-download-storage-sibling-errors`。
- **SEC/其它来源守恒**：`fins-download-other-source-summary-conservation`；**raw 诊断**：既有 job WARN `exc_info`、generic job `str(exc)` 归 `fins-other-raw-diagnostics-audit`；**无来源 hint**：`fins-download-no-source-retry-hint`；**二次投影失败**：`fins-direct-projection-failsafe`。
- **混合工作树**：846 passed/覆盖率/pyright 在含独立点号 WU dirty 文件的树上运行，「仅 14 文件纯净树」未单独重跑（与前两轮相同的既有残余）；S1 新测试不依赖点号忽略行为。
- **覆盖率方法边界**：2 项取消时序用例在 coverage 插桩下被排除，普通 suite 通过；插桩敏感性未调查（非 S1 语义）。
- **测试-实现耦合**：`list_source_integrity` 调用次数、storage 私有 helper（`_identity_directory_path`、`_ActiveBatchState`、`_validate_complete_source_tree` 等）被测试直接引用（裁决已允许，不重算哈希、委托真源），对内部重构敏感。
- **commit gate 待办**：三份 README 相邻句须按行 stage 并核对 staged patch；本审查不执行 stage/commit/push/PR。
- **双路 gate**：本报告为 final2 MiMo 路内容结论；`ds-flash` 备份路与总控裁决完成前，S1 code gate 不通过、不提交/集成。

## 结论

**pass-with-risks**

1. 锁一致：HEAD `47a9cb64e63780deb568a9e2c6fdd0120441cf2f` 与精确 14 文件 diff SHA-256 `f1e1a91557cda273c5d0b77900920381727322a8edea69d6061cda27f0f6bd21` 首尾复核逐字一致，未混入其它 dirty WU。
2. F2 成立：真实同仓中止帧与同请求重跑帧经一手 owner（Fs 仓储 meta/integrity/字节）、真实 adapter/runtime 链在 direct/job 两入口断言守恒与恢复语义；无手造公共结果、无测试侧重算、无伪称已处理；plan 第 57 行强制断言已落地。
3. F3 成立：`integrity_failed` 私有状态单真源（workflow 产生、pipeline 同向消费），双入口封闭校验 + 共用纯投影，依赖方向无反向。
4. 旧 F1~F21 修复逐项无回退（对照表见上）；三日 CLI 证据界限如实保留，单日缺口未被改写。
5. 独立复跑属实：focused 2 passed；受影响八文件 **846 passed**；pyright **0/0/0**；六生产文件覆盖率 **81/84/87/92/92/92%**（均 ≥80%）。
6. 剩余为 N1 记录精度、N2 风格延续与既有声明残余（含单日 CLI gap），无新增未分类风险，不阻断本快照内容结论；S1 code gate 仍待同版第二路与总控裁决。
