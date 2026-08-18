# UF-FIX11 slice-boundary amendment re-review（MiMo 最终复审）

## Review 元数据

- reviewed target:
  - `docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md`（修复后）
  - `docs/gateflow/uf-fix11-slice-boundary-amendment-20260817.md`（修复后）
  - `docs/gateflow/uf-fix11-slice-amendment-review-fix-20260817.md`
- 前置 artifacts:
  - `docs/reviews/uf-fix11-slice-amendment-review-ds-20260817.md`（DS 定向复审，pass-with-risks）
  - `docs/reviews/uf-fix11-slice-amendment-review-mimo-20260817.md`（MiMo 首审，pass）
- review scope: 确认 DS Finding-001/002/003 与 OQ-1 均已闭合；验证原子 S1+S2 最小边界、精确 blocker 测试终态、combined regression 硬门、共享文件符号边界、plan/code commit 文件集互斥且可执行
- review date: 2026-08-17 11:45:07
- 结论: **pass**

## 1. DS Finding 闭合验证

### Finding-001：blocker 测试新契约欠规格

**状态：✅ 已闭合**

| 修复位置 | 内容 |
| --- | --- |
| Plan §10 `Exact changes：publication/warning/producer/parser` 第12点 | 明确 blocker 测试改写要求：保留原始回归语义（publication-lock fresh re-read 丢弃 stale preflight action/decision），不得弱化为只断言 warning 或 skip |
| Plan §10 `Tests：publication/warning/producer/parser` | 冻结完整 exact assertions：terminal `filing_action=update`、`status=skipped`；metadata-only begin/commit 各恰一次且 token exact 对应；零 caller rollback；company stage token exact 对应且 source stage 为空；raw warnings 恰为唯一规范 warning；final `CompanyMeta` canonical JSON bytes（含 `company_name`、`updated_at`）不变；`published_tree_sha256` 与既有 source revision/version/meta/manifest/assets 不变 |
| Amendment `DS review fix 后的冻结契约 -> Blocker 测试 exact contract` | 同步完全相同的约束 |

**验证**：实施 agent 可从 plan/amendment 中直接读取该测试的完整断言契约，无需自行推断。规格空洞已消除。

### Finding-002：combined regression 未绑定 acceptance

**状态：✅ 已闭合**

| 修复位置 | 内容 |
| --- | --- |
| Plan §12.2 | 明确声明 combined regression 是 S1+S2 implementation review 与 accepted commit 的硬前置；focused suite 后、进入 review 前必须全绿；review fix 改动代码/测试后，accepted commit 前必须再次全绿；任何失败或缺失都禁止 acceptance/stage/commit，不得递延到 S3 |
| Plan §10 `Completion / review / commit boundary` | 同步列入该门槛："完整 focused suite 绿色、§12.2 combined regression 全绿、相关逐文件 coverage 达标、全仓 pyright 通过、static boundary checks 通过后" |
| Amendment `Combined regression gate` | 重申该硬前置 |

**验证**：§10 acceptance 前置清单与 §12.2 命令完全一致；§15 completion format 要求报告 combined regression 结果与 §10 前置一致。边界不再欠定。

### Finding-003：共享文件双 slice 边界缺符号级精度

**状态：✅ 已闭合**

