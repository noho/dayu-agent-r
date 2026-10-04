# 资产 S1 整合复审 I-R23～I-R26 修复记录

RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol
CANARY=gpt-6-sol-1480043b

## 范围与根因

- I-R23 动机成立。`plan_upload_assets` 在完整 `UploadAssetPlan` 构造前先调用 `FinsUploadMaterialFiles.from_upsert_paths`，后者逐项检查格式，导致混合控制名或重复 basename 与不支持后缀时，planner 先给格式错误；裸计划则先给资产名称原因。该差异会改变 CLI/tool 可见的 code、标签和文案，属同一资产计划 owner 的优先级分裂。
- I-R24 动机成立。旧 `UploadAssetPlan.validate()` 用 `filing_primary_original_name is not None` 推断来源类型；直接 material Service 只复核计划自身，不核对 Service 期待的来源类型，因此 filing 形态计划能在 material 分支读取原件后才被 fingerprint 拒绝。正确边界是计划契约与直接消费处。
- I-R25 为本切片测试死导入；I-R26 是裸计划 101 项分支缺少判别性回归，现行生产分支本身已正确拒绝。

## 实施

1. `UploadAssetPlan` 增加必填 `source_kind: SourceKind`。构造及 `validate()` 先校验显式类别，再据此验证非空 filing 的主文件身份、material 不携带主文件、各类原件和 Docling 命名、转换子集及 material 数量/名称/格式；空 delete 计划也保留类别身份。更新所有 19 个当前构造点。使用一个计划类型和一个显式枚举字段，是本调用图中比拆成两个类型更小、且不靠主文件名反推类别的单真源设计。
2. material planner 对可规范化的整批路径先构造完整计划，再构造格式受限的 selection；路径规范化失败仍交给原有整批名称分类。保留既有数量、重复规范路径、控制名、重复 basename、非法名、碰撞、格式优先级；合法输入的 selection 与 plan 保序不变。
3. `DoclingUploadService._prepare_upload_asset_plan` 在计划 owner 校验后检查其显式来源类型是否为 material，先于文件存在性、`read_bytes`、转换、batch 或发布拒绝 filing 计划。不在 fingerprint 或入口展示层重复 material 名称规则。
4. 删除四个测试模块中的本切片死导入，同时删除两个同测试模块的既存死导入；未调整这些测试的业务断言。按 README 触发规则更新 Fins 开发手册、测试手册及最终用户上传说明；未改分层装配关系。

## 验证

- owner 测试对 `META.JSON + deck.zip` 和 `same.txt` 两次重复加 `deck.zip` 的输入顺序反转，逐项比较 planner/裸计划的封闭原因、安全标签、完整 usage 文案；CLI/tool 测同样输入及公开错误码、文案、无任务启动。原有合法同 stem 不同后缀、100 文件上限、错误优先级和 filing 路径仍由相邻测试覆盖。
- 裸 material 计划直接构造 101 个不同名合法 pair，断言 `TOO_MANY_FILES`；另把已构造 material 计划损坏成 101 pair，直接调用 Service，断言零读取、零 converter、零发布。与此独立，filing 形态计划用单个 `META.JSON` 和 101 个原件分别作为 material selection，均在文件读取前拒绝；owner 测试锁定来源类型与主文件、命名一致性。
- 聚焦 `test_upload_asset_plan.py`、`test_docling_upload_service.py`、`test_fins_commands.py`、`test_fins_ingestion_tools.py`：479 passed。相邻十个上传/运行时/Service 测试文件：初跑 655 passed、1 skipped、1 failed；唯一失败是旧断言预期泛化“身份不一致”，新 owner 更早给出“material 资产计划不得携带 filing 主文件身份”。更新断言后该用例复跑 1 passed，其余 655 项未重跑。单项 `META.JSON` 与 101 filing 形态的最终 Service 测试复跑 2 passed。
- 全量 `python -m pyright dayu/ tests/ utils/`：0 errors、0 warnings、0 informations。`git diff --check` 与 `git diff --cached --check`：通过。

## 风险与边界

- 未运行真实 Docling 后端转换或全量测试矩阵；本切片关键承诺由计划 owner、直接 Service、CLI/tool 和相邻上传链测试覆盖。
- Service 对跨来源类型的手工计划返回 `ValueError`，属于直接调用方违反计划契约；material 原始用户输入仍使用现有封闭资产规划原因与 usage 投影。
- 主工作树已有大量 staged、unstaged 和 untracked 成果；本记录不代表整合 gate 通过。未 stage、commit、push、PR、merge，也未修改总控队列或 adjudication。
