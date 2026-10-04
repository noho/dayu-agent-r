# UM-O11-F01：material 日期真实公历前置校验

- Gate：`goal confirmation pass`；work unit：`UM-O11-F01`；workspace `/private/tmp/dayu-upload-o11`，branch `codex/upload-material-o11`，HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`。
- 授权：主工作区 `docs/reviews/upload-material-um-o11-oracle-adjudication.md` 记录用户接受修复方向，后续用户授权按 Gateflow 完成全部修复并纳入现有 draft PR #197，由用户手工 merge。

## 动机与直接证据

动机成立且严重性是错误日期事实已持久化。冻结 S10/S11 各用非法 `filing_date` / `report_date`，exit 0、meta/manifest 原样保存；它们是历史观察，不能代替本 HEAD 证据。当前 `dayu/fins/domain/filing_semantics.parse_iso_calendar_date` 是 strict 日期真源；Fins filing 的 `_validate_optional_upload_iso_date` 已复用它并以 `INVALID_FILING_DATE/INVALID_REPORT_DATE` typed usage code 拒绝。material request 两日期仍为 `str | None`，`_normalize_upload_request` 的 material 分支只规范化 action，不校验日期；`FinsIngestionRuntime.upload/prepare_observed_upload/start_upload` 都在建事件流/observation/job 前调用 `_validate_runtime_upload_request`。因此应在共享 material admission 直接复用现有日期 owner，避免 US/CN/HK、CLI、tool、仓储各建规则。

## 目标、成功信号、边界

目标：material 非空 `filing_date` 与 `report_date` 仅接受严格 `YYYY-MM-DD` 且实际存在的公历日期，分别给出字段明确的 typed usage failure；校验早于 upload lifecycle、公司/文档持久化和 meta/manifest，direct/job/tool/Service 从同一 admission 事实派生。合法日期在所有投影保持一致。CLI 已接受的显式空 `--filing-date ""` → `None` 保持；不以此推定公开 raw request/tool 的空值政策，也不从 S09 类推空 `report_date` 成为新增承诺。真实隔离 CLI 验证非法各一、合法对照与显式空 filing_date、零发布、退出/双流；补 owner 测试、pyright、单文件覆盖率和 README 职责检查。

非目标：不定义新日期格式、时区或模糊解析；不改 fiscal_year/period（O09/O10）、material form/name（O05/O06/O17）、manifest schema 或其它业务状态；不在 CLI 或市场 pipeline 补下游 fallback。日期 helper 的已有 `parse_iso_calendar_date` 与 typed usage code 应优先复用。若新证据表明这些 code 只允许 filing 且 material 无法同源复用，plan 必须说明 owner 与最小 public contract 修改，不可悄然复制校验。

## 停止条件、依赖和下一 gate

若代码证明某公开 material 入口绕过共享 admission，或严格校验会改变已接受的显式空 filing_date CLI 语义，停止 implementation 并记录具体调用链；若需新 schema/日期规则，也停止重新裁决。O05/O16/O11 触及同一 admission 函数，独立 worktree 只允许串行集成到 PR，后集成者复核前者 HEAD 并保持一个 owner。本 goal 依据用户既有裁决与本 HEAD 证据确认通过；下一 gate 是 gpt-6-sol plan，随后 Kimi/MiMo 双路 plan review。此处不实施或提交产品。
