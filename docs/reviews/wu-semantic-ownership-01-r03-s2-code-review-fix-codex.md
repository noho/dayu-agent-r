# WU-SEMANTIC-OWNERSHIP-01 / R03-S2 Code Review Fix — AgentCodex Zero-Change Disposition

## 0. Gate identity 与结论边界

| 项目 | 值 |
| --- | --- |
| umbrella work unit | `WU-SEMANTIC-OWNERSHIP-01` |
| remediation / slice | `R03 / R03-S2` |
| gate | `code-review fix` |
| record kind | mandatory zero-change disposition；不是新 WU、新 slice 或新 implementation |
| baseline / 当前 HEAD | `fe497da395e8511c684945b9282894fe322a90df` |
| accepted code finding | `0` |
| 唯一写入 | `docs/reviews/wu-semantic-ownership-01-r03-s2-code-review-fix-codex.md` |
| product / test / README change | `0` |
| commit / push | 均未执行 |
| 禁止推进项 | 不接受 R03-S2，不进入 R03-S3 或 aggregate |
| completion status | `READY_FOR_CONTROLLER_VALIDATION_AND_DUAL_FINAL_RE_REVIEW` |

本 gate 的动机成立，但正确结果是零代码修复：Controller 已裁决 accepted finding 为零。为了回应一个事实前提错误的 review finding 而删除既有字段，会在没有 owner 决策的情况下改写 accepted Tool Trace contract；这不是修复 root cause，而是制造 semantic ownership drift。因此本轮只持久化 no-fix disposition 与零变更证据。

## 1. 权威输入与 gate scope

本 gate 完整读取并以如下输入为裁决依据：

1. `AGENTS.md`
2. `docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md`
3. `docs/reviews/wu-semantic-ownership-01-r03-s2-implementation-codex.md`
4. `docs/reviews/wu-semantic-ownership-01-r03-s2-controller-validation.md`
5. `docs/reviews/wu-semantic-ownership-01-r03-s2-code-review-mimo.md`
6. `docs/reviews/wu-semantic-ownership-01-r03-s2-code-review-ds.md`
7. `docs/reviews/wu-semantic-ownership-01-r03-s2-code-review-controller-adjudication.md`

scope 只允许记录 accepted finding ledger、no-fix/deferred/retained-security disposition、受保护目标前后摘要及本 artifact 的静态 diff 检查。production、tests、README、design、accepted plan、Controller-owned `docs/host/issues-implementation-control.md` 与所有既有 artifacts 均为只读。

## 2. Finding ledger

### 2.1 `S2-CR-F01` — `rejected-with-direct-evidence / no-fix`

Controller 对 MiMo `S2-CR-F01` 的裁决精确如下：

1. **事实前提错误**。当前
   `rg -n 'query_state' dayu/host/tool_trace.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py`
   只有 `dayu/host/tool_trace.py::_tool_request_summary_from_tool_result` 的 accepted-result summary 一处 production 命中；`_tool_request_summary_from_payload` 的 payload summary 没有 `query_state`，两个测试文件也没有 reviewer 所称的 `query_state` 断言。
2. **accepted plan 明确保留 query-source provenance 和明确状态**。§4.6 固定 query 的合法来源为 producer `semantic_query_text` 或 exact canonical accepted arguments；§4.7 要求 `trace_summary.tool_request` readable fields 保留 query、exact accepted arguments/text 与“明确状态”。
3. **§7.3 只删除 `LIMITED_SIGNAL`**、字段名 blacklist、limited-query branch 与对应 diagnostic；它没有删除 `AcceptedToolResultQueryState`，也没有删除剩余的 `semantic_query | arguments_summary` 来源状态。
4. 该值描述 readable query 来自 producer query 还是 accepted arguments summary，是 query projection provenance，不是 Run、Attempt、wait、poll、dispatch、Engine 或 Host governance 状态，也没有被伪装为财报事实。
5. 无 owner 决策地删除该字段会削弱 accepted plan contract，并在 S2 外重定义 Tool Trace summary schema。若未来决定不展示 query provenance，必须先修改 design / accepted plan owner contract，不能由本 code-review fix gate 静默改写。

最终状态：`rejected-with-direct-evidence / no-fix`。不修改 code，不修改 tests，不修改 README。

### 2.2 Accepted finding closure

- accepted finding：`0`
- required product fixes：`0`
- finding fix/re-review 状态：没有 accepted finding，因此不存在可标记为“已修复/部分修复/未修复”的 accepted item；`S2-CR-F01` 是被直接证据否决的 no-fix observation，不得伪装为已修复。
- blocking open question：`0`

## 3. Reviewer dispositions

### 3.1 AgentDS

