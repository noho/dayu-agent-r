# UM-O17-F01 plan PR4 修复记录

状态：仅修订 plan；O17/O09/O05 产品行为均未实施。基线 HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`。

## SHA-256 与修复映射

- 修订对象：`upload-material-o17-form-plan-20260929.md`。
- 旧 SHA-256：`37d1c13e98e4db78d9ce02afe2dd6e92c53cead7e544690daa84e8845c4a3baf`；实施修改前已按文件字节核对，与任务锁定值一致。
- 新 SHA-256：`7c818f9dbc2a8276b5a47a49918307efb8437823b6c2cb677b3743b1e34eacd8`。

| 裁决项 | plan 修订 | 直接证据与边界 |
| --- | --- | --- |
| PR4-F1 | 串行集成段登记 O09-F01：`fiscal_year` 1800–2100（含端点）在 `build_material_ids` 生成 ID seed 前校验；实施 gate 按最终 HEAD 复核 O09/O17 合入先后、校验位置及 seed 顺序；O17 不预支财年域规则。切片 2 的不顺带实施清单同步列入 O09。 | `docs/reviews/upload-material-um-o09-oracle-adjudication.md` 明确 owner、域及未实施状态；当前 `dayu/fins/pipelines/docling_upload_service.py:1820-1856` 的 `build_material_ids` 仅将 `fiscal_year` 转字符串放入 seed，没有该域校验。 |
| PR4-F2 | 切片 7 指向 tool 入口真实 material 事件流与 pipeline 结果 JSON 中的 `form_type`，以及 runner 收到的准入后 request；排除无 form 字段的 observation snapshot、result summary 和 result details。 | `dayu/fins/pipelines/sec_upload_workflow.py:509,582,610`、`dayu/fins/pipelines/cn_pipeline.py:1125,1198,1226` 的事件/结果有 form；`dayu/fins/ingestion_runtime.py:4714-4744` 返回准入后 material request、`:5012` 将其交给 runner，`dayu/fins/ingestion/observation_handle.py:137-152`、`dayu/fins/ingestion_runtime.py:1798-1828,6903-6945` 的对应快照/摘要/详情无 form 字段。 |

原计划的唯一 `normalize_material_form_type` owner、O05 的 `None`/空白边界、合法 padded form 跨命令仓储读回、历史 raw 独立 WU、逐文件 coverage 与 README 条款保留。本轮没有改 goal、旧 review/裁决、产品、测试或 README；没有安装依赖或执行实现 gate。

## 检查与命令状态

- 预检 plan SHA、HEAD、指定文档和代码路径均由本 checkout 读取；新 SHA 由文件字节计算。文档修订不触及 Python 代码，本轮未运行测试或 pyright，留待实施 gate 按 plan 执行。
- 一次探索性 `rg` 因误写 `dayu/fins/ingestion/ingestion_runtime.py` 而 exit 2；随后用 `rg --files dayu/fins` 确认真实路径为 `dayu/fins/ingestion_runtime.py`，再从正确路径读到 owner/结果投影。其余检查命令 exit 0；该失败未用于结论。
