# WU-SEMANTIC-OWNERSHIP-01 P3-K S1 Code Review (DeepReview)

## Scope

- Mode: current changes (working tree diff against accepted plan commit)
- Base: `8515364a` (accepted plan commit)
- Branch: `phaseflow/host-issues-control`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-k-s1-code-review-ds.md`
- Included scope:
  - `tests/host/test_memory_projection.py` (unstaged working tree changes)
  - `tests/contracts/test_tool_result_envelope.py` (unstaged working tree changes)
  - `tests/host/test_run_input_builder.py` (unstaged working tree changes)
- Excluded scope:
  - `AGENTS.md`, `CLAUDE.md` — unrelated dirty files per review brief
  - `docs/cli_ci*` — unrelated untracked files
  - `docs/reviews/code-review-20260710-*.md` — unrelated review artifacts
  - S2 (raw SQL helpers), S3 (cancellation/compaction fakes) — intentionally excluded by plan
  - All production code — S1 is test-only per plan
  - `tests/engine/test_engine_event_contract.py` — legitimate public-contract locks, not modified
- Parallel review coverage: 无（单 reviewer 直接走读全部变更）

## Evidence Sources

- Plan: `docs/host/wu-semantic-ownership-01-p3-k-test-harness-semantic-coupling-plan.md`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-k-s1-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-k-s1-controller-validation.md`
- Production owners traced:
  - `dayu/host/memory.py:747` — `MemoryProjectionPolicy` (20 fields)
  - `dayu/host/memory.py:882` — `ConversationMemorySnapshotVNext` (14 fields)
  - `dayu/contracts/tool_result.py:64,88` — `ToolResultSuccess` (3 fields), `ToolResultFailure` (5 fields)
  - `dayu/host/run_input.py:3509-3531` — `_resume_wait_fallback_message()` (6-line guidance output)
- Working tree diff: full unstaged diff against HEAD

## Findings

### 1. 未发现实质性问题

经过逐行对比 working tree diff、逐链路追踪生产 semantic owner、以及 adversarial failure pass，未发现 correctness、stability、maintainability 或 semantic ownership 方面的实质缺陷。

以下逐项核查五个 review focus 问题：

---

#### 1.1 是否在移除 ownerless exact field-set lock 的同时保留了真实 contract 覆盖？

**`test_memory_projection.py` — `MemoryProjectionPolicy` 测试：**

旧测试 `test_memory_projection_policy_contract_uses_design_source_fields` 仅断言 `tuple(field.name for field in fields(MemoryProjectionPolicy)) == _POLICY_FIELDS`（精确有序元组锁），不消费任何生产 owner helper。

新测试 `test_memory_projection_policy_contract_uses_owner_level_fields`（第 696 行）：
- 子集断言 `_REQUIRED_MEMORY_POLICY_FIELD_NAMES <= policy_fields`（必需字段必须存在，但允许扩展）
- 消费 `default_memory_projection_policy(context_window_size=8192)` — line 1018 的 owner helper
- 消费 `memory_projection_policy_to_json_value(policy)` — line 1454 的 owner 序列化 helper
- 断言 `_REQUIRED_MEMORY_POLICY_FIELD_NAMES <= set(policy_json)` — JSON 投影包含必需字段
- 断言 `digest_memory_projection_policy(policy) != digest_memory_projection_policy(changed_window_policy)` — digest 对 `context_window_size` 敏感
- 断言 `digest_memory_projection_policy(policy) != digest_memory_projection_policy(changed_ref_policy)` — digest 对 `policy_ref` 敏感

**评估：** 新测试覆盖维度从"1 个（字段集相等）"提升到"4 个（字段存在、owner helper 构造、owner helper 序列化、owner helper digest 敏感性）"。精确闭集锁被替换为 owner 级行为断言。不构成回归。

**`test_memory_projection.py` — `ConversationMemorySnapshotVNext` 测试：**

