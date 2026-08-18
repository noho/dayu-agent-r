# Code Review

## Scope

- Mode: current changes
- Branch: `codex/upload-filing-oracle`
- Base: `a65cec93`（`gateflow: accept UF-FIX03 typed failure S2`）
- Output file: `docs/reviews/deepreview-uf-fix03-s3-agentds-20260813.md`
- Included scope: 未提交改动 7 文件（`dayu/cli/commands/fins.py`、`tests/cli/test_fins_commands.py`、`tests/fins/test_fins_ingestion_runtime.py`、`tests/service/test_fins_direct.py`、`README.md`、`dayu/fins/README.md`、`tests/README.md`）与 `docs/gateflow/uf-fix03-s3-implementation-20260813.md`
- Excluded scope: S1/S2 已提交改动（`607bfa4f`、`a65cec93`）及冻结 registry（只读核对）
- Parallel review coverage: 无（主 reviewer 全程走读）

## 核对基线契约

- `docs/cli_ci_scenarios.json` SHA-256 `a357e5a1…` 与 `docs/cli_ci_oracles.json` SHA-256 `88b04ca4…` 与 accepted plan §1 完全一致；两个 JSON 与 `docs/host/design.md`、`docs/engine/design.md` 均无 workspace 改动。
- 三个 accepted predicates（`docs/cli_ci_oracles.json`）：
  - `upload_filing.irrelevant-and-repeated-options`：summary 只报告实际存储/删除数量，禁止把被忽略请求文件计作 uploaded_files —— S1 已落地，S3 未触碰。
  - `upload_filing.malformed-and-empty-input`：expected「用户 stderr 只显示**文件名**和有界可理解原因，完整第三方 traceback 仅进入 debug log」—— **与 Finding 1 冲突**。
  - `upload_filing.direct-boundary-and-summary`：expected「不创建 Host Run/Attempt/EventLog/Memory/Tool Trace、Host/runtime SQLite 或 legacy ingestion job；summary 区分 requested_files 与 stored_files」—— 正控回归已落地（见残余风险中路径派生的轻微脆弱性）。
- `docs/host/design.md`、`docs/engine/design.md`：本 S3 无 Host/Engine 契约变化，plan §6.3 判定不更新成立，两文件 git 干净。
- UF-PF03：未执行（S3 artifact 声明 + workspace 无新增 evidence 文件），符合 plan §3.1。

## Findings

### 1-未修复-高-真实 CLI stderr 不展示 canonical file label，违反 frozen predicate 与 accepted plan S3 精确断言

