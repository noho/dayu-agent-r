# Code Review — UF-FIX02 S2 Re-review（AgentDS）

## Scope

- Mode: current changes（fix gate 后 re-review，只核验 Controller accepted 的两项 finding 及其无回归面）
- Branch or PR: `codex/upload-filing-oracle`（本地未提交，无 PR）
- Base: `08316516ca3da7f98299ee90d3fa753c32c59020`（accepted S1 commit，即当前 HEAD）
- Adjudication: `docs/gateflow/uf-fix02-action-and-update-identity-s2-code-review-adjudication-20260813.md`
- Reviewed artifacts: `docs/gateflow/uf-fix02-action-and-update-identity-s2-implementation-20260813.md`（含 §11 fix addendum）、`docs/gateflow/uf-fix02-action-and-update-identity-s2-code-review-fix-20260813.md`、首轮两份 review（DS / MiMo）
- Output file: `docs/reviews/code-review-20260813-190336-uf-fix02-s2-rereview-ds-20260813.md`
- Included scope:
  - `dayu/fins/pipelines/docling_upload_service.py`（唯一生产 diff）
  - `tests/fins/test_docling_upload_service.py`（fix 唯一测试 diff）
  - `tests/fins/test_sec_pipeline_upload_filing_stream.py`、`tests/fins/test_cn_pipeline.py`（确认 fix 未触及）
  - `README.md`、`dayu/fins/README.md`、`tests/README.md`（确认无 fix 期变更）
  - 沿真实主链路走读：`dayu/fins/storage/_fs_source_document_core.py`（`_upsert_source_document` merge/setdefault 语义）
- Excluded scope: 无（3 个 untracked gateflow artifact + 2 个首轮 review artifact 只读，不修改）
- Parallel review coverage: 无（单人走读）

## Findings

未发现实质性问题。

两项 accepted finding 的 fix 均在 owner boundary 内实现，独立验证通过；S2 原始行为与验证面无回归。详见核验清单。

## 核验清单（逐项直接证据）

### A. DS Finding 1：reset→create 后 `created_at` 保持（accepted，blocking）

| 核验项 | 结论 | 直接证据 |
| --- | --- | --- |
| `_build_upsert_meta` 从 reset 前 `previous_meta` 派生 `created_at`，缺失才用本次 `now` | PASS | `docling_upload_service.py:776`（`previous_created_at = _text_meta(previous_meta, "created_at") if previous_meta is not None else None`）、`:780`（`merged["created_at"] = previous_created_at or now`），与 `:773-779` 的 `first_ingested_at` 派生同形；`now = now_iso8601()` 在 `:772` 单次取得 |
| meta 派生发生在 reset 之前，`previous_meta` 为唯一真源 | PASS | 调用链：`prepare_upload:290` 拷贝 `normalized_previous_meta` → `:338-343` `_build_upsert_meta(previous_meta=normalized_previous_meta)` 产出 `staging_meta` → `_PreparedAssetMutation(previous_meta=…, meta=staging_meta)`（`:344-358`）→ `publish_prepared_upload:403-419` 透传 → `_store_upload_assets:483` 才 reset；`:531-541` final create 写入的是 reset 前构建的 meta。reset 后无第二次 `_build_upsert_meta` 调用 |
| 缺失/非文本/空白 `created_at` 时用本次 `now` | PASS | `_text_meta`（`:1438-1455`）缺失或非 str 返回 `""`，str 会 strip；`previous_created_at or now` 对 `None`/`""` 均落到 `now`，与 `first_ingested_at` 一致 |
| 不得在 storage 下游 fallback | PASS | `git status` 中无任何 storage 文件变更；storage `_fs_source_document_core.py:1689-1701` 仍是 `merged_meta.update(req.meta)` 后 `setdefault("created_at", now)`——caller meta 已含 `created_at` 时 setdefault 不触发，且没有新增下游补偿逻辑 |
| 不改变 batch/admission/workflow | PASS | 生产 diff 相对 base 仅 `docling_upload_service.py` 一个文件；fix 相对 S2 仅新增 `:776`、`:780` 两行（对照 fix artifact §4.1 与首轮 DS review 引用的 `:772-785` 旧文）；admission（`evaluate_upload_overwrite_precondition`、`_can_skip_upload`）、`commit_prepared_upload_batch`（`:839-892`）rollback 契约、SEC/CN/HK workflow 生产代码均未被 fix 触及 |
| storage 不会在最终 meta 中覆写 caller `created_at` | PASS | 直接行为证据：deterministic-clock owner 测试 GREEN（见 B），若 storage 用自身（同样被 patch 的）时钟覆写，`restored_meta["created_at"] == created_meta["created_at"]`（`2020-01-01` vs `2020-01-02`）必失败 |

