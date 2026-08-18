# UF-FIX11 slice-boundary amendment 最终定向 re-review（DS）

- 生成时间：2026-08-17 11:47:25 +0800（本机系统时钟）
- Review target：
  - `docs/gateflow/uf-fix11-slice-amendment-review-fix-20260817.md`（本轮 fix artifact）
  - `docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md`（修复后完整 plan）
  - `docs/gateflow/uf-fix11-slice-boundary-amendment-20260817.md`（修复后 amendment）
- 复核基准：`docs/reviews/uf-fix11-slice-amendment-review-ds-20260817.md` 的 Finding-001/002/003 与 OQ-1
- Scope：只 review 上述文档；dirty diff 仅用于验证契约对现有测试设施/代码事实的可执行性，不审查其代码质量。
- 结论：**pass**

## 1. Finding-001（中）：blocker 测试新契约欠规格 — 逐项复核

**状态：已闭合（CLOSED）。**

fix 的三处落地证据均存在且互相一致：

- plan §10 `Exact changes` #12（第 677 行）：显式授权改写 blocker 测试的旧 lifecycle 断言，并冻结原始回归语义——
  publication-lock fresh re-read 丢弃 stale preflight 的 `create` action 与旧 company decision，不得弱化为只测 warning/skip。
- plan §10 `Tests`（第 684 行）冻结完整 exact contract：`filing_action == "update"`、`status == "skipped"`；
  begin/commit 各恰一次且 `commit_tokens == begin_tokens`；caller `rollback_tokens == []`；
  `company.stage_tokens == begin_tokens` 且 source stage 为空；raw `warnings` 精确等于唯一规范 warning JSON；
  final `CompanyMeta` canonical JSON 序列化 bytes 完全相同（显式覆盖 `company_name` 与 `updated_at`）；
  `published_tree_sha256` 与 source revision/version/meta/manifest/assets 完全不变。
- amendment §「DS review fix 后的冻结契约 -> Blocker 测试 exact contract」与修订决策 #7 同步相同约束（第 36、44-53 行）。

对契约本身的可执行性挑战（结合代码事实逐项证伪尝试，均未找到反例）：

| 契约断言 | 验证结果 |
| --- | --- |
| `begin` 恰一次 | SKIP metadata 分支直接调用 `batching_repository.commit_batch(batch)`，不产生第二次 begin；begin 仅来自 `execute_prepared_filing_publication` 的 `_begin_publication_batch_or_raise`。成立。 |
| `commit_tokens == begin_tokens`、`rollback_tokens == []` | 该测试现有 tracking 设施（`_tracking_sec_pipeline` 的 begin/commit/rollback token 列表）已在本文件其他测试以同形态断言（第 1264-1266 行）；`batch_terminal_started=True` 在 commit 前置，outer finally 不二次 rollback。成立。 |
| `company.stage_tokens == begin_tokens`、source stage 为空 | SKIP 分支只 `stage_upload_company_meta_decision` 一次，禁止 stage filing/source asset（exact changes #4）；tracking 设施可断言。成立。 |
| raw `warnings` 精确等于规范 warning | SEC terminal 经 `host._build_result(**payload)` 序列化，`warnings` 由 workflow 从 `FilingUploadPublicationOutcome.warnings` 传入（exact changes #8）；codec 为 closed shape（§6.3）。成立。 |
| final `CompanyMeta` bytes 完全相同（含 `updated_at`） | `_company_meta_from_published`（company_meta_contract.py:371）在 `final_identity == current_published.ticker_identity` 时保留 `updated_at`；name-only preserve 场景 identity 不变，bytes 不变可达成。成立。 |
| `published_tree_sha256`/source revision/version/meta/manifest/assets 不变 | metadata-only commit 只写 company meta 文件且 bytes 相同，source staging 为空。成立。 |
| stale-re-read 原回归语义保留 | `filing_action == "update"` 只能来自 fresh recheck 看到 COMPLETE（preflight 对 stale missing state 解析为 `create`）；旧 company decision 的丢弃由 name bytes 不变 + warning 事实（requested name 被 final truth 拒绝）+ fresh intent staging 共同证明。成立。 |

