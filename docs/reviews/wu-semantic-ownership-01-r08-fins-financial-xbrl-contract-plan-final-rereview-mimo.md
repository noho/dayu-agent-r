# WU-SEMANTIC-OWNERSHIP-01 / R08 final fixed plan — 第二次并发第一路完整 re-review（AgentMiMo）

## 1. Gate identity

| 项 | 值 |
|---|---|
| umbrella | `WU-SEMANTIC-OWNERSHIP-01` 既有 umbrella 的 overdesign remediation continuation |
| internal sub-WU | `R08` Fins Financial/XBRL contract；不是新 WU |
| gate | 第二次并发第一路完整 plan re-review |
| timestamp | `2026-07-17 04:31:03 +0800` |
| reviewed plan | `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md` |
| reviewed plan SHA-256 | `bb37b88b46b2247530d6ce5cafdf875feaee1695a63e7d63f93ada9255e90251` |
| authoritative adjudication | `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-rereview-controller-adjudication.md` |
| fix artifact | `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-rereview-fix-codex.md` |
| fix validation | `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-rereview-fix-controller-validation.md` |
| result | **PASS / 0 material finding / 0 blocker** |

## 2. 复核 closure ledger

### 2.1 原 R08-PF-01..07 — 7/7 closed

以下映射以第一轮 Controller adjudication（`docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-review-controller-adjudication.md` §3）为真源。

| ID | 裁决内容 | plan 位置 | 状态 |
|---|---|---|---|
| R08-PF-01 | S1 immutable hash / full-pyright propagation ledger + 共享 fiscal test symbol boundary | §5.1 lines 370-374（symbol slice）；§5.4 lines 410-431（propagation ledger、S2 四路径限定）；§9 line 738（handoff checklist） | closed |
| R08-PF-02 | 七个 financial reason 业务含义与 LLM-safe 下一动作矩阵 | §4.1 lines 87-99（七值闭集与 complete/partial 规则）；§4.4 lines 297-309（reason→下一动作矩阵表） | closed |
| R08-PF-03 | citation `Mapping[str, JsonValue]` → 独立 `dict` copy 且 R07 no-touch | §4.3 lines 276（builder 接收 `Mapping[str, JsonValue]`、立即 `dict(citation)` 形成独立副本）；§6.7.D（R07 no-touch propagation scan） | closed |
| R08-PF-04 | 示例 `source_type` 使用 `SEC_EDGAR`，不存在 `sec_filing` | §4.4 lines 315-334（最小 XBRL 示例使用 `SEC_EDGAR`、description tests 断言不存在 `sec_filing`） | closed |
| R08-PF-05 | `fiscal_period` enum 从 `FISCAL_PERIODS` 同源派生 `FY|H1|Q1|Q2|Q3|Q4` | §4.2 line 231（`fiscal_period` 消费 `FiscalPeriod` / `FISCAL_PERIODS` 真源）；§4.4 line 311（schema enum 从 `sorted(FISCAL_PERIODS)` 派生）；§6.5 line 563（callable/schema tests） | closed |
| R08-PF-06 | `min_value`/`max_value` 显式拒绝 `bool`、接受 `int | float`、完整 owner test 矩阵 | §4.2 line 232（bool 先拒绝再接受 int/float、owner tests 覆盖 True/False/int/float/missing）；§5.3 line 396（S1 tests）；§6.5 line 563（S2 schema/callable tests） | closed |
| R08-PF-07 | tools 类型精确命名为 `PublicFinancialStatementResult` / `PublicXbrlQueryResult`，旧 tools 名无 compat alias/re-export/wrapper | §4.3 lines 255-256（S2 删除旧 tools `FinancialStatementResult` / `XbrlQueryResult` 名称、直接更新 imports/annotations/tests、不保留 alias）；§6.5 line 560（tests 断言旧名不存在） | closed |

