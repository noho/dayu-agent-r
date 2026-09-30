# Code Review

RUNTIME/PROVIDER/MODEL: codex/kimi/<进程内不可自省实际模型；按派发通道记 kimi，Codex CLI 0.157.1>

CANARY=kimi-c9124371

## Scope

- Mode: current changes
- Branch or PR: `codex/upload-material-assets`，工作区 `/private/tmp/dayu-upload-assets`
- Base: HEAD `1453a659a79d4c9a93838412dfdecfa7feeddf98`（全部改动未提交：tracked working-tree diff + 未跟踪新文件）
- Output file: `docs/reviews/code-review-assets-s1-final-kimi-20260929.md`
- Included scope: 32 个 tracked 修改文件（17 生产 + 4 README + 11 测试）、6 个未跟踪生产/测试新文件、accepted goal/plan、总控裁决 F1–F14/R1/R2、各 Sol 修复记录；真实入口 CLI/Service/tool/runtime/SEC/CN pipeline/Docling service/storage 三 walker 全链路
- Excluded scope: O05/O16/O25/O34 等后续工作单元；旧冻结 oracle；另一 reviewer（MiMo）并发 artifact 的内容（不照抄，独立核证）
- Parallel review coverage: 无，未派发子 Agent

## 锁定核验

- HEAD `1453a659a79d4c9a93838412dfdecfa7feeddf98`：一致。
- tracked `git diff --binary` SHA-256 `05d8977450722aa7cefbd51607ceec14721a1301b7d109ab4e98d46213b6c14b`：一致。
- 未跟踪生产 owner：`asset_filename_contract.py` `c2c91eee…`、`upload_asset_plan.py` `707d12a7…`、`upload_usage_contract.py` `eac24f88…`：全部一致。
- F14 记录表内其余 16 个未跟踪文件中 15 个一致；**偏差**：`upload-material-assets-s1-code-review-adjudication-20260929.md` 当前 SHA `ddcc2b7d…` 与表中 `65ebb9e3…` 不符。该文档末节为「Sol F14 候选核验」，与总控在 Sol 定稿 F14 记录后追加核验节的行为一致；关键生产 owner 锁全部一致，不触发停止条件，如实登记。
- 审查期间另一 reviewer 的 `docs/reviews/code-review-assets-s1-final-mimo-20260929.md` 新出现（任务预期的并发写），F14 记录表先于其存在；本 reviewer 未读取其内容，结论独立形成。

## Findings

