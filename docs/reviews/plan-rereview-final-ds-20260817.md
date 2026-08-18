# UF-FIX11 company-metadata-ignored-change-warning — 最终定向 Re-review (AgentDS)

## Reviewed target and scope

- Target：`docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md`（fix2 后当前版本）
- fix2 artifact：`docs/gateflow/uf-fix11-plan-rereview-fix2-20260817.md`
- 本路上一轮：`docs/reviews/plan-rereview-ds-20260817.md`（DS-RR1/DS-RR2，`pass-with-risks`）
- 本轮范围：仅核对 DS-RR1/DS-RR2 是否完整关闭、对应测试是否可实施、是否引入新 blocker。不重开 A1-A10 与 goal，不修改任何文件。
- 裁决源：controller 已接受 DS finding 1、2（fix2 §3）。

## DS-RR1 关闭核对（failure terminal producer + strict parser 同 Slice 收敛）

| 要求 | plan 落地点 | 判定 |
| --- | --- | --- |
| Slice 2 点名两个 failure builder 并规定显式 `warnings=[]` | Slice 2 Exact changes 8（`_build_sec_filing_failure_event`/`_build_cn_filing_failure_event` 必须把 `warnings=[]` 传入各自 result builder；禁止省略或从 exception/message 推断） | **已关闭** |
| 全部 filing terminal producer 枚举 | Exact changes 8：normal ok/skipped 用 shared warnings，early cancelled/delete 显式 `[]`，failed builders 显式 `[]` | **已关闭** |
| producer 与 strict parser 同 Slice 原子收敛 | Exact changes 11：A4 parser boundary（无默认值 `source_kind` + typed warnings parse）提前到 Slice 2；Slice 2 allowed files 增加 `ingestion_runtime.py`（仅 parser contract）与 `service_runtime.py`（仅 callsite `SourceKind`），并注明范围限定 | **已关闭** |
| 真实 workflow roundtrip 测试（非 handcrafted/mock） | Slice 2 Tests：`test_sec_filing_failure_event_roundtrips_typed_reason_with_empty_warnings`/`test_cn_...`，真实 workflow 触发 builder，取 `payload["result"]`，先断言 raw `warnings == []`，再 `from_pipeline_json(..., source_kind=SourceKind.FILING)` 断言 parsed `warnings == ()` 且原 failure code/kind/message 保留 | **已关闭** |
| 两个 builder 的调用点覆盖 | Tests「terminal producer coverage」：SEC/CN 各覆盖 fresh-validation typed failure 与 try-block 内 failure 至少一个真实路径 | **已关闭** |
| stop condition 拦截 | 「任一 SEC/CN filing terminal producer 省略 warnings，或 failure roundtrip 退化为 generic exception failure」 | **已关闭** |
| 静态验收 | §12.5：builder 参数显式含 `warnings=[]`；roundtrip 断言 raw empty list / parsed empty tuple / exact typed reason | **已关闭** |
| Slice 2 测试命令同步 | §12.1 Slice 2 增加 `test_fins_ingestion_runtime.py`、`test_fins_service_runtime.py` | **已关闭** |

**可实施性验证**：真实 workflow 触发两条失败路径均可用既有 fixture 实现——try-block failure 用 `TrackingCompanyMetaRepository.fail_after_stage`/既有 tracking 注入（`upload_filing_test_support.py`），fresh-validation failure 用 `resolve_fresh_filing_request` 返回 typed failure 的既有路径；failure event 的 `payload["result"]` 结构由 `collect_upload_result_from_events`（`sec_upload_workflow.py:114-141`）既有契约保证；`from_pipeline_json` 从测试直接调用无循环依赖。**测试可实施。**

## DS-RR2 关闭核对（SKIP metadata commit 的 capability 转交）

