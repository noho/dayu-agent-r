# WU-SEMANTIC-OWNERSHIP-01 R03 Aggregate Deepreview Controller Adjudication

## 1. Gate 与结论

- umbrella WU：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU。
- accepted R03 plan：`8c6ae966`。
- accepted slices：S1=`3e48f09e`、S2=`4b4696e5`、S3=`3f777753`。
- aggregate transition：`d6a1ef97`。
- Controller validation：`docs/reviews/wu-semantic-ownership-01-r03-aggregate-controller-validation.md`，verdict 为 `PASS / READY_FOR_AGGREGATE_DEEPREVIEW`。
- MiMo artifact：`docs/reviews/wu-semantic-ownership-01-r03-aggregate-deepreview-mimo.md`。
- DS artifact：`docs/reviews/wu-semantic-ownership-01-r03-aggregate-deepreview-ds.md`。
- decision：`PASS / ZERO_ACCEPTED_FINDING / ZERO-CHANGE FIX RECORD REQUIRED`。

两路 reviewer 都审查了 `8c6ae966..HEAD` 的 S1-S3 accepted commits 与当前 working tree 的 `R03-AGG-CV-F01..F03` fixes，并明确返回 `PASS`、accepted finding `0`、blocking open question `0`。Reviewer verdict 不独立接受代码；按用户要求的 `aggregate deepreview -> fix -> re-review` gate 顺序，本裁决只授权 AgentCodex 生成零产品变更的 aggregate fix record，随后仍须双路完整 aggregate re-review。

## 2. Findings ledger

本轮 accepted finding 数为 `0`，rejected finding 数为 `0`，deferred finding 数为 `0`。

两路共同确认：

- ordinary / awaiting accepted call 复用唯一 canonical request atom writer 与同一 digest invariant；
- `TOOL_AWAITING` 只保留 governance metadata 与 strict request link，不复制 accepted arguments / digest；
- wait resolution 由 suspended source Attempt 的 execution identity 同源写 result；
- F01 保留 typed accepted evidence shared renderer exact text，ordinary material normalization 不变；
- F02 正确区分 inline raw outcome 与 cold descriptor，并由 strict descriptor owner fail closed；
- F03 只让 typed `EventClass.CANONICAL_FACT` request / awaiting / result 进入 strict post-run diagnostic；
- RunInput、Memory、Compact、LLM-ready Tool Trace 从同一 typed material 派生，material corruption 统一 fail closed；
- opaque refs 只保留 internal provenance / audit，不进入 LLM-readable business source；
- LLM-facing 文本符合当前动作所需的业务可读语义；
- DNS/peer、path containment、symlink、resource budget、atomic/process fencing 等安全机制保持；
- 未实施统一 tool authorization framework，未越界实施 Issue 142、151、175、177、178。

`R03-AGG-CV-F01..F03` 继续为 `CLOSED`，当前没有需要 AgentCodex 修改的产品、测试、README、design、plan、smoke 或 control 语义。

## 3. Reviewer observations 裁决

| observation | Controller disposition | owner / destination |
|---|---|---|
| `compact_material.py` 的 material-missing diagnostic 文案只描述 raw outcome missing | `NO_CURRENT_DEFECT / NO_FIX`。当前 accepted envelope 保证 tool identity，实际失败路径仍是 result material 不可用；异常 fail closed，未对 LLM 承诺错误业务事实。 | Host Compact diagnostic owner；若未来错误分类 contract 改变，由该 owner 同步文案。 |
| `run_input.py` resume path 与 shared projection 使用不同 payload reader | `HYPOTHETICAL_ONLY / NO_FIX`。当前 wait-resolution result 始终 inline；shared projection 自身仍严格解析 descriptor。Reviewer 未给出可达错误状态或数据不一致。 | Host RunInput/shared projection owner；未来若 wait result 改为 cold descriptor，必须在该 schema owner 变更中重新验证。 |
| `waiting.py::_expire_wait_in_transaction` 私有 helper 本地实例化 stores | `STYLE_OBSERVATION / NO_FIX`。同一 durable transaction 内功能正确，不产生第二状态真源、不可测试分支或当前行为漂移。 | Host waiting owner；无当前 destination。 |
| `_WAIT_EXPIRY_MESSAGE` 是硬编码中文 Host timeout 文案 | `OWNER-CORRECT / NO_FIX`。它明确说明 Host 期限与结果未接受，不伪装成财报事实，不含 opaque ref/credential，属于 typed failed tool result 的治理原因。 | Host waiting error projection owner；无当前 destination。 |
| 全量六域有两个 logging-order failures | `BASELINE OWNER OBSERVATION / NO_R03_FIX`。二者在 fresh process 共同隔离为 `2 passed`；直接证据指向 `utils/smoke_web_ci.py::main` 以 `configure_root=True` 改写全局 logging state 且未恢复，不经过 R03 changed owner。 | Web smoke/test harness owner；若 umbrella 最终 aggregate regression 仍复现，进入最终 aggregate finding ledger 并由该 owner 修复。 |
| macOS coverage 预载入影响 Web/Fins spawn pickling | `INSTRUMENTATION LIMIT / COVERAGE GATE SATISFIED`。排除的真实子进程用例已在无 instrumentation 完整文件测试中分别通过。 | validation harness/environment owner；未来修改 process boundary 时继续以 plain subprocess tests 提供行为证据。 |

上述观察均不是 accepted finding，不要求当前 R03 fix，不得借此修改 unrelated owner。

## 4. Zero-change fix 要求

AgentCodex 必须只新增：

`docs/reviews/wu-semantic-ownership-01-r03-aggregate-deepreview-fix-codex.md`

该 artifact 必须：

1. 记录两路 aggregate deepreview、Controller 裁决与 accepted finding `0`；
2. 在创建 artifact 前冻结当前完整 R03 protected path/status 集合，并记录 ordered path digest、per-file content digest aggregate 与 status/path digest；集合必须覆盖所有 R03 production/tests/README/smoke、accepted plan、S1-S3 accepted artifacts、aggregate fix/validation/reviews、Controller control doc；
3. 在创建 artifact 后复算并证明除该 zero-change artifact 外，protected content、status 与 path 集合均未变化；
4. 复核 `git diff --check`、R03 allowlist/no-diff owners、deleted safe-argument/redaction/opaque-ref fallback source scans，以及当前 security/deferred boundaries；
5. 不重跑或声称新的 provider smoke；只引用 Agent 与 Controller 已通过且由 protected digest 保持的 smoke evidence；
6. 不修改任何 product/test/README/smoke/plan/design/control/既有 artifact，不 stage、不 commit、不 push、不进入 R04。

## 5. 下一 gate

Controller 验证 zero-change record 后，进入 AgentMiMo / AgentDS 双路完整 R03 aggregate re-review。两路必须确认 protected target 未变、F01-F03 仍关闭、零 accepted finding、安全与 deferred boundaries 未漂移。只有 re-review 与 Controller 最终裁决通过，才授权 R03 accepted local commit。

R03 与 umbrella WU 当前均未完成；R04 仍未授权。
