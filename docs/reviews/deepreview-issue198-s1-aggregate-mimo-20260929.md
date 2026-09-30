RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro[1m]
CANARY=mimo-bb142a2f

# Issue #198 S1 aggregate deepreview（Gateflow aggregate `$deepreview`）

## 基线锁

- 审查对象：已接受提交 `7234d42dbaea603112c6fed52776281228d261a7`（`gateflow: accept issue-198 S1`，Leo Liu，2026-09-29 19:39:52 +0800）相对父提交 `47a9cb64e63780deb568a9e2c6fdd0120441cf2f`（`docs: accept issue 198 S1 download failure plan`）的全部变更；不审主工作区其它未提交改动，不用它们填补本快照。
- 隔离 worktree：`/private/tmp/dayu-issue198-s1-aggregate`。`git rev-parse HEAD` = 目标 SHA 逐字一致（开始与收尾各核一次）；`git status --porcelain=v1` 在审查开始与收尾均为空，无范围外 dirty 文件；审查期间未观察到并发 review artifact 落盘（如其后出现未跟踪 artifact，按任务约定不影响本提交快照）。
- 提交构成：30 个文件（8 个产品/服务源文件、3 份 README、4 个测试文件、6 个 `docs/gateflow/` S1 产物、9 个 `docs/reviews/` 产物）。文件清单核验无 `dayu/fins/storage/_fs_source_integrity.py`、`tests/fins/test_fins_storage_atomicity.py`、upload-material/oracle 等独立 WU 文件混入（Python 断言：`forbidden WU hits: none`）。
- 对齐材料（实读）：`AGENTS.md`；binding goal `docs/gateflow/issue-198-download-failure-projection-goal-20260928.md`；accepted plan `docs/gateflow/issue-198-download-failure-projection-plan-20260928.md`（含 fix8/9/10 与现行 S1 正文）；S1 implementation 两份（20260928/20260929）；S1 code review adjudication（20260928，含后续追加裁决全文）；F1 fix、F2/F3 fix；CNInfo 单日证据（20260929）；S1 最终两份有效 code review：`docs/reviews/code-review-issue198-s1-final2-mimo-20260929.md`、`docs/reviews/code-review-issue198-s1-final3-dsflash-20260929.md`（final2-dsflash 因执行协议失败被裁决为无效轮，仅作历史）。

## 结论

**pass-with-risks（aggregate）**。无阻断级 material finding。本提交在契约、跨入口一致性、owner/生命周期/错误投影上与 accepted plan 的 S1 合同一致；两路 final review 的内容结论（F2 同请求恢复、F3 私有状态真源）经本审查独立读码复核成立；旧 F1~F21 裁决项在本提交中无回退。残余风险全部落在既有登记的独立 work unit 与已声明残余内，无新增未分类风险。本结论是 aggregate 结论，不是对任一 slice review 的转述：提交级 staging 边界、14 文件快照对账、控制流逐点复核与独立验证均由本轮重新完成。

## Material findings

无阻断项。以下 3 项为低/info 级观察，不阻断 gate，不要求本提交返工：

### A1（low，文档卫生）：历史实施 artifact 保留被裁决为错误的 staging 表述，未内联更正

- 位置：`docs/gateflow/issue-198-s1-implementation-20260928.md`「工作树归属与 README」节（“两句可按 hunk 单独裁决”）。
- 证据：adjudication 的 MiMo F5 已裁决该表述错误（相邻新增行不能用 `git add -p s` 按 hunk 拆开，须 patch 编辑按行 stage），其登记状态停留在“未修复；artifact/staging 待核”；最终裁决行再次明确“必须按行分开 stage”。本提交的三份 README diff 各仅 +1 行且只含 #198 S1 句（`git show` 逐 hunk 实读），证明实际 staging 行为已按更正后的程序执行，但该 artifact 文本自身仍是被取代的旧表述，与 f1-fix artifact 附有总控结构化纠正的做法不对称。
- 影响/修法：仅记录精度；后续 closeout 或触碰该 artifact 时补一行取代说明，不改代码与本提交。

### A2（info，维护性）：同一安全消息文本在两层各自成字面量，无漂移守卫

