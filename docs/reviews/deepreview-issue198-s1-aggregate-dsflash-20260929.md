RUNTIME/PROVIDER/MODEL: claude/ds-flash/deepseek-flash[1m]
CANARY=ds-flash-0dc80f65

# Aggregate Deepreview：issue #198 S1 accepted commit（ds-flash 备份路）

## 结论摘要

- 审查对象：绝对隔离 workspace `/private/tmp/dayu-issue198-s1-aggregate`，HEAD = 目标提交 `7234d42dbaea603112c6fed52776281228d261a7`（父提交 `47a9cb64e63780deb568a9e2c6fdd0120441cf2f`），只审该提交相对父提交的内容。
- **结论：pass-with-risks。material findings：无。** 未发现阻断项、跨层回归、typed 失败投影错配、已处理快照/同请求恢复缺口、CLI/job/Service 语义错配、README 承诺超界或 S1/S2 越界；未发现使门限结论不可信的测试假阳性。
- 关键独立验证：提交表面 30 文件 = 计划 S1 白名单 6 生产文件 + 3 处 README（各 +1 行）+ 5 测试文件 + 16 文档，Python 断言无越界文件；已审 14 文件快照与提交切片的差异恰为按行 staged 的 3 行 README（`+2163/-65` → `+2160/-65`），11 个代码/测试文件逐文件增删计数与既往 review 记录逐项一致；受影响八文件 846 passed、跨层 host/service 631 passed；对 `tests/fins+cli+service` 与 `tests/contracts+tools+engine+runtime+documents` 做了父提交基线对比，失败集合 Python 断言完全相同（76/13 条均为沙箱既有环境失败），净增 27 条通过用例；pyright 显式解释器下 0/0/0；5 份 CLI 留档流 SHA-256 与内容逐项复核一致。
- 非阻断观察 4 项（L1–L4，info/low）与记录级说明 1 项（L5）；残余风险集中在已登记的独立 WU（单日 CNInfo 发现窗口、不确定发布状态、sibling 分类、二次投影 failsafe、S2 未实施）。

## Scope 与锁

- Mode：aggregate deepreview（accepted commit 相对父提交；工作树 HEAD 必须等于目标提交；并发另一路唯一新 review artifact 允许未跟踪，不计入快照）。
- HEAD 锁：开始时 `git rev-parse HEAD` = `7234d42dbaea603112c6fed52776281228d261a7`，与任务给定值逐字一致；开始时 `git status --porcelain` 为空（工作树干净）；收尾复核时仅多出并发另一路 `docs/reviews/deepreview-issue198-s1-aggregate-mimo-20260929.md` 一个未跟踪文件，属任务允许项，非范围外 dirty。
- 父提交：`47a9cb64e63780deb568a9e2c6fdd0120441cf2f`（`docs: accept issue 198 S1 download failure plan`）。提交 `7234d42d` 是 S1 产品/测试/README/文档的首次落库；其前序 S1 内容（被双路 review 的 14 文件工作树候选）在 git 历史中没有未提交快照可复算，本审查因此以「提交相对父提交」为一手 diff。
- 对齐材料（本轮实读）：`AGENTS.md`；`docs/gateflow/issue-198-download-failure-projection-goal-20260928.md`；accepted plan `docs/gateflow/issue-198-download-failure-projection-plan-20260928.md`（第 41–63 行 S1 正文，含第 57 行同请求重跑与第 61 行 commit-time 覆盖）；`docs/gateflow/issue-198-s1-implementation-20260928.md`、`issue-198-s1-implementation-20260929.md`；`docs/gateflow/issue-198-s1-code-review-adjudication-20260928.md` 全文（F1–F5、F01/F02、fix4/fix5 边界、MiMo 第 3–7 次 plan re-review、K-F1、code review F1、ds-flash F2/F3 与最终裁决）；`issue-198-s1-code-review-f1-fix-20260929.md`；`issue-198-s1-code-review-f2f3-fix-20260929.md`；`issue-198-s1-cninfo-single-day-evidence-20260929.md`；最终 code reviews `docs/reviews/code-review-issue198-s1-final2-dsflash-20260929.md`、`code-review-issue198-s1-final2-mimo-20260929.md`、`code-review-issue198-s1-final3-dsflash-20260929.md`、`code-review-issue198-s1-mimo-20260929.md`。
- Parallel review coverage：无。按任务约束未派发任何子 Agent；全部读码、复跑、证据复核由主 reviewer 完成，未读并发另一路 artifact。
- 本轮协议：不执行故意失败的 pytest、不执行无匹配 `rg`/glob；预期无匹配或反例一律用 Python 捕获并断言；全部探索/验证命令自身 exit0（两处全量对照 pytest 自身 exit1 为既有环境失败，已单独如实披露）。

