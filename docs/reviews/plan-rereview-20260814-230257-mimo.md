# Plan Re-review — upload-filing-ticker-alias-contract（第二轮，AgentMiMo 复核）

## Review metadata

| 字段 | 值 |
| --- | --- |
| Reviewer | AgentMiMo |
| Artifact | `docs/reviews/plan-rereview-20260814-230257-mimo.md` |
| Review type | plan re-review（第二轮，plan fix round 2 后复核） |
| Reviewed plan | `docs/reviews/wu-upload-filing-ticker-alias-contract-plan-codex.md` |
| Plan fix artifacts | `docs/reviews/wu-upload-filing-ticker-alias-contract-plan-fix-codex.md`; `docs/reviews/wu-upload-filing-ticker-alias-contract-plan-fix-2-codex.md` |
| Controller adjudications | `docs/reviews/wu-upload-filing-ticker-alias-contract-plan-review-controller-adjudication.md`; `docs/reviews/wu-upload-filing-ticker-alias-contract-plan-rereview-controller-adjudication.md` |
| Goal confirmation | `docs/reviews/wu-upload-filing-ticker-alias-contract-goal-confirmation-controller.md` |
| Previous rereview artifacts | `docs/reviews/plan-rereview-20260814-222224-mimo.md`（MiMo, pass）; `docs/reviews/plan-rereview-20260814-222224-ds.md`（DS, fail — blocker: meta-less corpus） |
| Review scope | P1–P5 修复验证、A1–A8/R1/R2 回退检查、五个直接代码流挑战、旧 P4 撤回确认 |
| Conclusion | **pass** |

## Method

本轮复核完整读取：第二轮 plan fix artifact、rereview controller adjudication、两份上一轮 rereview artifact、goal confirmation、第一轮 controller adjudication、第一轮 plan fix artifact 与当前 plan。以直接代码/数据流证据验证 P1–P5 修复是否落入 plan，用直接代码流挑战五个指定区域，确认旧 P4 拒绝 material aliases 已彻底撤回且无 accept-ignore，并逐项检查 A1–A8 与 R1/R2 是否回退。

## P1–P5 修复验证

### P1 — meta-less corpus canonical-only identity：已修复，证据成立

**上一轮 blocker 本质**：DS F1 指出 plan 将 `missing_meta` 定义为 workspace corruption，与 `FilingUploadPublishedState.company_meta=None`、material upload 无 meta 路径、公开空 batch 提交等合法状态直接冲突。controller adjudication 裁决为 blocker。

**本轮 plan 修订验证**：

1. **`missing_meta` 从 corruption kind 移除**：§5.6 `CompanyTickerIdentityCorruptionKind` 闭集为 `invalid_descriptor | invalid_meta | identity_mismatch | duplicate_owner`，不含 `missing_meta`。与 DS F1 建议第 1 点一致。
2. **descriptor canonical 无条件进入 index**：§5.5 step 2 明确 "_scan_actual_published_company_identities() 只枚举 portfolio/ 实际 directories，strict 读取每个 descriptor，返回 descriptor canonical + optional valid CompanyMeta"。§5.5 step 3 "只有 meta.json 存在且 strict CompanyMeta.from_dict() 成功…才把 accepted_aliases 加入同一 index"。meta-less corpus 只贡献 canonical，不贡献 alias——符合 durable-fact 原则。
3. **read semantics 正确**：§5.5 step 4 "meta-less corpus 的 canonical query 返回自身 descriptor canonical 并可读取真实 documents；它没有 accepted aliases，alias query 返回 NOT_FOUND"。与今天 `_fs_company_meta_core.py:262-265` 的 direct canonical probe 行为一致，无用户可见回归。
4. **commit semantics 正确**：§7.4 step 6 "incoming canonical target 存在且 descriptor 合法但 meta.json 缺失时，current_published=None，允许 refresh_if_stale 的 create transition 给 material-first corpus 首次补齐 CompanyMeta"。与 DS F1 建议第 2 点一致。
5. **`publishes_new_corpus` 冻结**：§7.2 "begin_batch 在持有 same-ticker writer 并确认 target 是否存在后…把 publishes_new_corpus 冻结为本 batch 将首次发布 ticker descriptor 的 exact transaction-local fact"。§7.4 step 3 "company_meta_intent is None and publishes_new_corpus is False：既有 corpus 的 document-only commit，不取得 workspace recovery/identity guard"。首次 meta-less descriptor publication 通过 `publishes_new_corpus=True` 进入 identity-changing 路径。
6. **prevalidation 后 meta 消失**：§5.3 rule 6 "current 不存在但 expected_non_identity 非 None…抛 CompanyMetaConcurrentUpdateError"，不归为 corruption。与 DS F1 建议第 2 点一致。
7. **validation 完整**：§11.3 包含 meta-less corpus canonical list_documents、与健康 alias corpus 共存、补 CompanyMeta、canonical conflict 双向、invalid/meta mismatch/duplicate 仍 fail closed、prevalidation 后 meta 消失走 concurrent update。与 DS F1 建议第 5 点一致。