直接证据：第一轮 Controller adjudication §3 逐条列出 accepted plan-fix groups，final plan 各对应章节内容完整。代码复核确认：`FinancialStatementReason` 当前 9 值（`financial_result_contract.py` lines 28-38），plan §4.1 收窄为 7 值；`StatementLocator` 当前存在（line 68），plan 删除它及所有引用；`XbrlFactsResult.total` 当前存在（`xbrl_result_contract.py` line 30），plan 删除；`result_types.py` 当前 `FinancialStatementResult`（line 246）含 `statement_locator`、`XbrlQueryResult`（line 285）含 `total`+`deduped_fact_count`，plan S2 全部删除并重命名为 `PublicFinancialStatementResult`/`PublicXbrlQueryResult`。

### 2.2 新 R08-RR-PF-01..02 — 2/2 closed

| ID | 修复内容 | plan 位置 | 状态 |
|---|---|---|---|
| R08-RR-PF-01 | S1 正式 pytest/coverage 只运行 S1 fiscal exact node，不收集六个 S2 normalize/dedup nodes | §5.1 line 374；§5.4 lines 412-422；§9 line 734 | closed |
| R08-RR-PF-02 | forced-truncation 固定在 `test_fins_storage_provider.py`，窄扩 `_tool_runtime(...)`，pre-Host/post-Host/fetch-more 三段公开链路 | §6.4 lines 543-553；§6.5 lines 570-592；§9 line 752 | closed |

直接证据：Controller validation artifact 确认 2/2 closed，fix-codex artifact 记录 before/after 位置与 closure 判定。

**总 ledger：9/9 closed（7 + 2）。**

## 3. 特别检查项

### 3.1 S1 formal/coverage exact-node 收集

§5.4 修正后内容：

```text
pytest tests/fins/test_financial_read_contracts.py tests/fins/test_sec_pipeline_download.py tests/fins/test_fins_read_runtime.py::test_sec_fiscal_inference_consumes_countless_xbrl_contract tests/fins/test_processor_registry.py
```

§5.1 明确六个 S2 nodes：

```text
test_xbrl_query_payload_missing_total_fails_closed
test_xbrl_query_payload_non_int_total_fails_closed
test_xbrl_query_payload_mismatched_raw_total_fails_closed_before_dedup
test_xbrl_query_payload_preserves_processor_total_after_dedup
test_xbrl_query_payload_always_projects_dedup_count_and_owner_quality
test_xbrl_query_payload_rejects_producer_dedup_count
```

并明确 "S1 不运行它们，也不得对它们加 `skip` / `xfail`、兼容 fixture 或 production shim 伪造绿色"。

代码事实核对：`tests/fins/test_fins_read_runtime.py` 共 10 个 test nodes，其中 6 个是 S2 normalize/dedup nodes（lines 96-266，均依赖当前 producer `total` 字段），1 个是 S1 fiscal node（line 269，`test_sec_fiscal_inference_rejects_invalid_xbrl_total`），2 个是 generic LRU/form matching nodes（lines 48, 78）。S1 正式命令精确选择 fiscal node，不误收 S2 nodes。

**判定：通过。**

### 3.2 forced-truncation 真实 public seam

§6.4/§6.5 修正后指定了完整可执行机制：

1. `_tool_runtime(...)` 窄扩为 `_tool_runtime(workspace_root: Path, *, extra_config: Mapping[str, JsonValue] | None = None, enable_truncation_manager: bool = False) -> tuple[ToolRuntimeHandle, _AcceptingPort]`。
2. 命名常量 `_FORCED_XBRL_MAX_ITEMS = 1`，经 `_spec(..., extra_config={"limits": {"query_xbrl_facts_max_items": _FORCED_XBRL_MAX_ITEMS}})` 投影。
3. pre-Host：先 `"fact_count" in pre_value` 证明字段存在，再直接索引断言 `pre_value["fact_count"] == len(pre_value["facts"])`。禁止 `.get`。
4. post-Host：断言 `set(post_value) == set(pre_value)`、非 `facts` sibling 逐项相等、`post_value["fact_count"] == pre_value["fact_count"]`；`facts` 成为 cursor envelope。
5. fetch-more：经同一 executor 调用 `FrameworkToolName.FETCH_MORE.value`，visible prefix + remainder 逐项还原为 pre-Host facts。