## 命令与结果披露

| 命令 | exit | 结果 |
| --- | ---: | --- |
| `git rev-parse HEAD` | 0 | `7234d42dbaea603112c6fed52776281228d261a7`，与目标逐字一致 |
| `git status --porcelain`（开始 / 收尾） | 0 | 开始为空；收尾仅并发另一路未跟踪 artifact |
| `git diff --binary 47a9cb64 7234d42d -- <14 文件> \| shasum -a 256` | 0 | `39018b6580…77fe4`（见 L5：与既往 review 锁定的 `f1e1a915…f6bd21` 的差异恰为按行 staged 的 3 行 README） |
| `git diff --numstat 47a9cb64 7234d42d -- <14 文件>` | 0 | 14 文件 `+2160/-65`；逐文件计数见下节 |
| `git diff --check HEAD~1 HEAD` | 0 | 无空白错误 |
| `git show --name-only` + Python 断言（30 文件、前缀白名单、生产文件集合 == 计划 S1 六文件） | 0 | `ASSERT_OK`，无越界路径 |
| `rg`/`sed` 行号复核（`output.py:486/487`、`direct_events.py:441-442/677-690`、`cn_download_workflow.py:54/558`、`cn_pipeline.py:1472`、`fins_wait_adapter.py:592/618`、`ingestion_runtime.py:587/4344/5021/6911`、`test_cn_download_runtime.py:839/1677/1877`、`test_fins_ingestion_runtime.py:6149-6152`） | 0 | 与既往 review 记录的行号/语义逐项一致 |
| `python -m pytest tests/runtime/test_log.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/cli/test_output.py tests/cli/test_fins_commands.py tests/service/test_fins_wait_adapter.py tests/service/test_fins_direct.py -q` | 0 | **846 passed**，3 条 edgartools 第三方 warning（与记录一致） |
| 跨层消费方测试 10 文件（host accepted_result/compact/dispatch/memory/package_exports/run_input/tool_trace×2 + runtime smoke + service host_assembly） | 0 | **631 passed** |
| `python -m pyright --pythonpath <main-venv>/bin/python dayu/ tests/ utils/` | 0 | **0 errors, 0 warnings, 0 informations** |
| `python -m pyright dayu/ tests/ utils/`（不带显式解释器） | 1 | 29 条 `reportMissingImports`（docling*）——本隔离 checkout 无 `.venv`、pyrightconfig `venvPath=./.venv` 不存在所致，纯环境噪声，已用显式解释器复跑为 0 |
| CLI 留档流 SHA-256 + 内容 Python 断言（`/private/tmp/issue198-cli-narrow3-20260929/`） | 0 | 5 份流哈希与证据文档逐字一致；`classification="storage"`/`reason_code="unsafe_publication"`/零摘要/修复提示在 stderr；stdout 仅 preparing+started；普通日志仅一条进入流程 INFO；三个流均无外来 basename、`https://`、`/private/tmp` 泄漏 |
| `python -m pytest tests/fins tests/cli tests/service -q`（提交树 vs 父提交基线树，两树各一次） | 1 / 1 | 提交 `76 failed, 3770 passed, 8 skipped`；父提交 `76 failed, 3743 passed, 8 skipped`；**失败集合 Python 断言完全相同**（见下节） |
| `python -m pytest tests/contracts tests/tools tests/engine tests/runtime tests/documents -q`（两树各一次） | 1 / 1 | 提交 `13 failed, 1809 passed, 1 skipped`；父提交 `13 failed, 1809 passed, 1 skipped`；**失败集合 Python 断言完全相同** |
| 读 canary 文件 | 0 | `'ds-flash-0dc80f65'`（`repr` 复核，无尾随换行） |

两处全量对照 pytest 自身 exit1 为**沙箱既有环境失败**，与目标提交无关，且已在父提交基线逐条复现：典型为 `ValueError: missing env MIMO_PLAN_API_KEY`（17 条，interactive/prompt 需要模型 env）、`OSError: out of pty devices`（10 条，pty 资源耗尽）、以及需要真实 TTY/子进程的 CLI 用例。上表未用任何非零命令作为通过证据；对照结论由失败集合相等的 Python 断言给出。