上一轮指出的“实施者可能弱化回归或按旧期望拉锯”的风险已消除：改写被显式授权、终态被冻结到断言级、弱化被明文禁止（“不得把测试弱化为只断言 warning 或 skip”），且 §12.1 禁 deselect 与 stop condition（第 706 行）保留。

## 2. Finding-002（低）：combined regression 未绑定 acceptance — 逐项复核

**状态：已闭合（CLOSED）。**

- plan §12.2（第 866 行）明确 combined regression 是 S1+S2 implementation review 与 accepted code commit 的**强制 acceptance 前置**：focused suite 后、进入 review 前必须全绿；review fix 改动代码/测试后、accepted commit 前必须再次全绿；任何失败禁止 acceptance/stage/commit，不得递延 S3。
- plan §10 `Completion / review / commit boundary`（第 722、724 行）同步列入该硬门：combined regression 是 review/commit acceptance 的硬前置，“不得只在 completion report 中补记”；review fix 后必须在 accepted commit 前重跑且最终一次全绿。
- amendment §「Combined regression gate」（第 55-57 行）与修订决策 #4 同义收敛。
- 反 loophole 条款到位：S3 后跑不能补认 S1+S2 缺失 evidence（§12.2 第 876 行）；S1+S2 coverage gate 未达标不得进入 review/commit（§12.3）。

上一轮指出的“§10 与 §15 对 combined regression 时点不一致”的欠定状态已消除：三处文档现在给出同一硬门定义，且明确了两次运行时点（pre-review 与 pre-commit）与禁止补认规则。命令本身（`pytest tests/fins + tests/cli/test_output + tests/cli/test_fins_commands + tests/service/test_fins_wait_adapter`）可执行。

## 3. Finding-003（低）：共享 runtime 文件缺符号级边界 — 逐项复核

**状态：已闭合（CLOSED）。**

- plan §6.6 已拆为 §6.6.1（S1+S2：terminal producer 与 strict parser contract）与 §6.6.2（S3：summary/durable/direct/CLI/tool projection），符号归属互斥且覆盖完全：
  - S1+S2 `ingestion_runtime.py`：仅 `FinsUploadPipelineResult.warnings`、warnings/status invariant、`from_pipeline_json(result, *, source_kind)` 签名与 `CompanyMetadataWarning` 闭集解析（§6.6.1 第 327 行）；S3 才允许 `FinsUploadResultSummary.warnings`/`to_json_summary()`（§6.6.2 第 334 行）。
  - S1+S2 `service_runtime.py`：仅四个 `from_pipeline_json` callsite 的显式 `SourceKind`（第 330 行）；S3 才允许 `_upload_summary_from_result` 透传（第 335 行）。
- 双向防漂移 stop conditions 均已落地：S1+S2 stop condition 第 715 行禁止提前触碰 summary/`to_json_summary`/`_upload_summary_from_result`/direct/durable projection；S3 stop condition 第 786 行禁止改写 parser schema、warning codec 或四个 callsite。
- allowed files 注释（第 628-629、643 行）与 S3 allowed files（第 739-740、747-748 行）按同一符号边界标注；exact changes #11（第 676 行）与 S3 exact changes #2（第 763 行）一致引用 §6.6.1/§6.6.2。
- 测试文件侧同样收敛：`tests/fins/test_fins_ingestion_runtime.py`/`test_fins_service_runtime.py` 在两个 slice 的修改范围均带显式禁止项（第 639、643、747-748 行）。

上一轮指出的“typed upload result 语义歧义可双向漂移”的洞已封死：两个方向各有一条 stop condition 拦截，且 §6.6.1 的枚举把 `FinsUploadResultSummary` 明确排除在 S1+S2 符号清单之外。

