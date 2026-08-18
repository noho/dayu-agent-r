# UF-FIX03 plan re-review fix

## Gate

- gate：`plan re-review -> fix`
- work unit：`UF-FIX03 summary-and-bounded-errors`
- fixed plan：`docs/gateflow/uf-fix03-summary-bounded-errors-plan-20260813.md`
- controller input：`docs/gateflow/uf-fix03-plan-rereview-adjudication-20260813.md`
- re-review inputs：
  - `docs/reviews/plan-review-20260813-210131.md`
  - `docs/reviews/plan-review-20260813-210506.md`
- prior fix/adjudication inputs：
  - `docs/gateflow/uf-fix03-plan-review-fix-20260813.md`
  - `docs/gateflow/uf-fix03-plan-review-adjudication-20260813.md`
- scope：只修订 plan 中 N1–N3 的 owner contract 与测试要求；不进入 implementation 或 UF-PF03
- changed files：
  - 修改 `docs/gateflow/uf-fix03-summary-bounded-errors-plan-20260813.md`
  - 新增 `docs/gateflow/uf-fix03-plan-rereview-fix-20260813.md`
- completion status：`complete`
- next entry point：`plan re-review`（定向复核 N1–N3）

## Input completeness and first-principles judgment

已完整读取 plan re-review adjudication（50 行）、AgentMiMo re-review（212 行）、AgentDS re-review（129 行）、修订前现行 plan
（770 行）、此前 plan-review fix（159 行）与此前 plan-review adjudication（113 行）。controller adjudication 是本 fix gate 对 N1–N3
的最终裁决；既有 review/fix/adjudication artifact 均保持只读。

N1–N3 的修改动机成立，且严重性不应因 reviewer 标记为低而忽略：

- N1 是 pipeline typed owner 的状态矩阵缺口；producer 和 summary 下游都写对值，不能替代 owner constructor 拒绝非法
  `cancelled+positive`。
- N2 是 label canonicalizer 对合法输入不全导致的 known failure 分类漂移；label 安全化不能改变已知 content 业务事实。
- N3 是 reason constructor 与 parser 接受集分裂；public reason 类型自身必须强制唯一 label contract，不能依赖调用者自律。

三项均可在现有 owner boundary 内完成，不需要新模块、兼容层、下游 fallback、通用 sanitizer 或架构扩张。

## Accepted finding status

### N1 — pipeline `cancelled` 状态矩阵遗漏

- 状态：`已修复`
- plan 落实：§5.2 将 pipeline status 闭集明确为 `ok/skipped/deleted/failed/cancelled`，并把
  `cancelled -> stored_file_count == 0` 写入 `FinsUploadPipelineResult.__post_init__()` 的完整 owner 矩阵；明确禁止依赖 summary、
  renderer 或其它下游兜底。
- 测试落实：S1 要求 direct constructor 与 JSON parser 都接受 `cancelled+0`、拒绝 `cancelled+positive`，并证明 parser 不复制矩阵。

### N2 — 合法超长 basename 不得使 known failure 降级

- 状态：`已修复`
- plan 落实：§5.4 保持 pathful、空值和 `.`/`..` 输入拒绝；对合法 basename 超过 public label 上限 `240` 的场景，唯一
  canonicalizer 确定性返回固定标签 `输入文件（文件名已隐藏）`，与 fragment、URL/job/path public guard、Unicode `Cc/Cf` 的
  无法原样公开场景同源处理。
- 分类不变量：filing empty/conversion producer 必须先 canonicalize，再构造 reason；超长合法 basename 仍保持原 closed content
  kind/code，不得降级为 runtime/unknown failure。reason、durable、direct detail 与 CLI 消费同一 canonical label。
- 测试落实：S2 同时覆盖普通安全 basename、合法超长 basename、fragment、Unicode `Cc/Cf` 与 pathful 拒绝；对合法超长输入断言
  fixed label、原 typed code/kind 不变、所有 consumer label 一致。

### N3 — reason constructor 必须拥有 label 防御

- 状态：`已修复`
- plan 落实：§5.4 指定 `FinsUploadFailureReason.__post_init__()` 在 `file_label is not None` 时调用唯一
  `validate_fins_public_file_label(...)`。`upload_failure_reason_from_json(...)` 只做 five-field exact key/type 读取并调用 constructor，
  不直接调用 validator，也不复制长度、fragment、control 或 path 规则。
