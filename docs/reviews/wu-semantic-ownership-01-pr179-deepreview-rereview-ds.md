# WU-SEMANTIC-OWNERSHIP-01 PR179 deepreview re-review — AgentDS

## Gate 与证据锁

- **Gate**: Draft PR 179 第二路完整 PR re-review（Controller adjudication → AgentCodex fix → Controller validation → 本 re-review）。
- **PR**: `https://github.com/noho/dayu-agent-r/pull/179`，base `main`，reviewed HEAD `86174133b51f2e34cac5d93c4128d9b40a8c48b8`。
- **Scope**: 完整 PR diff（base main → HEAD `86174133`）+ 当前未提交 fix delta + 本 gate artifacts。
- **AgentCodex fix artifact**: `docs/reviews/wu-semantic-ownership-01-pr179-deepreview-fix-codex.md`，SHA-256 `b4d0f19c8330017f969ad5d3bfff043e3bfc969ebaec30f33e3e8ced6e0c7d4e`（由 Controller validation 锁定，本次不重算）。
- **Controller validation artifact**: `docs/reviews/wu-semantic-ownership-01-pr179-deepreview-fix-controller-validation.md`，SHA-256 由 Controller 锁定，本次不重算。
- **初轮 AgentDS artifact**: `docs/reviews/wu-semantic-ownership-01-pr179-deepreview-ds.md`，SHA-256 `e7953063af1e32155df62c469e330d7371d5a70606f9d5b18946db0a5d7c1a8e`。
- **初轮 AgentMiMo artifact**: `docs/reviews/wu-semantic-ownership-01-pr179-deepreview-mimo.md`，SHA-256 `6e03d5a32f48facf4d0988d49d0c82f2219a64a6e37c8b39888bb0a3f744a085`。
- **Controller adjudication**: `docs/reviews/wu-semantic-ownership-01-pr179-deepreview-controller-adjudication.md`，SHA-256 `1bf581def05e4e4fd080d62ab4bd4cf1826c56cbd7e5a6ca021299dc0371b3b9`。
- **本 artifact**: `docs/reviews/wu-semantic-ownership-01-pr179-deepreview-rereview-ds.md`。

## Binary diff identity 验证

| 项目 | 期望值 | 实际值 | 匹配 |
|------|--------|--------|------|
| `dayu/host/tool_runtime.py` SHA-256 | `f376dfe547f5f72c314fe018b28f49b5bdf504476b72484602eed3ba04ec28ea` | `f376dfe547f5f72c314fe018b28f49b5bdf504476b72484602eed3ba04ec28ea` | ✅ |
| `tests/host/test_toolruntime_executor.py` SHA-256 | `d73a69e900baaf619004c061f18c62288783026ea8258fb699ab9370cc80c8b3` | `d73a69e900baaf619004c061f18c62288783026ea8258fb699ab9370cc80c8b3` | ✅ |
| `git diff --binary` SHA-256 | `810bfb9cc01728cc98725177b613b29cc6483be22f5d833a1fcbf627d8aab6ba` | `810bfb9cc01728cc98725177b613b29cc6483be22f5d833a1fcbf627d8aab6ba` | ✅ |

验证命令：`git diff --binary -- dayu/host/tool_runtime.py tests/host/test_toolruntime_executor.py | shasum -a 256`。

## PR179-DR-F01 关闭验证

### Root cause 修复路径逐行走读

**修复前直接证据（初轮 Finding 016）**：

1. `_TOOL_RUNTIME_GOVERNED_ERROR = "host_tool_governed_error"`（旧 `tool_runtime.py:240`）
2. `_governed_failure_outcome()` 使用 `policy_decision.message or _TOOL_RUNTIME_GOVERNED_ERROR` 构造 outcome message
3. 当非 `ALLOW` decision 的 `message=None` 时，内部码 `"host_tool_governed_error"` 被写入 `ToolFailedOutcome.message`
4. 该 outcome 可沿 `accepted_tool_outcome_json → EventLog → project_accepted_tool_result → AcceptedToolEvidenceLLMMaterial.result_text → render_accepted_tool_evidence_for_llm()` 进入 LLM 上下文

