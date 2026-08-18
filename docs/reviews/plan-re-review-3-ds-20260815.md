# Plan Re-Review（第三轮 · AgentDS）：UF-FIX06 converter-capability-owner N1 追加裁决后计划

## Review Metadata

- **Reviewed target**：`docs/gateflow/uf-fix06-converter-capability-owner-plan-20260815.md`（N1 plan fix 后修订版，575 行）
- **Reviewer**：AgentDS（N1 原提出者，本轮为第三轮 re-review）
- **Timestamp**：2026-08-15T14:38:51+0800（系统时钟生成）
- **Baseline commit**：`a3d584fcf1444fcf5d633f2dd8bdb83eaf5adab9`
- **Review inputs**（均已完整读取至 EOF）：
  - 原 plan N1 修订版：`docs/gateflow/uf-fix06-converter-capability-owner-plan-20260815.md`（575 行）
  - plan-fix 记录（含 N1 修复状态）：`docs/gateflow/uf-fix06-converter-capability-owner-plan-fix-20260815.md`（147 行）
  - 第二轮 re-review：`docs/reviews/plan-re-review-2-ds-20260815.md`（133 行，N1 出处）、`docs/reviews/plan-re-review-2-mimo-20260815.md`（147 行）
  - Controller 追加裁决：`docs/reviews/uf-fix06-plan-re-review-adjudication-20260815.md`（61 行，第二轮 re-review 追加裁决段）
- **Review scope**：只验证 N1 是否按 Controller 追加裁决完全修复（`upload_failure_reason_from_json` 同步识别 `USAGE/UNSUPPORTED_UPLOAD_FORMAT`、owner test 明确 round-trip 相等并继续拒绝未知/错配），并确认第二轮 R1/R2/R3 与第一轮 M1/M2/D1–D5/O1/O2 无回退。不重裁 goal，不新增 scope 建议。只做 review；未修改 plan/代码/测试/README/registry/evidence，未 commit，未运行任何 PF。
- **核心判据**：追加裁决的每个可验证要点是否落到 plan 的 Slice 3 contract 与测试文本中；实现 agent 是否仍存在该守卫的自裁决空间。

## 一、N1 逐项验证（追加裁决 vs plan 证据 vs 代码事实）

Controller 追加裁决要点：`USAGE/UNSUPPORTED_UPLOAD_FORMAT` 是 closed failure contract 的新成员，`upload_failure_reason_from_json` 的 kind/code 一致性推导必须同步识别 usage code，否则合法 usage failure 无法 round-trip；Slice 3 必须明确扩展该守卫，并在 `tests/fins/test_upload_failure.py` 增加 usage reason 的 `to_json -> upload_failure_reason_from_json` 相等断言，同时保持未知/错配 kind-code 继续拒绝。

| 追加裁决要点 | plan 证据 | 状态 |
|---|---|---|
| Slice 3 明确点名 `upload_failure_reason_from_json` 的 kind/code 一致性推导同步扩展 | Slice 3 Exact changes #6："同步扩展 `upload_failure_reason_from_json` 的 kind/code 一致性推导，使 `UNSUPPORTED_UPLOAD_FORMAT` 唯一推导为 `USAGE`，同时保持未知 code 与错配 kind/code 拒绝" | 已修复 |
| `UNSUPPORTED_UPLOAD_FORMAT` 唯一推导为 `USAGE`，不再落入 RUNTIME 兜底 | 同 #6 原文"唯一推导为 `USAGE`"；§5.2（158–159 行）"不得落入 `RUNTIME/UNEXPECTED_RUNTIME`" 与之无冲突 | 已修复 |
| `tests/fins/test_upload_failure.py` 增加 usage reason round-trip 相等断言 | Slice 3 Tests："`USAGE/UNSUPPORTED_UPLOAD_FORMAT` failure reason 的 `to_json()` 结果经 `upload_failure_reason_from_json` 恢复后与原值相等"；`tests/fins/test_upload_failure.py` 在 Slice 3 allowed test files（393 行），是 Slice 3 中 failure owner 级断言的唯一归属文件 | 已修复 |
| 未知 code 与已知 code 配错 kind 继续被拒绝，不得因新增 USAGE 放宽 closed contract | Slice 3 Tests："未知 code 与已知 code 配错 kind 继续被拒绝，不得因新增 `USAGE` 放宽 closed contract" | 已修复 |
| 修复路径唯一、不改变已冻结 owner/suffix/event/typed selection 决策 | plan-fix N1 段（121–147 行）：修订范围仅原 plan 与原 plan-fix artifact；§5.1 冻结表、§5.4 closed union、§7 invariants 均未变 | 已修复 |

