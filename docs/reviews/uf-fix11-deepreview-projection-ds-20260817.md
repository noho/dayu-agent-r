# Code Review — UF-FIX11 aggregate 专项 B：projection / data-stability

## Scope

- Mode: current changes（gateflow aggregate 专项 B）
- Branch: `codex/upload-filing-oracle`
- Base: `94182a0c`；HEAD: `91dbf843`
- Review 时间：2026-08-17
- Output file: `docs/reviews/uf-fix11-deepreview-projection-ds-20260817.md`
- 变更范围：5 个 gateflow commit，75 文件，+9964/-138
- 本专项 scope（用户指定）：
  - typed warning public/runtime contracts、parser/codec
  - durable job summary、direct command result
  - CLI stdout/stderr/exit
  - wait/tool/LLM-facing projection
  - failure/cancelled/killed/rollback non-leak
  - README/test quality
  - type/docstring/project-instruction compliance
  - overcoupling/public exposure
- Excluded scope：
  - publication algorithm / merge 规则本身（S1+S2 已由 slice-level review 关闭；除非发现 projection 事实与 durable owner 断链）
  - Host/Engine 实现（本次零 diff，仅核对 design doc 契约）
  - plan/amendment review 过程质量（plan gate 已 closed）
- 审查输入：
  - `AGENTS.md`、`docs/host/design.md` §20（Tool Awaiting / Wait Record）、`docs/engine/design.md` §10-13（工具调用协议 / timeout / suspend / cancellation）
  - `docs/cli_ci_oracles.json` oracle #5 `cli.upload_filing.document-publication`，accepted，predicate `upload_filing.company-meta-refresh`：
    "stale resolver company meta 缺 company-name 时 fail-closed；提供显式名称时随新 source 原子刷新。已有 fresh canonical company identity 不被单次 filing 静默改名；忽略新名称或 alias update 时给出明确 warning。forbidden：静默改写 fresh identity，或静默忽略用户以为已生效的 metadata 变化。"
  - UF-FIX11 goal-confirmation / plan / slice-boundary amendment / S3 projection boundary amendment / 三个 acceptance artifacts
  - 完整 diff `94182a0c...91dbf843`

## 核查方法

沿真实 upload runner 链路逐行走读（非仅表层 diff）：

```text
SEC/CN workflow terminal producer (warnings JSON)
  -> FinsUploadPipelineResult.from_pipeline_json(result, *, source_kind)   [parser]
  -> ProductionFinsUploadRunner (service_runtime, 4 个显式 SourceKind callsite)
  -> _upload_summary_from_result (显式机械复制)                             [service]
  -> FinsUploadResultSummary (invariant + to_json_summary)
       -> durable: job_store.save_accepted_upload_terminal_if_active -> result_summary["warnings"]
       -> direct: _direct_upload_terminal_events -> _direct_result_event(warnings=) -> FinsResultSummary
            -> CLI render_fins_direct_event (stdout 摘要 / stderr warning / exit 0)
            -> wait adapter _completed_result_value (LLM-facing completed value)
  -> publication owner 反向核查: execute_prepared_filing_publication -> stage -> batch_terminal_started
       -> commit_batch -> _commit_batch_with_identity_guards -> _prepare_company_identity_commit
       -> merge_company_meta_for_commit -> CompanyMetaCommitOutcome -> _warnings_from_commit_outcome
```

另执行 adversarial failure pass（cancelled/killed/rollback/capability transfer/并发 final-truth）、semantic ownership drift pass、branch ordering、public exposure 与 overcoupling 检查。实际运行验证：`tests/cli/test_output.py` + `tests/service/test_fins_wait_adapter.py` + `tests/fins/test_company_meta_contract.py`（57 passed）、`tests/fins/test_filing_upload_publication.py` + `tests/fins/test_fins_service_runtime.py`（49 passed），与 acceptance 声称一致（完整 combined regression 未重跑，见 Residual Risk）。

## Findings

### 01-未修复-低-SKIP 分支对 company decision 的 disposition 判断不封闭，依赖 arbitration 远端不变量且无本地断言

