# WU-SEMANTIC-OWNERSHIP-01 PR 179 deepreview Controller adjudication

## Gate 与证据锁

- Gate：draft PR 179 双路完整 deepreview 后的 Controller 裁决。
- PR：`https://github.com/noho/dayu-agent-r/pull/179`，base `main`，reviewed HEAD `86174133b51f2e34cac5d93c4128d9b40a8c48b8`。
- AgentMiMo artifact：`docs/reviews/wu-semantic-ownership-01-pr179-deepreview-mimo.md`，225 lines，SHA-256 `6e03d5a32f48facf4d0988d49d0c82f2219a64a6e37c8b39888bb0a3f744a085`。
- AgentDS artifact：`docs/reviews/wu-semantic-ownership-01-pr179-deepreview-ds.md`，323 lines，SHA-256 `e7953063af1e32155df62c469e330d7371d5a70606f9d5b18946db0a5d7c1a8e`。
- 两路 review 均覆盖 PR full diff、R01-R12 组合行为、Topic 1-9 裁决边界、安全边界和 deferred owners；MiMo 独立报告 0 finding，DS 报告 1 个 actionable candidate、4 个已按真源驳回候选和 14 个 nonfinding。

## 第一性原理与 owner 判定

本轮唯一成立的问题不是“内部是否可以有治理错误码”，而是内部治理错误码是否可能被当作业务可读工具失败文本投影给 LLM。

直接代码证据如下：

1. `ToolRuntimePolicyPort.decide_tool_call()` 的返回类型是 `ToolPolicyDecision`；该 dataclass 的 `message` 为 `str | None`，端口实现可构造非 `ALLOW` 且缺少可读 message 的对象。
2. `_governed_failure_outcome()` 当前使用 `policy_decision.message or _TOOL_RUNTIME_GOVERNED_ERROR`，其中 `_TOOL_RUNTIME_GOVERNED_ERROR` 的值为内部码 `host_tool_governed_error`。
3. 该 outcome 会先返回 Engine / 进入 accepted result 路径，再可由 accepted evidence projection 投影为 LLM-readable result text。
4. `_validate_policy_decision_fields()` 虽然要求非 `ALLOW` decision 同时携带 reason 与 message，但它位于后续 accept-candidate governance validation，不能证明 `_governed_failure_outcome()` 的即时 LLM-facing 输出边界安全。

因此语义 owner 是 Host ToolRuntime 的 policy-decision invariant 与 governed-failure projection boundary。正确修复必须在该 owner 内 fail closed；不能在 Memory、RunInput、Compact、Tool Trace 或 renderer 下游过滤，也不能补另一条通用可读 fallback。

## Finding 裁决

### PR179-DR-F01 — ACCEPTED / fix required

- 来源：AgentDS Finding 016。
- 严重度：Medium；当前 production call sites 均提供 message，因此是潜在但可达的端口输入缺口，不是已观测用户事故。
- 问题：非 `ALLOW` `ToolPolicyDecision` 缺少非空 message 时，内部码 `host_tool_governed_error` 可成为 LLM-facing 工具失败文本。
- 必须满足的修复不变量：
  - 删除内部错误码充当 LLM-readable message 的 fallback；若常量无剩余合法消费者则删除常量。
  - malformed governed decision 在 Host ToolRuntime owner boundary fail closed，不能生成、accept、持久化或投影一个带内部码的工具 outcome。
  - `ALLOW` decision 不得误用 governed-failure projection。
  - 保留 reason code 供内部 digest、audit、diagnostic 或 durable governance 使用；不得把 reason code 当业务 message。
  - 保留所有已有合法 governed outcomes 的外部行为。
  - 补 owner-level adversarial tests，至少覆盖非 `ALLOW` decision 的 `message=None`、空白 message，以及 `ALLOW` 误入 governed-failure boundary；断言内部码不进入 outcome / Tool Trace / audit / LLM-readable material。
- 范围限制：不新增统一 tool authorization framework，不设计 permission schema、policy DSL、role/capability 或 sandbox，不修改 Topic 2 Web 默认 allow 裁决，不新增下游 LLM-safe normalization。

### Rejected-with-reason / closed

- DS Finding 001：reject。Fins read process 首次 cleanup failure 在业务成功路径转换为 `execution_error`、已有业务/异常失败保持 primary，是既有 owner-level 测试和 R07 裁决冻结的 bounded failure contract。
- DS Finding 002：reject。`categorized_count < selected_count` 是 cancellation-safe partial summary；P0-B 已明确接受 selected 大于 categorized 与 skipped-only success，不得补 equality shim。
- DS Finding 017：reject。`HostTransactionRetryExhaustedError` 已裁决为 transient backoff/reconcile；没有 authoritative typed lost outcome 或显式 Host durable evidence 时不得 self-close、terminalize 或 LOST。
- DS Finding 019：reject。Web private/custom port 的缺省 `allow` 是 Topic 2 明确产品裁决；不得以旧 deny 行为覆盖裁决。

### Nonfinding / closed

- DS Findings 003-015、018 全部 closed；其中 protocol tightening、durable cancel ownership、fresh-schema 语义和既有 LLM-facing cleanup 均是预期行为。
- `engine_ingest.py` 规模只作为 maintenance observation，不创建新 WU、future refactor WU 或当前 action。
- MiMo 报告 0 material finding；其 bounded tests/imports direct-evidence 收口不留下 pending、open 或 unclassified residual。

## 安全与 deferred 边界

- Config 与 Host internal SQLite/EventLog 属本地 trusted domain，允许存在 API key / headers；本 WU 不新增额外泄露模型。
- Tool Trace、audit、public/log/LLM/review evidence 仍禁止配置 credential / header value 明文；PR179-DR-F01 正是对 LLM-facing governance text 的 owner-boundary补强。
- 现有 allowed paths、Web DNS/peer 与 resource budget、filesystem containment、symlink/no-follow、atomic staging/swap/rollback、process fencing 均保留。
- Topic 8 与 Topic 9 是 no-code decisions，不是 deferred；统一 tool authorization framework 未实施。
- Issue 142、151、175、177、178 与既有 Web/WeChat/render trackers 保持各自 owner；本 fix 不偷带其能力。
- Gemini test-account quota 继续归类为 `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`。

## Gate 结论

- Accepted finding：1（`PR179-DR-F01`）。
- Rejected-with-reason：4。
- Blocker：0。
- Open design question：0。
- Unclassified residual：0。
- Remaining remediation sub-WU：0；本 fix 是当前 umbrella WU 的 PR review finding fix，不创建新 sub-WU 或新 WU。
- Correct next gate：AgentCodex 实施 `PR179-DR-F01` 并提交 implementation/fix artifact；Controller 验证后，AgentMiMo / AgentDS 对完整 PR diff 并发 re-review。不得 merge、mark ready、删除 branch 或关闭 deferred issues。