## 独立验证一：提交身份、范围与「已审快照 == 提交切片」

- **提交表面（Python 断言）**：30 文件 = `dayu/cli/output.py`、`dayu/fins/direct_events.py`、`dayu/fins/ingestion_runtime.py`、`dayu/fins/pipelines/cn_download_workflow.py`、`dayu/fins/pipelines/cn_pipeline.py`、`dayu/service/fins_wait_adapter.py`（生产，恰等于 accepted plan S1 允许代码文件集合）+ `README.md`、`dayu/fins/README.md`、`tests/README.md` + 5 个 S1 测试文件 + 16 个 docs（gateflow 记录与既有 review artifact）。无 `dayu/fins/storage/*`、无点号元数据测试、无 `workspace/`、无 `.venv` 等范围外文件。
- **三份 README 各恰 +1 行**（`git diff` 实读）：根 README 为计划规定的自足句「下载显示 `classification="storage"`、`reason_code="unsafe_publication"` 时，请检查工作区来源状态并修复后重试；重复下载不会自行修复。」；`dayu/fins/README.md` 与 `tests/README.md` 各为 S1 语义句，未夹带另一 WU 的点号元数据句——即裁决 MiMo F5 要求的「按行 stage、不整 hunk stage」已落实。
- **提交切片与既往 review 锁定快照的等价性**：既往双路 review 锁定 14 文件 diff `f1e1a915…`（`+2163/-65`）；本 checkout 同 14 文件相对父提交为 `39018b65…`（`+2160/-65`），差值恰为 3 行 README。逐文件 `numstat` 与既往记录逐项吻合：`output.py +2/-0`、`direct_events.py +20/-2`、`ingestion_runtime.py +124/-8`、`cn_download_workflow.py +180/-19`、`cn_pipeline.py +86/-15`、`fins_wait_adapter.py +12/-3`、`test_output.py +32/-6`（记录 38 变更）、`test_cn_download_runtime.py +852/-1`（记录净 +852/-1）、`test_cn_download_workflow.py +501/-0`、`test_fins_ingestion_runtime.py +296/-0`、`test_fins_wait_adapter.py +52/-11`（记录 63 变更）。所有既往 review 引用的代码行号在本提交中解析到同一语义（见命令表）。结论：**提交的代码/测试切片与通过双路 review 的候选同源，未发现审查后夹带改动**；唯一的字节差异是裁决明确要求的 README 分行提交（L5）。

## 独立验证二：测试、类型检查与跨层回归

- 计划规定的受影响八文件 suite：**846 passed**（与实施/评审记录一致），无 skip/deselect。
- 跨层消费方（Host / Service / Runtime 装配）10 文件：**631 passed** —— `FinsResultSummary` 放宽与 `FinsPublicFailure` 新增 JSON 字段未破坏 Host 侧 result/trace/memory 投影与装配测试。
- 全量 `tests/fins+cli+service` 与 `tests/contracts+tools+engine+runtime+documents` 的双树对照：失败集合完全一致，提交净增 27 条通过用例（S1 新增 18 个测试函数，含 direct/job 与四 reason 参数化）。**结论：本提交未引入任何新增测试失败。**
- pyright：显式解释器 0 errors / 0 warnings / 0 informations；不带解释器时的 29 条 `reportMissingImports` 已定位为隔离 checkout 缺少 `.venv` 的环境噪声（`pyrightconfig.json` 的 `venvPath: "."` 在此无不存在的 venv）。
- 真实 CLI 留档流 5 份 SHA-256 与内容逐项复核一致（含空 stderr 的空文件哈希），普通日志无临时绝对路径、无外来 basename、无 URL/token/异常原文。

## 对抗性审查：按任务指定维度逐条

### A. typed 失败投影是否错配（否）

