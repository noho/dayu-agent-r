# WU-SEMANTIC-OWNERSHIP-01 / R03 Plan Fix — AgentCodex

## 0. Gate、边界与结论

| 项目 | 值 |
| --- | --- |
| umbrella work unit | `WU-SEMANTIC-OWNERSHIP-01` |
| remediation | `R03 — accepted call 语义与 opaque provenance 的单一 LLM 投影` |
| 当前 gate | plan review fix only；未进入 implementation |
| 修订目标 | `docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md` |
| controller input | `docs/reviews/wu-semantic-ownership-01-r03-plan-review-controller-adjudication.md` |
| review inputs | `docs/reviews/wu-semantic-ownership-01-r03-plan-review-ds.md`、`docs/reviews/wu-semantic-ownership-01-r03-plan-review-mimo.md` |
| 本轮允许写入 | 上述 plan + 本 fix artifact |
| 本轮明确未做 | production/tests/README/design/control/prior review 修改、implementation、commit、push |
| 结论 | `R03-PLAN-F01..F08` 均已在 owner-correct plan 位置关闭；等待 AgentMiMo / AgentDS 完整 re-review |

三份输入均已完整读取。修订没有改变 Topic 3/4 产品裁决、三个 slice、真实 Doc/Web/Fins smoke、R01 handoff 或 deferred boundary。

## 1. Accepted finding closure

| accepted ID | 修订后的精确 plan 位置 | 关闭内容 | 状态 |
| --- | --- | --- | --- |
| `R03-PLAN-F01` | §4.2 writer、§4.4 sequencing、§4.5 corruption、§6.3 item 4、§6.4 | 明确 shared writer 只构造 request；`append_event(...).row` 产生真实 sequence；request -> awaiting -> run/attempt/wait/idempotency 全部同 transaction；same-digest/existing-row replay与任一后续失败 rollback contract及测试 | 已修复 |
| `R03-PLAN-F02` | §4.6 source contract、§11.3 item 2、§11.4 | `_source_projection(raw_outcome, diagnostics)` 直接接收 `_result_payload` 已 digest-check 的当前 raw outcome；按 `accepted_tool_outcome_json` exact path读取并 canonical-render整个 citation object；测试必须用真实 codec构造 | 已修复 |
| `R03-PLAN-F03` | §4.7 Tool Trace、§11.3 item 8、§11.4 | readable result exact mapping 为 `business_source_text=projection.source.text`、`business_source_state=projection.source.state.value`；复用现有 source state，不新增 enum/parser，diagnostic 不进入业务来源 | 已修复 |
| `R03-PLAN-F04` | §4.5、§4.6 renderer、§11.3 items 4/6/7/8、§11.4 | renderer 改为 non-optional；RunInput/Memory/Compact/LLM-ready Trace 缺 material统一抛 `HostDurableError`；禁止 skip、fallback、limited signal、局部 catch/recovery | 已修复 |
| `R03-PLAN-F05` | §4.2 atom mapping、§6.3 items 2/3、§6.4 | ordinary 从 `ToolAcceptCall.tool_identity_digest`、awaiting 从 `ToolAwaitingAcceptCandidate.tool_identity_digest` 原样映射；builder 不重算；waiting 三个私有 helper 的唯一调用闭集和删除闭集已记录 | 已修复 |
| `R03-PLAN-F06` | §4.5、§4.7、§11.3 item 8、§11.4 | request-event readable Trace 通过 `read_event_by_id` + strict `tool_call_request_atoms` 解析 exact inline/descriptor args/query；损坏抛 `HostDurableError`；删除 internal placeholder/ref/digest 输出 | 已修复 |
| `R03-PLAN-F07` | §7.3、§10.2、§13.1、§13.3 | `dayu/runtime/__init__.py` 仅删除 json-redaction 对应 module docstring 项，无 export/runtime logic 改动；保留 `>=80%`，由现有 runtime import-boundary test执行单文件 coverage | 已修复 |
| `R03-PLAN-F08` | §11.3 items 3/4、§11.4、§13.5 | sentinel matrix 新增 `eventlogg` typo；旧 material/source safe-display 文案与 `render(None)` assertions明确删除/替换；source 文案只保留业务中性 contract，无 compatibility alias | 已修复 |

## 2. Rejected / already-covered dispositions 保持不变

