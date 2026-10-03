# plan review：issue #198 S1 第十次 fix 候选独立 adversarial re-review（MiMo）

- RUNTIME/PROVIDER/MODEL: claude/mimo/mimo-v2.6-pro[1m]
- 日期：2026-09-29；reviewed target：`docs/gateflow/issue-198-download-failure-projection-plan-20260928.md` 第十次 fix 候选（Sol label `issue198-s1-plan-fix10-sol-20260929-01`；派发按协议 `agent_status=failed`，落盘仅作候选）
- 停止条件核验（预检通过后才开始审查）：
  - 计划 SHA-256=`2d18014ce605c8368d53247a43669f6ba597ecc875fe6d5a7b2ce558c0d92cd7` ✓ 与任务给定一致（审查前后各核一次，无 drift）
  - 分支 `codex/upload-material-oracle`、HEAD=`8d8d494fbbce0052372fb1b42097c9f7222cfa28` ✓ 与总控记录一致
- 阅读范围：总控裁决 `docs/gateflow/issue-198-s1-code-review-adjudication-20260928.md`（至「Sol 第十次 plan fix」段，含「MiMo 第七次 plan re-review 裁决」F1/F2/OQ1/OQ3）、上一轮 MiMo 第七次 artifact `docs/reviews/plan-review-20260929-033643.md` 的攻击点清单、计划全文、owner 代码与测试现状、三份 README 与 `git diff` 未提交候选
- 本路只产出本 artifact（`docs/reviews/plan-review-20260929-094111-issue198-s1-mimo.md`）；未改计划、产品、测试、README、旧 artifact，未 stage/commit/push/PR/外部评论，未派发子 Agent

## reviewed target 与范围

对象是第十次 fix 后的 S1 现行合同（计划 43–63 行）与测试验收（55–63 行），以及它与 fix10 声明（第 3 行）的一致性。S1 目标：storage 封闭 preflight 原因经 Fins 公共失败对象、direct RESULT、job failed record、CLI/等待投影保持同一事实，并在可证明的 typed 中止路径上守恒已确认 filings。S2（脱敏调用栈 helper）与四个已登记后续 work unit 不在本次裁决范围，只核对其未被偷渡回 S1。

## 独立重证方法

不接受 plan/裁决/前轮 review 转述，对每个攻击点直接读 owner 代码构造反例：

