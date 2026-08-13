# Code Review — UF-FIX02 S1 Re-review（AgentDS）

## Scope

- Mode: current changes
- Branch: `codex/upload-filing-oracle`
- Base: `56d159cb4bf13baf82858bb237b2f73075eaf717`（accepted plan commit；当前 HEAD 即该 commit，review 面为全部未提交 workspace diff）
- Output file: `docs/reviews/code-review-20260813-182233-uf-fix02-s1-rereview-ds.md`
- Included scope:
  - 生产 diff：`dayu/fins/pipelines/docling_upload_service.py`、`dayu/fins/ingestion_runtime.py`、`dayu/fins/storage/source_meta_contract.py`（新增）、`dayu/fins/storage/__init__.py`、`dayu/fins/storage/_fs_source_snapshot.py`、`dayu/fins/README.md`
  - 测试 diff：`tests/cli/test_fins_commands.py`、`tests/fins/test_docling_upload_service.py`、`tests/fins/test_fins_ingestion_runtime.py`、`tests/fins/test_source_meta_contract.py`（新增）
  - 沿真实调用链走读的既有生产文件（只读，无 diff）：`dayu/cli/commands/fins.py`（prevalidation 与 factory 顺序）、`dayu/fins/ingestion_runtime.py`（`validate_fins_upload_filing_request`、`resolve_upload_action` 消费点）、`dayu/fins/service_runtime.py`
  - Gateflow 基线：goal confirmation、approved plan、S1 implementation、Controller adjudication、code-review-fix 五个 artifact；首轮 AgentDS review（`code-review-20260813-180034.md`）
- Excluded scope: AgentMiMo 首轮与并行 re-review artifact（`code-review-20260813-175624.md`、`code-review-20260813-192100-uf-fix02-s1-rereview-mimo.md`）——本 review 保持独立，不读其结论；S2 及 UF-FIX03–12 的生产实现。
- Parallel review coverage: 无（未启动子 agent）。
- 独立复跑验证：本次 re-review 独立执行了 focused 测试、UF-FIX01 回归套件、完整 pyright 与五文件 coverage，非仅采信 artifact 证据。

## Verdict

**PASS**（1 个低严重度 finding 供 Controller 裁决，不阻塞 S1 核心语义；见 Findings）

## DS 核验结论摘要

| 核验项 | 结论 | 直接证据 |
| --- | --- | --- |
| DS-02 strict is_deleted reader 唯一 owner + 两消费者复用 | 通过 | 唯一实现 `dayu/fins/storage/source_meta_contract.py:13-32`；公共导出 `storage/__init__.py:35,66`；snapshot 两处（`_fs_source_snapshot.py:765,1089`）与 Docling skip（`docling_upload_service.py:1003`）复用同一实现；`_require_deleted_flag`/`_require_source_deleted_flag` 已删除，全仓零命中；错误文案仅此一份（grep 验证） |
| DS-03 CLI 已存在 filing 的 update 与 update+overwrite 只投影 typed request | 通过 | `tests/cli/test_fins_commands.py::test_upload_filing_existing_update_projects_typed_request_to_service` 通过真实 storage seed（`_seed_cli_filing_source`），断言 factory 被调用、`_UploadFilingCall(action="update", overwrite=…)` 全字段精确投影与 `stream_calls == [UPLOAD_FILING]`；missing 场景仍只走冲突矩阵（factory 不调用） |
| DS-04 prepare_upload Raises 完整 | 通过 | `docling_upload_service.py:261-262` 登记 corruption `KeyError`/`ValueError`；`_can_skip_upload` docstring（`:997-998`）同步登记 |
| S1：update missing 无论 overwrite 均失败 | 通过 | `evaluate_upload_overwrite_precondition`（`:186`）删除 overwrite 条件；validator（`ingestion_runtime.py:976-977`）、`prepare_upload`（`:299-300`）、CLI 三层测试均覆盖 ±overwrite，converter 0 调用 |
| S1：deleted auto 不 skip | 通过 | `resolve_upload_action` deleted 仍解析 update（`:1252-1254`）；`_can_skip_upload` 对 `is_deleted=True` 返回 False（`:1003-1004`）；runtime 测试固定 deleted auto→update 且 identity 与文件名无关；service 测试证明 deleted + equal fingerprint 进入 conversion 并 `uploaded` |
| UF-FIX01 零 mutation / atomic batch / bounded stderr / cancellation 无回归 | 通过 | 生产 diff 仅触及 admission/skip/message 符号与 storage reader 等价替换；CLI 冲突测试断言 exit 2、stdout 空、单行 bounded stderr、factory 零调用、workspace 树 SHA-256 零变化；UF-FIX01 回归套件独立复跑 `343 passed` |
| DS-01 material parity deferred-with-owner，diff 未新增或恶化 | 通过 | fix diff 未触碰 FILING 守卫（`prepare_upload:297`）、material workflow、`_resolve_upsert_mode`；`_can_skip_upload` 的 strict 读取语义与 S1 首轮实现逐字等价（仅实现身份收敛）；material 缺口已登记 residual（implementation §7） |
| tests-first 证据 | 通过 | 首轮 RED（9 failed 精确集合）、DS-03 RED（seed 前 2 failed exit 2）、DS-02 RED（ImportError）均已记录；GREEN 由本 review 独立复现 |
| 单生产文件 coverage ≥80% | 通过 | 独立复跑：`docling_upload_service.py` 86%、`ingestion_runtime.py` 91%、`storage/__init__.py` 100%、`_fs_source_snapshot.py` 86%、`source_meta_contract.py` 100% |
| 完整 pyright | 通过 | 独立复跑：`0 errors, 0 warnings, 0 informations`，exit 0 |
| README / no-touch | 部分通过 | `dayu/fins/README.md` 已按其更新约束登记契约；frozen 四文件与 `git diff --check` 通过；根 README 存在 1 个低严重度 plan-deviation（Finding 1） |
| 兼容 shim / lazy import / 下游 fallback / 重复 owner | 通过 | diff 中无 compat re-export（旧 reader 名直接删除）、无 lazy import、无 fallback/默认值、`evaluate_upload_overwrite_precondition` 仍为唯一 admission owner（validator 与 prepare_upload 共用） |

