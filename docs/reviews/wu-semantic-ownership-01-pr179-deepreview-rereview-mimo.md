# WU-SEMANTIC-OWNERSHIP-01 PR179 deepreview re-review — AgentMiMo

## Gate 与证据锁

- Gate：draft PR 179 accepted finding `PR179-DR-F01` fix 后的双路完整 PR re-review。
- PR：`https://github.com/noho/dayu-agent-r/pull/179`，base `main`，reviewed HEAD `86174133b51f2e34cac5d93c4128d9b40a8c48b8`。
- Fix delta：未提交工作区改动，production + test binary diff SHA-256 `810bfb9cc01728cc98725177b613b29cc6483be22f5d833a1fcbf627d8aab6ba`。
- Controller validation artifact：`docs/reviews/wu-semantic-ownership-01-pr179-deepreview-fix-controller-validation.md`。
- AgentCodex fix artifact：`docs/reviews/wu-semantic-ownership-01-pr179-deepreview-fix-codex.md`。
- Controller adjudication：`docs/reviews/wu-semantic-ownership-01-pr179-deepreview-controller-adjudication.md`。
- 初轮 MiMo review：`docs/reviews/wu-semantic-ownership-01-pr179-deepreview-mimo.md`（0 finding）。
- 初轮 DS review：`docs/reviews/wu-semantic-ownership-01-pr179-deepreview-ds.md`（1 actionable candidate = DS-016，即 `PR179-DR-F01`）。
- 本 re-review 覆盖：完整 PR diff（main → HEAD 86174133）+ 当前未提交 fix delta + 本 gate 所有 artifacts。
- 工作区中 Controller/AgentCodex/AgentDS 有意改动已保留，未 stash/reset/stage/commit。

## PR179-DR-F01 验证：CLOSED

### 1. Binary diff identity

```
$ git diff --binary -- dayu/host/tool_runtime.py tests/host/test_toolruntime_executor.py | shasum -a 256
810bfb9cc01728cc98725177b613b29cc6483be22f5d833a1fcbf627d8aab6ba
```

与 Controller validation 记录完全一致。✓

### 2. File SHA-256

```
f376dfe547f5f72c314fe018b28f49b5bdf504476b72484602eed3ba04ec28ea  dayu/host/tool_runtime.py
d73a69e900baaf619004c061f18c62288783026ea8258fb699ab9370cc80c8b3  tests/host/test_toolruntime_executor.py
```

与 AgentCodex / Controller 记录完全一致。✓

### 3. Malformed non-ALLOW message fail closed

`_governed_failure_outcome()` 重构后行为（`dayu/host/tool_runtime.py:7205-7232`）：

1. 先调用 `_validate_policy_decision_fields(policy_decision)`（复用既有 accept-governance invariant）。
2. 非 `ALLOW` 决策必须同时携带非空 `reason_code` 和非空白 `message`；`_validate_policy_decision_fields()` 内部通过 `_require_optional_non_empty_text()` 校验 `None`、空字符串、纯空白均抛 `ValueError`。
3. `ALLOW` 和 `REUSE` 显式拒绝进入 governed-failure projection（`ValueError`）。
4. 额外 `if message is None` 兜底（防御性编程）。
5. outcome message 只取已验证的 `policy_decision.message`；不使用任何 fallback 常量。

直接证据：`dayu/host/tool_runtime.py:7216-7227`。

`_validate_policy_decision_fields()` 本身（`dayu/host/tool_runtime.py:5431-5452`）：
- `ALLOW` 决策不得携带 `reason_code` 或 `message`。
- 非 `ALLOW` 决策两者均必填。
- 校验通过 `_require_optional_non_empty_text()`，该函数拒绝 `None`、空字符串、纯空白。

直接证据：`dayu/host/tool_runtime.py:5439-5452`。✓

### 4. ALLOW/REUSE 不误投影为 failure

`_governed_failure_outcome()` 第 7217-7224 行显式检查 `ToolPolicyDecisionKind.ALLOW` 和 `ToolPolicyDecisionKind.REUSE`，若命中则抛 `ValueError`。