| review item | controller disposition | 本轮记录 |
| --- | --- | --- |
| DS-F03 minimal Doc-only smoke | rejected / no code | §12.2 仅重申 aggregate hard gate；Doc-only 不能替代 Web/Fins awaiting，full smoke未削弱 |
| MiMo 001 citation key 枚举 | rejected | Host 只机械渲染整个 citation object；plan 明确禁止枚举或解释 Fins keys |
| MiMo N3 S1 descriptor/idempotency cases | already covered | 仍由 §6.4 small/large descriptor、same-key/different-digest tests覆盖；未增加第四 slice |
| DS-N03 legacy source tests scan | already covered | 仍由 §10.3 source gates和§11.4 replacement matrix覆盖 |
| DS-F04 coverage 降级 | rejected | `dayu/runtime/__init__.py >=80%` 保留，未设 N/A |
| 其它 non-blocking notes | no scope expansion | 未引入 BusinessSource、Fins reverse import、compatibility、Issue #177/#178、auth framework或新产品语义 |

## 3. Artifact-only validation

本节在两份 artifact 写入完成后执行；结果如下：

| validation | 结果 |
| --- | --- |
| artifact-only `git diff --check` | PASS；两份新增文件对 `/dev/null` 的 `--no-index --check` 均无 whitespace diagnostic（exit `1` 仅表示新增文件与空文件不同） |
| workspace path scope | PASS；本轮写入仅为 plan 与本 fix artifact；pre-existing control/review artifacts hash 未变化 |
| prompt inventory | PASS；`dayu/config/prompts` 当前 `37` 个文件，全部在 plan 有逐文件 disposition |
| constructor inventory | PASS；`dayu/tests/utils` 的 executable-Python constructor scan 当前 `114` 个路径，全部在 plan 有 disposition |
| R01 §11 handoff | PASS；5+5+5+5+10=`30` 个 data row 保持逐行消费 |
| slice count | PASS；仅 `S1/S2/S3` 三个 R03 slice heading，无第四 slice |

workspace 初始已有用户/其它 Agent 状态：`docs/host/issues-implementation-control.md` 为 modified，controller validation/adjudication 与两份 plan review 为 untracked，plan 本身也为 untracked。本轮只改已有 plan 并新增本 fix artifact；上述 control/prior review 五个文件修订前后 SHA-256 完全一致。

执行命令：

```bash
git diff --no-index --check -- /dev/null \
  docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md
git diff --no-index --check -- /dev/null \
  docs/reviews/wu-semantic-ownership-01-r03-plan-fix-codex.md
git status --short -- \
  docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md \
  docs/reviews/wu-semantic-ownership-01-r03-plan-fix-codex.md
shasum -a 256 \
  docs/host/issues-implementation-control.md \
  docs/reviews/wu-semantic-ownership-01-r03-plan-controller-validation.md \
  docs/reviews/wu-semantic-ownership-01-r03-plan-review-controller-adjudication.md \
  docs/reviews/wu-semantic-ownership-01-r03-plan-review-ds.md \
  docs/reviews/wu-semantic-ownership-01-r03-plan-review-mimo.md
find dayu/config/prompts -type f | wc -l
rg -l 'AgentRunRequest|SystemMessage|UserMessage|ToolFunctionSchema|ToolDefinition' \
  dayu tests utils --glob '*.py' | wc -l
rg -n '^## (6|7|11)\. R03-S[123]' \
  docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md
```

未运行 production tests、coverage、pyright 或 real public-run smoke：本轮只有 plan/fix artifact，且 controller 明确禁止进入 implementation；这些命令仍是 approved implementation/aggregate gate 的必做项。

## 4. Residual risks 与下一入口

| residual | 分类 / owner |
| --- | --- |
| real provider/Web/Fins 环境可能在 aggregate smoke 时缺失 | 真实 aggregate blocker；不得 fake/skip/降级，由 controller 提供或确认环境 |
| 非 Fins tool 无 explicit citation | accepted source-unavailable；未来若需要 citation，由具体 producer owner另行设计 |
| Issue #177/#178 | 既有 issue owner；不进入 R03 |
| internal EventLog/Tool Trace 仍持有 refs/digests | internal provenance/diagnostic owner；LLM-ready projection严格隔离 |

没有未分类 residual risk。下一入口是 AgentMiMo / AgentDS 对**完整修订计划**并发 re-review；在 re-review/controller 接受前不得 implementation、commit 或 push。

## 5. Artifact path

`docs/reviews/wu-semantic-ownership-01-r03-plan-fix-codex.md`
