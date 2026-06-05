# Re-Review: WU-DUR-P01-S2-R2 runner-call event link hardening

- **Reviewed target**: `docs/host/wu-dur-p01-s2-r2-runner-call-event-link-plan.md`（修订版）
- **Reviewer**: mimo
- **Timestamp**: 20260605-191243
- **Scope**: 只复核上一轮 `wu-dur-p01-s2-r2-plan-review-mimo.md` 与 `wu-dur-p01-s2-r2-plan-review-ds.md` 中的阻断项和强建议是否已关闭。不改代码，不扩大到 unrelated scope。

## 复核矩阵

### Mimo review 阻断项

| # | 原 finding | 修订版对应位置 | 关闭状态 |
|---|---|---|---|
| M01 | `ENGINE_EVENT_REJECTED` 未进入设计真源 event type 表 | plan §3 (L106-124) 新增完整 `ENGINE_EVENT_REJECTED` contract；Slice 0 (L207) 明确补录 event type list + matrix | **已关闭** |
| M02 | 新增 diagnostic reasons 未写入设计真源闭集定义 | plan §3 (L117-124) 定义 4 个 rejected reason 语义+使用边界；§2 (L99) 区分 link diagnostic reason 与 rejected reason 两个闭集 | **已关闭** |

### Mimo review 非阻断建议

| # | 原 finding | 修订版对应位置 | 关闭状态 |
|---|---|---|---|
| M03 | `_has_prior_iteration_observation` 范围未规格化 | plan §5 (L152-158) 完整规格化：scope、accepted prior 定义、排除项、事务内可见性 | **已关闭** |
| M04 | 现有 continuation 测试 fixture 需更新 | plan Slice 2 (L278) 明确要求 seed prior iteration observation | **已关闭** |
| M05 | `_find_runner_call_manifest_event` dead code | plan Slice 1 (L233) 明确删除；L260 静态检查命令验证 | **已关闭** |
| M06 | `validation_status` 语义过载 | plan §2 (L96) 明确 mismatch "不表达 link identity conflict" | **已关闭** |

### DS review 阻断项

| # | 原 finding | 修订版对应位置 | 关闭状态 |
|---|---|---|---|
| DS-F1 | `_has_prior_iteration_observation` durable query 契约未定义 | plan §5 (L152-158) 完整定义：只查 `run_id` + `attempt_id` + `execution_id`，只看 accepted link + accepted preview，排除 `RUNNER_CALL_INPUT_ASSEMBLED` 计数和 `ENGINE_EVENT_REJECTED`，事务内可见性约束 | **已关闭** |
| DS-F2 | "ordinary dispatch kind" 未给闭集 | plan §5 (L143) 明确闭集 `initial_user_dispatch` / `followup_user_dispatch` / `post_compaction_dispatch`，排除 `tool_result_continuation` 和 `compactor_proposal`，附加 `compactor_identity is None` 条件 | **已关闭** |
| DS-F3 | manifest write 与 ITERATION_STARTED ingest 之间 timing 约束 | plan §4 (L126-132) 新增 "Durable ordering guarantee" 章节；Slice 0 (L212) 要求检查并记录；Stop condition (L356) 要求无 ordering guarantee 时回到 design gate | **已关闭** |

### DS review 非阻断建议

| # | 原 finding | 修订版对应位置 | 关闭状态 |
|---|---|---|---|
| DS-F4 | anti-join 查询策略未给出 | plan §5 (L145) 明确 `NOT EXISTS` 子查询 + SQLite JSON1 `json_extract`，scope 固定到 `run_id` + `attempt_id` + `execution_id` + event type；Stop condition (L358) 要求无法实现时回到 design gate | **已关闭** |
| DS-F5 | diagnostic reason 枚举归属 | plan §2 (L99) + §3 (L117-124) 明确两个独立闭集：runner-call diagnostic reason vs. Engine ingest rejected reason；§3 (L124) 明确禁止交叉写入 | **已关闭** |
| DS-F6 | continuation reset 测试 seeding 路径 | plan Slice 2 (L277) 明确 "通过生产 helper / ingest 路径创建...或使用 dedicated test helper 追加 typed `RUNNER_CALL_INPUT_ITERATION_LINKED`；不得用 raw SQL 绕过 payload shape" | **已关闭** |
| DS-F7 | preview resolution result 传递机制 | plan §6 (L173-178) 明确新增 `_RunnerCallIterationResolution` typed result，`_append_iteration_started_events` 先完成 resolution 再传给 preview builder，禁止 preview builder 内重新查询 | **已关闭** |
| DS-F8 | link event 与 preview 事务原子性 | plan §5 (L160) 明确 "必须在同一个 Host write transaction 中 append"；Stop condition (L360) 覆盖 | **已关闭** |