- 位置：`dayu/fins/ingestion_runtime.py:_download_public_failure_from_exception` 的 `safe_message="本地来源完整性预检失败"`（请求级 public failure）与 `dayu/fins/pipelines/cn_download_workflow.py:_INTEGRITY_PREFLIGHT_MESSAGE`（私有 filing 行 `reason_message`）。
- 证据：二者是不同语义对象（请求级失败消息 vs 单文档行原因文本），当前文本一致使 CLI/JSON/job 的用户可读文案统一；但若一侧改词，另一侧无测试或常量约束会静默分叉。共享常量需跨层导入（runtime→pipeline 为反向依赖），本轮最小设计不引入是合理的。
- 影响/修法：登记为维护性观察；若未来两处文案需要语义绑定，由 Fins 投影 owner 单点持有并向下投影，不反向共享。

### A3（info，沿 final3 N5 复核确认）：`CnDownloadIntegrityAbort` 的 message 对 revision conflict 原因为 preflight 文案

- 位置：`cn_download_workflow.py:59-79`（构造函数无条件 `super().__init__(_INTEGRITY_PREFLIGHT_MESSAGE)`，`cause` 允许 `SourceIntegrityRevisionConflictError`）。
- 本轮复核：全仓唯一 catch 点 `cn_pipeline.py:1387` 只读 `exc.cause` 重新包装为 `FinsSourceDownloadAdapterFailure`，abort 文案不进入 public RESULT、job record、CLI/wait JSON 或日志；即便走 generic 残余路径 `str(exc)` 也是固定安全文本，无泄漏。当前无消费者投影该文案，不构成 LLM-facing 误述。
- 影响/修法：未来若新增处理器渲染 `str(abort)`，须由 owner 按 `cause` 分派文案；当前不立修复项。

## 残余风险（沿既有分类，无新增未分类项）

1. **`fins-cninfo-single-day-discovery-window`**（独立 WU）：accepted plan 的单日 `2025-03-28..2025-03-28` baseline 未满足（provider 第一页 `totalRecordNum=0`，`discovered=0`），该条验收**未通过**且不在本提交内改写；三日窗口与宽窗口真实 CLI 证据走同一生产链，仅作方法替代证据。本审查未做真实网络验证，仅复核留档证据与其自我限定文本未越界。
2. **`fins-download-indeterminate-publication-state`**（独立 WU）：precommit ValueError/OSError、post-commit release、physical swap/rollback 双失败的发布状态不确定；泛异常在已确认文档后仍退回零摘要，是**明确残余缺陷**，S1 不宣称覆盖。本提交无泛 `except Exception` 保留快照的越界收口。
3. **`fins-download-storage-sibling-errors`**：mid-filing `SourceIntegrityRevisionConflictError` 与 `SourceIntegrityRepairBlockedError` 仍走 `filing_execution_failed`/EXECUTION 兜底；本提交有注入测试锁定现状并标残余归属。
4. **`fins-other-raw-diagnostics-audit`**：generic job `_save_failed_from_exception` 的 `str(exc)` 持久化与既有 WARN `exc_info=True` 原始诊断；S1 新增 typed WARN 只含固定标识（实测无 `exc_info`/`error_type`/动态异常信息），不豁免该审计。
5. **`fins-direct-projection-failsafe`**：typed job 一次投影构造（`_download_public_failure_from_exception` / `to_json_summary()`）在非逃逸 try 之外，二次失败仍可能逃出 `_run_download_job`；direct 侧 RESULT 构造二次失败同理。S1 明确不兜底（final2 N3 复核一致）。
6. **`fins-download-no-source-retry-hint`** 与 **`fins-download-other-source-summary-conservation`**：无来源文档 hint、SEC/其它来源 typed 中止归零，均维持独立归属。
7. **测试-实现耦合**：`list_source_integrity` 调用次数、storage 私有 helper（`_identity_directory_path`、`_FILING_IDENTITY_NAMESPACE`、`_validate_complete_source_tree` 等）被测试按裁决允许的方式引用，对内部重构敏感。
8. **覆盖率方法边界**：2 项取消时序用例在 coverage 插桩下被排除（本轮与记录一致：613 passed/2 deselected），普通 suite 全量通过；插桩敏感性未调查（非 S1 语义）。
9. **S2 未开始**：未知 download 异常的脱敏 operator 调用栈、CLI 外层 catch 分流、`safe_exception_trace` 不在本提交范围，不因本 gate 宣称完成。
10. **commit/PR gate 待办**：三份 README 相邻另一 WU 点号元数据句后续须按行分开 stage（本提交已正确只含 S1 句）；merge 由用户手工完成。