## 4. OQ-1：plan-gate/code commit 文件集 — 逐项复核

**状态：已闭合（CLOSED）。**

- plan §10 新增 `Plan-amendment gate commit boundary`（第 598-612 行）：amendment 接受后先创建独立 plan-gate commit，逐文件显式 stage 9 类文档（plan、blocker、amendment、fix、acceptance、DS/MiMo 两篇 review、两篇 re-review），cached diff 必须证明零 production/test path，禁止目录 glob，建议 message `gateflow: accept UF-FIX11 slice-boundary amendment`；production/test partial diff 绝不 stage。
- S1+S2 code commit 内容边界（第 726 行）：仅本 slice production/test implementation、accepted scope 内必要 README（当前正常为零）与本 slice implementation/review/fix/re-review/acceptance closeout artifacts；显式排除 blocker/amendment/plan review/fix/re-review/acceptance 与完整 plan；README 例外必须先修订 allowed files。
- amendment §「Plan-gate 与 code commit 文件集」（第 66-81 行）同步同义约束。
- 互斥性验证：两个文件集交集为空（plan-gate commit 全部为 docs，code commit 排除全部 plan-gate docs）；顺序可执行（acceptance → plan-gate commit → S1+S2 implementation，见 §10 Prerequisites 第 593 行与 §16 第 1051 行）；“误判为已提交红色中间态”的原始担忧已由显式独立 commit + 独立 message + cached-diff 证明三重消除。

## 5. 本轮新发现的 material issue

无。

唯一非实质不一致（不构成 finding）：amendment §「Plan 具体变更」末条仍写“§16 将 next gate/entry point 固定为 `plan amendment review`”，而 plan §16（第 1052-1053 行）与 amendment 自身 Gate 元数据（第 6、14 行）已是 `plan amendment re-review`——属上一轮修复遗留的陈旧表述，语义无冲突，建议 acceptance 前顺手同步，不阻塞。

## 6. Residual risks 与追踪去向

- R-1：S1+S2 → S3 之间 typed warning 已产生但 direct/CLI/tool 尚不投影。接受；本地 commit 不对外发布，S3 有唯一 prerequisite。追踪：plan §10 S3 Prerequisite。
- R-2：coverage gate 对 `sec_upload_workflow.py`/`cn_pipeline.py` 整文件 ≥80% 依赖 tests/fins 既有路径覆盖；不足时 gate 自纠偏补测，plan 禁止 pragma/ignore 绕过。追踪：plan §12.3.1。
- R-3：§9.2 表中 `test_fins_ingestion_runtime.py` 行的“需要 completed warning 的路径返回 exact outcome”为能力性表述；该文件现有 fake（第 3503 行）只模拟 commit 失败路径，按契约其注解须为 exact union、行为保持抛错即可，无需强改。若 S1+S2 测试确需该文件内 success-path outcome，按 §9.2 表义补齐即可。追踪：plan §9.2。
- R-4：blocker 测试契约的逐项可执行性已在本 review 第 1 节对照代码事实验证；`stored_file_count == 0`、`get_company_meta(...).company_name` 等既有未翻转断言不在冻结清单中但可自然保留，不产生冲突。追踪：S1+S2 implementation 时按冻结清单逐项断言。

## 7. Final conclusion

**pass**

Finding-001/002/003 与 OQ-1 均已严格闭合：blocker 测试的 token/bytes/tree/warning/stale-re-read 契约冻结到断言级且对现有测试设施可执行；§12.2 combined regression 成为 S1+S2 review/commit 的显式硬门（pre-review 与 pre-commit 两次运行，禁止补认/递延）；`ingestion_runtime.py`/`service_runtime.py` 的符号级双 slice 边界在 §6.6.1/§6.6.2、allowed files、exact changes 与双向 stop conditions 五处一致落地；plan-gate commit 与 S1+S2 code commit 文件集互斥、可执行、带 cached-diff 证明。未发现新的 material finding，amendment 可进入 acceptance。
