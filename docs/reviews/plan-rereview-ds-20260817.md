# UF-FIX11 company-metadata-ignored-change-warning — Plan Re-review (AgentDS)

## Reviewed target and scope

- Target：`docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md`（经 A1-A10 裁决修订后的版本）
- 裁决源：`docs/gateflow/uf-fix11-plan-review-adjudication-20260817.md`
- fix artifact：`docs/gateflow/uf-fix11-plan-review-fix-20260817.md`
- 上一轮本路 review：`docs/reviews/plan-review-20260817-091441.md`（DS 1-6，`pass-with-risks`）
- 对路 review：`docs/reviews/plan-review-20260817-090453.md`（MiMo 001-006）
- Gate：plan re-review；只 review，不修改 plan 或代码
- 范围：逐项关闭核对 + 对修订内容做独立 adversarial 压测（不因 controller 已裁决而豁免）

## 上一轮 findings 关闭核对

| 上一轮 finding | Controller 裁决 | 修订位置 | 关闭判定 | 依据 |
| --- | --- | --- | --- | --- |
| DS 1 [中] commit_batch 返回类型收敛不受 pyright 强制 | A3 `accepted` | §6.4 / §9.2 全量清单 / Slice 1 allowed files / §12.5 | **已关闭** | §9.2 列出 dayu 3 定义（Protocol+2 implementation）与 test 7 文件/9 定义，与本机 `rg -n "def commit_batch" dayu tests` 实测 12 个定义一致（含 `test_docling_upload_service.py` 3 处）；§6.4 明写 `-> None` 协变盲区；§12.5 加入 `rg` 逐项验收与行为断言；Slice 1 将 4 个此前分属 Slice 2/3 的 fake 文件纳入"仅签名收敛"，消除跨 slice 类型漂移。 |
| DS 2 [中] SKIP+preserve 继承 whole-tree COMPLETE 校验未声明 | A7 `accepted` | §8.3 末段 / §8.4 新行 / Slice 2 tests+stop condition / §13.3.4 | **已关闭** | §8.3 明确"metadata-only commit 仍完整服从 `_validate_complete_source_tree`；无关 `REPAIR_REQUIRED` source 时 typed failure、无 warning、无 partial mutation，不新增 bypass"；§8.4 状态表新增对应行；Slice 2 加入 owner 级（`test_company_identity_storage_contract.py`）与 workflow 级 degraded-tree 测试；stop condition 禁止为 metadata-only commit 绕过完整性校验。 |
| DS 3 [中] SKIP 分支误复用 publish helper 未禁止 | A8 `accepted` | §8.3 步骤 1-6+禁令 / Slice 2 Exact changes 4 / stop condition | **已关闭** | §8.3 写死 `stage_upload_company_meta_decision -> commit_batch -> build_prepared_filing_skip_result -> dataclasses.replace` 顺序，并明确禁止 `publish_prepared_upload`、`commit_prepared_upload_batch` 与任何 filing/source asset staging；Slice 2 与 stop condition 双重固化；source stage token 为空与 tree hash unchanged 断言落名。 |
| DS 4 [中低] durable result_summary 未规格化 warnings | A9 `accepted` | §6.6 / §7.2 / Slice 3 Exact changes 2 / §12.5 | **已关闭** | `to_json_summary()` 必须写 `warnings`（空为 `[]`）；saved job record、direct/CLI/tool 使用同一 typed tuple；既有 re-read 只读 status/document_id 的事实被写入 plan 并禁止 re-read 重算 warning；durable record exact warning test 落名。 |
| DS 5 [中低] FilingUploadPublicationOutcome 双载体与早退/delete 分支缺口 | A6 `accepted` | §5.4 / §6.5 / §6.6 / Slice 2 tests | **已关闭** | `UploadOperationResult.company_meta_commit_outcome` 定性为 commit helper 到 shared publication 的最小内部载体（§6.5 写明不另建 wrapper 的理由：签名扩散到 material caller）；shared filing publication 是唯一读取/投影者、`warnings` 的唯一生产者；SEC/CN 主分支只读 `warnings`、early cancelled/delete 显式 `warnings=()`；owner invariant 测试 `outcome.warnings == projection(...)` 与"消费者测试不得访问内部字段"均落名。 |
| DS 6 [低] 并发 final-truth 测试未落名 | A10 `accepted` | Slice 2 Tests（两条 barrier/event 测试）+ stop condition | **已关闭** | 明确命名两条测试：同 ticker publish 后 stale-prepared 请求 skip+alias/name 的 outcome/warning 与 final durable meta 一致；跨 ticker 同 alias 竞争唯一 winner、loser typed collision failure 无 warning。禁止 sleep/polling 并写入 stop condition。 |

MiMo 001-006 中 A1/A2 为 `rejected-with-reason`：裁决理由与代码事实一致（`_company_meta_from_published` 在 identity 不变时保留 `updated_at`，等价名称本就 keep+rollback；UF-FIX10 no-mutation 契约针对 filing/source，company identity 由用户明确授权例外）。plan 采纳了其中无害的证据保留部分（§8.3 断言 final meta 逐字段/bytes 不变、source tree hash 不变），未采纳"commit 前 snapshot 推断 warning"与"取消 skip metadata commit"——与本路结论一致，无异议。