## 验证（本轮独立实跑，非引用他人记录）

| 项 | 命令/方法 | 结果 |
| --- | --- | --- |
| HEAD/身份锁 | `git rev-parse HEAD` / `git rev-parse HEAD^` | `7234d42d…` / `47a9cb64…`，与目标逐字一致 |
| 工作区纯净 | `git status --porcelain=v1`（开始/收尾） | 均为空 |
| 提交文件边界 | `git show --name-only` + Python 断言 | 30 文件，独立 WU 文件 0 命中 |
| 14 文件快照对账 | `git diff --numstat <parent> <commit> -- <14 文件>` | 插入 2160 / 删除 65，对 final review 记录的 2163/65 差 3 行插入，恰为三份 README 各 1 行非 S1 点号元数据句（`git show` 逐 hunk 实读确认已按 MiMo F5 拆出）；删除数 65 逐一对上。内容级对账闭合 |
| diff 完整性 | `git diff --check 7234d42d^ 7234d42d` | exit 0，无空白错误 |
| 受影响八文件 suite | `python -m pytest tests/runtime/test_log.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/cli/test_output.py tests/cli/test_fins_commands.py tests/service/test_fins_wait_adapter.py tests/service/test_fins_direct.py -q` | **846 passed, 3 warnings**（edgartools 第三方弃用），21.40s |
| pyright | `python -m pyright --pythonpath <venv-python> dayu/ tests/ utils/` | **0 errors, 0 warnings, 0 informations** |
| 覆盖率（plan 命令，排除 2 项插桩敏感取消用例） | `coverage run --branch --source=6 个生产模块 …` → `coverage report` | 613 passed/2 deselected；`output.py` 81%、`direct_events.py` 84%、`ingestion_runtime.py` 87%、`cn_download_workflow.py` 92%、`cn_pipeline.py` 92%、`fins_wait_adapter.py` 92%（TOTAL 88%），均 ≥80%，与全部既有记录逐项一致 |

**验证环境与方法边界（如实声明）**：

- 本隔离 worktree 无 `.venv`。测试/类型检查使用 `/Users/leo/workspace/dayu-agent-r/.venv/bin/python`（Python 3.11.15）作解释器与依赖来源，并以 `PYTHONPATH=/private/tmp/dayu-issue198-s1-aggregate` 钉住本 checkout；实跑前置断言 `dayu.__file__ == /private/tmp/dayu-issue198-s1-aggregate/dayu/__init__.py` 通过。被测代码全部来自本 checkout，未导入主工作区 `dayu` 代码冒充。pyright 的 `venvPath=.`, `venv=.venv` 配置在本 worktree 无 `.venv`，故以 `--pythonpath` 指向同一解释器（输出附带一条 venv 目录缺失提示行，不影响检查结论）。
- 真实网络 CLI（CNInfo 单日/三日）未复跑：沙箱无可用 provider 网络路径；仅复核提交内证据文档及其 SHA/自限性表述，单日缺口如实保留（残余 1）。
- 协议披露：本轮唯一非零 shell 事件是首条探索复合命令的尾部 `echo ===` 被 zsh 解析为 `== not found`（`find` 检索部分已成功输出并被采用）；此为 reviewer 命令卫生瑕疵，如实披露。此后所有 shell 命令自身 exit 0；预期无匹配检索全部经 Python 捕获并断言，未留下失败命令。

## 详细审查记录

### 1. 与 slice review 的关系

最终两份有效 review（final2-mimo `mimo-aa24b3b3`、final3-dsflash `ds-flash-4d0d85f8`）均为对未提交 14 文件 diff SHA `f1e1a915…f6bd21` 的内容审查（pass-with-risks，无阻断）。本 aggregate 不把其结论当作自身结论：下述契约、控制流、跨入口、对抗项均在本提交快照上重新读码/复算；slice review 的行号引用仅作对照，不作依据来源。

### 2. 提交构成与 staging 边界（slice review 未覆盖的提交级问题）

