# WU-CTX-01 Slice 3 Implementation Review Fix

## 1. Gate、状态与裁决

- gate：Slice 3 implementation review fix。
- base：accepted Slice 2 protected commit `126e67ca`。
- Controller 裁决：
  `docs/reviews/wu-ctx-01-slice-3-implementation-review-controller-adjudication.md`。
- 状态：`CTRL-S3-IMPL-01` 已修复，等待 AgentMiMo、AgentDS 双路
  implementation re-review 与 Controller 最终裁决。
- 未 commit、未 push、未创建 PR。

本轮只关闭 `CTRL-S3-IMPL-01`。`candidate_input_cursor` 的业务语义是 EventLog
sequence；`MAX_CONTEXT_TOKEN_COUNT` 的业务语义是 context token count ceiling。
二者恰好都能落入 SQLite/Python 整数范围，不构成共享 owner 的理由。原 query
boundary 把 cursor 与 token ceiling 绑定，问题动机成立，且修复 owner 是
`ContextAnchorQuery` 自身的 typed validation boundary。

## 2. 精确变更

### `dayu/host/context_anchor.py`

1. 删除
   `candidate_input_cursor > MAX_CONTEXT_TOKEN_COUNT` 的比较与对应
   `ValueError`；没有新增 EventLog sequence ceiling、fallback 或兼容分支。
2. 保留 cursor 的严格 typed boundary：
   - `bool` 不是合法整数；
   - 非 `int` 失败；
   - 负数失败；
   - 任意非负 `int` 可作为调用方冻结的 EventLog sequence atom。
3. 保留 `MAX_CONTEXT_TOKEN_COUNT` import 及其三个正确消费者：
   - `ContextAnchorQuery.context_window_size`；
   - `CompatibleContextAnchor` 的 usage / conservative anchor token；
   - strict parsed usage 的 prompt / completion / total token。
4. 澄清 `ContextAnchorQuery` docstring：
   - `current_run_id` 与 `candidate_input_digest` 是调用方从当前 complete
     candidate 冻结的 typed identity atoms；
   - 它们不是与历史 anchor 做相等比较的 compatibility predicates；
   - cursor 明确是 EventLog sequence，不是 token count。
5. 没有向 `_compatibility_mismatch` 或其它 resolver 分支新增 digest / Run id
   相等比较。

### `tests/host/test_context_anchor.py`

1. 新增
   `test_query_event_cursor_is_independent_from_token_ceiling`：
   - `MAX_CONTEXT_TOKEN_COUNT + 1` 作为非负 EventLog cursor 可通过 query
     construction；
   - 相同数值作为 `context_window_size` 仍按 token owner contract 拒绝。
2. 新增
   `test_query_event_cursor_fails_closed_at_typed_boundary`：
   - `True` 抛出 `TypeError`；
   - `-1` 抛出 `ValueError`；
   - 两者都在 `ContextAnchorQuery.candidate_input_cursor` owner boundary
     失败。

### 明确未变更

- 未实现 DS-03 的 overload / wrapper 扩展。
- 未实现 DS-04 的 `sequence=0` fallback。
- 未实现 DS-05 的损坏 link loose parsing 或下游 identity 补偿。
- 未修改 signed-delta、anchor eligibility、barrier、compact、replay、public
  projection 或其它 production 行为。
- 未修改两路 review、initial implementation artifact、Controller
  adjudication 或 `docs/host/issues-implementation-control.md`。

## 3. 验证

### 定向 owner tests

```text
pytest -q tests/host/test_context_anchor.py
21 passed in 0.44s
```

### 完整类型检查

```text
python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

pyright 另报告存在可升级版本 `1.1.411`；当前项目环境执行版本为
`1.1.409`，不影响本次零错误结论。

### Branch coverage

coverage 数据由 full Host 与 Slice 3 计划指定的四个 OpenAI usage tests 重新采集：

```text
2272 passed, 2 skipped, 6 deselected in 64.16s
```

随后对相对 `126e67ca` 的 10 个 changed production Python 文件逐文件执行
`coverage report --include=<file> --fail-under=80`：

| file | branch-aware coverage | threshold |
| --- | ---: | --- |
| `dayu/host/_runner_call_manifest.py` | 85% | pass |
| `dayu/host/admission.py` | 86% | pass |
| `dayu/host/context_anchor.py` | 83% | pass |
| `dayu/host/context_budget.py` | 83% | pass |
| `dayu/host/context_events.py` | 84% | pass |
| `dayu/host/dispatch.py` | 85% | pass |
| `dayu/host/engine_ingest.py` | 85% | pass |
| `dayu/host/recovery.py` | 84% | pass |
| `dayu/host/run_input.py` | 82% | pass |
| `dayu/host/waiting.py` | 83% | pass |

全部文件独立 `--fail-under=80` 通过；`context_anchor.py` 从 initial
implementation artifact 记录的 82% 提升为 83%。

### Diff 与 allowlist

- `git diff --check` 与 `git diff 126e67ca --check`：通过；对三个 untracked
  新文件分别执行 `git diff --no-index --check /dev/null <file>` 也无 whitespace
  error（命令仅因存在预期新增内容返回 diff 状态 1）。
- 相对 `126e67ca` 的 10 个 production Python changes 全部位于 Slice 3
  §8.4 allowed production files。
- 相对 base 的 changed tests 全部位于 Slice 3 §8.4 allowed tests。
- `dayu/host/README.md` 与 `tests/README.md` 位于 §8.4 allowed docs；本轮审计
  确认 cursor typed boundary 与 current-candidate identity clarification 是
  Host-private query contract，不改变 README 已记录的 durable anchor 稳定行为，
  因此本 fix 不再修改 README。
- implementation / review / adjudication / 本 fix 文档是 gated workflow
  artifacts，不是 production 或 test allowlist 扩张。
- `docs/host/issues-implementation-control.md` 是 Controller-owned dirty file，
  明确排除在 implementation review diff 与本轮修改外。
- 本 review-fix pass 的写入范围只有：
  `dayu/host/context_anchor.py`、`tests/host/test_context_anchor.py` 与本 artifact。

## 4. 边界与剩余风险

### 已关闭

- `CTRL-S3-IMPL-01`：EventLog cursor 与 context token ceiling 的错误 owner
  耦合已删除，并由 owner-level query validation tests 锁定。
- DS-01 的文档歧义已澄清，且没有引入错误的历史 digest equality predicate。

### 剩余风险

- 本轮没有新增未分类 correctness 风险。
- EventLog sequence 的产生与持久化范围继续由 EventLog / frozen candidate
  owner 保证；query 只校验 strict non-bool、non-negative typed boundary。绕过
  EventLog owner 人工注入不可持久化的超大 Python 整数不属于 resolver 的 token
  ceiling 职责。
- initial implementation review 已记录的长 Session keyset scan 性能风险、
  future parser exception audit 与其它非 blocking residual risks均未因本修复改变；
  它们不属于 `CTRL-S3-IMPL-01`，本轮未扩张 production scope。
- 下一入口是双路 implementation re-review；在 Controller 最终 accepted 前，
  Slice 3 review loop 尚未关闭。

## 5. Artifact

- 本文件：
  `docs/reviews/wu-ctx-01-slice-3-implementation-review-fix-codex.md`。
