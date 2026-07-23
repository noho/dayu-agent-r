# WU-CTX-01 Slice 3 Implementation Re-review Controller Adjudication

## 1. Scope

- Base：accepted Slice 2 protected commit `126e67ca`。
- Initial implementation：
  `docs/reviews/wu-ctx-01-slice-3-implementation-codex.md`。
- Initial reviews：
  - `docs/reviews/code-review-20260724-071249.md`
  - `docs/reviews/code-review-20260724-071353.md`
- Initial Controller adjudication：
  `docs/reviews/wu-ctx-01-slice-3-implementation-review-controller-adjudication.md`，
  decision=`needs-fix`。
- Fix：
  `docs/reviews/wu-ctx-01-slice-3-implementation-review-fix-codex.md`。
- Re-reviews：
  - AgentMiMo：
    `docs/reviews/wu-ctx-01-slice-3-implementation-re-review-mimo.md`，
    verdict=`PASS`，0 findings。
  - AgentDS：
    `docs/reviews/wu-ctx-01-slice-3-implementation-review-fix-ds-rereview-20260724.md`，
    verdict=`PASS`，0 findings。

## 2. Re-review adjudication

### `CTRL-S3-IMPL-01`

**状态：closed。**

直接证据：

1. `ContextAnchorQuery.candidate_input_cursor` 只保留严格 non-bool、
   non-negative integer validation，不再复用 `MAX_CONTEXT_TOKEN_COUNT`。
2. `MAX_CONTEXT_TOKEN_COUNT` 继续且只在本 resolver 边界约束：
   - context window token；
   - usage/conservative anchor token；
   - strict parsed usage prompt/completion/total token。
3. owner tests 证明：
   - 超 token ceiling 的非负 cursor 不再被 token owner 拒绝；
   - 相同数值作为 context window 仍被 token owner 拒绝；
   - bool cursor 抛 `TypeError`；
   - negative cursor 抛 `ValueError`。
4. `current_run_id` / `candidate_input_digest` 已明确为调用方冻结的当前
   complete candidate typed identity，不是与历史 anchor 做相等比较的
   compatibility predicate。
5. Controller 拒绝的 overload、sequence=0 fallback 与损坏 link loose parsing
   均未实施。

### Regression and scope

- fix 只修改 `dayu/host/context_anchor.py` 与
  `tests/host/test_context_anchor.py`，并新增 fix artifact。
- resolver eligibility、barrier、keyset、compact boundary、signed delta、
  conservative fallback、five-stage action、startup replay、canonical fact 与
  public 七字段均未漂移。
- fix owner tests=`21 passed`。
- full pyright=`0 errors, 0 warnings`。
- coverage suite=`2272 passed, 2 skipped, 6 deselected`。
- 相对 `126e67ca` 的 10 个 changed production Python 文件 branch-aware
  coverage 均 `>=82%`，`context_anchor.py=83%`。
- `git diff --check`、allowlist 与 README audit 均通过。

## 3. Residual risk

以下均为 non-blocking residual，不改变本 gate 结论：

1. 未量化从未 compact 的超长 Session reverse keyset scan 性能；设计明确禁止任意
   总 cap，当前无 correctness 或性能退化证据。
2. future durable parser 若新增其它异常类型，仍需按 owner contract 审计是否应转换
   为 barrier；当前 strict parsers 的异常集合已被测试覆盖。
3. provider 是否实际返回 usage 是外部行为；缺失、非法或 pairing 不可信时继续精确
   fallback 当前完整 `E_current`，因此不比 Slice 2 算法差。

## 4. Decision

**`pass`**

Slice 3 implementation review loop 已关闭。允许创建 accepted Slice 3 protected
commit，随后进入 whole-WU aggregate deepreview。