- **入口/函数**: `execute_prepared_filing_publication` 的 `SKIP` disposition 分支
- **文件(行号)**: `dayu/fins/pipelines/filing_upload_publication.py:769-799`（分支条件 771 行 `if company_decision.disposition == "keep"`）；配合 `dayu/fins/pipelines/upload_company_meta.py:149-150`（`if decision.disposition != "stage": return`）与 `dayu/fins/pipelines/filing_upload_publication.py:119-127`（`_require_skip_company_meta_outcome` 对 `None` 抛 TypeError）
- **输入场景**: fresh recheck 下 company decision 的 `disposition` 为 `"skip"`（当前只有 action 不在 `{"create","update"}` 时由 `resolve_upload_company_meta_decision:72-73` 产生；`_canonical_skip_requirements_are_met:451-455` 的闭集保证该组合当前不进入 SKIP，因此该输入当前不可达）
- **实际分支**: 771 行 `keep` 检查为 False → 落入 781-799 行的 stage+commit 路径；`stage_upload_company_meta_decision` 对非 `stage` disposition 静默 return（150 行），batch 无 intent → `batch_terminal_started = True`（787 行）→ `commit_batch` 在 staging 上执行一次无业务变更的物理 swap 并返回 `None` → `_require_skip_company_meta_outcome` 抛 TypeError，且 outer `finally`（846-851）因 flag 已置位不再 rollback
- **预期行为**: SKIP 分支应显式断言 `disposition == "stage"` 且 intent `merge_mode == "preserve_published"`，与 `_canonical_skip_requirements_are_met:451-455` 的闭集在本地同源表达；任何闭集外组合应立即以编程 invariant 违约失败，且失败发生在任何 stage/commit 之前
- **实际行为**: 分支正确性完全寄托于 arbitration 与 predicate 的远端一致性。一旦二者漂移（例如未来新增 disposition 或 merge_mode 值），错误在**物理 swap 已经 durable 完成之后**才以 TypeError 暴露，随后经 SEC/CN workflow generic handler 投影为 generic failure，而不是 typed conflict
- **直接证据**: 771 行只检查 `keep` 一个枚举成员，而 `UploadCompanyMetaDecision.disposition` 是 `Literal["keep", "skip", "stage"]` 三值闭集（`upload_company_meta.py:43`）；`stage_upload_company_meta_decision` 对 `"skip"` 的静默 return 在 `upload_company_meta.py:149-150`；commit 前的 `batch_terminal_started = True` 在 787 行早于 788 行的 `_require_skip_company_meta_outcome`。同一不变量在 `_canonical_skip_requirements_are_met:451-455` 有完整表达，但 SKIP execute 分支未复用或复述
- **影响**: 无直接用户可见错误（当前不可达），但这是未被测试锁定的结构不变量：漂移时产生一次无业务变更的物理 swap + generic failure，而非 typed conflict；违反本项目"dispatch/router 分支闭集必须由同源事实驱动、禁止依赖远端隐式规则"的约束（AGENTS.md 思考纪律 4）
- **建议改法和验证点**: 在 769-799 的 SKIP 分支入口处把 `_canonical_skip_requirements_are_met` 的 company-decision 条件本地显式断言（`decision.disposition == "stage" and intent.merge_mode == "preserve_published"`，或提取共享 predicate），并将 assertion 放在任何 repository 调用之前；新增一条 owner 测试直接构造 `disposition="skip"` + SKIP 决策的 fixture，断言在 stage/commit 零调用下立即失败
- **修复风险（低）**: 只加断言，不改状态机；断言文本不影响任何现有测试
- **严重程度（低）**: 当前不可达、fail-closed（TypeError 而非静默错误语义），但错误暴露时点晚于一次无业务变更的物理 swap，且不变量无测试锁定

### 未发现其它实质性问题

以下 scope 项经逐行核查未发现实质性问题（记录核查结论与关键证据，便于 controller 复核）：