- 三份 README diff 各仅含 #198 S1 句、自足条件（“下载显示 `classification="storage"`、`reason_code="unsafe_publication"` 时，请检查工作区来源状态并修复后重试；重复下载不会自行修复。”与 plan 裁定文本逐字一致）；点号元数据句未混入本提交，MiMo F5 的按行 stage 要求在提交行为上已闭合（文本残留见 A1）。
- 14 文件 numstat 对账（2160/65 vs 记录 2163/65）解释并确认提交内容 = final review 快照减去三行非 S1 README 句，无其它未审差异潜入。
- 提交含 9 个 review artifact（含被裁决为无效协议轮的 final2-dsflash）与 6 个 gateflow 产物，与 adjudication 的轮次登记一一对应，审计链完整；历史 artifact 的自述协议失败未被洗白，f1-fix artifact 附有总控结构化纠正。

### 3. 契约与语义 owner

- **封闭 reason 契约**：`direct_events.py:FinsDownloadFailureReason` 四值与 `storage.SourceIntegrityPreflightReason` 四值逐一对应、`.value` 相同（实读两处枚举定义）；`FinsPublicFailure.reason_code` 收紧为该 enum 或 `None`，非空时强制 `kind=STORAGE` 且 `transport_category=None`；`to_json_value()["reason_code"]` 输出 `.value` 或 `null`。`direct_events.py` 不 import storage，共享契约无仓储依赖。
- **唯一映射点**：`ingestion_runtime._SOURCE_INTEGRITY_PUBLIC_REASONS` 是 storage→public 的唯一映射，直接消费 `exc.reason`，无字符串反解析；owner 测试断言键全集=storage enum、值全集=public enum、成对 `.value` 相等（`test_fins_ingestion_runtime.py:6148-6151`）。运行时无第二份白名单（新成员漂移由测试锁定，KeyError 兜底属已声明投影二次失败残余）。
- **CLI 只渲染**：`output.py` 失败详情 `reason_code=` 输出公共 enum `.value` 或 `_EMPTY_CELL`（`"-"`）占位，不重新分类；文档行 `reason=` 自由文本语义未动（`_download_document_line` 未改）。
- **RESULT owner 放宽（fix4 修订）**：`FinsResultSummary.__post_init__` 在 `FAILURE + download` 下只拒绝 `CANCELLED` disposition（FAILED/PARTIAL_FAILURE/SUCCEEDED 允许），缺 failure、SUCCESS/CANCELLED 与 failure 混用仍拒绝；不按 `kind`/`reason_code` 放宽。与“文档终态与操作终态分离”的裁决一致，实读无回退。
- **wait 投影 owner**：`_failure_message` 拒绝 download 失败帧缺摘要，`scope_note` 固定常量 + 独立字面量逐字测试（`tests/service/test_fins_wait_adapter.py:505/534`），仅存在于 wait 失败 JSON，未扩公共 schema。

### 4. 生命周期、错误投影与同源性

