# upload_material 第一轮校准：UM-O01～UM-O06 用户裁决登记

登记日期：2026-09-16。用户已在本轮会话中逐项回复“同意建议，下一个”，并明确要求由当前 Agent 补齐 artifact。此记录落实已有裁决，不要求重新裁决，也不授权产品修复。

## 状态与证据真源

- UM-O01～UM-O06：用户裁决完成；本文件登记 accepted 行为及已接受的修复方向。
- UM-O07：见 [独立最终裁决](upload-material-um-o07-oracle-adjudication.md)。
- UM-O08～UM-O36：尚待逐项裁决；下一项仍为 UM-O08。
- 正式 `docs/cli_ci_oracles.json` / `docs/cli_ci_scenarios.json` 的统一登记仍待后续完成；本文件不声明 registry readiness，也不将 upload_material 纳入 readiness scope。
- 修复均未实施；下列验证要求属于未来修复后的待补跑要求，不表示本轮已补跑成功。

证据根目录 `E`：`/Users/leo/workspace/.dayu-cli-ci/upload-material-calibration-20260818-mNeTId`。下文所有 `evidence/…` 路径均相对于 E。

被测 commit：`fac32ecbff9bfe792b63ee9667c8697826b631f4`。这些历史观察不能当作当前 HEAD 的验证结果。

数据链：`run-manifest.json` / `inputs/input-manifest.json`（来源和输入）→ 各场景 command/result/原始双流与状态快照（Raw）→ matrix、execution index、`evidence-audit.json`（覆盖和审计底稿）→ `observed-behavior.md/json`（汇总）→ 本用户裁决。

冻结汇总摘要：

- `observed-behavior.md`：`4c73df2f41ed73b728231e64eb8daedb3561c7b49dd695c39a3fe983f60c5d64`
- `observed-behavior.json`：`23497494f9f5e4055f146fdcef93e6502d57a9bd6e27066f3ae518c6950cd8a0`

冻结报告中的 pending 状态和原建议保持原样；这些项目的当前用户裁决以本文件和后续明确替代它的裁决为准。

## UM-O01：help 与 public surface

**运行与观察**：UM-001 真实运行 `upload_material --help`，exit 0；仅 ticker 为 parser 必填；action 默认 auto；form/name/files 在 parser 层可省略。help 声明 auto/create/update 至少一个文件、delete 不得带文件，列出 13 个 eligible 后缀。

**直接证据**：`evidence/static/UM-001-help/command.json`、`screen.txt`。

**已接受**：help 作为本轮公开命令面的发现基线；成功显示帮助与 parser 默认值的观察可登记。help 不证明业务校验、文件格式转换或状态机行为正确。

**限定**：不得把后续明确要求移除的 internal_document_id 参数冻结为永久 public contract。格式支持需结合待裁决 UM-O20；文件与 action 组合需结合 UM-O16。业务必填在 UM-O05 独立裁决，不能因 argparse 可省略就认定业务可省略。

## UM-O02：usage/parser 基线

**运行与观察**：UM-002～012、019～023、026～029、032、036～038、040、042、057～059、D05/D06。缺必填值、非法 choice、空/路径型 ticker、未知或已移除选项、缺失/目录/不支持文件、多个 forms、日志冲突以 exit 2 拒绝，普通输出无 traceback；重复 scalar 参数最后值生效。

**直接证据**：

- `evidence/static/UM-002-missing-ticker/screen.txt`
- `evidence/static/UM-020-file-missing/screen.txt`
- `evidence/static/UM-029-forms-multiple-values/screen.txt`
- `evidence/diagnostics/UM-D05-quiet-debug-stream-conflict/screen.txt`

**已接受**：上述实际覆盖的 usage 拒绝及重复 scalar 参数语义。正式 scenario 必须逐场景引用 command/result，不把此摘要外推为所有非法业务字段都已前置校验。

## UM-O03：workspace 路径

**运行与观察**：UM-013～018、060/061 覆盖 workspace 别名、重复 base、相对路径、空格/Unicode、默认 cwd、隔离 symlink 和 regular-file base。正常路径解析进入对应 CI-owned workspace；regular-file base 以通用 storage_io / exit 1 结束。

**已接受**：正常路径解析，包括最后一个 base 值生效与默认 cwd 下 `./workspace`；不据此接受无关路径副作用。

**直接证据**：

- `evidence/static/UM-016-relative-base/command.json`、`filesystem-diff.json`
- `evidence/static/UM-060-default-base-from-cwd/command.json`
- `evidence/static/UM-061-symlink-base/filesystem-diff.json`
- `evidence/static/UM-018-workspace-root-file/screen.txt`

### UM-O03-F01：workspace root 为普通文件时提供明确路径错误

- 状态：修复方向已接受，未实施。
- 问题：错误目标类型被映射为笼统存储读写失败，无法指导用户改正 base。
- Owner：公共 workspace 路径解析/校验边界；不得在 material 下游存储异常展示处加单入口补丁。
- 要求：在 workspace path owner 边界明确识别该非法目标，给可操作的路径错误；具体内部错误类型由实现设计确定，不固化当前 storage_io。
- 后续验证：真实 CLI 重跑 regular-file base 并检查原文件保持不变、未生成业务发布；回归别名、相对/默认路径、空格/Unicode 和隔离 symlink。