- **入口/函数**: `dayu-cli upload_filing` → `render_fins_direct_event` → `_print_terminal_business_summary` → `_summary_parts`（真实 CLI 失败摘要渲染）
- **文件(行号)**: `dayu/cli/output.py:65`（`_FINS_SUMMARY_MAX_ITEMS = 8`）、`dayu/cli/output.py:504-509`（cap 处 break）；`dayu/fins/ingestion_runtime.py:6358-6397`（`_upload_result_details` 顺序）；`tests/cli/test_fins_commands.py:1675`（真实 CLI corrupt 测试未断言 label 存在）
- **输入场景**: 真实 CLI 上传损坏 PDF/DOCX（或空文件），typed content failure 携带 canonical `file_label`
- **实际分支**: failure 摘要 details 顺序为 source kind(1)、status(2)、requested files(3)、stored files(4)、failure kind(5)、failure code(6)、failure message(7)、retry hint(8)、file(9)。content failure 的 `retry_hint` 恒非 `None`（`dayu/fins/upload_failure.py:184,221`），故 `file` 恒第 9 项；`_summary_parts` 在第 8 项处 break
- **预期行为**: frozen predicate `upload_filing.malformed-and-empty-input` 要求「用户 stderr 只显示文件名和有界可理解原因」；accepted plan S3 §Tests first #2 要求「stderr包含各自canonical label、closed content kind/code与bounded reason」；plan §5.4/§5.5 要求 CLI 消费 reason 中的 canonical label
- **实际行为**: 实证真实 CLI 输出仅含 `Fins failure: … message="文件无法解析或已损坏，请检查文件后重试"` 与 `Fins summary: source_kind="filing" status="failed" requested_files="1" stored_files="0" failure_kind="content" failure_code="docling_converter_execution" failure_message="…" retry_hint="…"`——无 `file=` 字段，canonical label 完全不进入普通 stderr；且该测试只断言 failure_kind/code 与有界性，plan 要求的 label 断言被静默降级，S3 artifact 将其列为「Assigned to later work unit」
- **直接证据**: 对真实 CLI 运行 corrupt PDF 的 stderr 全文检查，`grep -c "corrupt.pdf"` 为 `0`；`_upload_result_details` 与 `_FINS_SUMMARY_MAX_ITEMS` 的代码路径如上
- **影响**: 违反本任务两个 frozen accepted predicate 之一与 accepted plan 的可行动公开 reason；用户对多文件/损坏上传无法从 stderr 定位具体文件；该缺口被留待后续而非回 plan gate 裁决，属本任务契约违约
- **建议改法和验证点**: 回 plan gate 做 owner 裁决：或 `_upload_result_details` 将 `file`/`retry hint` 前移（ingestion_runtime 不在 S3 allowed files，越界即停止）；或 `output.py` cap 差异化/提高（同样越界）。修复后补 CLI 断言 `file="corrupt.pdf"`（及 canonical 隐藏标签场景）出现在 stderr，并同步更新 S3 artifact 的 deferred 条目为已裁决状态
- **修复风险（中）**: 涉及两个 owner 的展示契约调整，需 controller 裁决而非实现者自行选边
- **严重程度（高）**

### 2-未修复-中-unknown failure 固定文案在默认临时日志下不可行动

- **入口/函数**: `run_fins_direct_command` generic `except Exception` → `render_cli_error`（`dayu/cli/commands/fins.py:218-226`）
- **文件(行号)**: `dayu/cli/commands/fins.py:99,223-225`；`dayu/cli/main.py:189-194`（`_open_default_log_file` 返回匿名 `tempfile.TemporaryFile`）；`README.md:180-182`（声明默认诊断日志进程结束即清理）
- **输入场景**: 用户以默认参数（不传 `--log-file`）运行 direct 命令并命中未知内部异常
- **实际分支**: stderr 固定输出「命令执行失败，请查看日志后重试」；traceback 经 `_LOGGER.exception` 进入默认临时日志
- **预期行为**: plan §9.2 假设「完整细节仍在 operator log」可抵消固定文案的信息损失，即文案对用户可行动
- **实际行为**: 默认日志是匿名 `TemporaryFile`，进程退出即删除且路径从不公布；用户读到提示时日志已消失，文案也未提及唯一可行动出口 `--log-file`。旧实现虽泄漏 `str(exc)`，但至少默认可见；本次修改在默认配置下把未知失败降为完全不可诊断
- **直接证据**: `dayu/cli/main.py:189`（`tempfile.TemporaryFile`）、`dayu/cli/main.py:128-137`（finally 中关闭并删除）、`README.md:180-182`（「未传 `--log-file` 时，诊断日志只保留到当前 CLI 进程结束」）
- **影响**: 未知内部异常时默认 stderr 提示对用户不可行动，排障必须依赖 README 知识重跑 `--log-file`
- **建议改法和验证点**: 最小 in-scope 修复：固定文案改为提及 `--log-file`，例如「命令执行失败，请使用 --log-file <path> 重新运行以查看诊断日志」（常量与 catch 均在 S3 allowed 文件内）；或回 plan gate 裁决把默认自动日志落到已知 workspace 路径并公布位置。验证：`test_unknown_fins_direct_failure_logs_traceback_and_hides_exception_from_stderr` 同步更新 exact stderr 断言
- **修复风险（低）**: 仅文案变更；若改默认日志落盘位置则需 plan gate
- **严重程度（中）**

### 3-未修复-中-plan S3 精确断言 #5 未实现：无任何 CLI 层测试断言渲染后的 requested/stored 摘要