1. **typed warning public/runtime contracts**：`CompanyMetadataWarning`（frozen slots dataclass + closed kind enum + 规范文案 `__post_init__` 校验，`company_metadata_warning.py:29-57`）与三个 runtime summary 的 invariant 一致：`FinsUploadPipelineResult` 只允许 ok/skipped 携带（`ingestion_runtime.py:1734-1742`）、`FinsUploadResultSummary` 同（1863-1871）、`FinsResultSummary` 只允许 SUCCESS 携带（`direct_events.py:637-642`）。三者 exact 类型检查 `type(...) is not CompanyMetadataWarning` 一致。
2. **parser/codec**：`from_pipeline_json` 的 `source_kind` 必填无默认值（1745-1750）；filing 缺失 `warnings` 抛 ValueError、material 缺失映射空 tuple、任一 source kind 的 `null`/非数组/未知 kind/非规范 message/多元素/重复 kind 均 fail closed（1768-1775 + `company_metadata_warning.py:88-113`）。`service_runtime.py` 四个 callsite 显式传 FILING/MATERIAL（182-269），未从 payload 推断。`commit_batch` 全量收敛：dayu 3 定义（protocol + 2 impl）与 test 7 文件 9 定义（docling 3 处）与 plan §9.2 清单 exact 一致，注解均为 `CompanyMetaCommitOutcome | None`。
3. **durable job summary**：`to_json_summary()["warnings"]` 恒序列化（空为 `[]`，`ingestion_runtime.py:1934`）；`_run_upload_job` 经 `save_accepted_upload_terminal_if_active(result_summary=summary.to_json_summary())` 持久化（5023-5029）；`_record_from_json` 用 `_required_json_object` 读回、不重新解析/推断 warning（8763-8798）；测试断言 saved `result_summary["warnings"]` 与 read_job roundtrip 相等（`test_fins_ingestion_runtime.py:8766-8768`）。
4. **direct command result**：`_direct_upload_terminal_events` 传 `warnings=summary.warnings`（6577），`_emit_claimed_direct_result` 显式传 `()`（6253），`_direct_result_event` 的 warnings 参数无默认值（6449-6458）且 CANCELLED 归一化分支不清空 warnings（6482-6499），非法组合由 `FinsResultSummary` fail closed。生产 callsite 恰为两处（6245/6565），AST 测试穷举数量与实参集合（`test_fins_ingestion_runtime.py:6379-6429`）。`_observation_failure_result`/`_observation_cancelled_result`/`_mark_observation_failed` 零 diff（hunk 列表仅 15 处，均不落在 7230/7285/7330）。
5. **CLI stdout/stderr/exit**：`render_fins_direct_event` SUCCESS 分支先 stdout 摘要、后逐条 stderr 输出规范 message（`dayu/cli/output.py:236-244`），exit code 来自 `terminal.exit_code`（`dayu/cli/commands/fins.py:270`），SUCCESS 恒 0；end-to-end 测试经真实 `cli_main.main` 断言 uploaded/skipped 双终态 stdout 精确不变、stderr 精确 warning、exit 0（`test_fins_commands.py:783-850`）。
6. **wait/tool/LLM-facing projection**：`_completed_result_value` 恒含 `warnings` 数组（`fins_wait_adapter.py:579-589`），从 `FinsResultSummary.warnings`（direct 真源）用同一 codec 序列化；failed/cancelled outcome 结构上不含 warnings（`_failed_outcome`/`_cancelled_outcome` 486-525）；completed value 的 message 为业务可读中文、无路径/内部术语/raw names。wait adapter 通过 observation queue 消费同一 direct RESULT event（`ingestion_runtime.py:4110-4145`），与 CLI 同源。
7. **failure/cancelled/killed/rollback non-leak**：warning 只在 commit 成功返回后由 `_warnings_from_commit_outcome` 投影（`filing_upload_publication.py:94-115`、788-798、841-843）；cancel 两 checkpoint、CONFLICT、validation failure 路径均 rollback 且不构造 warning（697-767、800-808）；SKIP capability transfer 在 commit 前置位（786-787），成功/commit 失败后 caller rollback 恒 0、stage 失败 rollback 恰 1（测试 `test_filing_upload_publication.py:2218-2354` 三态覆盖）；kill 无 terminal projection、recovery 不补发推测 warning（plan §8.5，未新增代码路径）。`FilingUploadPublicationOutcome.__post_init__` 强制 warnings 与内部 commit outcome 同源（174-186）。
8. **README quality**：根 README 按 plan §11.1 更新（删除"不要填写公司名称"规避建议、新增 stderr warning/exit 0/alias 原子保存的用户可见事实），符合其 `Agent更新约束`（用户手册边界，无内部术语）；`dayu/fins/README.md` 记录 commit outcome owner、lock final truth、skip 两分支与 warning 时机，无 gate 历史；`tests/README.md` 更新测试矩阵描述。均符合各 README 约束。
9. **type/docstring/project-instruction compliance**：新增/修改模块与函数均有中文 docstring（参数/返回/异常齐备）；无 `Any`/`object`/`hasattr`/`getattr` 新增；无魔法数字；S3 acceptance 的 pyright `0 errors` 与实测文件通过一致。
10. **overcoupling/public exposure**：`company_metadata_warning.py` 是单一 projection owner；`requested_company_name` 仅存在于 domain contract 与 pipeline 决策模块（grep 全仓无第三消费者）；`UploadOperationResult.company_meta_commit_outcome` 的消费者仅 shared publication（grep 无外部读取）；SEC/CN 只读 `publication_outcome.warnings` 不读内部 outcome；download 路径（`sec_company_meta.py:121`、`cn_download_company_meta.py:72/81`）不传 `requested_company_name`，无 upload warning 语义泄漏；依赖方向 domain ← warning ← direct_events/CLI/wait 无环。
11. **等价比较与 durable owner 一致性**：pipeline 层 `name_change_requested`（`upload_company_meta.py:95-98`）与 commit owner 的 warning predicate（`company_meta_contract.py:274-283`）复用同一 `company_names_are_equivalent`；warning fact 只在 publication lock 内基于 final `CompanyMeta` 产生，与 staging 写入值同源（`_prepare_company_identity_commit` 773-777 写 `final_meta = company_meta_outcome.company_meta`）；blocker 测试断言提交前后 CompanyMeta 序列化 bytes 与 published tree hash 完全不变（`test_sec_pipeline_upload_filing_stream.py:1792-1801`），未发现 projection 事实与 durable owner 断链。