**修复后逐行验证**：

1. **`_TOOL_RUNTIME_GOVERNED_ERROR` 已删除**（`tool_runtime.py:240` 行已不存在该常量定义）
   - 全仓库扫描 `host_tool_governed_error`：生产代码零命中
   - 仅 `tests/host/test_toolruntime_executor.py:144` 保留 `_LEGACY_GOVERNED_FAILURE_MESSAGE = "host_tool_governed_error"` 作为测试断言用的验证哨兵

2. **`_governed_failure_outcome()` 在构造 outcome 前调用 `_validate_policy_decision_fields()`**（`tool_runtime.py:7216`）
   - `_validate_policy_decision_fields()`（`tool_runtime.py:5431-5452`）：
     - `kind` 必须为 `ToolPolicyDecisionKind`（line 5439-5440）
     - `reason_code`/`message` 不能为空白字符串（line 5441-5446，经 `_require_optional_non_empty_text` 验证 `value.strip() == ""` 则 `ValueError`）
     - `ALLOW` 不得携带 reason 或 message（line 5447-5449）
     - 非 `ALLOW` 必须同时携带非空 `reason_code` 和非 `None` `message`（line 5451-5452）
   - 覆盖矩阵：
     - `message=None` + 非 ALLOW → `_require_optional_non_empty_text(None, ...)` 通过（None 合法），但 line 5452 捕获 → `ValueError("governed policy decision requires reason and message")` ✅
     - `message=""` + 非 ALLOW → `_require_optional_non_empty_text("", ...)` → `"".strip() == ""` → `ValueError("policy_decision.message must be non-empty when provided")` ✅
     - `message=" \t "` + 非 ALLOW → `_require_optional_non_empty_text(" \t ", ...)` → `" \t ".strip() == ""` → `ValueError` ✅

3. **ALLOW/REUSE 误入检测**（`tool_runtime.py:7217-7224`）
   - `policy_decision.kind in (ALLOW, REUSE)` → `ValueError("{kind} policy decision cannot produce governed failure")` ✅
   - 此检查在 `_validate_policy_decision_fields` 之后，形成双重防线

4. **message 二次防御**（`tool_runtime.py:7225-7227`）
   - 即使 `_validate_policy_decision_fields` 通过后 message 理论上非 None，仍执行 `message is None` 检查 → `ValueError("governed failure requires policy decision message")` ✅
   - 这是 belt-and-suspenders：类型检查器不知道 `_validate_policy_decision_fields` 的语义保证

5. **outcome message 仅使用已验证的 `policy_decision.message`**（`tool_runtime.py:7228-7232`）
   - `message=message`（line 7230），无 fallback、无 `or` 链 ✅
   - `reason_code` 完全不出现在 outcome message 中 ✅

### Accept/audit 边界防御验证

`ToolAcceptGovernance.__post_init__()`（`tool_runtime.py:592-599`）调用 `_validate_tool_accept_governance()`（line 5340-5357），后者调用 `_validate_policy_decision_fields()`。

- 即使调用者绕过 `_governed_failure_outcome` 直接构造 `ToolAcceptGovernance`，同一 invariant 在 accept/audit 构造边界拒绝 malformed decision ✅
- 测试文件 `test_governed_failure_projection_rejects_missing_readable_message`（test line 2891-2917）同时断言 outcome owner 和 accept governance 双边界 fail closed ✅

### 合法路径不回归验证

所有 `_governed_failure_outcome` 的 9 个 call site 逐个验证：

