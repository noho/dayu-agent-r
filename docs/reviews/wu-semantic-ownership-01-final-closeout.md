# WU-SEMANTIC-OWNERSHIP-01 Final Closeout

## Scope and authority

- Work unit：`WU-SEMANTIC-OWNERSHIP-01`，本 artifact 关闭的是同一 umbrella WU 的 overdesign remediation continuation，不是新 WU，也不是重新打开历史 sub-WU。
- 权威产品裁决：`docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`。
- 设计真源：`docs/host/design.md`、`docs/engine/design.md`、`docs/tool/design.md`、`docs/fins/design.md`、`docs/ui/design.md`。
- 总控真源：`docs/host/issues-implementation-control.md`、`docs/phaseflow-umbrella-optimization-control.md`。
- 审查起点：`b1a0631f397967e7530b676a90ef7467d83a1817^..HEAD`；draft PR 为 [PR 179](https://github.com/noho/dayu-agent-r/pull/179)，base 为 `main`。

## Final decision

`PASS / FINAL-CLOSEOUT-PASS`。

Topic 1-7 的 accepted code fixes、各 remediation sub-WU 的 accepted plan/code/aggregate findings、最终 aggregate regression findings、Windows evidence findings，以及 draft PR 179 deepreview finding 均已修复、验证并关闭。Topic 8-9 按权威裁决保持 no-code。当前 accepted/open、needs-evidence、design-contradiction、blocker、unclassified finding 均为 0；remaining remediation sub-WU 为 0；当前 WU residual risk 为 0。

## Product decisions closed

| Topic | Final state |
| --- | --- |
| 1 Doc | 删除 32 MiB 单文件失败、10,000 entries partial、对应 source/directory limit、oversized skip 与 LLM-facing 引导；保留 `ToolTruncateSpec`/`fetch_more`，Issue 177 仍拥有完整输出接通。 |
| 2 Web | 私网/自定义端口改由 `tool_discovery.json` 控制且默认 allow；DNS pin/peer proof 可配置且默认关闭；proxy 默认不 ban；`browser_enabled` 与私网权限解耦；保留按 owner 可配置的财报预算、challenge detection、diagnostics v2；删除本轮 storage-state lifecycle，Issue 178 继续拥有未来 lifecycle。 |
| 3 Host LLM-safe projection | 删除下游 safe/normalized argument repair 和字段名黑名单；只保留 digest、幂等、audit、replay 所需内部 canonicalization；prompt、tool schema 与 Host/Engine/Tool LLM-facing 投影由源头提供业务可读语义。 |
| 4 OpaqueEvidenceRef | opaque ref 仅保留 internal provenance；删除 unknown-kind 业务来源猜测；opaque、拼写错误或 internal ref 不再进入 RunInput、Memory、Compact 或 LLM-readable trace 充当业务来源；未引入 speculative `BusinessSource`。 |
| 5 wait poller | provider mode 由 `tool_discovery.json` 拥有，poller runtime policy 由 `host_runtime.json` 拥有；Service 不再按 scene 构造默认 policy；observation timeout 撤销 late publication、记录 transient diagnostic、释放 claim 并 backoff，不推断 LOST；仅 authoritative typed lost outcome 或显式 Host durable evidence 可进入 LOST。Issue 175 不在本轮实现。 |
| 6 Fins | batch transaction 收敛为唯一显式 authority；完整 source 只在 commit 一次发布；storage 唯一拥有 revision/snapshot；financial/XBRL LLM contract 收窄；exactly-one terminal 由单一 Fins validator 判定；HKEX 按官方 cumulative `rowRange`/`hasNextRow`/`loadedRecord`/`recordCnt` 完整续取；保留 filesystem containment 和 storage-owned opaque identity mapping。 |
| 7 CLI/Web/WeChat/render | `upload_filings_from` 完成 OLD 对齐的分类扫描、macOS/Linux shell 与 Windows cmd 脚本生成、默认/显式输出、正确 quoting 和摘要；删除 JSON argv v1 公共协议及未实现 package placeholders；`dayu-cli init` 完成当前架构下的 provider/model/key/optional integration/prewarm、补 prompt/overwrite/reset/atomic rollback 行为。Issue 142、151 与既有 Web/WeChat/render trackers 继续拥有 deferred 能力。 |
| 8 Engine exception | 保留 generic exception message 的 240 字符硬编码、脱敏和截断后缀；no-code。 |
| 9 tool authorization | 不实施统一 tool authorization framework；不设计 permission schema、policy DSL、role/capability 或 sandbox；未来若需要，其 owner 为 Host ToolRuntime 或同级 Host governance boundary。 |

## Remediation sub-WU reconciliation

| Internal remediation unit | Semantic boundary | Status |
| --- | --- | --- |
| R01 | Doc complete-input semantics | complete |
| R02 | Web config/transport/diagnostics owners | complete |
| R03 | accepted-call evidence、LLM projection、opaque provenance | complete |
| R04 | awaiting provider resolution composition | complete |
| R05 | wait observation state machine | complete |
| R06 | Fins transaction complete publication | complete |
| R07 | Fins storage snapshot / opaque identity | complete |
| R08 | Fins financial / XBRL contract | complete |
| R09 | Fins direct-stream terminal validator | complete |
| R10 | HKEX cumulative discovery | complete |
| R11 | upload script / placeholder removal | complete |
| R12 | init/reset workflow | complete |

All units followed the required plan、dual plan review/fix/re-review、implementation、dual code review/fix/re-review、accepted local commit sequence. The combined tree then passed dual aggregate deepreview, aggregate regression fix/re-review, fresh Windows evidence, and full draft-PR deepreview/fix/re-review.

## Findings and review closeout

- Aggregate regression `AR-F01` through `AR-F05`：closed。
- `AR-F06`：`REJECTED_NOT_A_DEFECT / EXPECTED_HOST_CLOSE_AND_STARTUP_RECOVERY`。设计真源要求 Host close 停止 scheduler/promotion、不启动新 Attempt；durable `QUEUED` Run 在下一次 `open_host` startup recovery 中重新触发 promotion。代码复核与真实 public-path smoke 均确认同一 SQLite 中的 Run B 会在重启后进入 worker accept 并成功收口。因此它不是 scheduler/lifecycle residual，也不需要 future fix owner。
- `AR-F07` and its Windows rounds `WIN2` through `WIN4`：closed by fresh non-skipped Windows evidence and current-code-head checks。
- Draft PR finding `PR179-DR-F01`：closed at the Host ToolRuntime owner boundary by rejecting malformed governed decisions before LLM-readable outcome projection and removing the internal-code fallback。
- AgentMiMo and AgentDS final PR re-reviews both returned PASS with finding/new/backflow/blocker/open/unclassified/pending all 0。
- Rejected/no-code observations remain unimplemented with recorded reasons；no accepted finding was deferred as “future optimization”。

## Validation evidence

- Final aggregate canonical suite：`5260 passed / 10 skipped / 5 deselected`。
- Exact-exclusion coverage suite：`5259 passed / 10 skipped / 6 deselected`；changed production files `219/219 >= 80%`。
- Full pyright：0 errors；full Ruff accepted current set 142、added 0；`git diff --check`、README triggers、source/propagation/security/configured-secret scans：PASS。
- PR finding focused adversarial tests：`6 passed`；ToolRuntime owner aggregate：`179 passed`；accepted-result projection / Phase 6 integration：`37 passed`；modified ToolRuntime file coverage：85%。
- Read-only HKEX official cumulative smoke、public awaiting smoke、CLI/init/upload cross-platform tests and real browser/local smokes：PASS。
- Explicit fresh Windows evidence：R11 run `29713519099` success，R12 run `29713522620` success；R11 `4/4`，R12 init `9/9`，embedded R11 `2/2`。
- Accepted code head `7166ae1f13a3016b0e010703d1c220a0524699da` current-head checks：R11 run `29716162938` success，R12 run `29716162959` success。
- AR-F06 定向复核：startup recovery / graceful-close recovery / terminal queue-promotion owner tests `3 passed`；额外 public-path smoke 验证关闭前 Run B 为 `QUEUED`，重启后 worker 按 `A -> B` 接收，A/B 最终均为 `SUCCEEDED`。
- Gemini is a low-budget test account；quota/provider adherence is `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`。

## Security-related behavior

This WU did not introduce a unified tool authorization framework. It did retain or modify local permission and defense-in-depth behavior where those mechanisms already have a concrete owner:

- Doc `allowed_paths`、filesystem containment、symlink rejection and Dayu-owned reset containment remain active。
- Web DNS/redirect/peer checks、configurable proof policy、resource budgets、challenge detection and diagnostic redaction remain active；private/custom ports are product-configurable and default allow per Topic 2。
- Atomic staging/swap/rollback、storage identity containment、process fencing and late-publication fencing remain active。
- Config and Host-internal SQLite/EventLog belong to the same trusted local domain；configured API keys or headers may exist there。Plaintext configured credential/header values must not appear in Tool Trace、audit output、public/log/LLM-readable material or review evidence。
- No permission schema、policy DSL、role/capability model、generic sandbox or replacement authorization WU was created。

## Current-scope residual reconciliation

当前 WU residual risk 为 `0`。AR-F06 已按设计真源和真实执行链路拒绝为非缺陷；AR-F07 已由真实 Windows 证据关闭；没有 accepted finding 以“后续优化”名义转移。

以下仅是本 WU 明确未实施的既有 scope destination，不属于本 WU residual：

| Deferred / excluded capability | Existing owner / destination |
| --- | --- |
| Doc output continuation | Issue 177 |
| Web storage-state lifecycle | Issue 178 |
| Fins Docling process isolation | Issue 175 |
| Workspace migration | Issue 142 |
| write/assets ownership | Issue 151 |
| Web/WeChat/render real entrypoints | Existing trackers |
| Gemini quota | Expected low-budget test-account condition；`NO_CODE / NON_BLOCKING` |

## Final controller state

- `WU-SEMANTIC-OWNERSHIP-01`：`final-closeout-pass`。
- Active work unit：None。
- Default next work unit：None。
- Draft PR 179 remains open and draft；this closeout does not authorize merge、mark-ready、request reviewers、delete branch or close deferred issues。
- Next entry point：user/maintainer decides how to handle draft PR 179；after merge, synchronize from `main` before selecting any separate backlog work。
