# UF-FIX07 Slice 1 acceptance

## Gate 结论

- Work unit：`UF-FIX07 multi-file-primary-and-collision`
- Slice：1（request contract / static admission）
- 日期：2026-08-15
- 结论：`SLICE ACCEPTED`
- Accepted plan checkpoint：`64050349`
- 下一入口：implementation Slice 2

## 接受依据

- AgentCodex 已完成 raw selector、静态准入与 authoritative filing selection 实现。
- 初轮双路 review：
  - `docs/reviews/code-review-20260815-193205.md`：AgentMiMo `pass`，无实质 finding；
  - `docs/reviews/code-review-20260815-193342.md`：AgentDS `pass-with-risks`，一个低严重度 finding。
- 主控接受 DS Finding 1：path normalization 的 `OSError` / `RuntimeError` 必须由 static admission owner
  投影为既有 `FILE_NOT_FOUND` typed usage failure；同时接受 R3 的 delete + 101 precedence 测试缺口。
- AgentCodex 已在 `docs/gateflow/uf-fix07-slice1-review-fix-20260815.md` 完成两项修复。
- 最终双路 re-review：
  - `docs/reviews/code-review-20260815-194142.md`：AgentMiMo `pass`；
  - `docs/reviews/code-review-20260815-194232.md`：AgentDS `pass`。
- 两路均确认原 finding 与测试缺口状态为 `已修复`，没有新 blocker 或未分类风险。

## Accepted contract

- `FinsUploadFilingRequest.primary_selectors` 保留 raw selector occurrence，不承诺已验证角色。
- static admission 在 workspace read、业务 mutation、converter 与 publication 前统一完成：
  raw 100 上限、delete 组合、normalized exact-path duplicate、selector cardinality/membership、文件存在性与
  primary/companion capability 校验。
- 单文件无 selector 时唯一文件是 primary；多文件必须恰有一个属于 files 集合的 selector。
- `FinsUploadFilingFiles.for_upsert()` 只接收已确定的 authoritative primary/companions；旧首项推断入口已删除，
  不保留 compatibility shim。
- path normalization 的底层 `OSError` / `RuntimeError` 收敛为只暴露安全 basename 的
  `FILE_NOT_FOUND`；所有拒绝继续保持零 workspace/state/job/runner/converter/publication 副作用。
- delete + 101 raw files 先返回 `TOO_MANY_FILES`；100 个不同文件允许进入后续 validation。

## 验证

- Affected tests：319 passed。
- Targeted pyright：0 errors。
- 单生产文件 coverage：`ingestion_runtime.py` 88%，`upload_format_contract.py` 88%。
- `git diff --check`：通过。
- 未执行 UF-PF07/UF-PF12 或真实 CLI evidence；未修改 README、registry、oracle/scenario 或冻结 evidence。

Slice 1 blocking finding 为 0，允许进入 Slice 2。Slice 2 负责 CLI/tool selector 构造与 LLM-facing schema 文案；
Slice 3 负责迁移剩余 filing constructor 测试并实现 asset identity；本 acceptance 不把这些后续职责当兼容窗口承诺。