- 映射真源唯一：`dayu/fins/ingestion_runtime.py:6904-6925` 的 `_SOURCE_INTEGRITY_PUBLIC_REASONS` + 单点 unwrap `_download_exception_cause`；`_classify_direct_error`（`:7176` 起）与 `_download_public_failure_from_exception`（`:6928` 起）都在同一 helper 解出原 cause，二者对 `SourceIntegrityPreflightError` 一致给出 `STORAGE`（前者 `OSError | SourceIntegrityPreflightError`，后者 kind=STORAGE + 封闭 `reason_code`）。storage 枚举四值与公共枚举四值逐值同名，唯一生产 raise 点传 enum，无字符串反解析、无第二份白名单。
- `FinsPublicFailure.__post_init__` 拒绝非 `FinsDownloadFailureReason` 与「非 STORAGE 或不带 transport 却携带 reason」的组合；`to_json_value()`/CLI/等待 JSON 均取 `.value`。
- 非 typed 异常不附 reason：`FinsDownloadProviderError`/`OSError`/unknown 路径的 `reason_code` 恒为 `None`（既有测试已加断言）。
- revision conflict 保持既有 `EXECUTION` + `reason_code=None`（workflow 显式抛出 → 私有 abort → adapter → runtime 兜底），与 adjudication「不私造 public reason」一致；`SourceIntegrityRevisionConflictError` 与 `SourceIntegrityPreflightError` 互不继承，typed catch 不会误吞冲突（直接读 storage 类定义确认）。
- 单点 unwrap 的实例一致性：`_bounded_download_summary` 是同一实例的类型确认（返回原对象），`_execute_download_request` 在验证后 `raise` 原异常，direct/job 消费同一实例，不存在「验证一份、消费另一份」。

### B. 已处理快照与同请求恢复（成立）

- 快照真源：workflow `_integrity_abort` 只用当前 `filings` 构造私有 `status="integrity_failed"` 快照（`cn_download_workflow.py:521-568`），pipeline 以两个互斥入口（`ok/cancelled` 与 `integrity_failed`）严格校验后共用纯投影 `_project_cn_pipeline_summary`。
- 不会重复计数：单 filing 流中所有 `FILING_FAILED` 产出后均立即 `return`（`cn_download_filing_workflow.py:202-215/270-281/343-358`），Phase B typed 抛点在 `_commit_cn_filing_assets_batch`（`:596-603`）且仅由 `:388` 调用，因此外层 typed catch（`cn_download_workflow.py:344`）补的 `failed` 行不会与循环内 `filings.append` 叠加；Phase B 用例断言 rows 恰为 `["downloaded","failed"]`、`FILING_FAILED` 恰 1 次、`commit=2/rollback=1`。
- 同请求恢复（F2）：`tests/fins/test_cn_download_runtime.py:1677`（direct/job 参数化）在真实 FS 仓储 + 真实 workflow/adapter/runtime 上先发布首候选、损坏其 PDF 触发真实 repair、在第二次真实 `list_source_integrity` 前注入非点号外来文件产生真实 typed 中止；随后仅删除该 mutation，用**同一 request 对象**重跑：首候选按仓储 `COMPLETE` 真实 `skipped`（无传输）、第二候选 `downloaded`、计数 `(1,1,0,0)`、两份来源 meta/完整性读回。count 调用数恰为 2 与生产调用点一一对应（`cn_download_workflow.py:261`、`:397` 是全仓 CN 路径仅有的两处 `list_source_integrity`）。
- 首候选前/公司 pre-swap 的零候选口径：workflow 在这两处不构造 abort（裸 typed 透传），runtime direct/job 共同使用 `_empty_download_summary_from_request(..., FAILED)`；K-F1 用例在注入前 `assert state.company_meta_intent is not None`、真实 `_validate_complete_source_tree` 访问恰 1 次、目标目录未创建，锁住了「不会经空 filings 派生 SUCCEEDED」。
- storage owner 前提复核：`_fs_storage_infra.py:545-570` 的 `commit_batch` 先 `_validate_complete_source_tree`（整树只读 staging 校验）、后进入 publication guard/identity guards，故 company 路径的 typed preflight 属 pre-swap；storage 全仓不抛 revision conflict from company commit（raise 点仅 `_fs_source_document_core.py:436-453` 的 staged 分类与 CN/SEC filing workflow），workflow 在 company 调用点只 catch preflight 与 owner 事实一致。

### C. CLI / job / Service 差异（无错配；L1 记录）

