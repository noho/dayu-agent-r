RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/GPT-6
CANARY=gpt-6-sol-e194ab6e

# Assets S1 code review：I-R9/I-R10/I-R11/I-R13 修复记录

任务 label：`assets-integrate-ir9ir13-sol-20260930-01`。工作树为 `/Users/leo/workspace/dayu-agent-r`；预检与最终核对均在 `codex/upload-material-oracle`、HEAD `359f907f1cadeaa86fab3e3596dafac91e05e46d`。原有 staged、unstaged 与 untracked 成果保留；本轮未 stage、commit、切分支、push、PR、merge、reset 或修改主队列、裁决文档及独立 review 工作树。

## 动机与 owner 复核

- I-R9 成立，严重性限于测试合同：`plan_upload_assets` 承诺 filing 保序选择及同源计划，未承诺返回同一个 Python 对象。owner 测试改用值相等、`ordered_files`、`require_primary()` 与 companions 断言；生产 planner 不变。
- I-R10 成立，当前没有即时超限错误，两类上限恰好都为 100 不能作为关系证据。`dayu/fins/upload_format_contract.py` 分别定义 `MAX_FILING_UPLOAD_FILES` 和已有 `MAX_MATERIAL_UPLOAD_FILES`；filing 静态准入只消费前者，material planner 及其文案继续消费后者。共享 tool `files.maxItems` 取两者最大值，不错误限缩任何类别；当前工具说明分别写明 filing/material 上限，各类准入执行细分规则。`_MAX_TUPLE_ITEMS` 继续只管 aliases/通用 tuple/metadata，不再承担 filing 文件数业务事实。owner/真实 tool 测试锁住关系，而非只锁住两个值碰巧相等。
- I-R11 成立，tool 对私有 `_validate_fins_upload_filing_static` 及私有返回结构的导入越过模块边界。静态准入 owner 新增公开 `admit_fins_upload_filing_selection(request)`，返回同次完整静态验证产生的 `FinsUploadFilingFiles`，具有工具在 observation 前验证文件状态所需的实际语义。tool 只消费该公开选择；CLI、Service、runtime 仍由同一私有静态验证真源取得完整身份/状态事实，没有第二张验证表或兼容 wrapper。
- I-R13 成立，原先先记录所有路径形状错误，再扫描组件名，导致同一个 `INVALID_ASSET_NAME` 的标签偏向形状阶段。planner 的规范化结果现在保留原始输入索引；组件错误只在索引更早时覆盖标签。控制名 reason 优先、重复/碰撞既有顺序、delete 分类、循环链接操作失败与公开文件标签 canonicalizer 均未改。正逆序测试覆盖反斜杠组件名、未知用户目录及多字节超长组件，并区分可见与隐藏标签。

## 验证

- 激活 `.venv` 后，受影响 owner、真实 tool、CLI、Service 与 service runtime 共 7 份测试文件：`840 passed`，另有 3 条第三方 edgar 弃用告警。最后一处测试类型收窄后，变更的聚焦用例再跑 `2 passed`。
- 激活 `.venv` 后运行 `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- 三个涉及的模块分别在新 Python 进程独立导入成功，未发现导入环。
- `git diff --check` 与 `git diff --cached --check` 均通过；HEAD 与分支未变。
- 按 README 触发规则检查并更新 `dayu/fins/README.md` 的公开准入/schema 边界和 `tests/README.md` 的测试合同描述。根 README 的安装、CLI 参数及最终用户工作流未变；分层/装配关系未变。

## 风险与范围

共享 schema 表示两类请求共同可容纳的最大数组长度；若未来两类上限分化，较低上限的类别仍会由其静态准入返回 typed 用法错误，工具说明也会从各自常量投影。此次只跑受影响及相邻矩阵，未跑全仓测试。I-R12 既存 material 英文文案、O16 action+files 业务规则及其它独立 work unit 均未修改。
