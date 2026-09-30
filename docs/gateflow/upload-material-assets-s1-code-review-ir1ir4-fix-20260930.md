RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol
CANARY=gpt-6-sol-de6d3d11

# 资产规划同版复审 I-R1～I-R4 修复记录

- 工作树：`/Users/leo/workspace/dayu-agent-r`，分支 `codex/upload-material-oracle`，HEAD `359f907f`；仅修改当前主工作树，未创建分支或 worktree，未提交、推送、创建 PR 或合并。
- 原始报告：`docs/reviews/code-review-20260930-085630.md`；总控登记：`docs/gateflow/upload-material-assets-s1-code-review-adjudication-20260929.md` 末尾及 `docs/gateflow/upload-material-issue-198-repair-sequence-20260928.md` 主队列。本记录只覆盖 I-R1～I-R4，不裁决 O16 或 PR197-R1 F2～F7，不宣布 gate pass。

## 动机与直接证据

- I-R1 成立：共享路径 owner 将未知用户目录的 `expanduser()` 失败从 `RuntimeError` 转成 `ValueError`，filing 准入仍只捕 `OSError/RuntimeError`；CLI 与 tool 在 filing owner 之前各自 `expanduser().resolve()`。同一用户路径可在 Service 抛裸异常、在 tool 被误报为启动失败。原始非法 basename 还可能被严格 public label 校验再次拒绝。
- I-R2 成立，未触发“行为证据与报告相反”的停止条件：`git show 359f907f:dayu/cli/commands/fins.py` 的 `_validated_upload_files` 对 raw 路径逐个检查存在性和普通文件；旧 `ingestion_runtime.py` 的摘要及进度均无条件执行 `_validate_upload_file_count(raw_request.files)`。当前 delete 计划为空且 CLI 只查 selection，因而放行缺失 raw 文件；raw 数量与权威 selection 数量分离。
- I-R3 成立：裸 `UploadAssetPlan.validate()` 和 `filing_original_storage_name()` 直接调用 `Path.resolve`，Python 3.11 的自引用符号链接抛含绝对路径的 `RuntimeError`；共享路径 owner 已有 `OSError(ELOOP)` 无路径明文投影。
- I-R4 成立：`prepare_upload` 的 material `selection` 已是资产计划，docstring 仍称通用 typed selection；路径 owner 的 Raises 有重复 `OSError` 条目。

## 修复与 owner

- I-R1：`dayu/fins/ingestion_runtime.py` 的 filing 静态准入捕获共享路径 owner 的 `OSError/ValueError`，文件标签统一经 rejected-label owner 投影为封闭 `FILE_NOT_FOUND`。`dayu/cli/commands/fins.py` 和 `dayu/fins/tools/upload_tools.py` 把 filing 原始 Path 交给同一静态准入；tool 在该准入后保留普通文件及非空状态预检。不根据异常文案或下游 cause 重建语义。
- I-R2：`dayu/fins/upload_asset_plan.py` 在 material delete 早退前校验 raw 文件数量，上限仍为 100；CLI 在 delete 准入后恢复 raw 路径的存在性和普通文件守卫，合法 raw 文件仍得到空 selection/plan。`dayu/fins/ingestion_runtime.py` 的 `validated_fins_upload_file_count` 从 filing authoritative selection 或 material asset plan 给出唯一上传数量；`dayu/fins/service_runtime.py` 与 SEC/CN pipeline 的摘要、进度、结果复用它。delete 携带合法 raw 文件时文件数为 0。
- I-R3：资产计划构造、再次校验和 filing 仓储身份校验复用 `normalize_upload_asset_path` 的循环链接操作失败分类；`OSError(ELOOP)` 消息不带绝对路径。Docling 直接消费损坏计划时先校验后读取。
- I-R4：更新 `DoclingUploadService.prepare_upload` 与 `normalize_upload_asset_path` 的中文参数、返回和异常说明；相关计划构造/验证 docstring 增补 `OSError`。

