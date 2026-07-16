# WU-SEMANTIC-OWNERSHIP-01 / R08 plan-fix Controller validation

## 1. Gate identity

| 项 | 值 |
|---|---|
| umbrella | `WU-SEMANTIC-OWNERSHIP-01` 既有 umbrella 的 overdesign remediation continuation |
| internal sub-WU | `R08` Fins Financial/XBRL contract；不是新 WU |
| gate | plan-fix Controller validation |
| timestamp | `2026-07-17 03:58:20 +0800` |
| fixed plan | `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md` |
| fixed plan SHA-256 | `07268a120c8b77f44fc4375b372c42ed539a922d63cbdf1b894f9b33397ecde5` |
| AgentCodex fix artifact | `docs/reviews/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan-fix-codex.md` |
| fix artifact SHA-256 | `349bbb77956df9efa333646913ebaf4121b1e57d139b4ff7ea67a1b1a7449a67` |
| result | **PASS / READY FOR DUAL COMPLETE PLAN RE-REVIEW** |

本验证只复核 Controller 已裁决的 `R08-PF-01..07` 是否完整进入固定计划，以及被拒绝路径是否缺席；不重新裁决产品问题，不授权 implementation。

## 2. Accepted findings closure

| ID | Controller 直接核验 | 状态 |
|---|---|---|
| `R08-PF-01` | S1 test allowlist 纳入共享 `tests/fins/test_fins_read_runtime.py`，并按 fiscal symbol/node 与 S2 normalize/dedup nodes 划定边界；S1 review 前必须锁定逐 path SHA-256、完整 binary diff SHA-256 和 full-pyright exact propagation ledger，两路 reviewer 必须重算同一 hash 并逐条核对 ledger。 | closed |
| `R08-PF-02` | 七值 reason 闭集保持不变；同源 description owner 明确每个 reason 的业务含义与安全下一动作，并禁止暴露 method、fallback branch、异常或 Host 治理语义。 | closed |
| `R08-PF-03` | 两个 public builder 精确接受 `Mapping[str, JsonValue]`，立即复制为独立 `dict[str, JsonValue]`；不修改 R07 `Citation` dataclass/owner，不新建 citation schema，不使用 `Any`、cast、alias 或 shim。 | closed |
| `R08-PF-04` | 唯一最小 JSON 示例使用 current truth `SEC_EDGAR`，保留 ticker/document/source provider；`sec_filing` 只在测试/negative scan 规则中作为禁止字面量出现。 | closed |
| `R08-PF-05` | `fiscal_period.enum` 从现有 `FISCAL_PERIODS` 派生；直接代码证据确认其 owner 是包含 `FY/H1/Q1/Q2/Q3/Q4` 的 `frozenset[FiscalPeriod]`，`sorted(...)` 给出确定性 schema 序列。 | closed |
| `R08-PF-06` | producer validator 明确先拒绝 `bool` 再接受 `int | float`；测试矩阵包含 `True`、`False`、`int`、`float` 和 missing。 | closed |
| `R08-PF-07` | tools projection 类型精确命名为 `PublicFinancialStatementResult` / `PublicXbrlQueryResult`；删除旧 tools 类型名且不留兼容 alias/re-export/wrapper，domain producer 类型名保持不变。 | closed |

结论：`7/7 closed`，`0 deferred`，`0 product blocker`。

## 3. Rejected path and scope audit

- `_build_financials_payload` 仍只按无 production caller 的 alternate owner 删除，未被重构为新 production path。
- 计划只有一个 JSON 示例；未增加第二套 complete/partial 示例协议。
- 未修改或复制 `Citation` owner；不存在 `PublicCitation`。
- 未引入 compatibility alias、re-export、wrapper、shim、cast 或 read-side query 重拼。
- 未授权 Host/Issue 177、R07 snapshot/citation owner、R09-R12、deferred Issues 或统一 tool authorization framework。
- 本 gate 没有产品代码、测试或 README 修改；当前 worktree 只包含既有 Controller/control 与 R08 plan/review artifacts。

## 4. Validation evidence

- 固定计划 SHA-256 重算：`07268a120c8b77f44fc4375b372c42ed539a922d63cbdf1b894f9b33397ecde5`。
- AgentCodex fix artifact SHA-256 重算：`349bbb77956df9efa333646913ebaf4121b1e57d139b4ff7ea67a1b1a7449a67`。
- `git diff --check`：PASS。
- 两个 untracked artifact 分别执行 `git diff --no-index --check /dev/null <path>`：零 whitespace/error diagnostic；exit `1` 仅表示预期内容 diff。
- source/plan scans 确认唯一 `json` fence；`SEC_EDGAR` 示例正确；`JsonNumber` 仅以“仓库不存在、不得引用”的负向说明出现；不存在 `PublicCitation` 或 `Citation` TypedDict 误述。

## 5. Handoff

下一 gate 是 AgentMiMo / AgentDS 对固定 SHA `07268a12...ecde5` 的并发、完整 plan re-review。两路必须逐项关闭 `R08-PF-01..07`，并审查整份固定计划与当前代码证据；不得只核对 diff。re-review 与 Controller adjudication 全部通过前，不授权 implementation、commit、R09-R12、deferred Issue、统一 authorization、push 或 PR。