旧测试 `test_conversation_memory_snapshot_vnext_contract_fields_are_fixed` 仅断言 `tuple(field.name for field in fields(ConversationMemorySnapshotVNext)) == _SNAPSHOT_FIELDS`。

新测试 `test_conversation_memory_snapshot_vnext_contract_uses_owner_level_sections`（第 717 行）：
- 子集断言 `_REQUIRED_MEMORY_SNAPSHOT_FIELD_NAMES <= snapshot_fields`
- 通过 `build_empty_conversation_memory_snapshot(...)` 构造完整空快照（owner helper）
- 逐字段断言所有 14 个字段值（identity、cursor、policy、memory sections、governance）
- 断言 `snapshot.snapshot_digest == calculate_memory_snapshot_digest(snapshot)`（owner digest helper）
- 断言 `conversation_memory_snapshot_to_json_value(snapshot)` 包含所有必需字段
- 断言 `conversation_memory_snapshot_from_json_value(snapshot_json) == snapshot`（JSON round-trip 恒等）

**评估：** 新测试的断言数量从 1 增加到 18+（14 个逐字段值断言 + subset 断言 + digest 断言 + JSON round-trip 断言 + JSON key 断言）。覆盖强度显著提升。精确闭集锁被替换为更强的 owner 级行为验证。

---

#### 1.2 Memory 断言是否保持 owner 级且足够强？

是。两个测试现在直接消费 `dayu.host.memory` 提供的 owner helper：
- `default_memory_projection_policy()` — 构造
- `memory_projection_policy_to_json_value()` — 序列化
- `digest_memory_projection_policy()` — 摘要
- `build_empty_conversation_memory_snapshot()` — 构造
- `calculate_memory_snapshot_digest()` — 摘要
- `conversation_memory_snapshot_to_json_value()` — 序列化
- `conversation_memory_snapshot_from_json_value()` — 反序列化

这些 helper 都是 `dayu.host.memory` 的 public API，是 memory policy/snapshot 语义的唯一 owner。测试不再定义独立的字段注册表；`_REQUIRED_*_FIELD_NAMES` 是测试侧的最小必需字段声明，用于验证 owner 确实暴露了这些字段——它不声称自己是字段真源。

唯一"削弱"是字段检查从 `==` 变为 `<=`（子集），但这正是 plan 明确要求的：精确闭集不是 public contract，测试不应成为字段变更的 gate。新测试对字段移除仍然敏感（`<=` 会在必需字段缺失时失败），对合法字段新增不再误报。

---

#### 1.3 Tool Result Envelope 断言是否仍保护 public discriminant 与 forbidden awaiting 字段？

是。`test_envelope_field_sets_do_not_contain_await_spec`（第 117 行）的变更：

```python
# 旧：精确集合相等
assert success_fields == {"ok", "value", "meta"}
assert failure_fields == {"ok", "error", "message", "hint", "meta"}

# 新：必需字段子集 + 禁止字段互斥
required_success_fields = {"ok", "value", "meta"}
required_failure_fields = {"ok", "error", "message", "hint", "meta"}
forbidden = {"await_spec", "await", "awaiting"}
assert required_success_fields <= success_fields
assert required_failure_fields <= failure_fields
assert success_fields.isdisjoint(forbidden)
assert failure_fields.isdisjoint(forbidden)
```

保留的断言：
- `ok` 判别字段仍被 protected（`required_success_fields` / `required_failure_fields` 都包含 `ok`）
- `await_spec` / `await` / `awaiting` 禁止字段仍被 `isdisjoint` 保护
- 文件内所有其他 discriminant / runtime validation 测试（`test_tool_result_success_ok_is_true`、`test_tool_result_failure_ok_is_false` 等）完全未变

生产侧 `dayu/contracts/tool_result.py` 的模块 docstring 明确声明：等待型工具结果不进入本信封，本信封不应包含 `await_spec` / `await` 字段。测试的 forbidden check 直接保护此 contract。字段集从 `==` 变为 `<=` 是 plan 明确要求的行为。

---

