# UF-FIX09 S2 Code Review 裁决

## Gate

- Gate：UF-FIX09 S2 code review
- Scope：S2 生产代码与测试变更；不包含 S3 终态仲裁、README 与 UF-PF09
- 冻结 base：`26e77e36d5a3340ad7f1aa75c2a538a3dd424f96`
- 冻结 implementation diff SHA-256：`427f9c5ed13afd53afaea7ebb8aa53078d692f807a30b906266b8d3a9216857a`
- AgentDS artifact：`docs/reviews/code-review-20260812-174021.md`
- AgentMiMo artifact：`docs/reviews/code-review-20260812-174511.md`

## Findings 裁决

### A1 — 接受：上传服务重复计算 converter 已承诺的 SHA-256

- 来源：AgentDS finding 1
- 严重度：低
- 证据：`DoclingConversionResult` 构造时已验证 `json_bytes`、`size` 与 `sha256` 一致；`DoclingUploadService._build_pending_assets` 仍从同一 bytes 重算 digest。
- 裁决：`fixed in current slice`。
- 理由：accepted plan 明确要求调用方直接消费 typed result，不各自重算 JSON、digest 或取消状态；修复只需读取 `conversion.sha256`，不改变 bytes、manifest 或 publication 语义。
- 验证：补强/保留 upload owner 断言，运行 focused tests、真实 Docling integration、pyright、格式与 diff check。

### R1 — 不接受为缺陷：共享 download adapter request 保留 callable checkpoint 运输类型

- 来源：AgentMiMo finding 1
- 严重度：reviewer 标记为中
- 裁决：rejected；不是未分类 residual risk。
- 理由：`FinsSourceDownloadAdapterRequest` 同时服务 SEC download 与 CN/HK download。前者只需要既有同步 checkpoint，后者在进入 shared converter 前必须同时满足 canonical `CancellationToken`。Python 类型系统没有直接交集类型；accepted plan 第 11.1 节已明确：request 中运输的是同一个 `FinsJobCancellationChecker` concrete object，普通 workflow checkpoint 继续调用 `__call__`，converter boundary 用公共 protocol 收窄并原样传递 identity。把共享字段直接标成 `CancellationToken` 会丢失普通 checkpoint 的可调用静态契约；标成 ingestion 层的 `FinsJobCancellationChecker` 又会让 pipeline/workflow 反向依赖上层 runtime owner。当前实现没有创建 adapter、fallback 或第二取消真源，并在 converter owner 前拒绝纯 callable，因此符合冻结 plan。
- 后续：无；若未来拆分 SEC/CN adapter request，应作为独立 owner 变更，不纳入本 work unit。

### D1 — covered by later approved slice：cancelled summary 仍可能先投影 upload.completed

- 来源：AgentDS finding 2
- 分类：`covered by later approved slice`（S3）
- 理由：这是本 work unit 的已知 root cause 第二部分；S2 明确禁止修改 `_produce_direct_upload`、`_run_upload_job` 与 terminal mapping。S3 将建立 typed terminal disposition 与单次 claim，保证 cancelled 不投影 completed。

### D2 — covered by later approved slice：CN/SEC status mapping 重复

- 来源：AgentDS finding 3
- 分类：`covered by later approved slice`（S3）
- 理由：S3 的统一 typed terminal disposition 将收口该映射；S2 不扩大终态 owner 范围。

## Validation

- 两路 reviewer 均核验 branch、HEAD、19 个 S2 allowlist 文件与冻结 diff digest。
- AgentCodex implementation validation：focused matrix `493 passed`；S1 回归 `91 passed`；SEC download 回归 `124 passed`；真实 Docling integration `1 passed`；pyright `0 errors`；逐修改生产文件覆盖率 `86%`–`100%`；Black、Ruff、`git diff --check` 通过。
- accepted finding 修复后必须重新冻结 implementation diff，并同时交两路 re-review。

## Docs Decision

README 更新仍属于 S3；S2 不修改 README。

## Residual Risks

- `covered by later approved slice`：direct/durable upload terminal arbitration、typed disposition、canonical cancelled terminal、README、UF-PF09。
- `assigned to later work unit`：company meta 独立事务、web fetch cancellation、非 POSIX descendant governance、格式范围扩展。
- `fixed in current slice`：重复 digest 计算。
- `requiring user decision`：无。
- 未分类风险：无。

## Completion Status

初轮双路 code review 已完成并裁决；accepted A1 已由 AgentCodex 修复。修复后冻结 target：

- implementation SHA-256：`f4bf8892e3047993562e84b379dd338ac011c44f77b0e180412b52efff78d4a8`
- production SHA-256：`333ae9078c99006719c3f1ef767d5d19b9fc35bb6bb91a6ca2a8e4075133bbe8`
- tests SHA-256：`266ca7484c152aa101e3776d71e168befaa54676b9bcd84b907c01f73cee9ef5`

双路 re-review 均核验 digest、allowlist、A1 修复与 R1 裁决，并未发现新 finding：

- AgentDS：`docs/reviews/code-review-20260812-175301.md` — PASS
- AgentMiMo：`docs/reviews/code-review-20260812-175731.md` — PASS

S2 code review gate accepted；所有 accepted finding 已闭环，无未分类风险、blocking question 或 requiring-user-decision 项。