## Findings

### 1-未修复-低-根 README 未按 approved plan 更新最终用户 update/overwrite 语义

- **入口/函数**: 用户手册 `README.md` 5.2「上传单份 filing 或材料」；行为入口 `dayu-cli upload_filing --action update [--overwrite]`
- **文件(行号)**: `README.md:314-317`（现有 upload 语义段落，未新增 update 前置条件说明）；对照 approved plan `docs/gateflow/uf-fix02-action-and-update-identity-plan-20260813.md:482-485`（README trigger 表第三行：用户可见 action/error/workflow → 更新根 README）与 fix artifact `docs/gateflow/uf-fix02-action-and-update-identity-s1-code-review-fix-20260813.md:171-175`（宣称「无用户入口、命令参数、工作流、排障方式……变化，不触发」）
- **输入场景**: 最终用户在目标缺失时执行 `--action update --overwrite`。S1 修复前该请求被 upsert 为 create 成功；修复后退出 `2` 且 stderr 为「update 目标不存在；请改用 create」。这是 S1 已实现并验证的用户可见行为变化
- **实际分支**: 文案与行为变更已落地生产（`dayu/fins/ingestion_runtime.py:753`、`dayu/fins/pipelines/docling_upload_service.py:186`），但根 README 未同步
- **预期行为**: approved plan §6.3 与 §10 明确决定根 README 写入「update 必须已有目标，overwrite 不提供 upsert」；root README 自身更新约束（`README.md:11-12`）也要求最终用户手册反映当前可用操作
- **实际行为**: 根 README 未改。现有文本（`README.md:314-317`）只描述 action 默认值与校验/退出码，不含已过时的 upsert 表述（无 stale 矛盾），但缺失 plan 承诺的显式语义说明；「auto 可恢复 logical deleted source」与「完整替换文件集合」属 S2，可后补，但 update 前置条件部分属 S1 已交付行为
- **直接证据**: `git status --short` 中根 `README.md` 无修改；plan `:482-485` 的触发决策与 fix artifact `:173-175` 的跳过理由直接冲突（plan 已将「update+overwrite 行为」分类为最终用户语义）
- **影响**: 文档完整性问题。用户手册未说明 update 现在必须有已存在目标，行为变化只通过 exit-2 单行错误暴露；非 correctness/stability 缺陷
- **建议改法和验证点**: Controller 裁决二选一：(a) 本轮在根 README 5.2 补一句 S1 可见语义（update 要求目标已存在，overwrite 不提供 upsert；S2 语义届时再补）；或 (b) 明确裁决为 deferred-with-owner，在 gate artifact 中登记「根 README update/auto-deleted 语义说明」由 S2 closeout 或最终 README gate 一并写入，owner 与 destination 写清，不得静默跳过。若选 (b)，需修正 fix artifact §8 的跳过理由表述（其「无用户可见变化」判断与 plan §10 冲突）
- **修复风险（低）**: 纯文档变更
- **严重程度（低）**:

