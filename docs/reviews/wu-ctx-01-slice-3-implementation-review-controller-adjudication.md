# WU-CTX-01 Slice 3 Implementation Review Controller Adjudication

## 1. Scope

- Base：accepted Slice 2 protected commit `126e67ca`。
- Implementation：
  `docs/reviews/wu-ctx-01-slice-3-implementation-codex.md`。
- AgentMiMo review：
  `docs/reviews/code-review-20260724-071249.md`，verdict=`PASS`，0 findings。
- AgentDS review：
  `docs/reviews/code-review-20260724-071353.md`，verdict=`PASS`，
  5 个低严重度 findings。
- `docs/host/issues-implementation-control.md` 是 Controller-owned，排除在
  implementation review diff 外。

## 2. First-principles verdict

实现动机、owner 边界和核心算法成立：

1. `CONTEXT_BUDGET_EVALUATED` canonical fact / public 七字段仍独立消费同一个
   `ContextSizingResult`，没有把 fact 的存在绑定到 usage anchor。
2. resolver 只在调用方同一个 `HostTransaction` snapshot 内读取 durable
   manifest、accepted link、paired usage、accepted completion 与 compact boundary；
   没有自开 transaction、provider branch、display-text estimator 或总条数 cap。
3. signed delta 由 `context_budget.py` 唯一拥有，负 delta 不 clamp；任何历史
   usage/anchor 不可用都精确回退当前完整 candidate 的 `E_current`，不导致 Run
   失败。
4. accepted compact immediate candidate、startup exact replay、reactive /
   continuation hard action 与 public projection 均保持 accepted plan 语义。

因此不存在 correctness blocker；但项目的语义 owner / 过度耦合硬约束要求修复一处
已证实的 owner coupling，之后再进入双路 implementation re-review。

## 3. Finding adjudication

### DS-01：`candidate_input_digest` 未参与历史 anchor 相等比较

**裁决：reject-behavior-change / accept-doc-clarification。**

当前 candidate digest 与历史 anchor input digest 在正常 signed-delta 场景本就应当
不同；把两者相等作为 compatibility predicate 会错误拒绝所有真实输入变化。
`PreparedRunnerCallCandidate` 或 complete continuation manifest 已在调用方 owner
边界证明当前 candidate 完整性，resolver query 保留 accepted plan 冻结的当前
candidate identity atoms。只接受在 query docstring 明确
`current_run_id` / `candidate_input_digest` 是当前 candidate typed identity，
不是与历史 anchor 做相等比较的 compatibility 维度；不新增错误 predicate。

### DS-02：EventLog cursor 复用 `MAX_CONTEXT_TOKEN_COUNT`

**裁决：accept，编号 `CTRL-S3-IMPL-01`。**

`candidate_input_cursor` 是 EventLog sequence，不是 token count。
`ContextAnchorQuery.__post_init__` 用 context budget token ceiling 约束 cursor，
属于不同语义 owner 的偶然同值耦合。修复必须：

1. 删除 cursor 对 `MAX_CONTEXT_TOKEN_COUNT` 的依赖，只保留严格非 bool、非负整数
   的 query boundary；实际 cursor 继续由 EventLog / frozen candidate owner 产生。
2. 保留 context window、anchor token 与 usage token 对
   `MAX_CONTEXT_TOKEN_COUNT` 的正确校验。
3. 补 owner-level query validation test，证明 cursor 与 token/window 语义分离，
   同时继续拒绝 bool / negative cursor。
4. 同步 DS-01 的 query docstring 澄清；不改变 exact plan interface。

### DS-03：`anchor_resolution` / `fallback_reason` 联合未由 overload 表达

**裁决：reject。**

`build_context_sizing_result_from_atoms` 的 docstring 已明确两分支互斥，函数在运行时
同时拒绝 `(None, None)` 与双非空，当前调用点数量有限且 pyright 全覆盖。
增加 overload 或新的联合 wrapper 不提升 correctness，反而增加内部类型与调用成本，
不符合最小设计原则。

### DS-04：`manifest_event.event_sequence - 1` 的 sequence=0 反例

**裁决：reject。**

EventLog sequence 由 SQLite `INTEGER PRIMARY KEY AUTOINCREMENT` owner 分配，从 1
开始；Engine continuation manifest 在 production 还必然晚于 Session / Run /
Attempt facts。最小结果为 cursor 0，满足 resolver query。显式注入 sequence=0
绕过 EventLog owner 属于当前 candidate durable integrity 破坏，正确边界是 fail
closed，不是“历史 usage 不可用”的 conservative fallback。

### DS-05：损坏 link parse 后未用其 identity 消费 usage/completion

**裁决：reject。**

损坏 link 已产生 `ITERATION_LINK_INVALID` barrier；其后 orphan usage/completion
继续产生 barrier，不可能越过选择旧 anchor。要把它们强行归属到损坏 link，必须从
未通过 strict parser 的 partial payload 提取 identity，正是项目禁止的 loose
parsing / 下游补偿。当前实现的 closed fallback 比诊断 reason 合并更重要且语义正确。

## 4. Required fix and validation

AgentCodex 只允许修改：

- `dayu/host/context_anchor.py`
- `tests/host/test_context_anchor.py`
- 新的 Slice 3 review-fix artifact

不得改其它 production、现有 review artifacts 或 Controller control doc。验证至少：

```bash
source .venv/bin/activate
pytest -q tests/host/test_context_anchor.py
python -m pyright dayu/ tests/ utils/
git diff --check
```

还必须核对相对 `126e67ca` 的 allowlist 与 changed production branch coverage
仍 `>=80%`。

## 5. Decision

**`needs-fix`**

Slice 3 correctness 主体通过；只接受 `CTRL-S3-IMPL-01` 的语义 owner 解耦与
query doc clarification。完成最小 fix 后由 AgentMiMo、AgentDS 双路
implementation re-review，Controller 再作最终裁决。