### B. DS Finding 1 的 owner 测试（确定性 owner contract）

| 核验项 | 结论 | 直接证据 |
| --- | --- | --- |
| renamed update 断言 `created_at` 保持 | PASS | `test_execute_upload_existing_full_input_replaces_exact_complete_set`（`:1452-1537`）parametrize `(FILING, update, False, report.txt, report.txt)`、`(FILING, update, False, old-report.txt, renamed-report.txt)`、`(MATERIAL, create, True, …)`（`:1444-1450`）；`:1535` `assert final_meta["created_at"] == initial_meta["created_at"]` |
| deleted equal/changed restore 断言 `created_at` 保持 | PASS | `test_execute_upload_deleted_input_republishes_complete_source`（`:1349-1441`）parametrize `(FILING, False)`、`(FILING, True)`、`(MATERIAL, False)`（`:1341-1348`）；`:1440` `assert restored_meta["created_at"] == created_meta["created_at"]` |
| material shared-owner parity 断言 `created_at` 保持 | PASS | 上述两测试均含 MATERIAL 参数（create-overwrite 与 deleted equal restore） |
| version / `first_ingested_at` / active / integrity 断言保留 | PASS | `:1437-1439,1441`（version v2-or-keep、first_ingested_at、integrity COMPLETE）、`:1533-1537`（version v2、first_ingested_at、is_deleted False、integrity COMPLETE） |
| 确定性时钟，无秒级偶然假绿 | PASS | `:58-59` 常量 `2020-01-01` / `2020-01-02`；`_set_upload_clock`（`:62-83`）同时 monkeypatch `docling_upload_service.now_iso8601` 与 `storage._fs_source_document_core.now_iso8601`，两个阶段分置，断言必须依赖 owner 派生而非同秒巧合 |
| RED 证据成立 | PASS | 构造性核验：若 owner 未派生，replace/restore 阶段时钟为 `2020-01-02`，`:1440`/`:1535` 必失败；fix artifact §3 记录的 6 failed 参数集（filing same-name、filing renamed、material create-overwrite、filing deleted equal/changed、material deleted equal）与当前断言位置一一对应；GREEN 独立重跑见 D |

### C. MiMo Finding 1：dead update override 删除，create failure 保留

| 核验项 | 结论 | 直接证据 |
| --- | --- | --- |
| `_FailingFinalUploadSourceRepository.update_source_document` dead override 已删除 | PASS | `tests/fins/test_docling_upload_service.py:106-120` 该类现在只 override `create_source_document`；全文件 `update_source_document` / `update_failed` 零命中（grep 仅 `create_failed` 命中） |
| final create failure 注入与 `create_failed` 断言保留 | PASS | `:109-120` 注入 `create_failed` 事件并 raise；`:1151`、`:1807` 均 `assert events[-1] == "create_failed"`；`test_execute_upload_update_failure_keeps_previous_document`（`:1744`）parametrize `overwrite=[False, True]` 保留，`:1804-1806` 旧 meta/files/tree SHA 不变断言保留 |

### D. 独立重跑验证

| 验证项 | 结果 | 命令/证据 |
| --- | --- | --- |
| 精确 owner/failure GREEN | **8 passed** | 两个 created_at owner 测试（3+3 参数）+ failure 测试（2 参数） |
| S2 focused | **74 passed, 3 warnings** | `test_docling_upload_service.py` + `test_sec_pipeline_upload_filing_stream.py` + `test_cn_pipeline.py` |
| 完整 owner/boundary focused | **321 passed, 3 warnings** | 同 fix artifact §5.3 命令 |
| UF-FIX01 / atomicity / cancellation regressions | **343 passed, 3 warnings** | 同 fix artifact §5.4 命令；warning 均为既有 edgar deprecation |
| 逐文件 coverage ≥ 80% | **87%**（391 stmts / 51 missed） | 独立 mktemp coverage data 重跑；missed 行清单（`183, 218, 220, 222, 271, 274, 276, 278, 280, 302, 336, 384, 525, 527, 584-592, 615-622, 711, 717, 922, 940, 944, 947, 969, 1089, 1092, 1112-1115, 1144, 1146, 1184, 1241, 1245, 1277, 1280, 1303, 1324, 1345, 1455`）**不包含** `:776`/`:780`，created_at 派生行被测试覆盖 |
| 完整 pyright | **0 errors, 0 warnings, 0 informations** | `python -m pyright dayu/ tests/ utils/`（唯一输出为版本升级提示，非项目问题） |
| `git diff --check` | exit 0 | 独立重跑 |
| frozen registry SHA-256 | 保持基线 | `cli_ci_scenarios.json` = `a357e5a1…788efb`、`cli_ci_oracles.json` = `88b04ca4…770b8`，与 plan 基线一致 |
| design / registry no-touch | PASS | `git diff --exit-code -- docs/cli_ci_scenarios.json docs/cli_ci_oracles.json docs/host/design.md docs/engine/design.md` exit 0 |
| `_resolve_upsert_mode` Python 源码零命中 | PASS | `rg -n '_resolve_upsert_mode' --glob '*.py' .` exit 1、无输出 |
| changed paths 精确 | PASS | `git status --short` 恰为 7 modified（README×2、tests/README、生产 1、测试 3）+ 5 untracked artifact docs，无 fix 期新增路径；SEC/CN 测试 diff 中 `created_at`/`_set_upload_clock`/`2020-01` 新增行数为 0，证明 fix 未触及 |
| 生产 added-lines static audit | PASS | 新增行零命中 `hasattr/getattr`、`Any/object`、`str(exc)`、lazy import、compat wrapper/re-export；无 basename/stem identity、无默认 deleted state、无下游 fallback、无补偿删除/跨 batch/ticker 级清空 |
| README 无 fix 期变更 | PASS | 三处 README diff 均为 S2 期内容（已由首轮双 review PASS），fix 未追加；`dayu/README.md` 未动，符合 plan §7 决策 |