- CLI 失败详情打印 `reason_code=<枚举值|->`，同一输出中的文档行仍为自由文本 `reason=`（`dayu/cli/output.py:450-473`、`:469-495`，`_EMPTY_CELL="-"`）——与 F3 裁决一致。
- Service wait 失败帧：`_failure_message` 在有 `failure` 时强制要求 `download` 非空，并输出 `status/title/download/failure/scope_note`；`scope_note` 常量与 plan 规定的逐字文本一致，测试用独立字面量断言字段名与值。observation 状态由 `_observation_status_from_result(result.status)` 派生，与 download 文档终态解耦；因此「整体 FAILURE + 文档 SUCCEEDED」组合不会把 observation 误判为成功。
- 全仓 `terminal_disposition` 消费者复核：无任何 download 消费者假定「FAILURE ⇒ FAILED disposition」（其余命中均为 upload 终态或运行时自造的 FAILED/CANCELLED 零摘要）。
- **L1（info）**：后台 job 的 durable failed record 只持久化 `failure_summary.message` + 结构化 `result_summary`，**不携带**公共 `reason_code`，而 direct RESULT / CLI / wait JSON 携带。该边界是 accepted plan 明示的（job 只取同一公共映射的 `safe_message`，且 S1 不新增 job record schema 字段），因此不是缺陷；但「显示有、durable 无」的投影不对称会在后续 WU 读取 job record 时重新出现，建议由 job record schema owner 单独裁决是否需要持久化原因码。

### D. README 承诺是否超界（否；L4 记录）

- 根 README 句自足、条件化（`classification="storage"` 且 `reason_code="unsafe_publication"`），不依赖另一 WU 点号句作主语；与 CLI 实测输出逐字对应。
- `dayu/fins/README.md` 新增句逐项可验证：四值映射（代码 + 四值参数化测试）、JSON/CLI 同一枚举值（`to_json_value()` 与 `_print_download_failure`）、非盲目重试提示（`retry_hint` 文案）、单文档/已处理文档后 pre-swap 中止携带快照、adapter 严格投影、direct/job 同源摘要、首候选前零候选、文档终态与操作终态分离。
- `tests/README.md` 新增句所述用例在树中一一存在（四值映射、JSON/CLI/wait 固定显示、CN/HK 真实仓储首候选前 company pre-swap、Phase B、commit-time、post-repair、direct/job 摘要）。
- 未命中 `README.md`/`dayu/README.md`/`dayu/config/README.md` 的职责变化；`dayu/service/README.md`、`dayu/cli/` 无「Agent更新约束」且不在 AGENTS.md 触发清单内，其现有描述未因本次改动失真。
- **L4（info）**：根 README 只文档化 `unsafe_publication` 一个值，而 CLI 可显示四个公共值（四者共享同一修复提示）。记录为非缺陷（用户手册只需覆盖最常见可行动场景），不要求本轮扩写。

### E. S1/S2 边界（未越界；L3 观察）

- 提交未触碰 S2 允许文件 `dayu/runtime/log.py`、`dayu/cli/commands/fins.py`：无 `safe_exception_trace`、无 `fins.download.unexpected_failure`/`command_unexpected_failure` 事件、无 CLI `--log-file` 提示常量（`output.py` 仅 +2 行 `reason_code` 显示）。
- S1 测试未断言 S2 行为（未知异常安全日志、外层 catch 文案、结果先于日志顺序均无断言）。
- **L3（info）**：新增 CLI EXECUTION 用例的 fixture `retry_hint` 采用了 plan 中属 S2 的未来文案（「请保存脱敏诊断并排查失败原因后重试。」），当前生产 EXECUTION 提示仍是既有文案；该值只作输入数据、未被断言，因此不影响结论，但读者可能误以为 S2 文案已实现，建议后续触碰该文件时对齐为当前生产文案或加注释。

### F. 测试假阳性对抗审查（未发现假阳性）