测试覆盖：`test_governed_failure_projection_rejects_non_failure_decision` 参数化覆盖两种 kind。✓

### 5. 合法 governed path 不回归

`HINT`、`REQUIRE_JUSTIFICATION`、`HARD_STOP`、`GOVERNED_ERROR` 等合法 governed-failure 类别仍走 `_governed_failure_outcome()` 正常路径，使用自己的非空业务 `message`。

测试覆盖：`test_governed_failure_projection_preserves_readable_message` 验证 `GOVERNED_ERROR` kind 的 outcome message 为原始业务可读说明，序列化后不含内部 `reason_code` 或已删除的 fallback 码。✓

### 6. 内部 reason code 不泄漏到 LLM-facing 通道

- `_TOOL_RUNTIME_GOVERNED_ERROR = "host_tool_governed_error"` 已删除，`rg` 扫描零命中。
- `policy_decision.message or` fallback 模式已删除，`rg` 扫描零命中。
- outcome message 只取已验证的 `policy_decision.message`。
- 测试断言：`_LEGACY_GOVERNED_FAILURE_MESSAGE`（`"host_tool_governed_error"`）不在 `ValueError` 消息中、不在序列化 outcome 中。
- 测试断言：`_INTERNAL_GOVERNANCE_REASON`（`"internal_governance_reason"`）不在序列化 outcome 中。
- `_validate_policy_decision_fields()` 要求非 `ALLOW` 决策必须携带非空 `reason_code` 和非空 `message`，两者分离。

直接证据：`tests/host/test_toolruntime_executor.py:2910, 2917, 2952, 2972, 2973`。✓

### 7. 无下游 fallback/normalization/blacklist/shim

diff 确认改动仅限 `dayu/host/tool_runtime.py` 和 `tests/host/test_toolruntime_executor.py`。未修改：
- Tool Trace 消费者
- accepted-result projection
- Memory / RunInput / Compact Material
- EventLog 投影
- renderer / prompt / tool schema

未新增任何下游 normalization、字段黑名单、内部码过滤或兼容 shim。✓

### 8. 无偷带能力

- 未引入统一 tool authorization framework。
- 未设计 permission schema / DSL / role / capability / sandbox。
- 未修改 Issue 142 / 151 / 175 / 177 / 178 状态或实现。
- 未修改 WeChat / Web / render tracker 能力。
- Web private/custom port 默认 allow 裁决保持不变。
- Topic 8 / Topic 9 no-code decisions 保持不变。

直接证据：diff 仅涉及两个文件，无新模块、新 schema、新 import 或新配置。✓

### 9. Credential / header 处理

- Config / Host internal SQLite / EventLog trusted-local 允许 API key / headers：未修改。
- Tool Trace / audit / public / log / LLM / review evidence 禁止 credential / header 明文：未修改。
- 本 fix 只阻止内部治理码成为 LLM-readable message，不涉及 credential 处理。✓

### 10. 测试覆盖

| 测试类别 | 结果 |
|----------|------|
| Focused adversarial（`governed_failure_projection`） | 6 passed ✓ |
| ToolRuntime owner aggregate（6 files） | 179 passed ✓ |
| Accepted-result projection | 34 passed ✓ |
| Phase 6 integration | 3 passed ✓ |
| Pyright（targeted） | 0 errors ✓ |
| `rg` legacy constant scan | 零命中 ✓ |
| `rg` reason-as-message fallback scan | 零命中 ✓ |

对抗测试覆盖：
- `message=None`、`message=""`、`message=" \t "` — 均在 `_governed_failure_outcome()` 和 `ToolAcceptGovernance` 双边界 fail closed。
- `ALLOW` kind — 拒绝进入 governed-failure projection。
- `REUSE` kind — 拒绝降格为 failure。
- 合法 `GOVERNED_ERROR` — outcome message 为原始业务可读说明，序列化不含内部码。✓

---

## 完整 PR 组合行为复核

### Topic 1-7 closure

