# WU-SEMANTIC-OWNERSHIP-01 / R08 fixed-plan re-review Controller adjudication

## 1. Gate identity

| 项 | 值 |
|---|---|
| umbrella | `WU-SEMANTIC-OWNERSHIP-01` 既有 umbrella 的 overdesign remediation continuation |
| internal sub-WU | `R08` Fins Financial/XBRL contract；不是新 WU |
| gate | dual complete fixed-plan re-review adjudication |
| timestamp | `2026-07-17 04:09:10 +0800` |
| reviewed plan SHA-256 | `07268a120c8b77f44fc4375b372c42ed539a922d63cbdf1b894f9b33397ecde5` |
| AgentMiMo review | `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-rereview-mimo.md` / `d0b3254aeb5f55f479a4d022ce6ddadeb0c257454ba6ead9f7ffe981e1ba52ff` |
| AgentDS review | `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-rereview-ds.md` / `e2f2c4fef597ef8d02e5215a6cc32091cbf51d761ae5dd1fd6b63f337e43c21b` |
| result | **FIX REQUIRED / 2 accepted plan-fix groups / 0 product blocker** |

两路均确认 `R08-PF-01..07` 在固定计划中 `7/7 closed`，被 Controller 拒绝的重复/兼容/Host/deferred 路径未回流。Controller 对新意见按当前代码、固定计划和裁决真源逐条复核如下。

## 2. Accepted plan-fix groups

### R08-RR-PF-01 — S1 正式验证必须遵守共享测试文件的 symbol slice

**裁决：accepted / must fix before implementation。**

直接证据：

- 固定计划 §5.1 已将 `tests/fins/test_fins_read_runtime.py` 划成 S1 单一 fiscal node 与 S2 六个 normalize/dedup nodes；S1 不得迁移后者。
- 固定计划 §5.4 却在正式 test 和 coverage 命令中运行整个共享文件。
- 当前 `dayu/fins/tools/read_runtime_helpers.py` 的 `_normalize_xbrl_query_payload` 仍读取 producer `total`，所以 S1 删除该字段后，六个 S2 nodes 在 S2 实施前必然失败；这正是 plan 已允许进入 exact pyright propagation ledger 的 consumer 断裂，不能伪装成 S1 test failure。

最小修复：

- S1 正式 pytest 命令只运行 S1 fiscal node；其余 S1-owned test files/registry 仍完整运行。
- S1 coverage 命令对共享文件使用相同 node selection，不得收集六个 S2 nodes；逐 production file `>=80%` 规则不变。
- S2 继续完整拥有并运行六个 normalize/dedup nodes；不得提前迁移、skip、xfail 或加兼容 shim。

### R08-RR-PF-02 — forced-truncation 组合验证必须给出 current-tree 可执行构造

**裁决：accepted / must fix before implementation。**

固定计划已正确裁决 Fins pre-Host typed result 与 Host cursor envelope 是两个 owner，并禁止 R08 修改 Host；但 §6.4/§6.5 只写“forced-truncation path”，未指定如何在当前 allowlist 内经过真实 ToolRuntime。`tests/fins/test_fins_storage_provider.py` 已有 `_tool_runtime(...)`、真实 `DefaultToolRuntimeFactory`、`ToolTruncateSpec` limits 和 process-backed 调用基础，因此无需 mock 或新 Host test 文件即可形成可执行验证。

最小修复：

- 指定在 `tests/fins/test_fins_storage_provider.py` 复用/窄扩现有真实 ToolRuntime fixture，使 truncation manager 启用，并通过 provider config 将 `query_xbrl_facts_max_items` 降到小于真实 fixture facts 数的正整数。
- 同一测试必须先捕获/断言交给 Host 前的 Fins public typed value 满足 `fact_count == len(facts)`，再断言 Host completed value 的 `facts` 已成为当前 cursor envelope、`fetch_more` owner 仍是 Host，且不把 envelope 解释成第二个 Fins result contract。
- 不硬编码 Host cursor 内部私有字段；只使用当前 public ToolRuntime/cursor contract assertions。若当前 public testing seam 无法同时观测 pre-Host value 与 completed envelope，则按计划 stop 回 Controller，不得 mock、改 Host 或越界实施 Issue 177。

## 3. Rejected / no-fix opinions

| 来源 | 意见 | 裁决 |
|---|---|---|
| MiMo finding 01 | Plan 必须写明把 `_required_financial_reason` / `_required_xbrl_reason` 改成先检查 key | **rejected as already specified / implementation detail**。§4.1 与 §4.2 已明确 reason 为 `NotRequired`、complete/xbrl 时缺席、partial 时必填；terminal validator 是唯一 owner；§5.2 明确 reason 改 optional 并验证 complete/partial 组合；§5.3 直接要求 complete+reason、partial 无 reason 和 exact-key owner tests。具体保留/重命名/替换私有 helper 由 implementation 在 owner 内选择，不应固化成第二套计划语义。 |
| DS residual `_FINANCIAL_STATEMENT_REASONS` 同步 | 建议 checklist 显式列出 frozenset | **no additional fix**。七值闭集、删除两值、unknown reason fail-closed 与 owner tests 已在 §3.1、§4.1、§5.2、§5.3 多处精确规定。 |
| MiMo residual routing | Host truncation 风险可跟踪到 R09 | **rejected routing**。R09 是 wait poller，不是 truncation owner；R08 不改 Host。Doc/TruncationManager 完整接通继续由 Issue 177 跟踪。 |

## 4. Final ledger

| 类别 | 数量 | 状态 |
|---|---:|---|
| 原 `R08-PF-01..07` | 7 | closed |
| 新 accepted plan-fix groups | 2 | open，必须由 AgentCodex 修复后双路完整 re-review |
| rejected/no-fix opinions | 3 | closed with reason |
| deferred accepted finding | 0 | none |
| product blocker | 0 | none |

## 5. Handoff

下一 gate 仅授权 AgentCodex 修改同一 R08 plan 和写一份 re-review fix artifact，关闭 `R08-RR-PF-01..02`。不得修改 control、design、code、tests 或 README，不得 stage/commit/push/PR，不得进入 implementation。Controller validation 通过后，AgentMiMo / AgentDS 必须再次对新固定 SHA 做完整 re-review，不能只看两处 diff。
