# UF-FIX10 S1 code review adjudication

## Gate 元数据

- work unit：`UF-FIX10 same-request-concurrency`
- slice：`S1 — behavior-preserving owner contracts`
- gate：`code-review fix adjudication`
- 日期：2026-08-17
- reviewed artifacts：
  - `docs/reviews/code-review-20260817-012504.md`
  - `docs/reviews/code-review-20260817-013652.md`
- accepted commit：无；用户明确禁止 commit
- scope：只允许 S1 owner contract、S1 allowlist tests 与本 gate artifact；禁止 S2 lifecycle 接线

## 结论

第一份 review 为 pass，确认 S1 behavior-preserving 边界、batch staging 单视图、
prepared/durable identity owner、纯仲裁闭集、typed failure 与 protocol fake conformance
均未发现实质 correctness 问题。第二份 review 的 Finding 2—5 与 Controller C1
暴露真实的 owner-contract 回归防护或运行时校验缺口，予以修复；Finding 1 与两个
open question 引入 accepted plan 之外的 contract 假设，按理由拒绝。

## Findings 裁决

### F1 — rebase 与 sequential prepare 的 document_version 路径分歧

- 裁决：`rejected-with-reason`。
- 理由：accepted plan §6.3 已明确冻结 rebase 规则：fresh durable fingerprint 与
  prepared fingerprint 相同则保留 fresh version，不同则递增。review 要求 sequential
  prepare 与 concurrency rebase 必须产生相同 version，属于当前 contract 之外的新假设。
- 实现动作：保持现有 rebase version 语义，不修改 `prepare_upload()` 或
  `rebase_prepared_filing_create_overwrite()` 的版本规则。
- deferred residual：多文件 role-ambiguous 输入下 sequential/rebase version 可能不同；
  owner 为未来独立的 document-version policy work unit，不属于 S1/S2。

### F2 — prepared/durable identity 缺少真实跨 owner 等价测试

- 裁决：`accepted-blocker`。
- 根因：两个 producer 各自有单侧测试，但没有真实 prepare → publish → storage read
  证明 exact identity equality；S2 的 canonical skip 依赖该 equality。
- 修复边界：只在 `tests/fins/test_docling_upload_service.py` 增加真实跨 owner 测试，
  覆盖 primary、companion、多文件 role 与 metadata；不枚举所有 mutation variant。

### F3 — §7.4 conflict grid、UNSAFE 与 stable invariant 缺少测试

- 裁决：`accepted`。
- 修复边界：在 `tests/fins/test_filing_upload_publication.py` 增加表驱动 conflict grid，
  覆盖 `MISSING→REPAIR_REQUIRED`、`COMPLETE→MISSING`、
  `COMPLETE→REPAIR_REQUIRED`、`auto+overwrite=True MISSING→COMPLETE`、
  `explicit create+overwrite=False MISSING→COMPLETE`；逐格断言 typed
  `SOURCE_PUBLICATION_CONFLICT` 且非 skip。另补 UNSAFE 入口拒绝与 stable invariant raise。
- 非必要项：decision constructor contract 不作为本 blocker 的必需修复。

### F4 — identity required text/content_type 缺少严格运行时类型校验

- 裁决：`accepted`。
- 根因：真值非字符串可绕过仅空值检查，违反 dataclass 自有 closed contract。
- 修复边界：在 `repository_protocols.py` 的 owner 边界对 required text、asset basename
  与非空 `content_type` 做显式 `isinstance(value, str)` 校验，并增加直接构造测试。

### F5(a) — 空 staging 合法 document batch read 缺少测试

- 裁决：`accepted`。
- 修复边界：增加空 staging batch read 测试，固定 `MISSING`、company/source meta 与
  publication identity 均为空，并证明零 mutation。

### F5(b) — published empty document_id fail-fast 行为收紧

- 裁决：`accepted-as-intended-contract`。
- 理由：accepted plan 已授权 malformed document id fail fast；这不是 accidental regression。
- 修复边界：增加 published read 空 `document_id` fail-fast 与零 mutation 测试；本裁决
  artifact 记录可观察行为收紧。按 Controller 裁决不更新 README。

### Controller C1 — stable REPAIR_REQUIRED action 检查重复 initial 值

- 裁决：`accepted-low`。
- 根因：`_require_stable_action_contract()` 的 REPAIR_REQUIRED 分支第二个 action 条件
  重复检查 `initial_request.resolved_action`，未在该分支直接检查 fresh 值。虽然前置 equality
  已 fail closed，owner logic 仍不精确。
- 修复边界：第二个条件改为检查 `fresh_request.resolved_action`，并由 stable invariant
  测试固定。

## Open questions 裁决

### Q1 — prepared identity 与请求业务字段是否增加防御性参数校验

- 裁决：`rejected-with-reason`。
- 理由：当前 owner contract 是同一 preparation process 产生 candidate，并在 arbitration
  校验 target triple 与 exact identity；S2 不能注入任意 candidate。新增参数或重复业务校验
  会制造第二语义 owner。

### Q2 — `disposition == "keep"` 是否修改 public contract

- 裁决：`rejected-with-reason`。
- 理由：owner public contract 已由 `Literal` 值封闭，accepted plan 冻结该 predicate；S1
  不为该字面值新增兼容常量或重塑 `upload_company_meta` contract。

### Q3 — service runtime 动态 monkeypatch fake

- 裁决：维持既有 `deferred/non-blocking residual`。
- 理由：本 work unit 无 batch-read 可达路径经过该 fake；未来 required protocol 或调用路径
  变化时由对应 work unit 同步处理。

## 修复后验证要求

- affected focused tests；
- 完整 amended focused suite；
- 完整 `tests/fins`；
- 全仓 `pyright dayu/ tests/ utils/`；
- frozen coverage（若 pytest-cov 本机 NumPy duplicate-load 复现，记录直接证据并使用既有
  accepted coverage.py 等价单次采集）；
- `git diff --check`。

禁止运行 UF-PF10/UF-PF12；禁止修改 README、workflow、oracle、scenario、registry、
evidence 或接通 S2 lifecycle。
