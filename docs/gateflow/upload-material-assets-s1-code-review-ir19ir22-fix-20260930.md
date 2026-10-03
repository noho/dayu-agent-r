# Upload material 资产 S1 整合审查 I-R19～I-R22 修复记录

- 工作树：`codex/upload-material-oracle` 主工作树；保留原有 staged、unstaged 和 untracked 成果。本次不 stage、commit、push、建 PR 或推进总控裁决。
- 依据：`AGENTS.md`、资产 S1 goal 与 code review adjudication、`code-review-20260930-112050.md`、`code-review-20260930-112741.md`；以当前代码和测试复核 finding，不把冻结审查快照当作当前真源。

## 动机与直接证据

1. **I-R19 成立，严重性低。** `ingestion_runtime.py` 的 `FinsUploadFormatFailureKind`、`sec_upload_workflow.py` 的 `Path`、`service_runtime.py` 的两个 raw request 类型、`fins_direct.py` 的 raw material request 只在导入处出现；后者同一已编辑导入块内的 raw filing/request 两项也未被使用。删除七项导入不涉及运行分支。
2. **I-R20 成立，严重性低。** CN/SEC 两份 material pipeline 测试的 `("create" or "auto")`、`(None or "auto")`、`tuple([x] or ())` 在当前用例中恒等于左侧值；SEC 的 `tuple(files or ())` 中 `files` 为已建立的列表。审查列出的 35 个恒等子表达式及同块另一个列表表达式均改为直接字面量或 tuple，事件序列与断言未改。
3. **I-R21 成立，严重性中。** `plan_upload_assets` 原来检查控制名、碰撞、material 后缀与派生名长度，`UploadAssetPlan.validate` 原来只检查 exact 原件名、路径和派生一致性；`DoclingUploadService._prepare_upload_asset_plan` 只调用 `selection.validate()`。因此手工裸计划可跳过 planner 的业务名规则。语义 owner 明确为 `dayu/fins/upload_asset_plan.py` 的资产计划契约；service 已在任何文件校验、读取、转换和发布前调用该契约。修复无需在 service 重写规则。
4. **I-R22 成立，严重性低。** planner 原先先遍历重复 basename，后扫描控制名；`same.txt`、`same.txt`、`META.JSON` 在两个顺序之一可能先报重复名，违反已有“整批控制名优先”的注释和测试。原因优先级由资产规则 owner 决定。

## 改法

- 将 material 控制名、组件安全、255 字节派生名、duplicate basename、Unicode/casefold 碰撞和格式 capability 收进私有纯函数 `_validate_material_asset_names`。`UploadAssetPlan.validate` 与 planner 共用这一个规则；planner 仅在路径形状已经失败时提前用该函数完成混合输入分类，正常输入交给 plan 构造校验，避免另建真源或递归。计划自身也校验 material 100 文件上限。filing 身份与选择规则未变。
- 固定顺序：规范路径重复仍由 planner 先拒绝；整批控制名优先；duplicate basename 仍先于非法名；非法名先于跨资产碰撞；格式后缀最后检查。这样仅调整控制名与重复 basename 的冲突次序，保留其余既有分类。直接构造或直接消费非法 material plan 时，在读取前抛出原 owner 的 typed 资产或格式错误。
- 删除 I-R19 七个死导入；清理 I-R20 恒等表达式；更新一个原先期待非法裸计划构造成功的 handoff 测试，使其断言构造期拒绝，并保留被篡改计划在 handoff 被拒绝的断言。
- 按 README 触发规则核对根 `README.md`、`dayu/fins/README.md`、`tests/README.md`。Fins 开发手册与测试手册补充已实现的边界和覆盖；根用户手册所描述的公共 CLI 行为未变化，故不改。

## 验证

- 新增 owner 反例覆盖裸计划的 casefold、Unicode 组合名、控制名、非法 material 后缀、超长派生名；direct service 反例将构造后计划损坏，确认同样拒绝且零文件读取、零 converter 调用、零发布树。
- duplicate basename 与 `META.JSON` 两种输入顺序均断言 `RESERVED_CONTROL_NAME`、安全标签 `META.JSON`、完整 usage 文案和 retry hint。既有合法 material 发布与 SEC/CN 事件序列测试继续通过。
- 激活 `.venv` 后运行 17 个受影响及相邻测试文件：**1386 passed，1 skipped**；三个第三方 `edgar` 弃用警告。全量 `python -m pyright dayu/ tests/ utils/`：**0 errors、0 warnings、0 informations**。`git diff --check` 通过；目标测试文件的恒等表达式扫描无剩余命中。

## 残余与边界

- 未做真实 Docling 后端转换或外部数据上传；相关负例用受控 converter 和真实 service 入口验证转换前拒绝，合法发布由既有相邻测试覆盖。
- O05 form/name 前置 typed 必填、O06、O16、O17 form canonical、material 文件状态、CNInfo 单日及其他未实施 work unit 仍由总控后续处理；本次未改 O34 公司事实独立提交语义。