初轮 MiMo / DS review 已逐一验证 P0-A 到 P2-C（历史 baseline sub-WU）+ R01-R12 目标实现。以下按 controller discussion 定义的权威 Topic 逐一确认 fix delta 未回归且均 closed：

| Topic | 定义 | Fix delta 影响 | 状态 |
|-------|------|---------------|------|
| Topic 1 | Doc source/directory hard product limits removal；保留 ToolTruncateSpec/fetch_more；Issue #177 边界 | 未涉及 | Closed ✓ |
| Topic 2 | Web private/custom port default allow；DNS pin/peer proof default off；proxy warning 不默认 ban；browser/private 解耦；owner-scoped budgets；challenge/diagnostics v2 保留；storage-state lifecycle 删除且 #178 承接 | 未涉及；Web 默认 allow 裁决保持 | Closed ✓ |
| Topic 3 | Host LLM-safe projection 删除下游 normalized/safe-argument repair 和字段名黑名单；只保留内部 canonicalization；从源头改 prompt/schema/projection | 本 fix 只加固 owner boundary fail-closed，未增加下游 normalization/shim | Closed ✓ |
| Topic 4 | OpaqueEvidenceRef 仅 internal provenance；opaque/misspelled/internal ref 不得作为业务来源进入 RunInput/Memory/Compact/LLM trace；不新增 BusinessSource | 未涉及 | Closed ✓ |
| Topic 5 | Wait provider mode 进入 tool_discovery；runtime policy 进入 host_runtime；scene/profile 不拥有；observation timeout 撤销 late publication + diagnostic + release/backoff，不 LOST；typed lost 或 Host durable evidence 才 LOST | 未涉及 | Closed ✓ |
| Topic 6 | Fins 单一 batch authority；完整 source 一次发布；typed provenance/errors；storage-own revision/snapshot；收窄 financial/XBRL；单一 direct terminal validator；HKEX cumulative rowRange；containment/internal key | 未涉及 | Closed ✓ |
| Topic 7 | CLI upload script 真实跨平台实现；删 placeholder Web/WeChat/render；init 对齐 OLD/current schema；补 prompt/overwrite/reset 安全；不越界 Issue #142/#151 | 未涉及 | Closed ✓ |

本 fix 仅改动 `dayu/host/tool_runtime.py` 的 `_governed_failure_outcome()` fail-closed 逻辑和对应测试，不涉及 Topic 1-7 任何模块边界。✓

### Topic 8-9 no-code

- Topic 8（Engine generic exception message）：no-code decision，未改动。
- Topic 9（统一 tool authorization framework）：no-code decision，未实施、未偷带。

✓

### R01-R12 / Windows gates

初轮 review 确认 R01-R12 全部 closed，R11/R12 Windows CI 均 success。本 fix 不影响。✓

### Security / deferred ledger

- Security ledger 8 项全部 PASS（初轮 MiMo / DS 独立确认）。
- Deferred issues：#142、#151、#175、#177、#178、#147 各自 owner 保持。
- 本 fix 不新增 deferred、不偷带 deferred 能力。✓

---

## Finding / New / Backflow / Blocker / Open / Unclassified / Pending Ledger

| Category | Count | Detail |
|----------|-------|--------|
| Findings | 0 | PR179-DR-F01 已从 root cause 关闭，无新 finding |
| New findings | 0 | — |
| Backflow findings | 0 | — |
| Blockers | 0 | — |
| Open findings | 0 | — |
| Unclassified residuals | 0 | — |
| Pending | 0 | — |
| Deferred with owner | 6 | #142, #151, #175, #177, #178, #147 |

## PR179-DR-F01 最终状态

**CLOSED** — root cause 已修复，fail-closed 传播已验证，无下游 shim，合法路径不回归，内部码不泄漏到 LLM-facing 通道。

## Correct Next Gate

1. Controller 裁决本 re-review。
2. 若双路 re-review 均无新 accepted finding，形成 exact accepted PR review commit。
3. Non-force push 当前 branch。
4. Final closeout artifact / control doc / accepted closeout commit 与 push。

不得 merge、mark-ready、delete branch 或关闭 deferred issues。