AgentDS 返回 `PASS — 零 material S2 finding`，finding 数为 `0`、blocking question 为 `0`。该 review 确认：blacklist、`arguments_summary_unsafe` limited branch、Tool Trace readable redaction 与 `dayu.runtime.json_redaction` 均已删除，没有 replacement normalization；三个 schema 缺口只在 producer owner 修复；测试、coverage、pyright、README 与安全边界满足 S2 contract。

DS 末尾“可进入 R03-S3”只是 reviewer 表述，不具备 gate authority。Controller 已明确要求先完成本 zero-change record、Controller validation、MiMo/DS dual final re-review、Controller final adjudication及 accepted local commit；本 artifact 不宣布 S2 accepted，也不进入 S3。

### 3.2 No-fix / deferred ledger

| 项目 | disposition | owner / destination |
| --- | --- | --- |
| MiMo `S2-CR-F01 query_state` | rejected-with-direct-evidence / no-fix | query projection provenance；未来若改须先改 design / accepted plan |
| `test_tool_trace_queries.py` 的 runner reconstruction `limited_signal` diagnostic | no-fix；不同 semantic owner | internal runner-input query diagnostic，不是 accepted arguments blacklist |
| descriptor strict row resolution、exact descriptor args/query、corruption fail-close | deferred；本 gate 不修、不建 loose resolver | accepted R03-S3 |
| opaque source guessing、internal refs propagation、`source_locator_refs` 删除 | deferred；S2 不越界 | accepted R03-S3 |
| `business_source_text/state` 与 non-optional shared material | deferred | accepted R03-S3 |
| R03 public Doc/Web/Fins smoke | deferred | aggregate hard gate；不得以当前 tests 替代 |
| Web default Ruff 13×F401 + 1×F841 | rejected as S2 finding / no-fix | 与 baseline `fe497da3` 同源且零扩散；不创建新 owner/issue |
| DS full Host run 的 scheduler 单节点失败 | rejected as S2 finding / no residual | 非 S2 调用链；Controller 独立复跑同一 node 为 `1 passed` |
| DS 关于当前 producer 不写 opaque refs 的可达性观察 | 不作为裁决前提 | S3 仍按 accepted propagation contract 完整关闭，不弱化 scope |
| Issue #177 / #178 | no-fix / out of scope | 既有 issue owner；不进入 R03-S2 |
| unified tool authorization framework | no-fix / non-goal | 不进入 R03 |

### 3.3 Retained security

以下独立安全 owner 均保留且本 gate 零改动：

- Engine provider diagnostic 的 `_SENSITIVE_KEY_FRAGMENTS`；
- runtime diagnostic text 与 compaction diagnostic 的敏感值脱敏；
- Web diagnostic、安全 DNS/peer/budget/challenge 边界；
- Doc `allowed_paths`；
- Fins filesystem/storage containment；
- Host durable Tool Trace `file_lock`；
- internal hot/cold rows 所需的 id/ref/digest 诊断事实。

本 gate 没有新增 LLM-safe normalization、compatibility、BusinessSource、统一 authorization，也没有实现 Issue #177/#178。以上 deferred 与 retained 项均有明确 owner/destination；无 unclassified residual risk。

## 4. Protected target 前后摘要

### 4.1 Protected target 清单

本 gate 将以下 21 个路径作为受保护目标。集合覆盖全部 R03-S2 production/tests/README diff、implementation / Controller validation、两份 code review、Controller adjudication，并额外保护 accepted plan：

```text
dayu/fins/tools/fins_tools.py
dayu/host/README.md
dayu/host/accepted_result_projection.py
dayu/host/tool_runtime.py
dayu/host/tool_trace.py
dayu/runtime/__init__.py
dayu/runtime/json_redaction.py
dayu/tools/web/web_tools.py
docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md
docs/reviews/wu-semantic-ownership-01-r03-s2-code-review-controller-adjudication.md
docs/reviews/wu-semantic-ownership-01-r03-s2-code-review-ds.md
docs/reviews/wu-semantic-ownership-01-r03-s2-code-review-mimo.md
docs/reviews/wu-semantic-ownership-01-r03-s2-controller-validation.md
docs/reviews/wu-semantic-ownership-01-r03-s2-implementation-codex.md
tests/README.md
tests/fins/test_fins_storage_provider.py
tests/host/test_accepted_result_projection.py
tests/host/test_memory_projection.py
tests/host/test_tool_trace_projection.py
tests/host/test_toolruntime_truncation_fetch_more.py
tests/tools/web/test_web_tools_provider.py
```

明确排除：本次新增 artifact，以及 Controller-owned `docs/host/issues-implementation-control.md`。

### 4.2 Canonical digest 方法

