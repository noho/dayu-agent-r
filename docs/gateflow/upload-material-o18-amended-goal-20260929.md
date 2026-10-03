# UM-O18-F01：material amended 单一发布事实 goal confirmation

- Gate：goal confirmation pass。隔离工作区 `/private/tmp/dayu-upload-o18`，分支 `codex/upload-material-o18`，基线 HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`，开始时干净。
- 用户已接受 `docs/reviews/upload-material-um-o18-oracle-adjudication.md` 中保留并实现 `--amended` 的方向，随后授权全部修复进入 PR #197。冻结 A16/A17 同时改变内容和标记，不证明同内容标记切换的行为；本目标不冒称已有因果证据。

## 动机与直接代码证据

CLI、Service、tool 及 `FinsUploadMaterialRequest` 接受 `amended`，`ingestion_runtime.py` 的请求摘要也记录它；但 `service_runtime.py` 将 material 请求转入 SEC/CN/HK pipeline 时未传该值，material workflow 的事件、`prepare_upload` meta 与结果也无此字段。`docling_upload_service.py` 中现有 `amended` 读取是 filing 分支，不能说明 material 已持久化。当前 source meta/manifest 缺该事实，用户请求与已发布材料状态分叉；内容版本因文件变化而升，不可替代 amended 事实。

## 目标与成功信号

1. `amended` 作为**当前发布材料是否修订**的布尔业务事实，由 material 请求/发布 owner 验证并写入 source meta；manifest、事件/结果与存在该字段的摘要只从同一事实投影。CLI、Service、tool、batch plan、US/CN/HK workflow 全链路传递同一值，不各自推导或从内容版本/文件名反推。
2. `amended` 不参与稳定 material ID；内容变化仍由现有内容/发布版本规则决定版本。A16 式未传标记首次发布为 false/v1，A17 式同身份新内容带标记为 true/v2；隔离真实 CLI 对照还覆盖同内容仅改标记、内容改但标记不改、首次带标记、delete/恢复。plan 必须为这些状态转换提出 owner 级精确规则并在 code review 前验证，不能被相同指纹 skip 吞掉元数据变更。
3. source meta 与 material manifest 的 amended 值、稳定 ID、版本、跨命令读取及用户可见结果一致；owner/入口测试、受影响测试、pyright、逐修改生产文件 >=80% coverage、README 职责检查与独立真实 CLI 证据完整。

## 边界与停止条件

不改 filing amended 参与 filing 身份的规则，不改 material 内容抽取/格式能力或 O13/O14/O15/O33 的独立动作/并发合同。schema 如需变更按全新 schema 起库，不做旧库兼容；material manifest 现有字段归属必须先读仓储类型确认，不能凭冻结摘要推断。若“同内容仅改标记”与现有 skip/版本 owner 不能在不分叉真源的前提下实现，plan 须列直接反例并提出最小裁决点，不在 CLI 展示层补偿。下一 gate：Sol plan → Kimi/MiMo 双路 planreview。