- **入口/函数**: CLI 渲染层 `_summary_parts` / `_print_result_details` 对 upload summary 的用户可见投影
- **文件(行号)**: `tests/cli/test_fins_commands.py`（全文件）、`tests/service/test_fins_direct.py`；对照 `dayu/cli/output.py:496-509`
- **输入场景**: success / delete / skip / failure 任一 upload 终态的 CLI 摘要渲染
- **实际分支**: 渲染路径存在但无测试覆盖
- **预期行为**: accepted plan S3 §Tests first #5 要求「success/delete/skip/failure CLI摘要分别显示正确requested/stored；不显示uploaded_files」
- **实际行为**: 全仓 `grep 'requested_files=\|stored_files=' tests/` 与 `grep 'Fins summary' tests/` 均零命中；S3 新增断言全部停留在 direct RESULT details dict 层（`tests/fins/test_fins_ingestion_runtime.py` 新增正控/失败测试），CLI 渲染边界无 count 回归护栏
- **直接证据**: 三个 S3 allowed 测试文件的 diff 中无任何 CLI 渲染层 count 断言；`tests/cli/test_fins_commands.py` 现有 `Fins summary` 断言仅存在于 download 场景且不校验 count
- **影响**: frozen predicate `direct-boundary-and-summary`（summary 区分 requested/stored）在用户可见边界无护栏；renderer cap 或 detail 顺序变化会静默破坏用户可见 counts 而不被任何测试发现
- **建议改法和验证点**: 在 `tests/cli/test_fins_commands.py` 用 fake service 注入 success/delete/skip/failure 终态 RESULT，断言 stdout/stderr 摘要含 `requested_files=`/`stored_files=` 正确值与 `uploaded_files` 缺失；与 Finding 1 的 renderer 修复在同一 gate 落地
- **修复风险（低）**: 纯测试补齐，fake 事件构造沿用现有 `_result_event` 模式
- **严重程度（中）**

## Open Questions

- 无。

## Residual Risk

- 正控 no-artifact regression 的负事实断言总体直接（`executor.operations == []`、`WorkspacePaths` 的 host_dir/host_sqlite/artifact_root/runtime_lanes_db 不存在、真实 source/company/blob 读回正控），但 `jobs_dir` 路径在测试中硬编码为 `".dayu/fins_ingestion/jobs"` 而非从 `default_runtime.ingestion_job_store.root_dir` 派生，若生产 `_JOBS_DIR_PARTS` 迁移该护栏会静默失守（低）。
- 失败路径（empty/corrupt/mixed）的零发布断言覆盖 company meta 与 source meta，未直接断言 blob 树；依赖「source meta 不存在 ⇒ blob 目录不存在」的同一路径推理（低）。
- 未在本轮复跑 S3 artifact 声称的 focused/broader pytest、pyright 与 coverage 数字（用户指示收敛）；artifact 声称 363/468 passed、pyright 0 error、总 coverage 88%，其中 `cn_pipeline.py` 69% 未达 plan 逐文件 ≥80% 阈值，需 controller 显式裁决（S3 未修改该文件）。
- broader 回归中 `tests/fins/test_fins_ingestion_tools.py::test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect` 的基线 fixture 失败（S2 prevalidation 新契约所致），归后续 work unit，不在 S3 修。
- 真实 Docling 多平台差异与 UF-PF03 evidence 按 plan 明确排除。
- 三个 README 的更新均符合各自「Agent更新约束」章节的读者与内容边界；根 README 新增句与现有「默认日志进程结束即清理」说明一致。

## 结论

NEEDS_FIX。Finding 1 为 blocker：真实 CLI 普通 stderr 不展示 canonical file label，直接违反 frozen accepted predicate `upload_filing.malformed-and-empty-input` 与本任务 accepted plan S3 的精确断言 #2，且实现以静默弱化测试 + 「留待后续」处理，未按 plan §7 停止并回 plan gate——按用户裁决规则不得接受 deferral。Finding 2、3 需与 Finding 1 在同一修复 gate 内收敛。