#### 1.4 Resume Guidance Helper 是否避免 vague substring check 并保留内部泄漏 negative？

是。文件私有 helper `_assert_resume_guidance_semantics`（第 6601 行）使用 **exact line membership** 断言，而非旧测试的 substring 断言：

```python
lines = tuple(content.splitlines())
assert _RESUME_GUIDANCE_COMPLETED_INTRO in lines          # 精确行匹配
assert f"完成的工具：{tool_name}" in lines                 # 精确行匹配
assert f"完成状态：{status}" in lines                      # 精确行匹配
assert f"工具结果：{result_text}" in lines                  # 精确行匹配
assert _RESUME_GUIDANCE_NO_REPEAT in lines                 # 精确行匹配
for fragment in _RESUME_GUIDANCE_FORBIDDEN_INTERNAL_FRAGMENTS:
    assert fragment not in content                          # 全文禁止片段检查
```

**对比旧测试：** 旧测试使用 `"上一轮被等待中断的外部工具步骤已经完成。" in message.content`（子字符串匹配），新测试使用 exact line 成员检查。新断言更严格——只有完整行匹配才通过，而子字符串匹配可能在意外位置命中。

**内部泄漏 negative 覆盖：**
`_RESUME_GUIDANCE_FORBIDDEN_INTERNAL_FRAGMENTS`（第 219 行）包含 11 个禁止片段：

| 片段 | 类别 | 保护语义 |
|---|---|---|
| `"Resume guidance"` | 内部类型名 | 禁止 Host 内部类名泄漏 |
| `'"kind"'` | JSON 键 | 禁止内部 envelope 字段名泄漏 |
| `'"result"'` | JSON 键 | 禁止内部 envelope 字段名泄漏 |
| `'"ok"'` | JSON 键 | 禁止判别字段名泄漏 |
| `"wait-resume-private"` | 测试标识 | 禁止内部 wait id 泄漏 |
| `"tool-call-private"` | 测试标识 | 禁止内部 tool call id 泄漏 |
| `"event-tool-result-resume"` | 测试标识 | 禁止内部 event id/ref 泄漏 |
| `"payload-ref-private"` | 测试标识 | 禁止内部 payload ref 泄漏 |
| `"sha256:"` | digest 前缀 | 禁止内部 digest 泄漏 |
| `"attempt-current"` | 测试标识 | 禁止内部 attempt id 泄漏 |
| `"execution-current"` | 测试标识 | 禁止内部 execution id 泄漏 |

所有 11 个 fragment 与旧测试中分散的 11 个 `assert ... not in message.content` 检查一一对应。未丢失任何 negative。

**生产语义对齐验证：**
- `_RESUME_GUIDANCE_COMPLETED_INTRO` = `"上一轮被等待中断的外部工具步骤已经完成。"` — 与 `dayu/host/run_input.py:3524` 的字符串字面量逐字符一致
- `_RESUME_GUIDANCE_NO_REPEAT` = `"这是同一次用户请求中已完成的工具结果。继续回答用户；不要为了同一次请求再次启动相同下载、上传或处理。"` — 与 `dayu/host/run_input.py:3528` 的隐式字符串拼接结果逐字符一致
- 动态行 `完成的工具：{tool_name}`、`完成状态：{status}`、`工具结果：{result_text}` — 与 `dayu/host/run_input.py:3525-3527` 的 f-string 模板一致

**Docstring 所有权文档：** helper 的 docstring（第 6608-6620 行）明确声明：
- 固定行镜像 `dayu.host.run_input` 当前拥有的 guidance 语义
- `tool_name`、`status`、`result_text` 是 wait completion 投影和 result payload 派生的动态事实
- 当 owner 有意变更 guidance 时必须同步更新

这满足 plan 要求"helper 的 name/docstring 必须声明这些片段镜像 production-owned resume guidance semantics"。

---

#### 1.5 实现是否未进入 S2/S3 及生产代码？

是。变更范围严格限制在三个 S1 文件：