## UM-O04：文件数量与重复输入

**运行与观察**：UM-024/025、F21/F22、S20。101 个文件在 stream 内以数量超限 exit 1；重复路径、同 basename、同 stem 输入进入转换后通用 runtime 回滚，未发布 material。

**直接证据**：

- `evidence/static/UM-024-files-count-101/screen.txt`
- `evidence/static/UM-025-duplicate-same-path/filesystem-diff.json`
- `evidence/supplement/UM-S20-duplicate-basename-debug/captured-debug.log`

### UM-O04-F01：文件数量与 identity 冲突前置校验

- 状态：修复方向已接受，未实施。
- Owner：material 文件选择/数量与资产身份 owner 的直接输入校验边界。
- 要求：无法唯一投影的输入须在转换前明确拒绝，并输出 typed、可操作的原因；数量上限须由唯一 owner 定义并前置校验，不以 stream 内通用失败替代 usage 校验。
- 范围：重复路径、同 basename、同 stem 派生冲突和超限输入；不因当前存在冲突就禁止正常不同 stem 的多文件上传。
- 未决细节：本裁决不凭 101 的样本宣称已完成所有数量边界验证，也不凭摘要确定最终数值上限。UM-O23 尚待裁决，若选择 collision-safe 派生名，须显式关联/细化本项，避免再登记重复或矛盾修复。
- 后续验证：实际 CLI 覆盖确定上限两侧、三类重复/碰撞、输入顺序与真正不同 stem 的对照；核对失败是否在转换前发生及有无 publication。

## UM-O05：material 必填业务字段

**运行与观察**：UM-031、033、034 分别为 form 缺失、name 空值、name 缺失；先输出 upload.started，再 exit 1 说明必填字段缺失，没有 document publication。

**直接证据**：

- `evidence/static/UM-031-forms-absent/screen.txt`
- `evidence/static/UM-033-material-name-empty/screen.txt`
- `evidence/static/UM-034-material-name-absent/filesystem-diff.json`

### UM-O05-F01：form/name 必填校验移至请求输入边界

- 状态：修复方向已接受，未实施。
- Owner：material request 的业务校验 owner 或直接上游输入边界；CLI 与其它入口复用相同业务规则。
- 要求：form_type/material_name 为该命令的无条件业务必填字段。缺失/空值应在开始上传生命周期前明确拒绝，不先输出“上传已开始”。
- 非目标：不凭 CLI argparse 的 optional 声明保留延迟错误，不在 UI 单独重建一套业务校验规则。
- 后续验证：真实 CLI 覆盖缺失、显式空值及有效对照，核对错误字段可行动、没有 upload.started、没有 material 发布；空白规范化分支按 owner 定义补足。

## UM-O06：material_name 长度

**运行与观察**：原 UM-035 混入 missing state，不能用于长度归因。隔离补跑 S01 使用有效输入和公司信息，241 字符名称上传 exit 0，原样持久化并参与稳定 ID。

**直接证据**：`evidence/supplement/UM-S01-overlong-material-name-isolated/command.json`、`key-json-artifacts.json`。原场景到补跑的替代关系见 `matrix-supplement.json`，不修改原 Raw。

### UM-O06-F01：定义并校验 material name 的公共长度上限

- 状态：修复方向已接受，未实施。
- Owner：material metadata/identity 的名称校验真源。
- 要求：定义有界的公开长度契约，并在名称参与身份生成、持久化及 LLM-facing 投影之前统一校验；错误应使调用者能改正名称。
- 未决细节：用户接受了“应有上限”的方向，未确定具体上限、字符/字节计量以及 Unicode 计数口径。不得从 241 字符样本自行倒推 240 为已接受阈值，也不自动增加静默截断语义。
- 后续验证：规则确定后用真实 CLI 覆盖上限内、恰好上限、超限、Unicode 及规范化相关边界，核对身份与持久化同源，失败不发布文档。

## 修复索引与登记边界

| 标识 | 状态 | 关联观察 |
| --- | --- | --- |
| UM-O03-F01 | 已接受方向，未实施 | workspace 路径错误 |
| UM-O04-F01 | 已接受方向，未实施 | 文件数量及身份冲突；关联待裁决 O23 |
| UM-O05-F01 | 已接受方向，未实施 | 必填字段校验时机 |
| UM-O06-F01 | 已接受方向，未实施 | 名称长度契约 |
| UM-O07-F01 | 已接受方向，未实施；详见 O07 文档 | 移除内部 ID 输入 |
| UM-O07-F02 | 已接受方向，未实施；详见 O07 文档 | document_id 错误与校验边界 |

本次补齐前六项的正式 adjudication 和四项修复登记；保留 O07 独立记录，不修改冻结证据。accepted 行为与 observed scenario 的正式 registry 映射仍需统一完成，不得误报已登记正式 scenarios、已经修复或 calibration/readiness 完成。后续 Agent 应直接从 UM-O08 继续逐项呈报，不重新裁决前七项。
