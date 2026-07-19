# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 2 Code Re-review Controller Adjudication

## 1. Gate identity

- 日期：`2026-07-19`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU。
- Gate：Slice 2 双路 complete code re-review 的 Controller 最终裁决。
- Immutable base：`ba44bf877138235d53606d082341a7f7280af488`。
- Immutable 20-path target manifest：`cb0d5f96da993dd7cbe65fe513d2432a25b5c4a091515e5f1a29f2ed8d303925`。

## 2. Final re-review artifacts

| Reviewer | Artifact | SHA-256 | Verdict |
| --- | --- | --- | --- |
| AgentMiMo | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-code-rereview-mimo.md` | `ef745b2817ee64891114849aa22ac51d8bdae43545d1ef32d6a3b42fd496d196` | `PASS / ZERO_MATERIAL_FINDING / ZERO_BLOCKER` |
| AgentDS | `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-code-rereview-ds.md` | `edd5ab6b4dd5ed6cd43e30babd6c404a9fbb1e1dbc1eb5c16926f13b46a70b26` | `READY_FOR_CONTROLLER_ADJUDICATION / ZERO_FINDING` |

两路均在同一未变化 target 上重新完成 owner、state/lifecycle、exception identity、import boundary、compatibility/fallback、security、LLM-facing、README、tests/coverage 与 scope containment 审查；没有沿用 initial review 结论替代完整复审。

## 3. Review-process evidence disposition

AgentMiMo 曾违反本 gate 的单主会话约束而启动 Explore 子代理。Controller 当场中断并作废全部子代理输出；这些输出不构成本裁决证据。随后 AgentMiMo 在主会话完整读取 9 份必读真源、accepted plan、authorization、implementation、Controller validation、initial reviews/adjudication与完整 20-path target，并独立重做 adversarial review。最终 artifact 已明确记录：

```text
SUBAGENT_OUTPUT_DISCARDED / MAIN_REVIEWER_FULL_READ_AND_REVIEW
```

因此该过程偏差已经关闭，未污染产品 target，也没有遗留 code finding。AgentDS 按要求在主会话完成独立复审，并 fresh 运行 focused tests 与 pyright。

## 4. Finding ledger

```text
ACCEPTED_CODE_FINDING = 0
OPEN_CODE_FINDING = 0
REJECTED_CODE_FINDING = 0
BLOCKER = 0
DESIGN_CONTRADICTION = 0
REVIEW_PROCESS_CORRECTION_OPEN = 0
```

- `ValidatedFinsEventStream` 及其状态机/close 语义现在由 `dayu.fins.direct_events` 唯一拥有；旧 `dayu.fins.direct_stream` 物理删除。
- awaiting resolution 的 config field、closed enum 与 strict parser 现在由 `dayu.fins.ingestion.awaiting_resolution` 唯一拥有；tools 私有 helper 不再拥有或转发该语义。
- 无 re-export、wrapper、fallback、lazy/dynamic import、第二套 enum/parser/validator 或兼容分支。
- `AR-F02` 从 `IMPLEMENTATION_PASS / CODE_REVIEW_PENDING` 关闭为 `CLOSED / ACCEPTED_SLICE_2_OWNER_REMEDIATION`。

## 5. Controller final independent validation

Controller 在 final re-review artifacts 固定后重新验证：

| Gate | Result |
| --- | --- |
| exact focused tests（8 test files，含 import boundary） | `321 passed, 3 warnings` |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| `git diff --check` | PASS |
| staged tree | EMPTY |
| new owner SHA-256 | `945ffedf2ab375afc24668db4c7a327fb2008c066a954d51046e3273b79ee481` |
| deleted base owner blob SHA-256 | `f724e51ca6ff5dd687dfe4709751b8f0e9bd440b4e02f0bfd343f598a1e50c53` |

Final target 仍恰好是授权的 20 路径；Controller/review/control artifacts 不属于产品 target。此前完整 canonical、coverage、Fins、build、security matrix、source/propagation scans 与五条真实 smoke 证据保持有效，final re-review 没有修改 target。

## 6. Security / quota / deferred decision

- Config 与 Host internal SQLite/EventLog 是同一可信本地产品域，允许内部 durable execution state 携带 API key/header；没有因此新增 secret infrastructure 或泄露分析层。
- Tool Trace、audit、public、LLM-facing、logs、输出及 review/diff 仍不得出现 API key/header 明文；本 Slice 没有改变该边界。
- Gemini 是低预算测试账号；quota 结果固定为 `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`，不改 provider/config/model/key/retry/quota/budget，也不追加真实 provider 调用。
- 未实施统一 tool authorization framework；现有 containment、symlink、DNS/peer、resource budget、atomic write、process fencing 均保留。
- Topic 8/9、Issues 142/151/175/177/178 与 Web/WeChat/render trackers 均未扩入本 Slice。

## 7. Decision

```text
PASS / ZERO_OPEN_FINDING / READY_FOR_EXACT_ACCEPTED_LOCAL_COMMIT
```

只授权将当前 Slice 2 产品、测试、README、utility、implementation/review/Controller artifacts 与同步 control state 做一次 exact-scope accepted local commit。Slice 3、aggregate、push、PR 与 final closeout 仍须后续独立 gate。