| # | 行号 | 场景 | message 来源 | 验证 |
|---|------|------|-------------|------|
| 1 | 2868 | batch awaiting suspension | 字面量 `"tool batch stopped after awaiting suspension"` | ✅ |
| 2 | 2964 | DURABLE_MISSING | `_policy_decision_from_duplicate()` → 强制 message 非 None（line 6247-6248） | ✅ |
| 3 | 2967 | 非 ALLOW policy | tool policy decision from policy port | ✅ |
| 4 | 3200 | batch deadline ≤ 0 | `_runtime_timeout_policy_decision()` → `"tool execution timed out after {n} seconds"` | ✅ |
| 5 | 3205 | pre-cancelled context | `_runtime_cancelled_policy_decision()` → `"工具调用在完成前已停止"` 或带 reason | ✅ |
| 6 | 3250 | WaitCancelled | `_runtime_cancelled_policy_decision()` | ✅ |
| 7 | 3260 | WaitTimedOut | `_runtime_timeout_policy_decision()` | ✅ |
| 8 | 3597 | awaiting binding 未配置 | `"该工具当前无法启动后台任务；请改用已可用的工具或稍后重试。"` | ✅ |
| 9 | 3617 | 缺少 external job ref | `"该工具后台任务未返回可跟踪的任务引用；请稍后重试或联系系统维护者。"` | ✅ |

所有 call site 提供的 message 均为业务可读文本。`HINT`/`REQUIRE_JUSTIFICATION`/`HARD_STOP`/`GOVERNED_ERROR` 决策全部走 line 2966-2967 路径，policy decision 由 policy port 产生时已携带合法 message。

### REUSE 路径验证

`_accept_reuse()`（line 3322-3356）是独立成功路径，返回 prior `ToolCompletedOutcome`。REUSE decision 在 line 2951-2952 被正确路由到 `_accept_reuse()`，不经过 `_governed_failure_outcome` ✅。

### 下游无 shim 验证

- 全仓库扫描 `host_tool_governed_error|_TOOL_RUNTIME_GOVERNED_ERROR`：生产代码零命中 ✅
- Host reason-as-message / message fallback 扫描（`policy_decision\.message\s+or|message\s*=\s*policy_decision\.reason_code`）：零命中 ✅
- `dayu/host/` 内无新增 normalization / fallback / blacklist / loose parsing / hasattr / getattr 路径 ✅
- `dayu/host/tool_runtime.py` 内无 `authorization` / `auth_framework` / `permission_schema` / `role` / `capability` / `sandbox` 引用 ✅

### 测试覆盖验证

**Focused adversarial tests**（`tests/host/test_toolruntime_executor.py`）：

| 测试 | 覆盖场景 | 断言 |
|------|---------|------|
| `test_governed_failure_projection_rejects_missing_readable_message[None]` | `message=None` | outcome owner + accept governance 双边界 `ValueError`；旧内部码不出现在异常消息中 |
| `test_governed_failure_projection_rejects_missing_readable_message[]` | `message=""` | 同上 |
| `test_governed_failure_projection_rejects_missing_readable_message[ \t ]` | `message=" \t "` | 同上 |
| `test_governed_failure_projection_rejects_non_failure_decision[ALLOW]` | `ALLOW` 误入 | `ValueError` with kind-specific message |
| `test_governed_failure_projection_rejects_non_failure_decision[REUSE]` | `REUSE` 误入 | `ValueError` with kind-specific message |
| `test_governed_failure_projection_preserves_readable_message` | 合法 GOVERNED_ERROR | outcome message 保留业务文本；序列化结果不含 reason_code 与旧内部码 |

**Aggregate 回归**：

- ToolRuntime owner aggregate: `179 passed` ✅
- Accepted-result projection + Phase 6 integration: `37 passed` ✅
- Focused adversarial: `6 passed, 62 deselected` ✅

### Type / lint 验证

- Targeted pyright: `0 errors, 0 warnings, 0 informations` ✅
- Full pyright: `0 errors, 0 warnings, 0 informations` ✅
- Ruff: `All checks passed!` ✅

---

## 完整 PR 组合行为复核

### Topic 1-7 — Closed

权威 Topic 1-7 定义（来源：controller discussion 与初轮 MiMo Topic Closure Ledger）：