**结论**：P1 修复精确落入 controller 裁决与 DS F1 的全部建议点。meta-less corpus 的 durable state 语义、read 语义、commit 语义和测试覆盖均已闭合。

### P2 — 补齐 FmpCompanyInfo 测试 consumers：已修复

§9.3 已加入 `tests/cli/test_prompt_command.py` 与 `tests/service/test_entrypoint_runtime.py`。§12.4 residue scan 改为 multiline `rg -U`，覆盖跨行旧 constructor fields。S1 allowed tests 明确包含这两个文件。修复完整。

### P3 — 6-K repair direct branch validation：已修复

plan 明确 "现有 module regressions 没有触达该分支"（删除旧 "既有 repair regression 已覆盖" 的错误表述）。S1 "必须新增或扩展 public-path test，以 reconcile_active_6k_primary_documents(..., target_tickers=None) 精确经过 inventory discovery 并断言 canonical projection"。由生产文件逐文件 branch coverage >=80% 兜底。修复完整。

### P4 — material aliases 与 filing 同源、可靠持久化：已修复，旧拒绝方案已彻底撤回

**旧 P4 拒绝方案撤回验证**：fix-2 artifact §P4 标题 "Controller 纠正与 rejected-with-reason"，正文 "该方案现为 rejected-with-reason 并已从 plan 完全撤回"、"若按旧 P4 拒绝/删除，会破坏既有 material CompanyMeta producer…因此不能实施，也不作为 residual risk 保留"。plan 中无任何 "material 非空 aliases typed reject"、"CLI 改单 ticker" 或 "删除 pipeline 消费" 的表述。撤回彻底。

**本轮 plan 修订验证**：

1. **数据流闭环**：fix-2 明确 "SEC run_upload_material_stream 与 CN upload_material_stream 的 create/update 都在 source document publication 前开启 CompanyMeta batch，调用 upsert_company_meta_for_upload(..., ticker_aliases=...) 并 commit"。§5.8 冻结 "FinsUploadMaterialRequest.ticker_aliases 是 accepted input；service_runtime 继续把 canonical ticker 与 aliases 原样交给对应 SEC/CN material producer"。
2. **统一 builder/intent**：§5.8 step 2 "S1 删除 upsert_company_meta_for_upload 内部重复的 fresh/stale/normalization 分支，改为语义准确的 stage_company_meta_for_upload"。§5.8 step 4 "S2 让 filing prevalidation 与 material direct producer 都只 stage 同一个 CompanyMetaCommitIntent"。
3. **residue 要求**：fix-2 §P4 "final residue 要求 upsert_company_meta_for_upload 零命中，证明重复 owner 已删除；同时 implementation artifact 必须列出 FinsUploadMaterialRequest.ticker_aliases -> service_runtime -> SEC/CN stage_company_meta_for_upload -> CompanyMetaCommitIntent 直接调用点，防止用删除数据流伪造零命中"。

**结论**：P4 修复正确闭合了 material aliases 的 producer 链。旧拒绝方案彻底撤回，无 accept-ignore。

### P5 — descriptor corruption closed kind 完整：已修复