**代码事实核验**（N1 成立性复核）：`dayu/fins/upload_failure.py:327–333` 的 `upload_failure_reason_from_json` 推导确为三元封闭集合逻辑（`code ∈ _CONTENT_FAILURE_CODES → CONTENT`，`∈ _STORAGE_FAILURE_CODES → STORAGE`，否则 `RUNTIME`）。若只增枚举与投影分支而不扩展该守卫，`USAGE/UNSUPPORTED_UPLOAD_FORMAT` reason 经 `to_json()`（`:109–128`）序列化后，恢复时 `UNSUPPORTED_UPLOAD_FORMAT` 会落入 else 分支被推导为 `RUNTIME`，与序列化的 `kind="usage"` 冲突，于 `:332–333` 抛 `ValueError("upload failure kind 与 code 不一致")`——与 N1 原判一致。真实恢复调用方 `dayu/fins/ingestion_runtime.py:1325` 及既有 round-trip 契约测试（`tests/fins/test_fins_ingestion_runtime.py:542/581`、`tests/fins/test_company_identity_storage_contract.py:665`）佐证该守卫是既有 public contract 行为。plan 的修订文本精确对准该守卫，无实现歧义：实现 agent 只需在 owner 文件中为 usage code 增加第三分类（集合或查表），并按其 owner 测试断言验证。

**N1 结论：已修复，无回退。**

## 二、第二轮 R1/R2/R3 与第一轮 findings 无回退检查

以第二轮两份 re-review 记录的"修复证据"位置为基准，逐条比对 N1 修订后的原 plan（N1 修订范围仅 Slice 3 Exact changes #6 与 Slice 3 Tests，plan-fix 已声明）：

| ID | 关键条款 | 修订后位置 | 回退？ |
|---|---|---|---|
| R1 | `USAGE` kind + `UNSUPPORTED_UPLOAD_FORMAT` code + bounded/path-free 投影 + try 内最前时序 + 端到端零副作用断言 | §4（83 行）、§5.2（150–159 行）、§5.3（174–183 行）、Slice 3 Exact changes #2/#6、Tests（418–425 行） | 无 |
| R2 | 9 format/13 suffix 冻结字面量、排除集、help/schema/batch 精确投影、batch enter/skip 测试 | §5.1（101–132 行）、§6.2（253–261 行）、Slice 1/2 Tests（311–313、362–365 行） | 无 |
| R3 | `file_selection` 非 Optional、validator 直接产生 `for_delete()`、Service 双向 action/emptiness 拒绝 + 零副作用测试 | §5.3（165–169 行）、§5.4（190–202 行）、§7 #13（283–284 行）、Slice 2/3 Tests | 无 |
| M1 | 模块级静态声明不 import Docling + 构造期 lazy 子集校验 | §5.1（98–99、130 行）、Slice 1 Tests/Stop condition（316、323 行） | 无 |
| M2 | `.xml` XBRL candidate 三面文案 | §5.1（129 行）、§6.2（266 行）、Slice 4 Tests（458 行） | 无 |
| D1 | `FinsUploadMaterialFiles` 同一 owner 构造入口覆盖 CLI 与 tool/Service、mutation 前准入、全转换 | §5.2（143 行）、§5.3（174–183 行）、§6.2（262–267 行）、Slice 2/3 Tests | 无 |
| D2 | closed union 签名 + `SourceKind` 一致性 + 非法组合 `ValueError` + 零副作用 | §5.4（190–202 行）、Slice 3 Tests（426–427 行） | 无 |
| D3 | 单向子集校验、缺失 fail-fast、新增不 fail 不扩面、`allowed_formats` 同源 | §5.1（99、132 行）、Slice 1 Tests（315 行） | 无 |
| D4 | batch 单文件命令、`.xsd` 稳定 skip、不自动归组 | §6.2（253–261 行）、Slice 2 Tests/Stop condition | 无 |
| D5 | companion 无 `conversion_started`、仅 source=`original` 的 `file_uploaded` | §5.4（210 行）、§7 #12（282 行）、Slice 3 Exact changes #5 / Tests | 无 |
| O1 | 三面一致文案：首文件 primary、companions 不转换、`.xml` candidate | §6.2（266 行）、Slice 2/4 Tests | 无 |
| O2 | DOCX+XLSX+DOCX fixture：只转首项、后两项原样存储、requested/stored=3 | Slice 3 Tests（415 行） | 无 |

