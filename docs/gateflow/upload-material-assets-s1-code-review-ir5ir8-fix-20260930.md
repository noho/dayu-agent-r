RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol

# assets-integrate-ir5ir8-sol-20260930-01 修复记录

CANARY=gpt-6-sol-ff029304

## 预检与边界

- 工作区：`/Users/leo/workspace/dayu-agent-r`；目标分支 `codex/upload-material-oracle`，起始 HEAD `359f907f1cadeaa86fab3e3596dafac91e05e46d`。主工作树已有大量 staged、unstaged 和未跟踪的资产集成改动；本轮未重置、切分支、暂存、提交或操作远端。
- 原始审查：`docs/reviews/code-review-20260930-093046.md`；总控裁决：`docs/gateflow/upload-material-assets-s1-code-review-adjudication-20260929.md`，I-R5～I-R8 为 accepted。O16 的 action+files 最终规则未裁决，本轮没有改写。
- 根因核证：`plan_upload_assets` 对 material delete 在数量检查后直接返回空 selection/plan，未经过 upsert 使用的 raw 路径解析；CLI 的 raw 文件存在性/普通文件守卫随后独立解析路径，使未知用户目录的 `ValueError` 从 typed usage 逃为 exit 1。`UploadAssetPlan.validate()` 已按保序值比较，两个 `is` 只在测试；上限文本字面量与 schema 常量分离；指纹函数 Args 保留旧参数名。

## 实际修改

1. **I-R5**：在 `dayu/fins/upload_asset_plan.py` 抽取 material raw 路径规范化过程，upsert 与 delete 共用。delete 在空 selection/plan 早退前分类未知用户目录、NUL、非法 Unicode 等形状错误为 `INVALID_ASSET_NAME`；循环链接的无路径明文 `OSError` 保持操作失败。数量上限仍先判；合法 delete 的 selection、plan、实际文件数仍为空/零。CLI 原有 raw 文件存在与普通文件守卫保留。
2. **I-R6**：`tests/fins/test_upload_asset_plan.py` 两处 tuple/条目 `is` 断言改为保序值相等；增加 material 与 filing 各自使用等值、不同对象的 converter 条目构造成功的 owner 正例。既有值不等反例保留。
3. **I-R7**：`MAX_MATERIAL_UPLOAD_FILES` 只定义于 `dayu/fins/upload_format_contract.py`。planner、usage/failure 投影、tool schema 的 `maxItems` 与 LLM 可读文案均引用该常量；相应测试从真源断言文案和 schema 一致。未向 LLM 文本暴露内部常量名；没有循环导入或兼容 re-export。
4. **I-R8**：`_build_upload_source_fingerprint` 的中文 Args 改为 `filing_primary_original_name`，说明其为资产计划中的 filing 主文件原件仓储身份，material 为 `None`；函数逻辑未改。
5. README 触发检查：`dayu/fins/README.md` 补充 material delete raw 路径分类的稳定设计边界，`tests/README.md` 补充本轮 owner/CLI 回归范围。根目录 `README.md` 已准确说明 material 文件名用法错误、delete raw 文件状态守卫/零文件数与循环链接操作失败，故未修改；未触及其他 README 的职责范围。

## 验证

- `source .venv/bin/activate && python -m pytest -q tests/fins/test_upload_asset_plan.py tests/fins/test_upload_format_contract.py tests/fins/test_upload_usage_contract.py tests/fins/test_fins_ingestion_tools.py tests/cli/test_fins_commands.py tests/fins/test_docling_upload_service.py`：`487 passed, 3 warnings`（三条 edgartools 依赖弃用提示）。真实 argv CLI 覆盖 delete 未知用户目录 exit 2、零工作区副作用，create/delete 循环链接 exit 1，以及已有 delete 缺失文件、目录、101 路径守卫；NUL 无法进入 argv，由 `cli_main.main` 参数边界回归覆盖。
- `source .venv/bin/activate && python -m pytest -q tests/fins/test_upload_asset_plan.py tests/cli/test_fins_commands.py --cov=dayu.fins.upload_asset_plan --cov-report=term-missing`：`217 passed, 3 warnings`；`dayu/fins/upload_asset_plan.py` 覆盖率 `90%`。
- `source .venv/bin/activate && pyright`：最终复跑 `0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。

## 残余风险与停止边界

- O16 的 delete+files 三入口最终业务规则仍未裁决；本轮维持 CLI raw 存在/普通文件检查、delete 空选择与零文件数，没有统一或拒绝该动作组合。
- CLI 为保留既有 raw 文件状态守卫，仍在 planner 分类成功后对 delete raw 路径解析一次；它不再承担可修正路径形状的失败分类。两次检查间的文件系统变化仍遵循既有预检时序。
- 本轮未执行全仓 pytest；已执行受影响测试、真实 CLI 回归、planner 单文件覆盖率和全量 pyright。修复到此停止，交由总控继续裁决和 review。
