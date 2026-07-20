# WU-SEMANTIC-OWNERSHIP-01 / R03-S1 最终代码复审总控裁决

## 1. 裁决身份

- umbrella WU：`WU-SEMANTIC-OWNERSHIP-01`
- remediation sub-WU：`R03 — accepted call evidence 与 LLM-facing 投影真源`
- slice：`R03-S1 — ordinary/awaiting shared request atom + durable replay identity`
- 基线：`6e11d916..working tree`，包含 untracked 文件
- gate：dual final code re-review adjudication
- 日期：2026-07-15

本裁决只决定 R03-S1 是否可以进入 accepted local commit；不关闭 R03，不进入 R03 aggregate，也不关闭 umbrella WU。

## 2. 输入

- accepted plan：`docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md`
- implementation：`docs/reviews/wu-semantic-ownership-01-r03-s1-implementation-codex.md`
- Controller validation / re-validation：
  - `docs/reviews/wu-semantic-ownership-01-r03-s1-controller-validation.md`
  - `docs/reviews/wu-semantic-ownership-01-r03-s1-controller-revalidation.md`
- initial reviews / adjudication：
  - `docs/reviews/wu-semantic-ownership-01-r03-s1-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-r03-s1-code-review-ds.md`
  - `docs/reviews/wu-semantic-ownership-01-r03-s1-code-review-controller-adjudication.md`
- mandatory zero-change fix / validation：
  - `docs/reviews/wu-semantic-ownership-01-r03-s1-code-review-fix-codex.md`
  - `docs/reviews/wu-semantic-ownership-01-r03-s1-code-review-fix-controller-validation.md`
- final re-reviews：
  - `docs/reviews/wu-semantic-ownership-01-r03-s1-code-rereview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-r03-s1-code-rereview-ds.md`

Controller 已完整读取两份 final re-review，并复核当前 working tree status、完整 S1 target 与 gate artifacts。

## 3. 双路结论

| reviewer | verdict | material findings | open questions |
| --- | --- | ---: | ---: |
| AgentMiMo | `PASS` | 0 | 0 |
| AgentDS | `PASS / FINDINGS=0` | 0 | 0 |

两路均完整复核 `6e11d916..working tree` 的 production、tests、README 与 gate artifacts，并非只审 zero-change record。两路独立验证均报告：

- S1 9-file matrix：`389 passed`；
- full Host：`1952 passed, 2 skipped, 5 deselected`；
- exact transition owner suite：`77 passed`，`run_transition.py 80%`；
- pyright：0 errors；
- ruff 与 `git diff --check`：PASS；
- S1 production per-file coverage 达标。

## 4. Findings 最终状态

### 4.1 当前 accepted findings

`ACCEPTED_FINDINGS_ZERO`。本轮没有新增 material finding，不需要产品或测试修复。

### 4.2 既有 finding

- `R03-S1-CV-F01`：**CLOSED**。两个真实 durable `NOT_FOUND` / 五表 no-mutation owner cases 已进入 `test_resolve_wait_command.py`；Controller 和两路 reviewer 均复现 `77 passed / 80%`。
- initial MiMo / DS code review：finding 集合为零；mandatory zero-change fix record 已完成并由 Controller 验证。

### 4.3 四项 no-fix disposition

1. MiMo full-Host timing observation：维持 no finding；Controller 与两路 final reviewer 的 full Host 均绿色。
2. control doc 不在 S1 product allowlist：维持 authorized Controller state；它是 phaseflow gate 状态真源，不是产品改动。
3. DS duplicate-preimage observation：维持 rejected as finding。producer 与 writer validator 承担独立 proof 角色，digest equality fail closed；共享同一实现反而会让同一错误同时污染产生与校验，当前不存在第二 durable truth。
4. unused imports 删除：维持 no finding；pyright、ruff 和 full Host 均证明无错误。

## 5. Contract 与边界裁决

Controller 接受两路共同结论：

- ordinary / awaiting 共用唯一 `TOOL_CALL_REQUESTED` writer；
- `TOOL_AWAITING` 只保留真实 `{event_id, event_sequence}` governance link；
- canonical arguments / digest / descriptor shape 在 writer 与 reader 边界严格校验；
- accepted-result、RunInput、Memory、Compact、Trace 对缺失或损坏 request material 统一 fail closed，不再发布 fallback/partial material；
- wait-resolution result identity 来自 suspended source Attempt，WaitRecord/source Attempt execution mismatch 在写入前拒绝；
- `llm_safe_replay_arguments` 与旧 fallback helper 删除闭合；
- S2 的下游 blacklist/schema/source audit、S3 的 opaque ref propagation、Issue 177/178 与统一 authorization framework 均未被提前实施。

## 6. Residual risk 所有权

- source blacklist、producer schema 与 LLM-facing source audit：`R03-S2`。
- opaque refs internal-only 与四消费者传播闭合：`R03-S3`。
- public real-provider smoke：R03 aggregate gate。
- Issue 177、Issue 178：继续由各自 tracker 拥有。
- 统一 tool authorization framework：Topic 9 no-code decision，本 slice 未设计或实施。

AgentDS 将独立 producer/validator 实现列为低风险可选 cleanup；Controller 不将其登记为 residual。它是当前 accepted proof boundary 的有意设计，既不需要 S2 修复，也不应在下游增加共享 normalization。

## 7. 安全相关确认

本 slice 只删除下游 LLM-safe 参数修复/猜测语义，没有删除 Host durable identity、digest equality、descriptor shape、transaction rollback 或 fail-closed corruption guards。现有 allowed paths、DNS/peer、resource budgets、path containment、symlink、atomic write、process fencing 等安全机制不在本 slice diff 中且保持不变；未实现统一 tool authorization framework。

## 8. 最终裁决

**VERDICT: ACCEPTED_CODE_RE_REVIEW / READY_FOR_ACCEPTED_LOCAL_COMMIT**

R03-S1 的 accepted-plan contract、验证门槛、README 触发项、zero-change integrity 与全部 finding 状态均已闭合。授权 Controller 创建 R03-S1 accepted local commit；不授权 push、R03 aggregate、R03-S3 或 umbrella closeout。accepted commit 完成并回填真实 SHA 后，下一 gate 为同一 R03 的 S2 implementation。