## 精确文件

- 生产代码：`dayu/cli/commands/fins.py`、`dayu/fins/ingestion_runtime.py`、`dayu/fins/upload_asset_plan.py`、`dayu/fins/tools/upload_tools.py`、`dayu/fins/service_runtime.py`、`dayu/fins/pipelines/cn_pipeline.py`、`dayu/fins/pipelines/sec_upload_workflow.py`、`dayu/fins/pipelines/docling_upload_service.py`。
- 测试：`tests/cli/test_fins_commands.py`、`tests/fins/test_upload_asset_plan.py`、`tests/fins/test_fins_ingestion_tools.py`、`tests/fins/test_fins_ingestion_runtime.py`、`tests/fins/test_fins_service_runtime.py`、`tests/fins/test_docling_upload_service.py`、`tests/fins/test_sec_pipeline_upload_material_stream.py`。
- README：`README.md`、`dayu/fins/README.md`。已检查 `tests/README.md` 的更新边界；没有新增测试层级、运行方式或维护规则，不再修改该文档。
- 记录：`docs/gateflow/upload-material-assets-s1-code-review-ir1ir4-fix-20260930.md`。

## 验证与过程失败

- 首轮聚焦 `pytest -q -p no:randomly tests/fins/test_upload_asset_plan.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py tests/cli/test_fins_commands.py tests/fins/test_docling_upload_service.py`：**3 failed, 838 passed**。失败均为旧断言仍期待 delete 放行 101 项或旧 tool 英文文案；测试按 owner 合同迁移。
- 首轮 `python -m pyright dayu/ tests/ utils/`：**2 errors**，旧 service 测试向已收窄的结果汇合函数传 raw request；测试改用 validated handoff。
- 聚焦复跑（上述五文件加 `tests/fins/test_fins_service_runtime.py`）：**865 passed**。新增真实公开入口覆盖 filing unknown-home/NUL/代理码位/反斜杠循环、material delete 缺失文件/目录/101 项、裸计划与 Docling 直接消费循环链接，以及 durable 摘要/进度/结果数量。
- 相邻矩阵：`pytest -q -p no:randomly tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_docling_upload_service_integration.py tests/service/test_fins_direct.py tests/service/test_fins_wait_adapter.py tests/fins/test_upload_usage_contract.py tests/fins/test_upload_format_contract.py`：**209 passed, 1 skipped**。
- 新增 SEC 真实 delete 正控首跑 **1 failed**：测试构造 create 请求漏了必填公司名；补齐后单例 **1 passed**。随后 pyright 曾报告测试 `**dict` 展开造成 **10 errors**；改为显式构造参数。`test_sec_pipeline_upload_material_stream.py` 全文件最终 **14 passed**。
- `pytest -q tests/fins/test_upload_asset_plan.py --cov=dayu.fins.upload_asset_plan --cov-report=term-missing:skip-covered`：**33 passed，规划 owner 覆盖率 90%**。
- 最终 `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：**0 errors, 0 warnings, 0 informations**。最终 `git diff --check`：**exit 0**。测试运行均有第三方 `edgar` deprecation warnings。
- 一次 README `apply_patch` 因待匹配的长行不精确而失败，按实际文本重新应用成功；记忆注册表 `rg` 查询无命中（exit 1），没有据此使用历史结论。

## 剩余风险与交接

- O16 对 material delete 携带 files 的最终业务规则未裁决；当前仅保留合法文件的既有 delete 行为并恢复旧输入守卫。tool 自身仍按其现有工具参数规则拒绝 delete 携带 files。
- 高代理码位和 NUL 不能通过常规文件系统 argv 建立真实文件；以公开 Service/tool JSON 及 owner 边界验证安全失败，CLI 对可达的 unknown-home 与合法文件/缺失文件执行了真实子进程测试。
- 尚待总控锁定本主工作树内容并做同版双路复审。本次不宣告 code gate pass。