```
tests/host/test_memory_projection.py           — 仅 S1: owner-level assertions
tests/contracts/test_tool_result_envelope.py   — 仅 S1: required field assertions
tests/host/test_run_input_builder.py           — 仅 S1: resume guidance helper
```

以下 S2/S3 范围文件未修改：
- `tests/host/public_smoke_support.py` — S2 raw SQL helper，未触及
- `tests/host/recovery_support.py` — S2 raw SQL helper，未触及
- `tests/host/stress_support.py` — S2 raw SQL helper，未触及
- `tests/host/fake_cancellation.py` — S3 fake，未触及
- `tests/engine/runners/openai/_fakes.py` — S3 fake，未触及
- `tests/service/test_fins_direct.py` — S3 fake consumer，未触及
- `tests/host/fake_compaction.py` — S3 fake，未触及
- `tests/host/memory_snapshot_factories.py` — S3 factory，未触及

生产代码零修改：`git diff -- dayu/` 无输出。

---

### 观察记录（非缺陷）

以下观察不构成 material finding，但记录以供后续切片或 gate 参考：

**OBS-1: Resume guidance 首行 "恢复上下文：" 未断言。** 生产代码 `_resume_wait_fallback_message()` 输出 6 行，其中首行 `_RESUME_GUIDANCE_PREFIX = "恢复上下文："`（`run_input.py:209`）既不在旧测试中也不在新 helper 中被断言。旧测试从未断言此行，plan 未要求断言此行。该前缀是格式约定而非语义事实；关键语义由第 2 行（完成通知）和第 6 行（禁止重复指令）承载，两者均已断言。不需要修改。

**OBS-2: 行序独立。** `_assert_resume_guidance_semantics` 使用 `in lines`（元组成员检查）而非位置索引，不验证行序。旧测试使用 `in message.content`（全文子字符串），同样行序独立。无回归。若未来需要锁定 LLM-facing 文本行序作为 contract，应在 plan 层面决定，不在 S1 scope。

**OBS-3: Forbidden fragment 检查可能产生假阳性。** `'"kind"'`、`'"ok"'` 等带引号的 JSON 键名作为禁止片段，若合法工具结果文本恰好包含这些字符串，测试会误报。但此检查与旧测试完全相同，非 S1 引入的新风险。若需解决，应在独立 work unit 中设计更精确的 LLM-facing 泄漏检测策略。

## Open Questions

无。

## Residual Risk

| 风险 | 分类 | 说明 |
|---|---|---|
| 字段新增静默通过 | 已由 plan 接受 | Memory policy/snapshot 和 tool result envelope 的字段检查从 `==` 变为 `<=`，新字段加入不会触发测试失败。这是 plan 明确要求的 owner-level contract 行为。 |
| Resume guidance 行序未锁定 | 已由 plan 接受 | 当前 helper 只验证语义存在性，不验证行序。旧测试同样如此。若需锁定行序，应作为独立 contract 决策。 |
| Forbidden fragment 假阳性 | 已由旧测试继承 | 非 S1 引入，不阻塞 S1 closeout。 |
| S2/S3 未实现 | 已分配给后续切片 | Raw SQL helper coupling (TF-2)、cancellation fake consolidation (TF-4)、compaction/memory fixture coupling (TF-3) 属于 S2/S3 scope。 |
| Resume guidance 固定行与生产代码耦合 | 预期耦合 | Helper docstring 已声明耦合关系，且 plan 明确允许在生产不暴露 public constant 时镜像生产字符串。 |

## Completion Report

- **PASS/FAIL: PASS** — 无 material findings
- **Material findings:** 无
- **Residual risk:** 4 项已知且可接受的风险（见上表），均不阻塞 S1 closeout
- **Validation:** 166 tests passed, pyright 0 errors, 旧模式扫描零残留
- **README:** `tests/README.md` 正确未更新（无跨模块约定引入）
- **S2/S3 boundary:** 未侵入
- **Production code boundary:** 未侵入