代码事实核对：`_tool_runtime` 当前签名 `def _tool_runtime(workspace_root: Path) -> tuple[ToolRuntimeHandle, _AcceptingPort]`（line 5792），`_spec` 当前签名 `def _spec(workspace_root: Path, *, extra_config: Mapping[str, JsonValue] | None = None) -> ToolsDiscoveryProviderSpec`（line 5269）。当前 `EffectiveToolBundleBuildRequest` 已有 `enable_truncation_manager` 参数。当前 `_tool_runtime` 设 `enable_truncation_manager=False`。窄扩只增加两个 keyword-only 参数并保持默认行为，与现有 under-limit/cancellation tests 兼容。

公开 shape 证据（fix-codex §7.2）：当前 pre/post 旧 contract key set 完全相同，Host 只替换 `facts`、保留全部 siblings。`fact_count` 当前不存在是 R08 尚未实施的旧 contract 事实，不是 Host 删除。正式测试必须在 S2 产生 `fact_count` 后重新证明。

**判定：通过。**

### 3.3 evidence correction 核对

Controller 退回的 evidence correction 事实：

- 当前旧 contract pre/post 都无 `fact_count`：代码事实确认 `XbrlQueryResult`（line 285）和 `FinancialStatementResult`（line 246）均无 `fact_count` 字段；当前 `.get("fact_count") -> None` 是取值路径错误。
- Host 仅替换 facts 并保留 siblings：公开 shape 确认 pre/post key set 完全相同（`citation|data_quality|deduped_fact_count|document_id|facts|query_params|reason|ticker|total`），只有 `facts` 从 list 变为 cursor envelope。
- 未来测试用 membership/direct index/key-set/sibling equality，不能用 `.get`：§6.4/§6.5 已明确写入。

**判定：通过。evidence correction 已正确反映在 final plan 中。**

## 4. Adversarial owner/slice/test/LLM/scope review

### 4.1 Architecture boundary review

- **Producer → public boundary**：Financial/XBRL producer contracts 在 `dayu.fins.domain.*_result_contract.py`，public projection 在 `dayu.fins.tools.result_types.py`。plan 不允许 read/tool/serializer 手写第二份 mapping，必须机械消费 builder。
- **Fins → Host boundary**：Fins 只拥有 pre-Host typed result 等式；Host cursor envelope 是独立治理层。plan 明确禁止 Fins 解析 envelope、禁止越界改 Host。
- **R07 no-touch**：snapshot acquire/borrow/release、cache revision、citation generation 保持零语义变更。plan 以 R07 no-touch propagation scan 验证。
- **Domain vs tools 类型命名**：`FinancialStatementResult` 同名出现在 domain（line 77）和 tools（line 246），plan 要求 S2 将 tools 版重命名为 `PublicFinancialStatementResult`，消除命名歧义。

未发现架构边界违反。

### 4.2 Best-practice review

- 使用真实 fixture、真实 provider config、真实 process-backed ToolRuntime，不依赖 mock。
- 测试条件基于 "facts 数大于 limit" 而非冻结 fixture 数量，具备可维护性。
- 逐文件 coverage `>=80%`，不以 aggregate 掩盖低文件。
- 双向 scans（positive inventory + negative propagation + unique count owner + R07 no-touch）确保删除后无残余。

未发现最佳实践偏离。

### 4.3 Optimal-solution review

- 在 producer owner 收紧 contract 再机械投影，比 "只改 tool 文案" 或 "在 read 补默认" 更直接修 root cause。
- 删除 `_build_financials_payload` alternate owner，比保留兼容分支更安全。
- 窄扩 `_tool_runtime(...)` 而非新增 Host test 文件或 mock，是最小侵入路径。
- 七值 reason 闭集比九值更精确反映业务语义（`statement_method_missing` 和 `statement_empty` 是 method 级内部观测，不是用户可行动 reason）。

未发现非最优路径。

### 4.4 Overengineering review