| 修复位置 | 内容 |
| --- | --- |
| Plan §6.6 | 拆为 `6.6.1 原子 S1+S2：terminal producer 与 strict parser contract` 和 `6.6.2 后续 S3：summary、durable、direct、CLI/tool projection`，每个 symbol 按 slice 归因 |
| Plan §10 S1+S2 Allowed files 注释 | `ingestion_runtime.py`（仅 `FinsUploadPipelineResult.warnings`、其 invariant、`from_pipeline_json(..., source_kind)` 与 `CompanyMetadataWarning` 闭集解析；禁止触碰 `FinsUploadResultSummary`/`to_json_summary`）|
| Plan §10 S1+S2 Allowed files 注释 | `service_runtime.py`（仅四个 `FinsUploadPipelineResult.from_pipeline_json` callsite 的显式 `SourceKind`；禁止触碰 `_upload_summary_from_result`）|
| Plan §10 S3 Allowed files 注释 | `ingestion_runtime.py`（仅 `FinsUploadResultSummary.warnings`、其 invariant 与 `to_json_summary()`；不得改写 S1+S2 已冻结的 pipeline parser）|
| Plan §10 S3 Allowed files 注释 | `service_runtime.py`（仅 `_upload_summary_from_result` 的 warnings 机械透传；不得改写四个 parser callsite 的 `SourceKind`）|
| Amendment `共享 runtime 符号边界` | 明确列出 S1+S2 owner 和 S3 owner 的完整符号清单 |
| Plan §10 Stop condition | S1+S2 禁止提前触碰 S3 symbols；S3 禁止重写 pipeline parser/codec/四个 callsite |

**验证**：两个 slice 的 allowed files 注释精确到符号级，互不重叠。§6.6.1 与 §6.6.2 的契约边界清晰，§10 stop condition 直接拦截双向漂移。

### OQ-1：plan docs 与 S1+S2 code commit 文件集

**状态：✅ 已闭合**

| 修复位置 | 内容 |
| --- | --- |
| Plan §10 `Plan-amendment gate commit boundary` | 逐项列出 plan-gate commit 的完整文件集（9 个文件）；要求逐个显式 stage、cached diff 证明零 production/test path，禁止目录级 glob |
| Plan §10 `Completion / review / commit boundary` | "accepted S1+S2 code commit 只允许包含本 slice 的 production/test implementation、按 accepted scope 确属本 slice 必要的 README（当前计划把 README 放在 S3，因此正常应为零）及本 slice implementation/review/fix/re-review/acceptance closeout artifacts；不得混入 blocker、amendment、plan review/fix/re-review/acceptance 或完整 plan 等 plan-gate docs" |
| Amendment `Plan-gate 与 code commit 文件集` | 同步明确两个互斥文件集 |

**验证**：plan-gate commit 和 S1+S2 code commit 的文件集已完全分离。两个 commit 的内容边界互斥，且有逐文件 stage + cached diff 证明零 production/test path 的执行要求。仓库既有惯例（如 c7f5ddb1）的 docs+code 同 commit 模式已被明确否定。

## 2. 核心主张验证

### 2.1 原子 S1+S2 最小边界

**结论：✅ 成立**

因果链已逐环验证（DS review A1-A10 已确认）：

1. `upload_company_meta.py` 产生 name-only `preserve_published` intent
2. `_canonical_skip_requirements_are_met` 必须扩展为接受 `stage/preserve_published intent`
3. `SKIP + preserve_published intent` 必须执行 metadata-only commit
4. `commit_batch` 必须返回 typed `CompanyMetaCommitOutcome`
5. `UploadOperationResult` 必须携带内部 outcome
6. `FilingUploadPublicationOutcome.warnings` 必须从 outcome 投影
7. SEC/CN terminal producer 必须序列化 warnings
8. `FinsUploadPipelineResult.from_pipeline_json` 必须 fail-closed 解析 warnings
9. `service_runtime.py` 四个 callsite 必须显式传 `SourceKind`

每环都直接由前一环变红或语义断链强制；拆分任何一环都会制造红色中间态或语义断裂。

### 2.2 精确 blocker 测试终态

**结论：✅ 已冻结**

Plan §10 和 Amendment 都完整冻结了 `test_upload_filing_fresh_recheck_discards_stale_action_and_company_decision` 的 exact contract：