§5.6 `CompanyTickerIdentityCorruptionKind` 包含 `invalid_descriptor`。定义精确："实际 published ticker directory 缺少 identity descriptor，或 descriptor 不是 non-symlink regular file、JSON/schema/namespace/external identity/private locator 双向关系非法，或 descriptor external ticker 不能被唯一 ticker owner 接受为该目录的 exact canonical"。§11.3 测试覆盖 descriptor 缺失、symlink/non-regular、invalid JSON/schema/namespace/locator/external canonical。合法 missing meta.json 不属于 invalid_descriptor。修复完整。

## 五个直接代码流挑战

### 挑战 1：meta-less descriptor canonical-only index

**挑战**：descriptor-only corpus 的 canonical 如何进入 index？alias 是否会凭空产生？

**plan 代码流**：
- `_scan_actual_published_company_identities()` 枚举 `portfolio/` 实际 directories，strict 读取 descriptor → 返回 `(descriptor_canonical, optional_valid_CompanyMeta)`
- `_build_unique_company_identity_index()` 先登记每个 descriptor canonical → `dict[canonical, canonical]`
- 若 meta.json 存在且 strict valid 且 canonical/market 与 descriptor 一致 → 登记 `accepted_aliases` → `dict[alias, canonical]`
- meta-less corpus：只有 descriptor canonical 进入 index，无 alias → alias query 不命中，canonical query 命中自身

**验证**：§5.5 step 2-4 精确描述此流程。与今天 `_fs_company_meta_core.py:262-265` 的 direct canonical probe 行为一致（`ticker_dir.exists()` 命中），alias index 构建（`:345-349`）只过滤 `status == "available"` 且需要 CompanyMeta。无回归。

### 挑战 2：publishes_new_corpus 原子冲突

**挑战**：首次发布 meta-less descriptor 时，如何保证其 canonical 不与既有 alias 冲突？

**plan 代码流**：
- `begin_batch` 在 same-ticker writer 下确认 target 不存在 → `publishes_new_corpus=True`
- commit: `company_meta_intent is None and publishes_new_corpus is False` → 跳过（不适用）
- 进入 identity-changing 路径：recovery guard → identity guard → publication guard
- identity guard 内：重读 current published（`publishes_new_corpus=True` → `current_published=None`）
- 无 meta intent → 不写 meta.json
- actual-published scan：登记所有 descriptor canonical + valid meta aliases
- 检查 incoming lookup keys（仅 descriptor canonical）：index 未命中或 owner == incoming canonical → 继续；owner 为其它 canonical → `CompanyTickerAliasConflictError`
- 通过 → backup/swap/COMMITTED

**验证**：§7.4 step 6/8/9 精确描述。incoming canonical 自身不误报冲突（"index 未命中或 owner 等于 incoming canonical 可继续"）。meta-less canonical 撞既有 alias 和 alias 撞 meta-less canonical 两个方向都原子拒绝（§7.4 step 9 注释）。验证完整。

### 挑战 3：normal material SEC/CN 确实通过统一 builder/intent 持久化 aliases

**挑战**：material 是否真的写 CompanyMeta？还是 plan 声称但实际不写？

**直接代码证据**：
- `dayu/fins/pipelines/sec_upload_workflow.py::run_upload_material_stream`：create/update 都在 source document publication 前调用 `upsert_company_meta_for_upload(..., ticker_aliases=...)`
- `dayu/fins/pipelines/cn_pipeline.py::upload_material_stream`：同上
- `dayu/fins/service_runtime.py`：把 request aliases 原样下传

**plan 代码流（S1）**：
- SEC/CN material direct producer 迁移到 `stage_company_meta_for_upload`：caller 已 `begin_batch(canonical)` → public-read `existing_meta | None` → 调用 `resolve_upload_company_meta_decision` → 调用 stage helper
- `resolve_upload_company_meta_decision` 调用 `build_company_ticker_identity(canonical, declared_aliases)` → fresh meta 新增 alias → stage（非 keep）

**plan 代码流（S2）**：
- 同一 `CompanyMetaCommitIntent` → storage commit 在 writer/recovery/identity guards 下 authoritative 重读 → `merge_company_meta_for_commit` → stable union aliases