### E. S2 原始行为无回归

| 核验项 | 结论 | 直接证据 |
| --- | --- | --- |
| exact reset/create 同 batch | PASS | `docling_upload_service.py:477-488`（`replace_existing` → 同 `batch` reset）、`:503-521`（blob 同 batch）、`:531-541`（final create 同 batch），与 S2 评审时一致 |
| rollback / old-or-new | PASS | `commit_prepared_upload_batch:839-892` 与 `rollback_prepared_upload_batch:895-` 未变；cancel/blob/final/failure 测试全部在 D 中重跑通过 |
| fresh-state（SEC/CN/HK） | PASS | workflow 生产代码无 diff；SEC/CN 回归测试通过（74/321/343 三套） |
| `_resolve_upsert_mode` 零命中 | PASS | 见 D；diff 仅删除函数，无 re-export/wrapper/compat shim |

## Open Questions

- 无阻碍裁决的问题。
- 信息性提示（非 finding）：`dayu/fins/README.md:110` 明确点名 reset 前 source meta 是「version 与 `first_ingested_at`」真源，未点名 `created_at`。fix artifact §7 以「既有 README 已承诺首次创建事实真源」为由不改 README，该表述略宽于 README 字面。README 现状不构成语义矛盾（`created_at` 与二者同源、同机制），且本 fix 不改变用户可见语义；是否把 `created_at` 补入该句由 Controller 决定，不阻塞本 re-review 裁决。

## Residual Risk

- 未独立重跑 fix 期的精确 RED（6 failed）：与首轮 DS review 相同的原因——fix 已进入工作树，禁止修改生产/测试以复现 RED 状态。已做构造性核验：RED 参数集与当前断言一一对应，且确定性双时钟下该断言不可能偶然通过。
- UF-PF02 focused-real 仍未执行（plan 归后续 gate），本 re-review 结论基于 owner/workflow 测试与真实 FS 仓储。
- 首轮已列 residual risks 及 owner 不变：UF-FIX10 同请求竞争、UF-FIX08 repair、UF-FIX07 collision、UF-FIX06 format、UF-FIX03 counts/errors、UF-FIX11 company warning、UF-PF12 broader conformance、material broader typed projection、frozen evidence 后续统一刷新。

## Conclusion

**PASS。**

两项 accepted findings 的 fix 均在 owner boundary 内实现并被独立验证：

1. DS Finding 1（created_at 漂移）：`_build_upsert_meta` 在 reset 前从 `previous_meta` 派生稳定 `created_at`，缺失才用本次 `now`，与 `first_ingested_at` 同形同源；无 storage 下游 fallback，batch/admission/workflow 未变；renamed update、deleted equal/changed、material parity 均有确定性双时钟 owner 断言（6 参数），version / `first_ingested_at` / active / integrity 断言保留。
2. MiMo Finding 1（dead update override）：已删除，create failure 注入与 `create_failed` 断言（overwrite 两参数）保留。

S2 原始 exact reset/create、rollback、fresh-state、`_resolve_upsert_mode` 零命中无回归；8/74/321/343 四套测试独立重跑全绿，生产文件 coverage 87%（created_at 派生行被覆盖），完整 pyright 0 错，frozen/design no-touch、changed paths、static audit 全部通过。未修改生产、测试或任何既有 artifact；本 re-review 后停止，未 commit / 未进入下一 gate。