- 测试落实：S2 增加 direct constructor owner tests，覆盖 `None`、canonical label 与 raw fragment、Unicode `Cc/Cf`、pathful、
  超长未 canonicalize label；另以受控 constructor delegation test 证明 parser 只原样传递 five-field 值，不在 parser 测试复制 label
  接受规则表。

## Prior accepted findings status

- M1–M7：全部维持`已修复`；N1 补全 M5 的 pipeline owner 矩阵，不改变其它 contract。
- D1、D2 的 accepted component、D3–D5：全部维持`已修复`；N2/N3 补强 D3 的唯一 label owner，不扩大 material scope。
- C1–C5：全部维持`已修复`；C4 的 summary 状态矩阵与 success/non-ok 原则不变，pipeline `cancelled` 缺口由 N1 关闭。
- rejected/deferred findings：本轮无新增，既有裁决不变。

## Prior C4 factual correction

此前只读 artifact `docs/gateflow/uf-fix03-plan-review-fix-20260813.md` 的 C4 写有“避免给 pipeline 虚构 cancelled 状态”。该事实前提
错误：现行 pipeline status 闭集包含 `cancelled`，shared cancelled producer 也会产生该状态。正确 contract 是 pipeline owner 与
summary owner 都接受 `cancelled`，并分别强制其 stored count 为 `0`。

按本 gate 约束，不修改既有 fix artifact；本节是唯一勘误记录。现行 plan §5.2 与 S1 测试要求已经使用正确事实，后续 implementation
不得沿用旧 C4 的错误表述。

## Validation

- 输入完整性：六份指定输入均读取到 EOF；未以裁决摘要替代现行 plan 或此前 fix/adjudication。
- plan 一致性：N1 同步修改 §5.2 owner contract、S1 constructor/parser tests、§8 matrix 与 completion；N2/N3 同步修改 §4 owner
  evidence、§5.4 exact contract、§6 affected symbols、S2 tests、§8 matrix、risk/over-design 与 completion。
- owner boundary：pipeline count 只由 `FinsUploadPipelineResult.__post_init__()` 校验；label canonicalization/validation 仍只在
  `direct_events`；reason constructor调用唯一 validator，parser/consumer不复制规则。
- scope/no-touch：未修改生产代码、测试、README、冻结 JSON、evidence、goal-confirmation、review、adjudication或此前 fix artifact；
  未执行 UF-PF03，未 commit、push 或创建 PR。
- 运行验证：本 gate 仅修改 Markdown plan artifacts，未运行 pytest、coverage 或 pyright；这些命令仍由 implementation slices 执行。

## Documentation decision

- 已更新：`docs/gateflow/uf-fix03-summary-bounded-errors-plan-20260813.md`。
- 已新增：`docs/gateflow/uf-fix03-plan-rereview-fix-20260813.md`。
- 未更新 README：当前仅为 plan re-review fix gate，没有生产/测试行为落地，且用户明确禁止 README 修改。
- 未修改旧 artifact：C4 事实勘误仅记录在本 artifact，保留历史 review/fix 证据不可变。

## Residual risks and uncovered areas

- N1–N3：`fixed in current slice`；仍须由下一 `plan re-review` gate 做独立定向验证，fix 自述不等于 re-review pass。
- 真实 Docling 跨平台底层异常差异：`assigned to later UF-PF03 evidence work`；本 gate 明确未执行。
- material generic raw failure 与 company-first publication：`assigned to later work unit`，owner 为 Fins material workflow；本 WU 仅共享
  count contract 机械迁移。
- 旧 durable upload summary/failure record：`explicitly excluded by fresh-schema rule`；不兼容读取，不在本 WU 迁移或删除。
- 大型 production 文件单文件 coverage 可行性：`covered by later approved implementation slices`，按 plan §8.3 报告具体 uncovered
  branches，不在 plan fix gate运行。

无 unclassified residual risk，无 blocking open question。

## Completion

- N1：`已修复`
- N2：`已修复`
- N3：`已修复`
- 此前所有 accepted findings：维持`已修复`
- plan re-review fix gate：`complete`
- next entry point：`plan re-review`（仅定向复核 N1–N3；通过前不得进入 accepted plan commit 或 implementation）

## Artifact path

`docs/gateflow/uf-fix03-plan-rereview-fix-20260813.md`