## 重点检查项逐项验证

| 检查项 | 验证结果 |
|---|---|
| ENGINE_EVENT_REJECTED design sync/event matrix | §3 (L106-115) 完整定义 scope/payload/状态副作用/consumer；Slice 0 (L207) 明确补录 |
| 新增 rejected reason 与 runner-call diagnostic reason 的枚举归属和语义 | §2 (L99) 区分两个闭集；§3 (L117-124) 定义 4 个 rejected reason 语义；§3 (L124) 禁止交叉写入 |
| `_has_prior_iteration_observation` durable query scope | §5 (L152-158) 完整规格化，包括 scope、accepted prior 定义、排除项、事务内可见性 |
| ordinary dispatch kind 闭集 | §5 (L143) 明确 3 个 kind + `compactor_identity is None` |
| manifest commit-before-start ordering stop condition | §4 (L126-132) + Slice 0 (L212) + Stop condition (L356) |
| anti-join 查询策略 | §5 (L145) `NOT EXISTS` + `json_extract` + scope 收窄 + Stop condition (L358) |
| preview resolution result 传递 | §6 (L173-178) typed result + 禁止 preview builder 内重新查询 |
| link+preview/rejected 同事务 | §5 (L160) + Stop condition (L360) |
| 旧 fallback/dead code 清理验收 | Slice 1 (L233) 删除旧函数 + (L260) 静态检查命令 |
| Tool Trace 最小实现语义 | §7 (L182-190) + 非目标 (L22) 不强制投影 link event |

## Open Questions 检查

| OQ | 状态 |
|---|---|
| M-OQ1 (link event 是否进 Tool Trace) | 非目标 (L22) 明确不强制；§7 (L189) 允许可选实现。**不阻断，deferred** |
| M-OQ2 (`stop_worker_stream` payload vs. result 字段) | §3 (L113) 明确 "event payload 也必须记录同名布尔值"。**已关闭** |
| M-OQ3 (`manifest_schema_version` 语义) | 未显式回答，但 hot payload 字段列表 (L78) 保持原样。**低风险，deferred** |
| DS-OQ1 (preview validation summary 与 link event ref 关系) | §6 (L167-171) 明确 preview 增加 link event id + manifest ref fields。**已关闭** |
| DS-OQ2 (双重 iteration_index=0) | §5 (L148) 候选数为 0 + 有 prior observation → continuation limited-signal。**行为明确，deferred 为 known edge case** |
| DS-OQ3 (rejected 后状态迁移) | §3 (L114) "无 Run / Attempt lifecycle transition"。**已关闭** |

## 新增发现

无新增阻断项。修订版 plan 在所有上一轮阻断项和强建议上都给出了明确的规格化回答，且规格内容与代码事实一致。

## Conclusion

**accept**

上一轮 2 个阻断项（M01 `ENGINE_EVENT_REJECTED` 设计真源缺定义、M02 新增 diagnostic reason 缺语义定义）和 3 个 DS 阻断项（F1 prior observation query scope、F2 ordinary dispatch kind 闭集、F3 ordering guarantee）全部已关闭。修订版 plan 新增了 §3（ENGINE_EVENT_REJECTED 与 reason 契约）、§4（Durable ordering guarantee），并在 §5（Link resolution contract）中补充了 anti-join 查询策略、同事务原子性约束、`_has_prior_iteration_observation` 完整规格化。非阻断建议也已覆盖。plan 现在 code-generation-ready，可进入 implementation。