**结论：上一轮 DS 1-6 全部关闭。**

## 修订内容的新一轮 adversarial 检查

对 A3-A10 修订本身做了独立压测，发现两个新的、可定位到具体 plan 位置的问题：

### 1-未修复-中低-§6.6 要求"所有 FILING terminal JSON 显式携带 warnings"，但 Slice 2 未点名 SEC/CN failure event builder，漏改会把 typed failure 退化为 generic failure

- **位置**: §6.6 第 1 条 / Slice 2 Exact changes 8 / Slice 2 Tests（"失败无 warning"）
- **问题类型**: 契约缺失 / 测试缺口
- **当前写法**: §6.6 要求"SEC/CN `upload_filing` 的所有 terminal JSON（`ok`/`skipped`/failed/cancelled/delete）必须显式包含 `warnings` 数组，failed/cancelled/delete 分支只能是 `[]`"，且 `from_pipeline_json(..., source_kind=FILING)` 对缺失 fail-closed。但 Slice 2 Exact changes 8 只点名"early cancelled/delete 显式 `warnings=()`"；failure 事件结果由 `_build_sec_filing_failure_event`（`sec_upload_workflow.py:359`）与 `_build_cn_filing_failure_event`（`cn_pipeline.py:1824`）单独构造（共 8 处 yield 点），这两个 builder 未在 Slice 2 的修改清单与测试清单中落名。
- **反例/失败场景**: 实现者按 Slice 2 清单执行，漏改两个 failure builder。failure result dict 缺 `warnings` key → `service_runtime._run_filing_upload` 调 `from_pipeline_json(FILING)` fail-closed 抛 `ValueError` → `run_upload` 无捕获 → direct upload runner 的 `except Exception` 走 `_save_failed_from_exception` → 用户看到 generic failure，`FinsUploadFailureReason`（如 `SOURCE_PUBLICATION_CONFLICT`）丢失。所有上传失败路径回归到 UF-FIX01/UF-FIX03 已关闭的"有界 typed reason"行为。且 Slice 2/3 的 workflow 测试多用 mocked pipeline 返回，测试作者自造的 payload 若同样漏写 `warnings`，全绿通过而生产断裂，没有任何 red 拦截。
- **为什么有问题**: A4 修订把 schema 收紧为"FILING 缺失即 fail-closed"后，producer 侧的完整性变成硬依赖；plan 对 producer 的枚举差一个（且是失败路径上用户可见度最高的一个），与"code-generation-ready"的目标不符。
- **直接证据**: `sec_upload_workflow.py:171/308/317/326` 与 `cn_pipeline.py:802/939/948/957` 各自 yield failure event；两个 builder 定义于 `sec_upload_workflow.py:359`、`cn_pipeline.py:1824`；`service_runtime.py:179-193` 对 filing 结果统一走 `from_pipeline_json`；`ingestion_runtime.py:5935` `_save_failed_from_exception` 是 direct runner 的兜底。
- **影响**: typed failure reason 丢失（用户可见回归）；生产断裂被 mocked 测试掩盖；review 不可验收。
- **建议改法和验证点**: Slice 2 Exact changes 8 增补点名 `_build_sec_filing_failure_event`/`_build_cn_filing_failure_event` 必须输出 `warnings: []`；Slice 2 Tests 增加一条真实 failure event → `from_pipeline_json(FILING)` roundtrip 断言（typed failure 保留且 `warnings == ()`），或至少一条断言 failure event result dict 显式含 `warnings == []` 的测试。验证点：grep 两个 builder 的结果构造含 `"warnings"`。
- **修复风险（低）**: 一处 plan 措辞 + 一条测试。
- **严重程度（中低）**:

### 2-未修复-低-Slice 2 的 SKIP+commit 分支 wiring 未写死 `batch_terminal_started` capability 转交，漏设会把已 durable 的成功提交反转为异常终态