### 001-未修复-低-`docling_upload_service.py` 残留 `FinsUploadMaterialFiles` 死导入
- **入口/函数**: 模块 import 块
- **文件(行号)**: `dayu/fins/pipelines/docling_upload_service.py:59-62`（名字在第 61 行）
- **输入场景**: 任意导入该模块
- **实际分支**: `from dayu.fins.upload_format_contract import (FinsUploadFilingFiles, FinsUploadMaterialFiles)`
- **预期行为**: F4 裁决要求删去本切片残留的 `FinsUploadMaterialFiles` 死导入（SEC/CN 两处已删）；模块签名改为 `FinsUploadFilingFiles | UploadAssetPlan` 后不应再引用该符号
- **实际行为**: 全文件仅 import 行出现该符号（逐行扫描确认唯一命中），无其它消费点
- **直接证据**: 全文件符号扫描唯一命中第 61 行；`__all__` 亦不含该符号；pyright 当前配置不报未使用 import，故矩阵绿不能掩盖
- **影响**: 仅局部卫生问题，无运行时错误；但与已接受的 F4 同类且在本切片边界内
- **建议改法和验证点**: 从 import 块删除该名字；复跑 `tests/fins/test_docling_upload_service.py` 与 pyright
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 002-未修复-低-两处改动函数的 docstring 与现行为不符
- **入口/函数**: `_validate_runtime_upload_request`、`_build_pending_assets`
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:4631`（Returns 段）、`dayu/fins/pipelines/docling_upload_service.py:932`（Args `preparation` 段）
- **输入场景**: 读者按 docstring 理解契约
- **实际分支**: 不适用（文档偏差）
- **预期行为**: 按项目中文 docstring 约束，改动函数的契约描述应与现行为一致
- **实际行为**: `_validate_runtime_upload_request` Returns 仍写「material 返回既有 normalized request」，实际 raw material 经 `admit_fins_upload_material_request` 返回 `ValidatedFinsUploadMaterialRequest`，Raises 段也未列 material 的 `FinsUploadUsageError`；`_build_pending_assets` 仍写「入口 typed selection 投影的 ordered/converter inputs」，实际参数已是 `UploadAssetPlan`
- **直接证据**: `ingestion_runtime.py:4656-4664` 的实际返回与 `docling_upload_service.py:932-958` 的签名
- **影响**: 仅文档准确性；不影响执行
- **建议改法和验证点**: 按现行为改写两段 docstring；无需行为测试变化
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- filing planner 双输入单权威签名（`_prepare_upload_asset_plan` 在 pipeline 边界对 filing 重新规划）沿用总控裁决文档已登记 OQ；本片两次求值均为同一纯函数，未观察到身份漂移，是否收敛由后续 owner 决定。
- 001/002 两个低严重度项是否在本片收口，由总控裁决；均不阻塞语义正确性结论。

## Residual Risk

- **既有失败（非本切片引入）**：`tests/service/test_import_boundary.py::test_service_does_not_import_forbidden_layers` 在本 HEAD 独立失败：`dayu/service/fins_direct.py:26` import `dayu.fins.download_contract`、`dayu/service/fins_wait_adapter.py:26` import `dayu.fins.company_metadata_warning` 两个越界在 HEAD 已存在，该测试文件未被本切片修改；`fins_direct.py` 的本片改动未新增该 import。12/13 复跑通过后的唯一稳定失败即此项。
- **环境/负载抖动**：全量 `tests/fins`+cli+service 带 coverage 运行时 12 个时序敏感用例失败（`test_docling_process_converter` spawn 2s 超时 4 例、`test_fins_storage_atomicity` 并发 barrier 4 例、`test_fins_storage_provider` 3 例、`test_sec_pipeline_upload_filing_stream` spawn 1 例）；不带 coverage 单独复跑 12/12 通过，归因于共享机负载与 coverage 减速，非本切片回归。
- 验证复用主仓共享虚拟环境 `/Users/leo/workspace/dayu-agent-r/.venv`（与既有记录一致）；coverage 采用先预加载 `dayu.documents.processors.registry` 再启动 coverage API 的既有 workaround。
- 未重跑真实 Docling 完整发布；混合超长名与代理字符名无法在本文件系统创建/作 argv，沿用 planner/tool JSON 边界证据（与各轮记录一致）。
- `test_upload_usage_contract.py` 存在精确断言 240 码点填满文案的紧度（总控已登记 R2 非阻断残余）。
- adjudication 文档 SHA 漂移（见锁定核验）；F14 记录自身 SHA 未回读校验（记录声明其在交付报告列出）。

## 独立核证结论（F1–F14/R1/R2 抽检）

- F1：`ValidatedFinsUploadMaterialRequest.__post_init__` 构造期校验 filing primary 为空、converter 与 ordered 保序值相等、delete 唯一空、非 delete 按同一 normalize 比较 raw 与 selection/plan；未引入 O16 的 delete+files 新规则。F5：runner/Service/runtime 对 validated handoff 对象身份直通不重入 admission；`upload_failure` 斜杠白名单为整条 MISSING_FILES 文案精确匹配。F7：值相等比较。
- F2/F6：标签预算按模板前后文扣除，独立探针两目录同名 `"a"*222/225/230/235+".txt"` 均得 typed `duplicate_original_basename` 且消息恰 240 码点、无绝对路径、category 为 `asset_plan`；`"a"*240` 退固定隐藏标签；无裸 ValueError。
- F3：`dayu/fins/README.md` 指纹公式已改为「原件 name/sha256/size/source，派生名不参与」，失实断言移除。
- F4：SEC/CN 死导入已删；另见新 finding 001。
- F8/F10/F13：planner 先数量/重复路径/重复 basename，逐路径收口 `UnicodeEncodeError/ValueError/RuntimeError` 为 INVALID 候选并继续扫描，控制名立即抛，碰撞最后；独立探针 NUL、未知 `~user`、高代理单独及与 `META.JSON` 正逆序均为封闭 reason 且控制名优先；操作性 `PermissionError` 注入透传原实例（owner 测试钉住）。
- F9/F11：`canonicalize_fins_rejected_file_label` 为非法形状名给固定隐藏标签，严格 canonicalizer 未放宽；隐藏判定含 Cc/Cf/Cs。
- F12：tool/CLI material 只构造原始 `Path`，先唯一 admission 再在边界做原文件状态预检；tool 不再内联 resolve；action→identity→文件名分类顺序有测试钉住。
- F14：`FinsUploadUsageCategory.REQUEST/ASSET_PLAN` 由 usage owner 校验，planner 投影为唯一 ASSET_PLAN producer，tool 只读 fact category、不再 import planner 类型或读 `__cause__`；真实 tool 有/无 cause 同结果测试存在并随矩阵通过。
- R1/R2：正逆序混合冲突与多字节/Cc 标签 240 预算测试存在并通过。
- batch/skip/version/manifest：`DoclingUploadService` 原件/派生/primary/指纹全部消费同一 `UploadAssetPlan`；filing 身份字节规则不变（owner 测试含 digest 复算）；material 指纹公式与 README 一致；storage 三 walker exact 语义不变且有新共享集合测试；数量 100/101 与受控 100 次调度有 owner 证据。

## 独立验证证据

- 锁/canary：见「锁定核验」；canary 文件内容逐字为 `kimi-c9124371`。
- owner 测试：`test_upload_asset_plan.py + test_upload_usage_contract.py + test_storage_asset_filename_contract.py` 54 passed。
- accepted plan 相邻矩阵（17 文件）：1248 passed、1 skipped（既有 skip）、3 条 edgar 第三方 deprecation warning。
- 全量 `tests/fins` + `tests/cli/test_fins_commands.py` + `tests/service`：2653 passed、13 failed、1 skipped（归因见 Residual Risk；该命令 PYTEST_RC=1，不因后续绿测抵消，已逐条归因）。
- `python -m pyright`：0 errors、0 warnings、0 informations。
- 逐改生产文件 coverage（全量矩阵、同一 venv）：20/20 ≥80%——`asset_filename_contract.py` 100%、`storage/__init__.py` 100%、`_filing_upload_fresh_validation.py` 100%、`fins_direct.py` 100%、`upload_usage_contract.py` 94.55%、`service_runtime.py` 94.83%、`upload_tools.py` 93.75%、`sec_upload_workflow.py` 93.75%、`observation_handle.py` 93.70%、`cn_pipeline.py` 92.95%、`_fs_maintenance_core.py` 92.42%、`upload_asset_plan.py` 92.21%、`ingestion_runtime.py` 92.05%、`docling_upload_service.py` 89.81%、`direct_events.py` 89.17%、`filing_upload_publication.py` 87.36%、`_fs_source_integrity.py` 86.96%、`sec_pipeline.py` 86.67%、`upload_failure.py` 96.10%、`cli/commands/fins.py` 86.21%。
- 真实 CLI（隔离 `--base`，子进程）：缺失文件 exit 2 且原文案 `upload file does not exist: <resolved>`、工作区未建立；未知 `~user`（引号防 shell 展开）exit 2 且 `文件名无法安全保存：x.pdf；请缩短或重命名后重试`、无原始 RuntimeError 文本、工作区未建立；101 个 `--files` exit 2 `--files 数量不能超过 100 个`；100 个 `--files` 通过数量 admission 后由原预检 exit 2，证明 100 侧被接受。
- 直接探针：见「独立核证结论」F2/F6 与 F8/F10/F13 条；全部 exit 0。
- 失败命令披露：记忆索引 `rg` 搜索 exit 1（预期无匹配）；全量测试 13 failed（已归因）；其余命令均 exit 0。临时 coverage runner 写于 `/private/tmp/kimi_cov_runner.py`、coverage 数据在 `/private/tmp/kimi-cov-data/`，工作区唯一新增 artifact 为本文件。

## 结论

pass-with-risks：F1–F14/R1/R2 修复内容经独立代码走读、探针、真实 CLI 与矩阵复核未发现语义回退；新增 2 个低严重度 finding（死导入、docstring 偏差）与 1 项既有 import boundary 失败、1 项 adjudication 文档 SHA 漂移登记，是否收口由总控裁决。本 reviewer 不提交、不集成、不宣告 code gate 通过。