- content records 按上面固定的 C-locale 路径顺序生成：存在文件为
  `PRESENT<TAB>path<TAB>byte_count<TAB>sha256(file)<LF>`；已删除/不存在文件为
  `ABSENT<TAB>path<TAB>0<TAB>-<LF>`。对完整 record stream 再取 SHA-256。
- status/path records 对同一顺序逐项运行
  `git status --porcelain=v1 --untracked-files=all -- <path>`，记录
  `STATUS<TAB>XY|??|CLEAN<TAB>path<LF>`；对完整 record stream 再取 SHA-256。
- `dayu/runtime/json_redaction.py` 在 content records 中固定为 `ABSENT`，在 status/path records 中为 tracked deletion ` D`；这能区分预期删除与路径遗漏。

### 4.3 写前 / 写后结果

| 摘要 | 写前 | 写后 | 比较 |
| --- | --- | --- | --- |
| protected content aggregate SHA-256 | `2fe691991f9bfb4d16498712b62904a2bd0561890579a49b1355068875fc27ee` | `2fe691991f9bfb4d16498712b62904a2bd0561890579a49b1355068875fc27ee` | identical；protected content 零变化 |
| protected status/path aggregate SHA-256 | `036a65637fe7c1fe7fa4bf3260c8b142e64250ebc9bb326e5ec9b13f5b26a9c5` | `036a65637fe7c1fe7fa4bf3260c8b142e64250ebc9bb326e5ec9b13f5b26a9c5` | identical；protected status/path 零变化 |

写前完整 working-tree status 共 `21` 条，SHA-256 为
`c22595219550f9848496a845e520aab319845cb263f3d2a33e93cc009a32673b`。写后完整 status 为 `22` 条，SHA-256 为
`20d67865f336131d8e203705656988fbf4ce0e2143e9f847a6c54b6b074dccde`；排除本 artifact 后仍为 `21` 条，SHA-256 恢复为
`c22595219550f9848496a845e520aab319845cb263f3d2a33e93cc009a32673b`。因此 working-tree status delta 只有新增本 artifact，protected targets 零变化。

## 5. Validation

### 5.1 本 gate 静态检查

| 检查 | 结果 |
| --- | --- |
| 本 artifact `git diff --no-index --check /dev/null <artifact>` | exit `1`（表示新文件存在 diff），stdout/stderr 无 whitespace 诊断；PASS |
| tracked working tree `git diff --check` | exit `0`、无输出；PASS |
| protected content/status digest 前后比对 | 两个 SHA-256 均 identical；PASS |
| working-tree status delta | `21 -> 22`；排除本 artifact 后行数与 SHA-256 均恢复写前值；PASS |

### 5.2 Product tests / pyright 决定

本 gate 是零产品变化 disposition，不重跑既有 product tests、coverage 或 pyright；重跑不会增加对本轮唯一 Markdown 写入的产品正确性证据。引用的三方已通过证据为：

1. AgentCodex implementation handoff：accepted plan §10 两组分别为
   `519 passed, 1 skipped, 3 warnings` 与 `171 passed, 3 warnings`；full pyright 为
   `0 errors, 0 warnings, 0 informations`；所有修改 production file 的逐文件 coverage 达标。
2. Controller validation 独立复跑：同样得到 `519 passed, 1 skipped, 3 warnings`、
   `171 passed, 3 warnings`、full pyright 零错误，并独立确认逐文件 coverage、Ruff baseline 对照、prompt `37`、constructor `114` 与 R01 handoff `30` 全部闭合。
3. AgentDS 独立复跑：同样得到两组 pytest 结果、full pyright 零错误和全部修改 production file coverage 达标，并返回零 material S2 finding。

MiMo 同时确认 S2 主要 owner contract、schema owner、测试与 retained-security 边界；其唯一 finding 已由 Controller 按 §2.1 的直接证据否决，不能触发代码或测试修改。

## 6. Changed files、docs 与 residual

- 本 gate changed file：仅本 artifact。
- production、tests、README、design、accepted plan、control、既有 artifacts：零修改。
- README decision：零产品/测试行为变化，不触发任何 README 更新；且用户明确禁止修改 README。
- residual：R03-S3 与 aggregate 项均按 §3.2 保留既有 owner/destination；本 gate 没有新 residual，也没有未分类风险。

## 7. Completion status

本 zero-change fix/disposition record 完成后，结论只能是：

**ready for Controller validation / dual final re-review**。

这不是 R03-S2 accepted，不是 accepted local commit authorization，也不授权进入 R03-S3 或 aggregate。

Artifact path：`docs/reviews/wu-semantic-ownership-01-r03-s2-code-review-fix-codex.md`