- **位置**: §8.3 步骤 1-6 / Slice 2 Exact changes 4
- **问题类型**: 状态机漏洞 / 不可直接实施
- **当前写法**: §8.3 写死 `stage_upload_company_meta_decision -> commit_batch -> build_prepared_filing_skip_result -> replace`，但未提 `execute_prepared_filing_publication` 内 `finally: if not batch_terminal_started: rollback_prepared_upload_batch(...)` 的既有守卫与该新分支的交互。
- **反例/失败场景**: 实现者在 SKIP+commit 分支调用 `commit_batch` 前未按既有模式置 `batch_terminal_started = True`。若 commit 成功：函数正常 return 前 finally 执行，`sys.exception()` 为 `None`，对已终态 capability 调 `rollback_batch` 抛 `ValueError("无效的 batch token：transaction 已进入终态")`，且 `rollback_prepared_upload_batch(operation_error=None)` 原样 re-raise——**alias/company meta 已 durable 提交，但请求以异常收场**，workflow 落入 `except Exception` 生成 generic failure event，outcome 与 warning 全部丢失。这正是 UF-FIX10 已关闭的"durable 成功但上报失败"反演的同类故障。
- **为什么有问题**: plan 对 A8 已经写死了该分支的函数调用序列，却漏掉唯一会改变函数返回语义的守卫；相邻 PUBLISH/CANCEL/SKIP 分支均有 `batch_terminal_started = True` 先行（`filing_upload_publication.py:679/694/704/743`），plan 的新分支 step 序列与该文件结构强相关，不写死就有真实反例。
- **直接证据**: `filing_upload_publication.py:755-761` 的 finally 守卫；`:743` PUBLISH 分支 commit 前置 flag；`repository_protocols.py:704-712`（commit 后 capability 终态消费、caller 不得再 rollback）；`docling_upload_service.py:1433-1460`（rollback helper 在无主异常时原样抛出）。
- **影响**: 已提交成功被上报为失败（durable/report 不一致）；alias 持久化但用户无 warning 且看到 failure；实施 slip 概率低但后果难恢复（无法重试：再次上传会命中 identical skip 或 alias 已存在）。
- **建议改法和验证点**: §8.3 增补一步："进入 `commit_batch` 前按既有 terminal 分支模式置 `batch_terminal_started = True`（capability 转交 storage owner，finally 不再二次 rollback）"。验证点：Slice 2 增加断言——skip+alias commit 成功后异常路径 rollback 次数为 0、结果返回 `skipped`；commit 失败时原异常携带 capability 消费语义（rollback 不执行）。
- **修复风险（低）**: 一处 plan 措辞 + 现有测试矩阵内补断言。
- **严重程度（低）**:

## 其余 lens 复核（修订引入的部分，无 finding）

- **goal drift**：A1/A2 被拒建议未进入 plan 目标；新增验收（fake 清单、barrier 测试、durable summary、exact 文案）全部是原 goal 的必要正确性条件或 controller 指派的规格收敛，无新增业务目标。✓
- **A4 修订方向正确性**：`from_pipeline_json(result, *, source_kind: SourceKind)` 无默认值显式分流优于上一轮"仅文档说明"的建议；本机核验 filing/material 各自 callsite 均在 allowed files（`service_runtime.py:180/187/226/246`），material 缺失→空、`null` fail-closed 与"material 是 out-of-scope 共享 parser 的既有事实"一致，不构成旧 schema 兼容。✓
- **A5 文案**：新文案"本次提交的公司名称未生效；已保留现有公司名称。请核对上传目标公司是否正确。"对 §8.4 全部 warning 行事实为真（preserve-published 恒保留当前名称），逐字一致地固化在 §6.3/Slice 3 tests/§12.5，满足 oracle 的"明确 warning"与 allowed_variants。✓
- **§9.2 清单与实测一致**：本机 `rg -n "def commit_batch" dayu tests` = 12 定义（dayu 3 + test 9），与清单"3 + 7 文件/9 定义"exact 对应。✓
- **切片顺序**：Slice 1 将全部 fake 文件纳入签名收敛，消除了此前跨 slice 的类型漂移窗口；Slice 1 测试命令与 allowed files 同步更新。✓

## Open questions

无 blocking open question。两个新 finding 均可由 controller 以一行 plan 修订关闭，不需要用户重新决策。

## Residual risks（逐项）

1. **Finding 1 残余**（若 controller 不采纳）：filing failure payload 缺 `warnings` 时 typed reason 退化为 generic failure——`fixed in current slice` 候选，建议裁决后按上述改法落地。
2. **Finding 2 残余**（若 controller 不采纳）：SKIP+commit 分支 capability 转交守卫未写死——同上，一行修订。
3. name-only metadata batch 的 writer lock/physical swap 成本：`assigned to later work unit`（plan §13.4.1），本轮以 final-truth 正确性优先，可接受。
4. degraded unrelated source 使 metadata-only commit fail closed：`fixed in current slice`（§13.3.4），方向正确，维持。
5. material company-name warning：`assigned to later work unit`（§13.4.2），维持。
6. 真实 CLI evidence / oracle / scenario / frozen evidence 刷新：`assigned to later work unit`（§13.4.3），用户已排除，维持。
7. commit 已 durable 但 post-commit guard-release/cleanup 报错时不发 warning：`assigned to later work unit`（§13.4.4），维持。
8. fake 收敛依赖人工 `rg`+清单验收而非编译器强制：已由 §9.2/§12.5 结构化，残余风险为执行纪律风险，归 implementation review 必查项。

## Final plan review conclusion

**pass-with-risks**

- **Blocker**：无。上一轮 DS 1-6 全部关闭；修订未引入结构性方向问题，goal/owner/状态机/原子性/投影契约均与 Goal Confirmation、accepted oracle 和已关闭 work unit 证据一致。
- **不 pass 的理由**：存在两个新的、evidence-based 的规格缺口（failure event builder 未落名、capability 转交守卫未写死），任一漏改都会在真实场景产生用户可见的 typed-failure 丢失或 durable/report 不一致。两者均可在 plan fix gate 以极低成本关闭，不需重开 goal confirmation，故为 pass-with-risks 而非 fail。