| 要求 | plan 落地点 | 判定 |
| --- | --- | --- |
| 状态机写死转交 | §8.1：`SKIP + preserve metadata intent: stage intent -> set batch_terminal_started=True -> commit metadata batch`；`COMMIT_FAILURE` 注明「storage 已消费 capability，caller rollback=0」 | **已关闭** |
| exact sequence 固化 | §8.3 步骤 2：commit 前必须置 flag，转交后无论成功/抛错 outer `finally` 禁止再 rollback；末段禁止 flag 晚设、commit 后复位、二次 rollback | **已关闭** |
| Slice 2 Exact changes | #4：`stage -> batch_terminal_started = True -> commit_batch -> build skip result -> replace`，明写 flag 前置与 finally 禁止二次 rollback | **已关闭** |
| 成功路径测试 | 「SKIP capability 成功」：terminal-aware batching spy 断言 `commit_count == 1`、caller `rollback_count == 0`、返回 `skipped`、alias/outcome durable；二次 rollback 已消费 token 时测试直接失败 | **已关闭** |
| 失败路径测试 | 「SKIP capability 失败」：commit 消费 capability 后抛错，断言原异常保留、`commit_count == 1`、caller `rollback_count == 0`、无 warning；附 commit 前 stage error 恰好 rollback 1 次的对照 | **已关闭** |
| stop condition | 未在 commit 前置 flag / commit 后二次 rollback 即停止 Slice 2 | **已关闭** |
| 静态验收 | §12.5：`rg -n "batch_terminal_started|commit_batch|rollback_prepared_upload_batch"` + flag 文本顺序严格早于 commit + 成功/失败 rollback 0、stage 失败 rollback 1 | **已关闭** |

**可实施性验证**：`TrackingBatchingRepository.commit_tokens/rollback_tokens` 与 `TrackingCompanyMetaRepository.stage_tokens/fail_after_stage`（`upload_filing_test_support.py:24-149`）已具备全部观测点；capability 转交（局部 flag）通过行为后果（commit 失败后 rollback==0）间接断言，测试规格自洽；rollback 已消费 token 会由既有 `_resolve_active_batch` 契约抛 `ValueError` 使测试按预期失败。**测试可实施。**

## 附带核对（fix2 §6 cleanup，非本轮 focus 但随修订落点）

- 规范化规则去重：`casefold`/NFKC 仅存于 §6.2（本机 grep 确认 3 处引用均在该节）；Slice 1 Exact changes 1 改为「实现 §6.2 已冻结的唯一 helper，本 Slice 不重复列举步骤」。✓
- README allowed-files 去重：§9.3 改为引用 Slice 3 的唯一文档清单。✓

## 新 finding

无。fix2 引入的 parser 前置（Slice 2）在 allowed files、pytest 命令、stop condition、§12.5 与 §13.2.9/§13.5（原子 schema slice 理由）五处自洽；未发现新的规格缺口或方向性风险。

## Open questions

无 blocking open question。

一项非阻塞实施提示（不属于 finding）：Slice 2 引入 strict parser 后，`test_fins_service_runtime.py` 内既有 filing mock payload 可能需同步补 `warnings: []` 才能保持绿色；这属于该文件已允许范围内的同一契约机械同步，若实现发现超出「callsite regression」范围，按既有规则停止并回到 plan gate。

## Residual risks（逐项）

| Residual | 分类 | 结论 |
| --- | --- | --- |
| DS-RR1 failure producer/schema 漂移 | `fixed in current slice` | 已由命名 roundtrip + stop condition 关闭，不递延 |
| DS-RR2 capability 二次 rollback | `fixed in current slice` | 已由 exact 顺序 + rollback-count/terminal-token tests 关闭，不递延 |
| name-only metadata batch 的 writer lock/physical swap 成本 | `assigned to later work unit` | 维持，final-truth 正确性优先 |
| degraded unrelated source fail closed | `fixed in current slice` | 维持 whole-tree owner tests，不 bypass |
| material company-name warning | `assigned to later work unit` | 维持，本轮不改 material flow/schema |
| 真实 CLI evidence / oracle / scenario / frozen evidence | `assigned to later work unit` | 用户已排除，维持 |
| durable 后 guard-release/cleanup 报错不发 warning | `assigned to later work unit` | 维持既有 failure contract |
| A1-A10 | 已裁决并关闭 | 本轮按用户指示不重开 |

## Final plan review conclusion

**pass**

- **Blocker**：无。DS-RR1/DS-RR2 均已在计划当前版本完整关闭，落地点覆盖 contract、exact changes、tests、stop conditions 与 §12.5 静态验收五个层面，且两项测试均经既有 fixture/契约核验可实施。
- **不 pass 的理由**：不存在。剩余风险全部已分类（`fixed in current slice` / `assigned to later work unit`），无未分类项、无需要用户重新决策的项。
- **下一入口建议**：plan 已满足 code-generation-ready；可进入 implementation gate（Slice 1）。