- 关键用例均走真实 owner 链（真实 `FsSourceDocumentRepository`/`FsBatchingRepository`/`CnDownloadAdapter`/`FinsIngestionRuntime`），provider discovery/transport/converter 为确定性 fake（外部依赖，允许）；spy 只观察并委托真实实现（`_BatchIdentityCnBatchingRepository` 继承真仓储并 `super()` 调用；company pre-swap spy 在真实 `commit_batch` 前注入并断言 `company_meta_intent is not None`）。
- 无法「空断言」通过：F2 用例若首候选被重下会触发 `downloaded_sources` 多出 `cn-runtime-a1`；若中止帧丢行会触发 `document_rows[0].document_id` 断言；若注入点漂移会触发 `len(calls)==2`/`rows==["downloaded","failed"]`。
- 负例真实可失败：`test_download_public_failure_rejects_open_or_non_storage_reason`、`test_failed_operation_accepts_only_valid_processed_document_dispositions`（含 CANCELLED disposition 负例）、`test_typed_download_job_second_save_failure_logs_only_fixed_event`（注入含秘密路径与类名的二次保存异常，断言 record 仍 `RUNNING`、摘要仍 `{}`、日志恰一条固定事件且无 `exc_info`/`error_type`/类名/路径/秘密）；`test_cn_mid_filing_revision_conflict_injection_remains_ordinary_failure` 明确把受控注入标记为「workflow 宽 catch 残余」，未冒充真实 owner churn。
- 松紧守恒：`_summary_from_pipeline_result` 仍只接受 `ok/cancelled`，`_summary_from_integrity_abort` 只接受 `integrity_failed`，坏 row/坏 locator 仍拒绝；`FinsResultSummary` 放宽只删除「FAILURE 必须 FAILED disposition」，未放宽无 failure、SUCCESS/CANCELLED 混用。
- 唯一弱断言（既有记录延续）：job 零候选用例以生产 helper `_empty_download_summary_from_request(...).to_json_summary()` 作为期望；因同帧还有 direct 侧的 `terminal_disposition is FAILED`/`discovered_count == 0`/文档行空 与 job 侧 `failure_summary["message"]` 字面量断言，且该比较形状是 plan 指定，记为可接受。

### G. 提交身份与快照缺口的边界（L5）

- **L5（record，非缺陷）**：既往两路 code review 与裁决锁定的 `f1e1a915…` 是「pre-commit 工作树 14 文件 diff」，其中三份 README 各含另一 WU 的点号句；accepted commit 按裁决 MiMo F5 只 stage S1 句，因此提交后的同文件 diff 变为 `39018b65…`，差异恰为 3 行 README。该差异是**提交动作本身**造成的、被裁决明确要求的差异，不是审查后内容漂移；但任何后续以 `f1e1a915…` 作为「已审版本」的核对都会对不上。建议 aggregate closeout 显式记录：`39018b65…`（或提交 SHA `7234d42d`）为 S1 的最终已审身份，`f1e1a915…` 只代表 pre-staging 工作树候选。
- 在隔离 checkout 中无法逐字复算 `f1e1a915…`（pre-commit 工作树状态不可得，且任务约束禁止用主工作树混合改动填补该缺口）；本轮以「逐文件增删计数一致 + 全部 review 行号复核一致 + 3 行 README 差分可解释」作为等价性证据，不冒充逐字复算。

## Findings

无 material/blocking finding。以下为非阻断观察项，均不改变本提交的门限结论：

### L1（info；job durable record 不含公共 reason_code）
- 位置：`dayu/fins/ingestion_runtime.py:4999-5035`（`_save_typed_download_failure`）与 job record schema。
- 证据/影响：direct RESULT、CLI 失败详情、wait JSON 均含 `reason_code`；job 持久化只有安全 message 与结构化摘要。读 durable record 的后续消费者无法看到闭合原因码，只能由 message 推断。
- 归属与建议：accepted plan 明示 job 只取同一公共映射的 `safe_message`，S1 不新增 job schema 字段；留给 reading-side owner（job record schema 或 Service 投影）在后续 WU 显式裁决，不要求 S1 返工。

### L2（info；私有 adapter failure 未运行时校验 persisted_summary）
- 位置：`dayu/fins/ingestion_runtime.py:587-614`。
- 证据/影响：`cause` 有精确 `isinstance` 校验，`persisted_summary` 只靠类型注解；若未来有调用方传 `None`，`_execute_download_request` 的 `_bounded_download_summary` 会抛 `TypeError`，direct/job 因此降级为 EXECUTION + 零候选摘要（fail-closed，不虚报部分摘要）。当前唯一构造点在 `cn_pipeline.py:1393`，参数来自严格投影，不可达。
- 建议：无需本轮修改；若后续该类型出现第二个构造者，可在构造器内补同形校验。

### L3（info；CLI EXECUTION 用例 fixture 使用 S2 文案）
- 位置：`tests/cli/test_output.py`（新增 EXECUTION `FinsPublicFailure`）。
- 影响：仅作为输入数据，未被断言；不会让 S2 缺失被误判为通过，但可读性上易与 S2 交付混淆。建议后续触碰时对齐当前生产文案。