**验证**：fix-2 §P4 引用了直接 producer 代码证据。§5.8 冻结了完整数据链。§11.2 "material owner tests：US/CN create 以 DELTA,MSFT,V.BA 成功后 strict CompanyMeta 包含 MSFT/V-BA 且不重复 canonical"。residue 要求 "upsert_company_meta_for_upload 零命中 + 必须列出直接调用点"。验证完整。

### 挑战 4：invalid_descriptor closed kind

**挑战**：`invalid_descriptor` 是否精确覆盖 descriptor 结构损坏？是否与合法 meta-less 状态混淆？

**plan 代码流**：
- §5.6 closed kinds：`invalid_descriptor | invalid_meta | identity_mismatch | duplicate_owner`
- `invalid_descriptor` 精确定义：缺 descriptor、symlink/non-regular、JSON/schema/namespace/locator/external identity 非法、external ticker 非 exact canonical
- `_scan_actual_published_company_identities()` 把 `FileNotFoundError`/validation `ValueError` 收敛为 `invalid_descriptor`；普通 permission/I/O → storage unavailable/storage_io
- 合法 missing meta.json → 不是 corruption，canonical-only identity

**验证**：§5.6 闭集定义精确，§11.3 测试逐一覆盖四种 corruption kind + 合法 meta-less 共存。与 P1 的 missing_meta 移除一致。无混淆。

### 挑战 5：6-K 与漏列 fixtures

**挑战**：6-K `_resolve_target_tickers` 是否有直接测试覆盖？§9.3 测试清单是否完整？

**6-K 验证**：
- plan 明确 "现有 module regressions 没有触达该分支"
- S1 "新增或扩展 public-path test，以 reconcile_active_6k_primary_documents(..., target_tickers=None) 精确经过 inventory discovery 并断言 canonical projection"
- 生产文件逐文件 branch coverage >=80% 兜底

**漏列 fixtures 验证**：
- §9.3 已包含 `tests/cli/test_prompt_command.py` 与 `tests/service/test_entrypoint_runtime.py`
- §12.4 residue scan 改为 multiline `rg -U`

**验证**：P2/P3 修复已闭合。无遗漏。

## A1–A8 回退检查

### A1 — same-canonical lost update：未回退

plan §5.3 commit intent/merge 规则不变：current aliases 在前、intent aliases 在后 stable union；`preserve_published` 保留 current 非 identity 字段；`refresh_if_stale` 按 optimistic precondition 判定。§7.4 identity guard 内 authoritative 重读。§11.3 spawn barrier tests 不变。A1 修复未回退。

### A2 — 6-K production consumer：未回退

§9.1 仍含 `sec_6k_primary_document_repair.py`，S1 allowed files 包含。迁移仍限定为 `ticker_identity.canonical_ticker` 机械替换。P3 提高了验证精度但未改变 scope。A2 修复未回退。

### A3 — S1 storage 中间契约：未回退

§10 S1 change #5 保留 `resolve_existing_ticker(list[str])`、`dict[str, list[str]]` index、duplicate-owner late `ValueError`。S2 一次切换为 `resolve_company_ticker(str)` + `dict[str, str]`。S1 residue 临时允许项不变。A3 修复未回退。

### A4 — incoming conflict / published corruption 分型：未回退，且增强

`CompanyTickerAliasConflictError` 与 `CompanyTickerIdentityCorruptionError` 分型不变。P5 补齐了 `invalid_descriptor` closed kind，增强了 corruption 分型完整性。read/upload 投影路径不变。A4 修复未回退。

### A5 — company-name-required reason 收窄：未回退

`UploadCompanyNameRequiredError` typed exception + 只捕获该异常不变。§11.2 "builder/identity corruption 不得被 catch 成 COMPANY_NAME_REQUIRED" 断言不变。A5 修复未回退。

### A6 — invalid published meta commit fail closed：未回退，且更精确

§7.4 step 6/8 fail-closed 时点不变。P1 将合法 meta-less 从 corruption 移除，使 fail-closed 更精确地只覆盖真正的 invalid/mismatch/duplicate。A6 修复未回退。

### A7 — recovery/read barrier 及 guard failure tests：未回退

§7.5 recovery identity guard 位置不变。§11.3 barrier、guard acquire/release failure tests 不变。A7 修复未回退。