1. `dayu/fins/storage/source_integrity.py`：`SourceIntegrityPreflightReason`（四值封闭）、`SourceIntegrityPreflightError(RuntimeError)`、`SourceIntegrityRevisionConflictError(RuntimeError)`——确认两 typed 异常是 **sibling**（均直挂 `RuntimeError`，互不继承），`classify_source_integrity_preflight`（290–330）纯计算且在 UNSAFE inventory/MULTIPLE/UNSELECTED/SELECTED_REJECTED 时抛 typed。
2. `dayu/fins/storage/_fs_source_integrity.py`：`_inspect_source_kind_unguarded` 在 whole-kind（`requested_document_id=None`）遇 `unassignable_root_fact`（root 非点号杂散条目）时抛 `SourceIntegrityPreflightError(UNSAFE_PUBLICATION)`；exact-target 模式下 root 杂散仅当 target **非 MISSING** 时升级为 `CROSS_SOURCE_INCONSISTENCY` UNSAFE。
3. `dayu/fins/storage/_fs_storage_infra.py`：`commit_batch` 533–611（`_validate_complete_source_tree` 557–559 严格先于 identity/publication guard 与 physical swap；失败后 `_rollback_precommit_batch`；`raise commit_error from rollback_error` 保留原 typed 与 cleanup 链）；`_validate_complete_source_kind_tree` 1099–1158（whole-kind 调 `_inspect_source_kind_unguarded`，typed 可从该 inspect 透传）。
4. `dayu/fins/pipelines/cn_download_filing_workflow.py`：Phase A `classify_source_integrity` UNSAFE→typed（173）；Phase B `classify_staged_source_integrity` 在 `begin_batch` 后、内容落 staging 前调用（596–603），UNSAFE→typed 并 rollback（608/612）；churn 耗尽 `raise SourceIntegrityRevisionConflictError()`（512）。
5. `dayu/fins/pipelines/cn_download_workflow.py`：whole-kind 预检 227–231、循环前 `_publish_cn_company_after_repair` 249–255、单 filing 宽 catch 311–331、post-repair classify+显式 revision conflict+publish 332–355、`_publish_cn_company_after_repair` 410–448、`_build_summary`/`_build_result` 750–828（`status: str` 自由参数，可构造私有 `integrity_failed`）。
6. `dayu/fins/pipelines/cn_pipeline.py`：`_run_async_download_sync` 145–161（`try/except RuntimeError` 只包 `get_running_loop()`，`asyncio.run(coro)` 在 except 外——stream 异常原样透传）；`collect_cn_download_result_from_events` 186–211（无 catch，异常直穿）；`CnDownloadAdapter.download` 1335–1382、`_summary_from_pipeline_result` 1403–1447（现仅收 `ok/cancelled`）；**cn_pipeline 已从 `ingestion_runtime` 导入 adapter 类型（39–46 行）**。
7. `dayu/fins/ingestion_runtime.py`：`_run_direct_stream_producer` 4289–4346（catch-all 发零候选 `FAILED` 摘要）、`_run_download_job` 4918–4963（现仅 `_UnsupportedDownloadSourceError` + 宽 catch）、`_execute_download_request` 5275–5340（happy path 已用 `_bounded_download_summary`+`_validate_download_summary_request_identity`）、`_save_failed` 5905–5945（`save_failed_or_cancelled_if_active` 原子终态）、`_save_failed_from_exception` 5989–6016（`str(exc)` 入 record、WARN 带 `error_type`+`exc_info=True`）、`_empty_download_summary_from_request` 6787–6823（`terminal_disposition` 显式入参）、`_SOURCE_INTEGRITY_PUBLIC_REASONS` 6826–6831、`_download_public_failure_from_exception` 6834–6897、`_classify_direct_error` 7066–7096（`OSError | SourceIntegrityPreflightError → STORAGE`）。
8. `dayu/fins/direct_events.py` 未提交候选：`FinsDownloadFailureReason` 四值、`FinsPublicFailure.reason_code`（仅 `STORAGE`+`transport_category=None` 可非空）；`FinsResultSummary.__post_init__` 677–682 **当前仍拒绝** `FAILURE + terminal_disposition≠FAILED`——即 post-repair 单行 `SUCCEEDED` 摘要形状今天构造不出来，S1 必须改该校验（计划 51 行已列）。
9. `dayu/service/fins_wait_adapter.py`：`_failure_message` 592–617（typed 失败帧缺 download 拒绝已在该 owner；帧含 `download.to_json_value()` 与 `failure.to_json_value()`）；`_failed_outcome` 501 取 `result.failure.retry_hint`。
10. 测试与 README 现状：`tests/fins/test_cn_download_runtime.py` 的 `_summary_from_pipeline_result` owner 测试归属、`tests/fins/test_cn_pipeline.py` 无同类投影测试、三份 README 未提交 hunk（相邻点号句 + #198 句，且根 README 现为 `reason="unsafe_publication"`，计划 35 行已要求改写为 `reason_code=`）。

## 攻击点逐项重证结果

### A. CNInfo 选中修复后 typed failure 保留已确认 filings 快照 —— 成立

- 反例尝试 1（post-repair typed 丢快照）：当前代码 post-repair 块（336–354）抛裸 typed 越过 collector，producer catch-all 归零摘要——正是缺陷。计划 47 行在 post-repair 调用点专设 typed catch 构造 `CnDownloadIntegrityAbort` 携带 `filings` 快照（含刚完成 repair filing 终态行），49 行 adapter 严格投影为 `FinsDownloadResultSummary`，51/57 行以计数口径与测试固定「已发布候选保留、失败当前候选仅一行、未开始候选无行」。反例被合同封死。
- 反例尝试 2（repair filing 自身 typed 失败被误记双行）：单 filing typed 在发 `FILING_COMPLETED/FAILED` 事件**之前**抛出（`run_cn_download_single_filing_stream` 原样抛，55 行配方明确），workflow typed catch 只补一行；57 行「失败当前候选仅一行」断言兜底。成立。
- 反例尝试 3（取消被后置 catch 吞掉）：计划 47 行明确 `CnDownloadCancelledError` 不入 typed catch、保留取消控制流与唯一终态合同；typed 类型是 sibling，天然不吞取消。成立。