行数核对：第二轮 re-review 时原 plan 为 571 行，N1 修订后为 575 行，增量与 plan-fix 声明的修订范围（Slice 3 #6 + Tests 两处文本扩充）一致。

**结论：R1/R2/R3 与第一轮九项 findings 全部维持"已修复"状态，无任何回退。**

## 三、Findings

无 material finding。N1 的每个可验证要点均已落到 plan Slice 3 文本；`upload_failure_reason_from_json` 的守卫扩展被显式点名，实现 agent 无自裁决空间；round-trip 相等、未知 code 拒绝、错配 kind/code 拒绝三条断言齐备，且与既有 closed contract 测试契约（`test_fins_ingestion_runtime.py:542/581`、`test_company_identity_storage_contract.py:665`）语义一致，不会为贴合新实现而削弱既有断言。

## 四、Open Questions

无 blocking open question。一条非阻断性 ledger 一致性注记：

- plan §12（Plan gate 完成报告）逐条记录了 R1/R2/R3 的"已修复"状态，但未新增 N1 条目；N1 的修复状态记录在 plan-fix 的"N1 plan fix 状态"段。plan 正文（Slice 3 #6 + Tests）与 plan-fix 已构成完整证据链，不影响 implementation agent 实施与 Controller 审计；若 Controller 要求 plan §12 与 plan-fix 的 finding 台账完全同构，可做一次一句话补充，但非本 review 的 blocking 条件。

## 五、Residual Risks and suggested tracking destination

| 风险 | 去向 |
|---|---|
| batch companion association（同目录归组） | 后续 batch association / UF-FIX07 类 work unit（plan §10 已分类） |
| 真实全格式矩阵与 XBRL companion CLI evidence | UF-PF06（plan 已声明不重跑） |
| 137 条 full-real mandatory matrix | UF-PF12（plan 已声明不重跑） |
| 显式 primary、重复输入、basename/derived-name collision | UF-FIX07（plan 已分类） |
| `.xsd` 以外 companion-only 类型 | 后续 Fins/XBRL 产品能力 work unit（plan 已分类） |
| 第三方删除已声明 suffix 时 help 静态展示但运行 fail-fast | plan §10 已定性为有意的安全失败；pinned dependency + owner test 管理 |

无新增或未分类 residual risk。

## 六、Final plan review conclusion

**pass**

N1 已按 Controller 追加裁决**完全修复**：`upload_failure_reason_from_json` 的 kind/code 一致性推导被 Slice 3 显式点名同步扩展，`UNSUPPORTED_UPLOAD_FORMAT` 唯一推导为 `USAGE`；owner test 明确断言 usage failure reason 的 `to_json()` 经该函数恢复后与原值相等，并继续拒绝未知 code 与错配 kind/code，不因新增 `USAGE` 放宽 closed contract。代码事实核验确认原守卫（`upload_failure.py:327–333` 三元推导）确为 N1 所述缺陷，plan 修订精确对准该守卫及其 owner 文件（`dayu/fins/upload_failure.py` 在 Slice 3 allowed production files）。

第二轮 R1/R2/R3 与第一轮 M1/M2/D1–D5/O1/O2 全部维持"已修复"状态，无回退。

按裁决 gate 要求，本路（AgentDS 第三轮）pass 仅为两路 re-review 之一；两路都通过前仍不得进入 implementation。