### L4（info；根 README 只文档化四值之一）
- 位置：`README.md` 新增行。
- 影响：无错误；其余三个公共值共享同一修复提示，未文档化不影响可行动性。

### L5（record；已审 diff SHA 与提交 diff SHA 的差异来源）
- 见 G 节。非缺陷，但需在 closeout 记录中以提交身份为准。

## Residual Risk

- **单日 CNInfo 发现窗口未通过**：计划的 `2025-03-28..2025-03-28` 真实 CLI baseline 因 provider 第一页 `totalRecordNum=0` 未取得候选；三天窗口证据是同一 whole-kind/公共投影路径的替代证据，不冒作原命令通过；归独立 WU `fins-cninfo-single-day-discovery-window`。本审查未重跑真实网络（沙箱无外网）。
- **不确定发布状态面**：company `commit_batch` 的 precommit ValueError/OSError、post-commit release、physical swap/restore 与 rollback 双失败仍会退回零候选摘要（明确残余缺陷），归 `fins-download-indeterminate-publication-state`；S1 未宣称覆盖。
- **sibling 分类**：mid-filing `SourceIntegrityRevisionConflictError`（现为普通 filing 失败并继续循环）与 `SourceIntegrityRepairBlockedError` 仍走 EXECUTION，归 `fins-download-storage-sibling-errors`。
- **二次投影失败 failsafe**：producer/CLI 侧公共失败或日志投影自身再抛时的兜底归 `fins-direct-projection-failsafe`；S2 的未知异常安全日志尚未实施（本提交不含）。
- **S2 未实施**：未知 download 异常的脱敏 operator 调用栈、CLI `--log-file` 提示、`fins.py` 外层日志分流均不在本提交内，未由本审查覆盖。
- **隔离环境差异**：本审查在无 `.venv` 的隔离 checkout 内用共享解释器运行（已断言 `dayu.__file__` 指向本 checkout），pyright 需显式 `--pythonpath`；沙箱内 76 + 13 条既有环境失败（缺 `MIMO_PLAN_API_KEY`、pty 资源、TTY/子进程）与本提交无关，已在父提交基线逐条复现。
- **旧快照逐字不可复算**：被 F2 用例替换的 pre-commit 旧用例内容不可得（N1 延续）；fix 记录已如实披露替换，新用例覆盖了其所声明语义，但「断言语义并集」只有内容级证据。
- **测试与实现耦合**：`list_source_integrity` 调用次数、storage 私有成员（`_identity_directory_path`、`_FILING_IDENTITY_NAMESPACE`、`_ActiveBatchState`、`_validate_complete_source_tree`）被测试直接引用（既往裁决允许，不重算哈希、委托真源），对 storage 内部重构敏感；本轮未新增该类耦合。

## 结论

**pass-with-risks（无 material finding，无阻断项）**

1. 提交身份与范围闭合：HEAD/提交 SHA 与任务给定逐字一致，工作树开始时干净、收尾仅并发另一路未跟踪 artifact；30 文件表面经 Python 断言等于计划 S1 白名单 + README 按行提交 + S1 测试 + 文档，无范围外产物。
2. 已审快照等价性：逐文件增删计数与既往 review 记录逐项一致，全部引用行号在本提交解析到同一语义；唯一的 3 行 README 差分正是裁决要求的按行 staging，未发现审查后夹带改动（L5 记录该差异来源）。
3. 功能面独立复核通过：typed 失败投影无错配、映射封闭且单源；已处理快照与同请求恢复在真实 owner 链上成立且不重复计数；CLI/job/Service 语义一致（L1 记录 job durable 记录不含原因码的计划内边界）；三份 README 承诺与真实行为一致；S1 未越界到 S2。
4. 验证独立可复现：受影响八文件 846 passed、跨层 631 passed、pyright 0/0/0、两棵全量树的失败集合与父提交完全相同（净增 27 条通过用例）、5 份 CLI 留档流哈希与内容复核一致。
5. 未决项均为已登记独立 WU 与本轮方法边界，不构成本提交的阻断或未分类风险。

## 回传

CANARY=ds-flash-0dc80f65

Artifact 绝对路径：`/private/tmp/dayu-issue198-s1-aggregate/docs/reviews/deepreview-issue198-s1-aggregate-dsflash-20260929.md`
