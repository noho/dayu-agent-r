# assets-integrate-ir15ir17-sol-20260930-01

RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol

CANARY=gpt-6-sol-99df71e4

## 预检与直接证据

- 工作区为 `/Users/leo/workspace/dayu-agent-r`，分支 `codex/upload-material-oracle`，HEAD `359f907f1cadeaa86fab3e3596dafac91e05e46d`。开始时已有大量 staged、unstaged、untracked 成果；本轮未 stage、commit、push、清理或修改主队列与 adjudication。
- I-R15 根因：此前 `admit_fins_upload_material_request` 只做 raw normalization 和资产规划，允许无 `form_type` / `material_name` 的 handoff；SEC/CN workflow 各自到执行阶段才抛裸 `ValueError`。业务身份 owner 应是 material 请求准入，所有当前动作均需这两个字段。
- I-R17 根因：此前公开 `ValidatedFinsUploadMaterialRequest.__post_init__` 只查部分字段对齐；手工构造的同值 plan 可绕过 `_normalize_upload_request` 的 strict 日期、ticker/action/source kind 与 planner 的控制名判定。runtime 对 validated handoff 直接返回，公开 SEC/CN validated stream 也直接消费。

## 修复

- `dayu/fins/ingestion_runtime.py`：`_required_material_identity` 对缺失、空串或纯空白的 `form_type` / `material_name` 产生两个封闭 typed usage code；有效字符串原样保留，不加入 O06 长度或 O17 表单规则。`_admit_material_upload_facts` 从 raw 请求统一生成规范 action、静态校验、文件选择和完整资产计划；factory 与公开 handoff 构造器都调用它。构造器比较完整 selection/plan，并承诺非可选的 `form_type` / `material_name`。公开 validated 消费的 `validate()` 与 runtime validated 分支复核同一事实。
- `dayu/fins/pipelines/sec_pipeline.py`、`cn_pipeline.py`：公开 validated stream 在首事件前调用 handoff `validate()`。SEC/CN workflow 使用 handoff 已准入的身份字段，移除各自 `None` 本地判断。`dayu/fins/tools/upload_tools.py` 保留 material 身份原始 nullable 文本供同一 owner 分类。
- `dayu/fins/upload_usage_contract.py`：新增 `missing_material_form_type`、`missing_material_name` 的封闭中文文案。按触发规则核对并更新 `dayu/fins/README.md`、`tests/README.md`、根 `README.md`。
- 成本：factory 构造时对最多 100 个 material 路径做两次纯静态规划；公开 validated 消费时再规划一次。规划不读取文件内容，不创建 job/observation，不写仓储；重复计算是公开可手工构造且可被持有后消费的 handoff 保证同源不变量的成本。无递归或私有跳过分支。

## 验证

- owner 构造反例覆盖非法日期、ticker/alias、action、source kind、缺失/空白身份和手工同值控制名计划；create/delete 的原有合法基线保留。raw runtime 覆盖 direct、observation、observed、job 前的 typed 拒绝；消费前漂移的 validated handoff 在 runtime 与 SEC/CN 公开 stream 首事件前拒绝。tool 与真实 CLI 覆盖缺失身份，断言无 observation/job/公司目录/材料发布。原有 SEC/CN material 上传、Service/runner、CLI、tool 回归仍通过。
- `source .venv/bin/activate && pytest -q --tb=short tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_service_runtime.py tests/fins/test_upload_usage_contract.py tests/fins/test_upload_asset_plan.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_tools.py tests/cli/test_fins_commands.py tests/service/test_fins_direct.py`：915 passed，3 个第三方 deprecation warnings。此后只增加 owner 构造参数反例；对应 focused pytest：4 passed。
- `source .venv/bin/activate && pyright`：0 errors、0 warnings、0 informations。
- `git diff --check && git diff --cached --check`：通过。

## 边界与残余

- 未实施 O16 delete+files、O34 公司事实独立提交、材料文件存在/普通/非空跨入口 WU，也未改 O06/O17 规则。当前 delete raw files 行为仍按既有 planner 保留。
- 本轮未测单文件覆盖率；已运行上述受影响测试和全仓 pyright。既有工作树改动与暂存区全部保留，未提交。