- 不引入 generic builder、god bag、reflection 或新 schema framework。
- 只建两个小型 typed projection helpers。
- 不新增 Host protocol、cursor abstraction 或第二 contract。

未发现过度设计。

### 4.5 Overcoupling review

- S1/S2 是同一次破坏性 cutover，但 plan 通过 symbol-level slice 和 pyright propagation ledger 确保两 slice 边界清晰。
- 共享 `test_fins_read_runtime.py` 已按 symbol 划分 S1/S2 归属，不产生跨 slice 耦合。
- provider business bundle 不拥有 `fetch_more`，Host effective bundle 注入独立断言，无跨层私有状态耦合。
- `_tool_runtime` 窄扩保持默认关闭，不影响现有 tests。

未发现过度耦合。

### 4.6 LLM-facing 文本 review

- §4.4 要求 description 自足说明字段、类型、必填性、枚举与最小示例。
- 七值 reason 均有业务含义和 LLM-safe 下一动作矩阵（§4.4 table）。
- 示例使用 `SEC_EDGAR`、不暴露 `sec_filing`、不暴露 processor method/fallback branch。
- `fiscal_period.enum` 从 `FISCAL_PERIODS` 同源派生 `FY|H1|Q1|Q2|Q3|Q4`。
- `min_value`/`max_value` 保持 `type: number`，与 S1 bool 拒绝共同受约束。

未发现 LLM-facing 文本问题。

### 4.7 Test gap review

- S1 owner tests 覆盖：exact keys、optional reason、七值闭集、complete/partial 组合、method absent/None/empty/table/rows 五类 terminal 归一。
- S2 public tests 覆盖：exact keys、producer→public 逐项相等、flat query params、fiscal_period 共享 owner、bool 拒绝、normalize/dedup 前后不变、fact_count 唯一同源、tool description 自足、R07 citation 一致性、forced-truncation 组合验证。
- Coverage 门逐文件 `>=80%`。
- 双向 scans 确保无残余/无漂移。

未发现测试缺口。

## 5. Rejected paths 复核

Controller 已拒绝且无新直接证据的问题不重开：

| 已拒绝意见 | 复核 |
|---|---|
| optional-reason 私有 helper 指令 | §4.1/§4.2 已明确 terminal validator contract；具体 helper 实现由 owner 内选择。无新证据。 |
| reason frozenset 额外 checklist | 七值闭集在 §3.1、§4.1、§5.2、§5.3 多处精确规定。无新证据。 |
| Host truncation routing 到 R09 | R09 是 wait poller，不是 truncation owner；Issue 177 跟踪。无新证据。 |

## 6. Open questions

无。

## 7. Residual risks

- Host 截断 `facts` 后不会原子改写 sibling `fact_count`：R08 只验证 pre-Host Fins 等式及 post-Host owner 分离，不宣称 envelope 是第二个 Fins result。继续由 Issue 177 跟踪。
- S1 full-pyright ledger 预期只有四个 S2 production paths 的传播诊断；若出现其它 path 的诊断，S1 必须停止。
- `fact_count` 在 S2 实施后才存在；forced-truncation test 必须在 S2 产生该字段后才能实际运行。

以上均不是本次 re-review blocker。

## 8. Final plan review conclusion

**PASS / 0 material finding / 0 blocker。**

固定计划 SHA-256 `bb37b88b46b2247530d6ce5cafdf875feaee1695a63e7d63f93ada9255e90251` 已确认。原 `R08-PF-01..07` 为 7/7 closed，新 `R08-RR-PF-01..02` 为 2/2 closed，总 9/9 closure。evidence correction 正确反映：当前旧 contract pre/post 都无 `fact_count`，Host 仅替换 facts 并保留 siblings，未来测试用 membership/direct index/key-set/sibling equality。整份计划在 owner 边界、slice 划分、测试覆盖、LLM-facing 文本、scope 控制和架构约束上均通过 adversarial review。

不修改 plan/control/design/code/tests/README，不 stage/commit/push/PR，不进入 implementation。