| Topic | 定义 | 初轮验证 | 本次确认（fix delta 不回归） |
|-------|------|---------|---------------------------|
| Topic 1 | Doc source/directory hard product limits removal；保留 ToolTruncateSpec/fetch_more；Issue #177 不越界 | Closed | ✅ |
| Topic 2 | Web private/custom port default allow；DNS pin/peer proof default off；proxy warning/default no-ban；browser/private 解耦；owner-scoped budgets；challenge/diagnostics v2 保留；storage-state lifecycle 删除且 Issue #178 承接 | Closed | ✅ |
| Topic 3 | Host LLM-safe projection 删除下游 normalized/safe-argument repair 和字段名黑名单；只保留内部 canonicalization；从源头改 prompt/schema/projection | Closed | ✅ |
| Topic 4 | OpaqueEvidenceRef 仅 internal provenance；opaque/misspelled/internal ref 不得作为业务来源进入 RunInput/Memory/Compact/LLM trace；不新增 BusinessSource | Closed | ✅ |
| Topic 5 | Wait provider mode 进入 tool_discovery；runtime policy 进入 host_runtime；scene/profile 不拥有；observation timeout 撤销 late publication + diagnostic + release/backoff，不 LOST；typed lost 或 Host durable evidence 才 LOST | Closed | ✅ |
| Topic 6 | Fins 单一 batch authority；完整 source 一次发布；typed provenance/errors；storage-own revision/snapshot；收窄 financial/XBRL；单一 direct terminal validator；HKEX cumulative rowRange；containment/internal key | Closed | ✅ |
| Topic 7 | CLI upload script 真实跨平台实现；删 placeholder Web/WeChat/render；init 对齐 OLD/current schema；补 prompt/overwrite/reset 安全；不越界 Issue #142/#151 | Closed | ✅ |

历史基线 P0-A 到 P2-C（8 个 sub-WU）已在 committed PR 中实现并经过初轮双路 review 验证。本 fix delta 仅修改 `_governed_failure_outcome` 与相关测试，不触及任何 Topic 语义或 P0-A~P2-C 实现。

### Topic 8-9 — No-code

| Topic | 定义 | 状态 | 本次确认 |
|-------|------|------|---------|
| Topic 8 | Engine generic exception message（240-char limit, secret redaction, truncation suffix） | Closed / no-code | 未变化 ✅ |
| Topic 9 | Not implementing unified tool authorization framework | Closed / no-code | 未变化 ✅ |

### R01-R12 / Windows gates

| Round | 目标 | 初轮验证 | 本次确认 |
|-------|------|---------|---------|
| R01-R10 | Full-repository deepreview rounds | Closed | 未变化 ✅ |
| R11 | Upload script + Windows CI (run 29714042683) | success | 未变化 ✅ |
| R12 | Init workflow + Windows CI (run 29714042672) | success | 未变化 ✅ |

### Security ledger

按用户裁决：Config 与 Host internal SQLite/EventLog 属 trusted-local domain，允许存在 API key/headers。Tool Trace/audit/public/log/LLM/review evidence 禁止 credential/header 明文。

| # | 项目 | 初轮状态 | 本次确认 |
|---|------|---------|---------|
| S1 | Credential/header plaintext in Tool Trace/audit/public/log/LLM/review evidence | PASS — 无泄漏 | 未变化 ✅ |
| S2 | API key/headers in Config + Host internal SQLite/EventLog | PASS — trusted-local domain，允许 | 未变化 ✅ |
| S3 | Provider credential in runner-call manifest | PASS — hot atoms 不含 API key | 未变化 ✅ |
| S4 | Cancellation token exposure to LLM | PASS — typed durable state, not LLM-facing | 未变化 ✅ |
| S5 | Unified authorization framework not implemented | PASS — explicitly no-code boundary | 未变化 ✅ |
| S6 | Gemini low-budget quota | EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING | 未变化 ✅ |
| S7 | Web egress default allow policy | PASS — product decision, controlled by `tool_discovery.json` | 未变化 ✅ |

### Deferred ledger