### B. storage pre-swap 与 physical swap 边界 —— 成立

- 计划 47 行称 `_validate_complete_source_tree` 的 typed 从 pre-swap 抛出、target 未动。实证：`commit_batch` 557–559 注释与代码确认完整性校验只读 staging 且严格先于 guard/swap；typed 的真实来源是 `_validate_complete_source_kind_tree` → whole-kind `_inspect_source_kind_unguarded` 对 root 杂散抛 `UNSAFE_PUBLICATION`（typed 从 inspect 透传，不是 ValueError——曾构造反例怀疑 commit 路径只会抛 ValueError，被 1099–1112 与 280–305 的调用链证伪）。
- `raise commit_error from rollback_error`（574–579）保留原 typed 对象与 cleanup 异常链；计划明确只声明「文档未被本次 swap 改动」，不宣称 cleanup 成功、不以 `__cause__` 判归零——与 owner 语义一致。
- physical swap/restore 双失败、postcommit、ValueError/OSError 泛路径：计划 47/87 行明确禁止泛 `except Exception` 保留快照、触发停止条件转 `fins-download-indeterminate-publication-state`，未偷渡回 S1。

### C. 首候选前零摘要 —— 成立

- 两个首候选前来源分界准确：初始 whole-kind（227–231，含 `list_source_integrity` inspect 抛 typed 或 classify 抛 typed 两种真实来源，同一表达式同一 catch 覆盖）与循环前 `_publish_cn_company_after_repair`（249–255，typed 只可能来自 `commit_batch` pre-swap 校验；`stage_company_meta_for_cn_download` 仅 ValueError）。
- 计划 45/47 行要求两者裸透传、direct/job 均用 `_empty_download_summary_from_request(..., terminal_disposition=FAILED)` 请求级零候选摘要；实证该 helper 形状（零 counts/rows + 显式 FAILED）与 `FinsDownloadPublicSummary` 的 `empty_terminal_override`（0 候选允许 FAILED/CANCELLED 终态）吻合。
- fix10 新增的 57 行专测：「尤其断言 `terminal_disposition=FAILED`，使误用空 `filings` 快照派生的 `SUCCEEDED` 必然失败」——直接封死 F1 反例（空快照经 `from_document_rows` 会派生 `SUCCEEDED`）。catch 位置约束（「不能放进共享函数内部或包住循环前调用点」）+ 两用例「分别证明两个调用点，不相互替代」完整闭合第七次 F1。

### D. job/direct 同源 typed reason+retry —— 成立（附残余）

- 映射唯一性：`_SOURCE_INTEGRITY_PUBLIC_REASONS` 四对全量映射 + `reason_code` 仅 STORAGE 可非空 + 57 行反向全集断言，无第二白名单。direct `error_kind=STORAGE` 与 `failure.kind=STORAGE` 一致（`_classify_direct_error` 已收 typed）。
- job 两条 typed catch（53 行）取同一公共投影 `safe_message`，`result_summary` 用同一 summary 的 `to_json_summary()`，不落 `{}`/`str(exc)`；57 行断言 `result_summary` 非 `{}`、`failure_summary.message` 逐字等于安全消息、无原异常文本/路径。
- 试构造 direct/job 漂移反例：私有 `FinsSourceDownloadAdapterFailure` 的 `persisted_summary` 已在 `_execute_download_request` 边界经 `_bounded_download_summary`+`_validate_download_summary_request_identity` 验证后才被两入口消费，禁止重算 raw filings（49 行）；单点 unwrap 后同一 cause 进 `_classify_direct_error`/`_download_public_failure_from_exception`，revision conflict 沿既有 EXECUTION。反例不成立。
- 残余（非缺陷）：job record 的 `failure_summary` 仍是既有 `{message}` 形状，不持久化 `reason_code`/`retry_hint`（计划禁止扩 schema 正确）；job record 目前无 Service/CLI/LLM 投影消费者，四值 reason 到 LLM 的通道是 wait/direct RESULT。若未来接 job 投影，须复用同一公共失败映射派生，不得从 message 反推——记入残余，不塞回 S1。