### A8 — S1/S2 完成语义：未回退

§1 末段 "用户只排除 PR 与 push，不把普通 gate 完成视为停止条件" 不变。S1 completion signal "只是 reviewed local checkpoint…不得部署、close 或进入 final closeout" 不变。A8 修复未回退。

## R1/R2 rejection 复核

### R1 — recovery 不用 meta.json 存在推断 mutation：rejection 仍合理

plan §7.5 "无条件对所有 recovered ticker tree 使用 guard；绝不以 staging/published meta.json 存在猜测 mutation"。`begin_batch` 的 `shutil.copytree` 会复制整个 published tree（含 meta.json）到 staging，因此 staging meta.json 存在不表示本 batch 修改过 CompanyMeta。rejection 理由经代码再次验证成立。

### R2 — `_STORAGE_FAILURE_CODES` 是 S2 planned-new code：rejection 仍合理

`upload_failure.py` 当前不存在 `_STORAGE_FAILURE_CODES`。plan §5.7 明确 "新增" 该 closed set。fix-2 "R2 保持 rejected-with-reason：_STORAGE_FAILURE_CODES 仍是 S2 planned-new code，不是当前遗漏"。rejection 理由成立。

## Over-design / Goal drift 检查

- **Goal drift**：plan §14 goal alignment matrix 与 goal confirmation 8 条 success signal 一一对应。P1–P5 修复均为闭合已确认 goal 或 safety condition，无新增目标。
- **Over-design**：第一轮 MiMo rereview 的五个 over-design challenge 结论不变（CompanyMetaCommitIntent、identity guard、two typed errors、two slices、no durable index 均非过度设计）。本轮无新增 abstraction。

## Open questions

无。P1–P5 修复闭合了上一轮全部 open questions（meta-less corpus canonical read 语义已冻结为保留 descriptor 直查；A1 残余分类已在 §5.3 rule 6 中明确为 `CompanyMetaConcurrentUpdateError`）。

## Residual risks

| Risk / uncovered area | Classification | Owner / destination |
| --- | --- | --- |
| 旧 workspace 歧义 alias / 旧 CompanyMeta schema | `assigned to later work unit` | fresh schema 边界；如需升级另立 migration WU |
| UF-PF05 真实 CLI evidence | `assigned to later work unit` | 用户明确排除 |
| oracle/scenario registry、冻结 evidence、其它 finding | `assigned to later work unit` | 用户明确排除 |
| workspace descriptor/meta scan 成本随公司数增长 | `assigned to later work unit` | 仅在真实 profile 超标后另立性能 WU |
| recovery 对所有 orphan tree 取 identity guard 的等待 | `assigned to later work unit` | R1 correctness 优先；只有实测 contention 后优化 |
| SEC upload/SEC download/CN download 既有 resolver version 不一致 | `assigned to later work unit` | rereview controller 裁决为既有行为且本 WU 不恶化 |

没有 unclassified residual risk。

## Final plan review conclusion

**pass**

P1–P5 全部精确落入 plan：P1 将 meta-less corpus 从 corruption 收窄为 canonical-only identity，闭合了上一轮唯一 blocker；P2 补齐两个 FmpCompanyInfo 测试 consumer；P3 修正 6-K 验证表述并要求新增 direct branch test；P4 按完整 material producer 数据流撤回旧拒绝方案并冻结 material/filing 共用 builder/intent/authoritative merge；P5 将 `invalid_descriptor` 加入 closed corruption kind。A1–A8 全部未回退，R1/R2 rejection 理由经代码再次验证成立。五个直接代码流挑战全部通过：meta-less descriptor canonical-only index 流程正确、publishes_new_corpus 原子冲突验证完整、normal material SEC/CN 通过统一 builder/intent 持久化 aliases 有直接 producer 代码证据、invalid_descriptor closed kind 精确且不与合法 meta-less 混淆、6-K 与漏列 fixtures 已闭合。旧 P4 拒绝 material aliases 已彻底撤回，plan 中无 accept-ignore。

plan 可以交给 implementation agent 进入 S1。next entry point：Gateflow 在当前分支创建 accepted plan local commit，自动进入 S1 implementation。
