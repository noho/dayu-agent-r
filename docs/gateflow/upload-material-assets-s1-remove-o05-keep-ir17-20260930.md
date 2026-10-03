# 资产 S1：撤出 O05 提前实施并保留 I-R17

## 范围与直接证据

- 主工作树：`/Users/leo/workspace/dayu-agent-r`；分支：`codex/upload-material-oracle`；HEAD：`359f907f1cadeaa86fab3e3596dafac91e05e46d`。本记录只描述未提交的当前候选，不替代总控裁决。
- `upload-material-o05-required-identity-goal-20260929.md` 的 O05 仍为 goal pass；本次整合必须等其它分支全部并入且近远端同步后才能实施尚未实施的 WU。此前 I-R15 的 form/name 前置 typed 必填与 O05-F01 是同一规则，属于提前实施，改为 **deferred-to-UM-O05**。
- I-R17 的独立根因是公开 `ValidatedFinsUploadMaterialRequest` 可手工构造，而旧构造器只查资产局部对齐；validated 消费可绕过 raw `_normalize_upload_request` 的 O11 严格日期和静态准入。其 owner 是 material handoff 构造和公开消费边界，不依赖 O05 身份必填规则。

## 逐项撤出与保留

1. 从 `ingestion_runtime.py` 撤出 `_required_material_identity`、material admission 的 form/name 前置拒绝、validated handoff 中非可选的 form/name 派生字段及其漂移检查。raw request 的 `str | None` 和原文保持不变；手工构造与 factory 仍共用 `_admit_material_upload_facts`，验证日期、ticker、action、source kind、文件选择与完整资产计划。公开 validated 消费继续调用 `validate()` 复核同一事实。
2. 从 `upload_usage_contract.py` 撤出两个 O05 专属 typed code 与文案。工具恢复原有 `_required_text` 对 form/name 的入口校验；SEC/CN workflow 恢复原有 `None` 判断及执行阶段 `ValueError`。这保留了各入口旧失败时序，没有添加下游兼容分支。
3. 移除 raw runtime、tool、真实 CLI 对 O05 前置 typed 拒绝及零生命周期副作用的测试承诺；撤回旧测试中仅为满足提前准入补上的 form/name 参数。新增 owner 回归确认 create/delete 的缺失与空白原文可通过静态 admission，缺失值在 SEC/CN workflow 原位置失败。I-R17 回归继续覆盖手工构造的非法日期、ticker、action、source kind、控制名，以及 runtime 和 SEC/CN 公开 validated 消费前漂移时零事件、零 job、零发布。
4. 删除根 `README.md` 中 O05 已上线的用户承诺；`dayu/fins/README.md` 和 `tests/README.md` 改为描述当前静态准入、公开 handoff 复核及既有身份失败位置。
5. I-R9/I-R10/I-R11/I-R13、其它资产 S1 修复和 O34 公司事实独立提交语义未改。未实施 O06、O16、O17 form canonical 或 material 文件状态 WU。未 stage、commit、push、PR、merge、改 main、修改主修复队列或 adjudication。

## 验证

- `source .venv/bin/activate && pytest -q --tb=short tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_service_runtime.py tests/fins/test_upload_usage_contract.py tests/fins/test_upload_asset_plan.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py tests/fins/test_fins_ingestion_tools.py tests/cli/test_fins_commands.py tests/service/test_fins_direct.py`：**913 passed**，3 条第三方 edgartools deprecation warnings。
- `source .venv/bin/activate && pyright`：**0 errors、0 warnings、0 informations**；另有版本更新提示。
- `git diff --check && git diff --cached --check`：通过；产品代码和测试中不再有 O05 专属 typed code、helper 或前置必填承诺。

## 残余风险与移交

- material form/name 在当前各入口的旧校验位置并不统一；这是 deferred-to-UM-O05 的已知目标，不能在本次 S1 集成中提前收口。
- I-R17 复核在公开 validated handoff 构造和消费时重复执行纯静态规划；未触发文件内容读取、job 或仓储写入。未做单文件覆盖率测量，也未进行新的双路同版 code review；总控应基于本候选重新裁决后续 gate。
