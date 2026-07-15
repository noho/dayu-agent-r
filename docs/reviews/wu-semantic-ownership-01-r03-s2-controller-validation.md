# WU-SEMANTIC-OWNERSHIP-01 / R03-S2 Controller Validation

## 0. Gate 与结论

| 项目 | 值 |
| --- | --- |
| umbrella work unit | `WU-SEMANTIC-OWNERSHIP-01` |
| remediation / slice | `R03 / R03-S2` |
| baseline | `fe497da395e8511c684945b9282894fe322a90df` |
| implementation artifact | `docs/reviews/wu-semantic-ownership-01-r03-s2-implementation-codex.md` |
| Controller verdict | `PASS / READY_FOR_DUAL_CODE_REVIEW` |
| accepted implementation finding | `0` |

R03-S2 的动机与实现边界成立：accepted arguments 已由 ToolRuntime accept boundary 形成 canonical JSON 与 digest，下游按字段名重写、隐藏或降级会让同一业务事实产生多套语义。当前实现删除该下游 repair，而没有增加替代 normalization；LLM-facing schema 缺口只在具体 producer owner 修复。

本结论只授权 R03-S2 的 AgentMiMo / AgentDS 完整双路 code review。它不接受本 slice、不授权 commit、R03-S3、aggregate、Issue 177/178、统一 tool authorization framework 或其它 deferred scope。

## 1. Owner 与实现复核

Controller 逐文件读取了 production、test、README diff，并确认：

1. `accepted_result_projection.py` 删除 `LIMITED_SIGNAL`、字段名 blacklist、`arguments_summary_unsafe` 与 limited fallback；缺 producer semantic query 时只机械展示 bounded canonical arguments。
2. `tool_trace.py` 删除 readable redaction 与 descriptor ref/digest placeholder。inline 和 accepted-result request summary 展示 exact arguments；internal hot row 仍可持有完整性 digest。没有 loose descriptor resolver。
3. accepted plan §11.3 item 8 与 `R03-PLAN-F06` 明确把 `TOOL_CALL_REQUESTED` descriptor 的 strict row resolution、exact args/query 和 corruption fail-close 放在 R03-S3。S2 §10.1 的 descriptor 要求是 ref/digest/placeholder 不进入 readable summary；当前 S2 没有漏实现或提前越界。
4. `fetch_more`、`fetch_web_page.url`、Fins `ticker/document_id` 的说明分别改在 Host framework、Web producer、Fins read producer；名称、参数名、required、enum、结果、citation 与执行行为不变。Fins 的九个 ticker schema 与八个 document-id schema各自复用唯一 helper。
5. `dayu.runtime.json_redaction` 在唯一调用方删除后整体删除，package 概览同步删除；没有 re-export、wrapper、lazy import 或替代 helper。
6. tests 断言合法 `file_path`、`scope_token`、password-like 业务名称原值可见，Tool Trace exact args 与 descriptor readable/internal 分界，以及三个 producer schema 的 exact contract；没有 fixture 迫使生产保留兼容分支。
7. Host README 与 tests README 的修改均命中各自职责；根 README、`dayu/README.md`、Fins README、config README 无职责内用户工作流或架构变化，保持 no-diff 正确。

## 2. 独立验证

Controller 在当前 working tree 独立执行并得到：

| 验证 | 结果 |
| --- | --- |
| accepted plan §10 第一组精确测试 | `519 passed, 1 skipped, 3 warnings` |
| §10 no-diff 回归 | `171 passed, 3 warnings` |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| coverage | `fins_tools.py 80%`、`accepted_result_projection.py 94%`、`tool_runtime.py 88%`、`tool_trace.py 88%`、`runtime/__init__.py 100%`、`web_tools.py 81%` |
| default Ruff（Web 之外的修改 Python 文件） | `All checks passed!` |
| Web default Ruff | 当前与 baseline `fe497da3` 均为同一 `13 x F401 + 1 x F841`；仅 URL schema 插入导致后续行号平移，零新增/扩散 |
| `git diff --check` | PASS |
| prompt inventory | 当前 `37`，与 accepted baseline 集合闭合 |
| executable constructor inventory | 当前 `114`，与 accepted baseline 集合闭合 |
| R01 mandatory handoff | `5+5+5+5+10=30` 行全部保留并有 disposition |

三条 edgartools deprecation warning 与本 slice 无关；既有 skip 由原测试环境条件拥有，未被本实现新增或放宽。

## 3. Source / propagation 裁决

- `llm_safe_replay_arguments`、`arguments_summary_unsafe`、`unsafe_argument`、`safe_arguments` 在 production 无命中；唯一 `accepted_arguments_source_digest` 命中是 S1 owner 测试中的 absence assertion。
- Host/runtime/tests 已无 `redact_sensitive_json_fields`、`json_redaction` 或 `JSON_REDACTION_MARKER`。Engine provider diagnostic 的 `_SENSITIVE_KEY_FRAGMENTS` 是独立安全诊断 owner，保持 no-diff 正确。
- `_INTERNAL_SOURCE_REF_KINDS` 与 `_readable_ref_text` 只留在 accepted plan 明确指定的 R03-S3 opaque source owner；不得在 S2 删除。
- prompt assets `37`、真实 ToolDefinition/Agent message constructor paths `114` 和 R01 handoff `30` 均已逐项审计；没有发现需要在 S2 owner 修改而被误标 no-diff 的当前语义源。
- 未实现统一 authorization、Issue 177/178、R03-S3 public smoke、aggregate 或 deferred producer scope；现有 allowed paths、containment、Web DNS/peer/budget/challenge 等安全 owner 未被删除。

## 4. Residual 与下一 gate

| 项目 | 裁决 / owner |
| --- | --- |
| opaque source guessing / internal refs propagation | R03-S3 accepted owner；当前必须保留待下一 slice 关闭 |
| descriptor strict resolution + exact readable args/query | R03-S3 accepted owner；S2 已只关闭 readable ref/digest placeholder |
| Web 14 项 default Ruff baseline | baseline observation，不是本 slice finding；用户禁止借 schema-only diff 修改无关代码 |
| R03 public Doc/Web/Fins smoke | aggregate hard gate；不得用本 slice 测试替代 |

下一 gate 是 AgentMiMo 与 AgentDS 对 baseline `fe497da3..working tree` 的 R03-S2 完整双路 code review。所有后续 accepted findings 必须交 AgentCodex 修复并完整 re-review；即使 accepted finding 为零，也按本 WU 已采用的 mandatory zero-change record 和 final re-review 流程推进后才能接受本 slice。