## Open Questions

- 无。root README 的补写时点是唯一需要 Controller 裁决的点（Finding 1），不影响其余核验项。

## Residual Risk

- RED（tests-first）证据为 artifact 记录，本 review 未通过回退生产代码复现 RED；GREEN、coverage、pyright 均已独立复现且与 artifact 数字完全一致。
- `ingestion_runtime.py:5102` 的既有 loose deleted reader 未修改，按 adjudication 归 UF-FIX08；另有 `read_runtime.py:643/2559`、`cn_download_rebuild.py:151`、`sec_rebuild_workflow.py:395`、`_fs_processed_core.py:581`、`domain/document_models.py:849/950/1029` 等既有 loose 读法，均不在本 S1 upload 调用链、非本 diff 引入，DS-02 修复边界按 Controller adjudication 只覆盖两个逐字重复的 strict reader——这些 loose reader 的收敛仍需各自 owner（UF-FIX08 / 后续 WU）处理，不构成本 slice 缺口。
- material create-existing 的 typed admission / public failure contract 仍为 deferred-with-owner（后续独立 `upload_material action-contract` WU）；本 diff 未新增或恶化该缺口。
- S2 的 complete-set reset/create 与 `_resolve_upsert_mode` 删除未开始；`_resolve_upsert_mode` 的 missing-update→create 分支在 S1 后经 `prepare_upload` 入口不可达（`docling_upload_service.py:299-300` 先抛），为 S2 前的已知活代码残留。
- 同请求竞争窗口（UF-FIX10）与 multi-file collision（UF-FIX07）不在本 slice 覆盖范围。
- 并行 AgentMiMo re-review artifact（`code-review-20260813-192100-uf-fix02-s1-rereview-mimo.md`）在本次 review 期间出现于工作树，本 review 未读取，保持独立；两个 re-review 结论的冲突裁决留给 Controller。

## 验证证据（本 review 独立执行）

```text
git diff --check                                                -> PASS
git diff --exit-code -- docs/cli_ci_scenarios.json
  docs/cli_ci_oracles.json docs/host/design.md
  docs/engine/design.md                                         -> PASS（frozen no-touch）
pytest tests/fins/test_source_meta_contract.py
  tests/fins/test_docling_upload_service.py
  tests/fins/test_fins_storage_atomicity.py
  tests/fins/test_fins_ingestion_runtime.py
  tests/cli/test_fins_commands.py -q                            -> 428 passed, exit 0
pytest tests/fins/test_fins_storage_atomicity.py
  tests/fins/test_fins_storage_provider.py
  tests/fins/test_docling_process_converter.py
  tests/fins/test_fins_service_runtime.py
  tests/service/test_fins_direct.py
  tests/cli/test_import_boundary.py -q                          -> 343 passed, exit 0
python -m pyright dayu/ tests/ utils/                           -> 0 errors, 0 warnings, 0 informations
coverage（五修改生产文件独立 report）:
  docling_upload_service.py 86% / ingestion_runtime.py 91% /
  storage/__init__.py 100% / _fs_source_snapshot.py 86% /
  source_meta_contract.py 100%                                  -> 全部 >=80%
grep 静态审计：
  "source meta 缺少 is_deleted" / "必须为布尔值" 仅
  source_meta_contract.py 一份实现；_require_deleted_flag /
  _require_source_deleted_flag 全仓零命中；"或允许覆盖"
  仅存于 CREATE_TARGET_EXISTS 文案（plan §5.4 明确保留）
```

## 执行边界确认

- 未修改任何生产代码、测试或既有 artifact；仅新建本 review artifact。
- 未 commit、未 push、未创建 PR、未进入下一 gate；按任务指示停在 re-review。
