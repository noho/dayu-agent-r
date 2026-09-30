# UM-O09-F01 + UM-O10-F01：material 财年与财期同源输入域

- Gate：`goal confirmation pass`；work unit：`UM-O09-F01 + UM-O10-F01`（同一 material fiscal identity owner 的两个已接受修复）；workspace `/private/tmp/dayu-upload-fiscal`，branch `codex/upload-material-fiscal`，HEAD `8d8d494fbbce0052372fb1b42097c9f7222cfa28`。
- 授权：主工作区 `docs/reviews/upload-material-um-o09-oracle-adjudication.md` 和 `docs/reviews/upload-material-um-o10-oracle-adjudication.md` 记录用户已接受具体规则；后续用户授权按 Gateflow 完成完整修复清单并汇入 draft PR #197，由用户手工 merge。两项合并为一个 work unit 是因为它们共同决定同一材料身份 seed，使用一次共享前置校验可防规则/验收漂移；修复标签仍分别追踪。

## 动机、直接证据与严重性

动机成立且是错误业务身份已发布。冻结隔离补跑 S03/S04/S05 的财年 `-1/0/10000` 原样进入 material meta 与稳定 ID；S07/S08 的超长/任意财期原样保存并进入 ID，均非 accepted 行为。当前 HEAD `FinsUploadMaterialRequest` 的 fiscal_year/period 是可选；`_normalize_upload_request` material 分支只规范化 action。晚期 `build_material_ids()` 将 year 直接 `str()` 加入 seed，并由 `_normalize_optional_upload_fiscal_period()` 仅 trim/uppercase，没有域检查。`dayu.fins.domain.filing_semantics.normalize_fiscal_period` 已有 `FY/H1/Q1/Q2/Q3/Q4` 的 canonical 规则，material 的私有实现没有复用它；filing 静态准入有 typed fiscal code，但 material 未调用。因此问题在身份输入准入与单一 canonical 事实缺失，而非转换器或仓储。

## 目标、成功信号与边界

目标一（O09）：material 可选 `fiscal_year` 提供时必须是含端点 1800–2100 的整数；非法值在身份生成、`upload.started`、job/observation 和业务持久化之前由共享 Fins material admission 给出字段明确 typed usage 拒绝。目标二（O10）：material 可选 `fiscal_period` 复用 filing 域唯一 `normalize_fiscal_period`，trim/uppercase，空或全空白 → `None`，非空仅 `FY/H1/Q1/Q2/Q3/Q4`；同一 canonical 值流向稳定 ID、source meta、manifest/对外投影中存在该字段的位置。没有独立财期长度限，枚举自然约束长度。真实隔离 CLI 验证年份域内/端点/越界、`" q1 "`、空、非法和超长，核对错误零发布、合法身份与 meta/manifest 同源；受影响 owner 测试、pyright、覆盖率及 README 职责检查通过。

非目标：不改 filing 的合法年域或 filing 域 period 真源；不改变空财期等同缺失的 accepted 行为；不处理 O05/O06 form/name、O07 ID 输入、O17 form canonical 或 action/files。不能只在 ID builder 迟报，不能在 CLI/US/CN/HK/仓储各写一套校验。O17 的 form canonical 与本 work unit 的 fiscal period 是两个独立事实，不混用同一函数。

## 语义 owner、停止条件、下一 gate

`dayu.fins.domain.filing_semantics` 拥有现有财期枚举及 canonical 解析；material fiscal_year 的 1800–2100 专属合同与两个字段的共同前置承诺应由 Fins material admission/身份直接上游输入校验实现，并让后段身份/元数据复用同一值。若代码事实证明 `build_material_ids` 或 US/CN/HK 绕过该 admission 作为受支持公开入口，plan 必须明确同源调用而非下游补偿；若要改变已接受空 period 语义、现有 filing 年域或持久化 schema，停止重新裁决。O05/O11/O16 同 admission 修改要串行集成，后者复核先前 HEAD，不保留第二套规则。当前 goal 依据用户具体裁决与本 HEAD 证据确认通过；下一 gate 是 gpt-6-sol plan，再 Kimi/MiMo 双路 plan review。不提前实施或提交产品。