### E. 二次落盘 —— 成立

- 53 行：typed catch 复用 `_save_failed_from_exception` 的 terminal 幂等读取与不逃逸控制流，但**不**复用其 `str(exc)` 写法与 WARN 日志写法；不以 `{}` 覆盖原摘要、不虚称已落终态。实证 `_save_failed` 用 `save_failed_or_cancelled_if_active` 原子终态、二次失败可抛（OSError/ValueError），typed catch 的二次失败面真实存在。57 行测试读 job store 核对未虚称持久化。闭合。

### F. WARN 脱敏/无 raw traceback —— 成立

- fix10 将第七次 F2 简化为固定事件标识：53/57 行合同与断言一致——仅 `fins.download.typed_failed_record_save_failed`，无 `error_type` 字段、无异常类名/`str/repr`/`exc_info`/路径/秘密/traceback；注入自定义异常类（类名与内容分别含秘密、路径）逐项断言不出现。与 fix9 旧「可信 error_type」表述的冲突由第 3 行「以现行 S1 正文为准」显式消解（全文核对现行正文无残留矛盾表述）。既有两处 WARN 的 raw `exc_info` 留 `fins-other-raw-diagnostics-audit`，未宣称已修。闭合。

### G. LLM wait 结果范围 —— 成立

- `scope_note` 只在 wait 失败 JSON 帧（`_failure_message`）出现，固定字段名 + 私有命名常量逐字「下载摘要只统计已处理文档；整体下载操作失败，请按失败原因和处理建议处理。」；测试用独立字面量断言字段名与值，不与常量/动态 JSON 互比；同帧 `status`/`download.terminal_disposition`/`failure.{safe_message,retry_hint,reason_code}` 可读。实证 wait 帧由 `result.download.to_json_value()` 自带 `terminal_disposition`、「含 download 的失败帧」条件精确；`FAILURE + public failure + download=None` 在跨操作 dataclass 可成立、由 `_failure_message` 拒绝——owner 边界（51 行）与 59 行测试一致。不改公共 schema。闭合。

### H. 测试/coverage/pyright/README/真实 CLI 证据 —— 成立

- 白名单与 75 行 pytest 命令闭合（含 fix9 补的 `test_cn_download_runtime.py`；`test_fins_commands.py` 无 reason 断言、不入 S1 白名单正确）；两个真实 mutation 配方（Phase B exact-target IDENTITY_UNTRUSTED、company pre-swap staging stray）经代码推演可真实命中目标路径——特别是「Phase B exact-target/MISSING 不升级」经实证成立：Phase B classify 在 `begin_batch` 后、内容落 staging 前执行，fresh 候选二 exact-target 为 MISSING，root 杂散不升级，typed 延迟到 filing 自身 `commit_batch` 的 whole-kind 校验；若配方落偏，55 行有「按直接证据修正配方并重新复审」停损。
- 单文件覆盖率 ≥80%、pyright 不扩散、三份 README 的 #198 句自足改写（根 README `reason=`→`reason_code=`）与相邻点号句按行 stage 均在 35–37/79/83 行固定；真实 CLI 隔离配方（不 init、mktemp、基线+stray 重跑、分通道隐私核对、网络不稳报 validation gap）完整。闭合。

## 第七次复审 F1/F2/OQ1/OQ3 收口判定

| 裁决项 | 判定 | 直接证据 |
| --- | --- | --- |
| F1 首候选前 company pre-swap typed 零候选 + 两调用点区分 | 已闭合 | 45/47 行零候选口径与 catch 位置约束；57 行专测断言 `terminal_disposition=FAILED`、无伪 filing 行，并声明与 post-repair company spy 用例互不替代 |
| F2 typed job WARN 只固定事件标识 | 已闭合 | 53 行固定标识合同；57 行注入自定义异常类断言无任何动态信息、不逃逸、不虚称持久化；fix9 `error_type` 残留表述被 fix10 头部声明消解 |
| OQ1 post-repair catch 覆盖 classify+显式 revision conflict 整块、不误称 classifier 抛 conflict | 已闭合 | 47 行正确归因（classify 抛 PreflightError；`SelectedSourceRepairRequired` 时 workflow 显式抛 RevisionConflictError）+「不得只包住 classifier」 |
| OQ3 mid-filing churn 注入证据界限 | 已闭合 | 57 行选定受控注入配方并明确「只证明 workflow 收口，不证明三轮 churn 真会耗尽/owner 真抛冲突」，改真实 churn 须另行证据、不得互冒充 |