## Open Questions

无。

## Residual Risk

- 未重跑完整 combined regression（`tests/fins` + `tests/cli` 全量）：本次实测验证了 3 个关键测试文件组（57+49 passed），S1+S2/S3 acceptance 声称的 `2155 passed, 1 skipped` 未在本次复核中重现；剩余风险低（无未验证的生产代码路径发现）。
- 真实 CLI evidence / UF-PF11 / scenario / oracle 校准：按 work unit 非目标明确未运行，`assigned to later work unit`。
- material upload 的同类 name 行为、name-only metadata batch 的 writer lock/physical swap 成本、post-commit cleanup 可见性：plan §13.5 已分类 `assigned to later work unit`。
- Finding 01 修复后需同步检查 `_canonical_skip_requirements_are_met` 与 SKIP 分支的断言是否从同一 helper 派生，避免出现第二处漂移真源。

## Covered / Not-covered

- Covered（逐行走读）：`company_metadata_warning.py`、`company_meta_contract.py`、`upload_company_meta.py`、`filing_upload_publication.py`（skip predicate / arbitration / execute 全路径）、`docling_upload_service.py`（skip result / commit capability）、`_fs_storage_infra.py`（begin_batch staging 副本、commit_batch、identity guards、publication guard）、`fs_batching_repository.py`、`repository_protocols.py`、`ingestion_runtime.py`（parser/summary/durable save/re-read/direct builders/observation drain）、`service_runtime.py`（4 callsite + `_upload_summary_from_result`）、`sec_upload_workflow.py`、`cn_pipeline.py`（全部 terminal producer 收敛）、`direct_events.py`、`dayu/cli/output.py`、`dayu/cli/commands/fins.py`（exit code 链）、`fins_wait_adapter.py`；测试文件：`test_company_meta_contract.py`、`test_company_identity_storage_contract.py`、`test_filing_upload_publication.py`、`test_docling_upload_service.py`、`test_sec_pipeline_upload_filing_stream.py`、`test_cn_pipeline.py`、`test_fins_ingestion_runtime.py`、`test_fins_service_runtime.py`、`test_fins_direct_stream.py`、`test_output.py`、`test_fins_commands.py`、`test_fins_wait_adapter.py`、`upload_filing_test_support.py`；README ×3。
- Not-covered / excluded：publication merge 算法细节与 alias uniqueness guard 内部实现（S1+S2 slice-level 已关闭，本专项只核查 outcome 与 durable 写入同源）；Host/Engine 实现与 design doc 除 §20/§10-13 外的章节；`test_cn_download_workflow.py`、`test_sec_pipeline_download_stream.py` 的 fake 收敛只经 `rg` 清单核对签名与注解，未逐行读；material 流程非目标。
