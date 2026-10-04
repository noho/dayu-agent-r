RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol
CANARY=gpt-6-sol-61d1466d

# UM-O04/O23 资产规划 F15～F20 修复记录

日期：2026-09-30。工作树：`codex/upload-material-oracle` 主工作树。仅记录本次候选修复；未提交、推送、合并或宣告 code gate 通过。工作树开始时已有 #198/O11 与资产切片的 staged/unstaged/untracked 改动，本次没有覆盖 CLI material 日期原文校验：非空但带首尾空白的日期仍在 Service factory 前由共享准入拒绝。

## 动机、owner 与改动

- **F15**：真实符号链接自循环使 Python 3.11 `Path.resolve(strict=False)` 抛 `RuntimeError`，旧 planner 将其误归 `INVALID_ASSET_NAME`。`dayu/fins/upload_asset_plan.py` 现将用户目录展开阶段的 `RuntimeError` 转成输入 `ValueError`，解析阶段的循环转成无路径明文的 `OSError(ELOOP)`；planner 仅把输入形状错误映射为 sealed usage。现有工具 `fins_upload_start_failed`、CLI exit `1` 与公共 `storage_io` 为操作失败投影，不新增公开 code。真实循环、NUL、未知用户目录及控制名混合顺序在 owner/入口测试中覆盖。
- **F16**：裸 `UploadAssetPlan` 的冻结字段原先不保证彼此一致。计划 owner 的 `validate()` 同时用于构造和 `DoclingUploadService` 直接消费边界，校验规范路径、material 原件名与完整派生名、全部保序转换输入，以及 filing 原件身份与唯一 primary 转换子集。损坏计划在文件读取、转换和发布前被拒绝。没有在下游按文件内容或异常文本重算身份。
- **F17**：`dayu/fins/upload_usage_contract.py` 对四种规划专属 code 增加 `REQUEST` 反向拒绝，保留 `missing_files`、`too_many_files`、`duplicate_file_path` 等共享 code 的双类别合法性。工具继续只读同一 typed usage fact。
- **F18**：`dayu/fins/upload_format_contract.py` 的 LLM-facing `files` 说明现直接写出 material 上限、完整原件文件名重复、控制文件、本批原件/派生名冲突和 `deck.txt -> deck.txt_docling.json` 示例；控制文件名从 storage 的 `DOCUMENT_SOURCE_CONTROL_FILENAMES` 真源投影。实际 tool schema 测试断言这些规则存在。
- **F19/F20**：删除 `docling_upload_service.py` 的死导入；更新 `ingestion_runtime.py::_validate_runtime_upload_request` 与 `docling_upload_service.py::_build_pending_assets` 的中文参数、返回和异常说明，不更改行为。

## 精确修改文件

生产代码：`dayu/fins/upload_asset_plan.py`、`dayu/fins/upload_usage_contract.py`、`dayu/fins/upload_format_contract.py`、`dayu/fins/pipelines/docling_upload_service.py`、`dayu/fins/ingestion_runtime.py`。

测试：`tests/fins/test_upload_asset_plan.py`、`tests/fins/test_upload_usage_contract.py`、`tests/fins/test_upload_format_contract.py`、`tests/fins/test_docling_upload_service.py`、`tests/fins/test_fins_ingestion_runtime.py`、`tests/fins/test_fins_ingestion_tools.py`、`tests/cli/test_fins_commands.py`。

README：`README.md`（CLI 路径循环对用户可见的退出分类）、`dayu/fins/README.md`（计划 owner 与操作失败边界）、`tests/README.md`（本层测试范围）。检查了三份文档的职责约束；无其它 README 的职责触发。本文档也是本次新增交付物。

## 验证

- 受影响 pytest：`source .venv/bin/activate && python -m pytest -q tests/fins/test_upload_asset_plan.py tests/fins/test_upload_usage_contract.py tests/fins/test_upload_format_contract.py tests/fins/test_docling_upload_service.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/cli/test_fins_commands.py`；最终 881 passed，3 条第三方 edgar 废弃警告。
- 相邻 SEC/CN 与 Docling 集成 pytest：`source .venv/bin/activate && python -m pytest -q tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_docling_upload_service_integration.py`；103 passed、1 skipped，3 条相同的第三方警告。
- 类型：`source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`；最终 0 errors、0 warnings、0 informations（另有 pyright 可升级提示）。
- 覆盖率命令：`source .venv/bin/activate && python -m pytest -q tests/fins/test_upload_asset_plan.py tests/fins/test_upload_usage_contract.py tests/fins/test_upload_format_contract.py tests/fins/test_fins_ingestion_tools.py --cov=dayu.fins.upload_asset_plan --cov=dayu.fins.upload_usage_contract --cov=dayu.fins.upload_format_contract --cov-report=term-missing:skip-covered`；最终 195 passed；计划 90%、格式 93%、usage 94%。
- `git diff --check`：exit `0`，无空白错误。运行后仅修改了本记录文字。

## 过程失败命令与处理

- 首轮聚焦 pytest（资产计划、usage、格式、Docling Service、ingestion runtime）：4 failed / 576 passed。原因分别为新双向 usage 约束下旧 owner 测试未提供类别、格式文案精确断言未更新、filing 冲突提前到计划构造、handoff 旧异常文案断言；测试迁移到新的 owner 边界。
- 首轮完整受影响 pytest：1 failed / 880 passed。新 tool 循环测试误写公开 error 为 `job_start_failed`；实际固定 code 是 `fins_upload_start_failed`，已修测试断言。其后同一矩阵 881 passed。
- 诊断命令 `source .venv/bin/activate && python -c '...'` 对真实自循环链接调用 `Path.resolve`，按预期 exit `1`，trace 证明 Python 3.11 抛 `RuntimeError: Symlink loop from ...`；测试使用该直接根因证据，不依赖异常文本分类。
- 两次 README `apply_patch` 因目标段落是长单行而匹配失败，随后按唯一锚点完成同一文档更新；首次工具编排 JavaScript 存在括号语法错误，重试后正常读取。两个探索 `rg`（memory 关键词、子目录 AGENTS.md）因无匹配 exit `1`，不代表测试失败。

## 残余风险与后续

- `UploadAssetPlan.validate()` 仅保证本 finding 所需的原件、路径、转换与主文件身份；真实路径存在性/普通文件、material 文件名碰撞等其余准入仍由已有 planner 和入口负责。本次不扩展 O16、O25 或 PR197-R1 F2～F7。
- 没有运行真实 Docling 长转换或全仓测试；当前证据为受影响矩阵、真实 CLI/tool 前置失败、owner 覆盖与类型检查。最终同版 MiMo/ds-flash 复审和 gate/PR 裁决留待总控。