| # | 项目 | Owner | 本次确认 |
|---|------|-------|---------|
| D1 | Issue 142 (migration) | Issue 142 | 未变化 ✅ |
| D2 | Issue 151 | Issue 151 | 未变化 ✅ |
| D3 | Issue 175 | Issue 175 | 未变化 ✅ |
| D4 | Issue 177 | Issue 177 | 未变化 ✅ |
| D5 | Issue 178 | Issue 178 | 未变化 ✅ |
| D6 | Web/WeChat/render trackers | Respective trackers | 未变化 ✅ |

### 未偷带能力验证

| 禁止项 | 验证 | 状态 |
|--------|------|------|
| 统一 tool authorization framework | `grep -rn "authorization\|auth_framework\|permission_schema\|role.*capability\|sandbox" dayu/host/tool_runtime.py` → 零命中 | ✅ |
| Issue 142/151/175/177/178 能力 | fix delta 仅修改 `_governed_failure_outcome` 与相关测试，不触及这些 issue 的 owner | ✅ |
| WeChat/Web/render tracker 能力 | 同上 | ✅ |
| Web 默认 allow 裁决变更 | `tool_runtime.py` 不包含 Web egress/discovery 逻辑 | ✅ |

---

## Findings

未发现实质性问题。

PR179-DR-F01 的修复从 root cause 关闭，满足 Controller adjudication 定义的全部不变量：

1. ✅ 删除 `_TOOL_RUNTIME_GOVERNED_ERROR` 常量；全仓库生产代码零引用
2. ✅ 内部 error code 不得充当 LLM-readable message 的 fallback
3. ✅ Malformed governed decision 在 Host ToolRuntime owner boundary fail closed（`ValueError`）
4. ✅ `ALLOW` decision 不得误用 governed-failure projection
5. ✅ `REUSE` decision 不得误投影为 failure（走独立 `_accept_reuse` 成功路径）
6. ✅ Reason code 保留供内部 governance/digest/audit/diagnostic 使用，不替代业务 message
7. ✅ 所有已有合法 governed outcomes 的外部行为保持不变（9 个 call site 逐行验证）
8. ✅ Owner-level adversarial tests 覆盖 `message=None`/`""`/`" \t "` 以及 `ALLOW`/`REUSE` 误入
9. ✅ Accept/audit 构造边界（`ToolAcceptGovernance.__post_init__`）提供防御纵深
10. ✅ 下游无 fallback/normalization/blacklist/shim
11. ✅ 未引入统一 tool authorization framework
12. ✅ Config/Host internal SQLite/EventLog trusted-local domain 保持

---

## Finding / New / Backflow / Blocker / Open / Unclassified / Pending Ledger

| Category | Count | Detail |
|----------|-------|--------|
| **Findings** | **0** | 无新增 actionable finding |
| **New** | **0** | — |
| **Backflow** | **0** | — |
| **Blocker** | **0** | — |
| **Open** | **0** | PR179-DR-F01 已关闭 |
| **Unclassified** | **0** | — |
| **Pending** | **0** | — |

### PR179-DR-F01 状态

**CLOSED** — 修复从 root cause 关闭，满足全部不变量，经 Controller 独立代码验证与本 re-review 逐行复核。MiMo re-review artifact 已存在（`docs/reviews/wu-semantic-ownership-01-pr179-deepreview-rereview-mimo.md`），双路 re-review 均无新增 finding。等待 Controller 对本轮双路 re-review 的最终 adjudication。

---

## Correct Next Gate

**Controller adjudication**（对本 re-review 及 MiMo re-review 的 accept/reject/defer 裁决）。

裁决通过后按序执行：

1. Controller 选定 exact accepted PR review commit hash
2. Non-force push current branch 到 remote
3. Controller 产出 final closeout artifact，更新 control doc
4. Accepted closeout commit 与 push

明确禁止：

- 在 Controller final closeout 前 merge、mark ready、delete branch 或关闭 deferred issues
- 本 artifact 不授权任何 push/merge/closeout 动作

---

*Re-review by AgentDS。完整走读 production/test diff、全仓库 scan、9 个 call site 逐行验证、6 个对抗测试逐断言验证、179 ToolRuntime owner aggregate + 37 downstream projection 回归通过。Commit range: base `main`..HEAD `86174133` + uncommitted fix delta。*