- `filing_action == "update"` 且 `status == "skipped"`
- metadata-only batch `begin` 恰一次、`commit` 恰一次，且 `commit_tokens == begin_tokens`
- caller `rollback_tokens == []`
- `company.stage_tokens == begin_tokens`，source stage token 为空
- raw terminal `warnings` 精确等于 `[{"kind": "company_name_ignored", "message": "本次提交的公司名称未生效；已保留现有公司名称。请核对上传目标公司是否正确。"}]`
- 提交前后 final `CompanyMeta` canonical JSON 序列化 bytes 完全相同（显式覆盖 `company_name` 与 `updated_at`）
- `published_tree_sha256` 与既有 source revision/version/meta/manifest/assets 完全不变
- 原回归语义保留：publication-lock fresh re-read 丢弃 stale preflight 的 `create` action 和旧 company decision

### 2.3 Combined regression 硬门

**结论：✅ 已绑定**

§12.2 combined regression 是 S1+S2 implementation review 与 accepted commit 的硬前置：

- focused suite 后、进入 review 前必须全绿
- review fix 改动代码/测试后，accepted commit 前必须再次全绿
- 任何失败或缺失都禁止 acceptance/stage/commit
- 不得递延到 S3
- S3 后续重跑不能补认 S1+S2 缺失 evidence

### 2.4 共享文件符号边界

**结论：✅ 已精确**

`ingestion_runtime.py`：
- S1+S2：`FinsUploadPipelineResult.warnings`、其 warnings/status invariant、`from_pipeline_json(result, *, source_kind)` 与 `CompanyMetadataWarning` 闭集解析
- S3：`FinsUploadResultSummary.warnings`/success-only invariant、`to_json_summary()`；不得改写 S1+S2 已冻结的 pipeline parser

`service_runtime.py`：
- S1+S2：四个 `FinsUploadPipelineResult.from_pipeline_json` callsite 的显式 `SourceKind`（SEC/CN filing=FILING，US/CN material=MATERIAL）
- S3：`_upload_summary_from_result` 的 warnings 机械透传；不得改写四个 parser callsite 的 `SourceKind`

### 2.5 Plan/code commit 文件集互斥

**结论：✅ 已明确**

Plan-gate commit 只允许 stage：
- `docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md`
- `docs/gateflow/uf-fix11-s1-slice-boundary-blocker-20260817.md`
- `docs/gateflow/uf-fix11-slice-boundary-amendment-20260817.md`
- `docs/gateflow/uf-fix11-slice-amendment-review-fix-20260817.md`
- `docs/gateflow/uf-fix11-slice-amendment-acceptance-20260817.md`
- `docs/reviews/uf-fix11-slice-amendment-review-ds-20260817.md`
- `docs/reviews/uf-fix11-slice-amendment-review-mimo-20260817.md`
- re-review 实际产生的 DS/MiMo artifacts

S1+S2 code commit 只允许包含：
- 本 slice production/test implementation
- accepted scope 内必要 README（当前正常为零）
- 本 slice implementation/review/fix/re-review/acceptance closeout artifacts

两个文件集互斥，且有逐文件 stage + cached diff 证明零 production/test path 的执行要求。

## 3. Open questions

无。DS OQ-1 已由 plan §10 `Plan-amendment gate commit boundary` 关闭。

## 4. Residual risks

无新增。DS review 的 R-1/R-2/R-3 分类仍然有效：

- R-1：S1+S2 → S3 之间，typed warning 已产生但 direct/CLI/tool 尚不投影。接受：本地 commits 不对外发布，S3 是唯一后续入口。
- R-2：coverage gate 对 `sec_upload_workflow.py`/`cn_pipeline.py` 的整文件 ≥80% 依赖既有覆盖。接受：gate 自纠偏。
- R-3：metadata-only skip 的 fail-closed 权衡与 name-only 物理 publication 成本。接受：已分类为 accepted tradeoff。

## 5. Final conclusion

**pass**

DS Finding-001/002/003 与 OQ-1 均已文档修复并验证闭合。原子 S1+S2 最小边界、精确 blocker 测试终态、combined regression 硬门、共享文件符号边界、plan/code commit 文件集互斥均已有完整证据支撑。

Amendment 是 code-generation-ready 的，可以交给 implementation agent 恢复实现。下一入口为 plan amendment acceptance，随后恢复 S1+S2 implementation。