## Findings

无 surviving material finding。逐项攻击（快照守恒、pre-swap 边界、零候选、job/direct 同源、二次落盘、WARN、wait 范围、测试/验证）均被现行 S1 合同 + 可执行测试验收封死；曾构造的反例（commit 路径只抛 ValueError、`_run_async_download_sync` 吞 typed、Phase B 提前升级导致 commit-time 配方落空、cn_pipeline→ingestion_runtime 循环依赖、空快照派生 SUCCEEDED）全部被 owner 代码直接证据证伪。

## Open Questions

1. 计划 59 行「使真实 `classify_source_integrity_preflight` 抛 typed」对 root 杂散配方是**宽泛归因**：root 杂散实际先在 `list_source_integrity` 的 whole-kind inspect 抛 typed，classify 自身只对 UNSAFE inventory item 抛 typed。因两者是同一表达式且被同一 catch 包住，行为无差别；实施时 catch 范围须盖住整个 `classify_source_integrity_preflight(host.source_repository.list_source_integrity(...), ...)` 表达式（Python 参数求值在 try 内，最小写法即安全）。不构成 finding，实施注意即可。
2. 53 行「复用 `_save_failed_from_exception` 的 terminal 幂等读取与不逃逸控制流」字面可被误读为直接调用该函数（其会写 `str(exc)` 且 WARN 带 `exc_info`）。同段负面清单（不能复用其日志写法）+ 57 行 WARN 断言足以在测试层拦截误读；建议实施按「复制控制流骨架、独立实现 WARN」理解。

## Residual Risks 与去向

| 残余 | 去向 |
| --- | --- |
| generic 异常在已确认文档后仍退回零摘要；physical swap/restore 双失败、postcommit 发布状态不确定 | `fins-download-indeterminate-publication-state`（独立 work unit，先由 storage batch owner 给 typed publication certainty；S1 明确不宣称覆盖，禁止回填） |
| `SourceIntegrityRepairBlockedError`/`SourceIntegrityRevisionConflictError` 落 EXECUTION 的公开分类 | `fins-download-storage-sibling-errors`（独立 goal confirmation） |
| 既有 job WARN `exc_info=True`、generic job `str(exc)` 入 failure record 及其 Service/LLM 投影 | `fins-other-raw-diagnostics-audit` |
| 无来源文档公共 `retry_hint` 在默认临时日志下欠可操作 | `fins-download-no-source-retry-hint` |
| 投影机制自身二次失败（RESULT 构造/logger 再抛） | `fins-direct-projection-failsafe` |
| job record 不持久化 `reason_code`/`retry_hint`（现无消费者）；未来接 job→LLM 投影须复用同一公共失败映射派生 | 未来 job 投影 work unit 的 owner 约束，届时 goal confirmation；不扩 S1 schema |
| mid-filing churn 注入只锁 workflow 收口；真实三轮 churn 耗尽未经 owner 证据 | `fins-download-storage-sibling-errors` 或其验证阶段 |
| 真实 CLI 基线（不 init 首次建库、网络/provider 稳定性）与跨布局受信帧降级 | 本 work unit 实施后验证/closeout 记录，失败须报 validation gap |

## 最终结论

**pass-with-risks**（针对第十次 fix 候选的 S1 合同与测试验收）：

- fix10 对第七次 F1/F2/OQ1/OQ3 的四项收口全部成立且有可执行验收；第八次 F1–F5 与既有边界未回退；S1 目标、允许文件、真实配方、计数口径、同源消费链与停止条件可直接交给 implementation agent。
- 风险不在 S1 合同本身，而在已登记残余（上表）与两条实施注意（Open Questions）。按 gate 约定，本结论是单路 re-review，不构成 plan pass；仍须 Kimi 有效第二路与总控逐项裁决后才可进入 S1 implementation。
