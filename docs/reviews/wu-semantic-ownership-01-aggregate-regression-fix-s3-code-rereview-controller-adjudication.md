# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 3 Code Re-review Controller Adjudication

## Verdict

`PASS / MATERIAL_FINDING=0 / ACCEPTED_OPEN=0 / READY_FOR_EXACT_SCOPE_ACCEPTED_SLICE_COMMIT`

本裁决只关闭既有 umbrella WU 的 aggregate regression fix Slice 3 本地 code re-review gate，不创建新 WU，不关闭 umbrella，也不授权 push、PR、远端 workflow 或 final closeout。

## 审查输入

- accepted plan HEAD：`9ad5711e20dd35d5a0cdc0cf79067333ff3b3daf`
- AgentMiMo final re-review：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-code-rereview-mimo.md`
  - SHA-256：`09b34859f0512d0b490317fc065f8ee14651599feb797add571c1ba9f7d943ec`
  - verdict：`PASS / NO_NEW_MATERIAL_FINDING / INITIAL_FINDINGS_CONFIRMED_ZERO`
- AgentDS final re-review：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-code-rereview-ds.md`
  - SHA-256：`1dde6a0d915edad231f575e9f7f33db7538b6f36b027e7f390a373399d80cd76`
  - verdict：`PASS / MATERIAL_FINDING=0 / ZERO_NEW_FINDING`
- initial review Controller adjudication：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-code-review-controller-adjudication.md`
- AgentCodex zero-change disposition：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-code-review-fix-codex.md`
- Controller zero-change validation：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-code-review-fix-controller-validation.md`

## Controller 复核

两路 reviewer 都对完整、不变的九路径 target 和 review/fix evidence 重新完成了审查，而不是沿用初审结论。两路共同确认：

1. `S3-STOP-F01` 的 Docling 多 caption 投影仍只消费同一 `DoclingDocument` 的 typed caption refs，没有旧单数 caption、raw JSON/private path、第二 resolver 或 LLM-facing internal ref 泄露。
2. `S3-STOP-F02` 的 Fins virtual-section owner 以 `BUILDING / VIRTUAL_PUBLISHED / BASE_FALLBACK_PUBLISHED` 单一 typed state machine 原子发布完整 virtual projection 或完整 base fallback；contradiction-first、zero-table、whole-base fallback、五个 public consumers 和首次/二次 refresh 幂等 contract 均成立。
3. 已删除的静默过滤、按位置猜测及首/最近章节补偿没有恢复；DocumentProcessor/SecProcessor marker contract、form-common guard、SEC/BS subclasses 与其它 protected owners 保持不变。
4. 初审中的重复 marker 计算、浅拷贝、private typed harness、既有 broad exception 与 unbound-base oracle 均按 Controller 既定证据维持 non-blocking 或 not-a-finding；AgentCodex 没有错误实施这些建议。
5. immutable review locks、九路径逐文件 hash、staged-empty、diff-check、focused tests、full pyright 与 protected-owner zero-diff evidence 均保持成立。

## Finding ledger

| 来源 | 候选 | 最终裁决 | 状态 |
|---|---|---|---|
| AgentMiMo initial | 重复 `_build_markers` 计算 | 无 correctness 证据，仅可在未来有 profiling 证据时由 owner 评估 | `REJECTED_NO_FIX` |
| AgentMiMo initial | publication 使用浅字典副本 | owner 需要保留同一对象 identity，不是 defect | `REJECTED_NO_FIX` |
| AgentDS initial | 测试使用 private typed mode | accepted plan 明确授权 owner-contract harness，且 public assertions 完整 | `REJECTED_NO_FIX` |
| AgentDS initial | marker producer 的既有 broad exception | 本 slice 未修改，现有 safe-degrade 有直接契约；无当前 defect 证据 | `REJECTED_NO_FIX` |
| AgentDS initial | unbound base oracle | reviewer 与 Controller 均确认不是 defect | `NOT_A_FINDING` |
| 双路 final re-review | 新 material finding | 无 | `ZERO` |

最终 ledger：accepted/open `0`，needs-evidence `0`，design contradiction `0`，local blocker `0`，unclassified residual `0`。

## Residual 与边界

- Gemini 是低预算测试账号；既有 provider 未调用 `search_web` 的 smoke 结果保持 `EXPECTED_TEST_ACCOUNT_QUOTA / PROVIDER_ADHERENCE_RESIDUAL / NO_CODE_ACTION / NON_BLOCKING`。不追加真实请求，不修改 config/model/key/retry/quota/budget。
- `AR-F06` 保持 `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`，owner/destination 仍是未来 Host scheduler/lifecycle coordination；本 slice 不修复也不豁免。
- `AR-F07` 保持 `PENDING_RELEASE_BLOCKER`。Darwin skip 不是 Windows 成功证据；本裁决不授权 push 或 workflow。
- Config 与 Host internal SQLite/EventLog 保持 trusted local domain；仅 Tool Trace、audit、public、LLM-facing、logs/outputs/diff/reviews 要求 API key/header 明文为零。本 slice 未引入 secret infrastructure 或统一 tool authorization framework。
- Issues 142、151、175、177、178 及 Web/WeChat/render trackers 承接的 deferred 能力均未带入。

## Gate decision

Slice 3 code re-review 本地通过。Controller 只授权下一步：把九个 product/test/README target、当前 control 状态及本次 accepted plan 后的完整 implementation/review/fix/re-review/controller evidence 作为一个精确路径集合，执行 staged diff-check 后创建本地 accepted Slice 3 commit。

该 commit 完成后必须做 parent/tree/path-set/path-digest/post-commit clean-tree 验证，再从最终整合树重新执行 aggregate regression。只有 aggregate regression 通过后，才可进入 AgentMiMo / AgentDS 双路 umbrella aggregate deepreview。