- **单 filing typed 中止**：workflow 候选循环内 `except SourceIntegrityPreflightError` 先于 `except Exception`；记 1 行私有 `failed`（`reason_code="source_integrity_preflight"` 通用类别，不复制四值公开 reason）、发 1 次 `FILING_FAILED`、以同一 `filings` 快照抛 `CnDownloadIntegrityAbort`（原 cause 保留，`from exc`）。实读循环主体确认 filings 只在单 filing 流给出终态事件时追加，typed 中止不会与补行叠加成双行（与 Phase B 测试“rows 恰两行、FILING_FAILED 恰 1 次”互证）。
- **首候选前/循环前**：whole-kind 预检与无 repair 路径的 `_publish_cn_company_after_repair`（实读 `cn_download_workflow.py:283`）**不在**任何 typed catch 内 → 原始 `SourceIntegrityPreflightError` 裸透传，direct/job 走 `_empty_download_summary_from_request(..., FAILED)` 请求级零候选摘要；空 `filings` 快照派生 `SUCCEEDED` 的陷阱被 `terminal_disposition=FAILED` 断言封闭。
- **post-repair**：分类块 try 同时覆盖 `classify_source_integrity_preflight` 与其后显式 `raise SourceIntegrityRevisionConflictError`（fix10 合同）；`_publish_cn_company_after_repair` 的 post-repair 调用点（`cn_download_workflow.py:423`）单独 catch preflight → 同一 `_integrity_abort`。两处 catch 仅覆盖封闭 typed，非 typed 与物理不确定面不保留快照。`_raise_if_cancelled`/`CnDownloadCancelledError` 在 typed catch 之外，取消控制流保留原单一终态，不被后置 catch 转 FAILURE（外层唯一宽收口 `except CnDownloadCancelledError`，abort/preflight 均不被吞）。
- **adapter 边界**：仅 `CnDownloadAdapter.download` 捕获 abort；`_summary_from_integrity_abort`（只收 `integrity_failed`）与 `_summary_from_pipeline_result`（只收 `ok/cancelled`）双入口严格校验后共用纯投影 `_project_cn_pipeline_summary`；F3 修复后 `integrity_failed` 唯一定义在 workflow，pipeline 同向导入，旧 `_CN_TERMINAL_INTEGRITY_FAILED` 无残留（既有正向/负向测试与本轮 grep 实测一致）。抛 `FinsSourceDownloadAdapterFailure`（cause 类型 TypeError 限封闭两型）。
- **runtime 单点 unwrap**：`_download_exception_cause` 是唯一 unwrap 实现，direct catch、job typed catch、`_classify_direct_error`、`_download_public_failure_from_exception` 复用同一入口且幂等；direct 与 job 均经 `_execute_download_request` 的 `_bounded_download_summary` + `_validate_download_summary_request_identity` 验证后才消费 `persisted_summary`（实读 `adapter.download` 全仓唯一调用点在该验证 try 内）；direct/job 不各自遍历 `__cause__`、不解析字符串。
- **job 持久化同源**：`_save_typed_download_failure` 用同一 `failure.safe_message`（与 direct 公共消息同源）+ `summary.to_json_summary()`（与 direct 共用同一 typed summary，仅入口投影格式不同）；二次读/保存失败仅记固定标识 `fins.download.typed_failed_record_save_failed`（无 `error_type`/`exc_info`/动态异常信息），record 不虚称终态、不以 `{}` 覆盖；控制流与 `_save_failed_from_exception` 的 terminal 幂等读取 pattern 一致。
- **计数守恒**：typed 中止当前候选计一次 `failed`；post-repair 保留已有唯一终态行、`failed_count=0`、row 机械派生 terminal；未开始候选不计数不造行。与 plan 计数口径逐条相符（focused 测试断言实读）。

### 5. 跨入口一致性

同一 typed 事实投影到：direct 唯一 RESULT（`FinsResultSummary`）、job failed record（`result_summary` 精确等于同一 `to_json_summary()`、`failure_summary.message` 逐字安全消息）、CLI 失败详情/文档行、wait 失败 JSON（`scope_note` + `failure.to_json_value()` 含 `reason_code`）。四个消费面全部消费 runtime 唯一映射输出，无消费者重算 reason；三份 README 的用户语义与实际 CLI 输出字段（`classification=`/`reason_code=`）实测一致，无文档越界宣称（含未改写单日验收为通过）。

### 6. 可对抗失败（本轮独立对抗推演）

- 私有摘要校验失败（identity 不符）→ ValueError 落 EXECUTION、零候选摘要：属已登记 generic 零摘要/投影残余，不伪装 typed。
- `CnDownloadIntegrityAbort` 意外逃出 adapter（非 CN adapter）→ generic 路径 `str(exc)` 为固定安全文本，无秘密泄漏。
- revision conflict cause 带 reason_code → `FinsPublicFailure.__post_init__` 强制拒绝（非 storage/带 transport 时 ValueError），四值公开码不被 sibling 异常污染。
- `FAILURE + CANCELLED disposition`、`SUCCESS + failure`、`reason_code` 非 enum、非法 string 等负例均有 owner 测试锁定。
- 取消竞争：取消检查在 typed catch 之外，后置 typed 中止不吞取消语义；既有取消控制流八文件 suite 全绿。
- 枚举未来扩员：映射 KeyError 在投影点，由全集断言测试先于发布发现；不在运行时加第二白名单（符合 plan 明示选择）。

### 7. 文档真伪

- 根 README/`dayu/fins/README.md`/`tests/README.md` 的 S1 句与本提交行为逐条相符（映射、零候选、快照守恒、direct/job 同源、测试覆盖清单有对应测试名实证）。
- CLI 证据文档（单日/三日）自限性表述如实（单日未通过、三日为方法替代、无越界断言）；本审查未复算其原始流 SHA（证据文件在主工作区临时路径，本快照无网络/无该目录），以提交内文本自洽 + final3 的逐字复核为界，登记为验证边界。
- 历史实施 artifact 的过时 staging 表述见 A1；其余历史轮次数字（450/844/846 等）与其各自轮次状态在 adjudication 中有登记，无相互冒充。
