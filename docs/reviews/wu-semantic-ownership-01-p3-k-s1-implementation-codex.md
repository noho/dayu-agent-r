# WU-SEMANTIC-OWNERSHIP-01 P3-K S1 Implementation - AgentCodex

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-K - Test harness semantic coupling cleanup`
- Slice: `S1 - Owner-Level Contract Assertions`
- Gate: `implementation`
- Accepted plan commit: `8515364a`
- Artifact path: `docs/reviews/wu-semantic-ownership-01-p3-k-s1-implementation-codex.md`

## First-Principles Decision

S1 motivation成立：当前缺陷不是测试不能锁定契约，而是测试在非公开闭合集合处承担了并行 schema / semantic owner 职责。实现只调整测试断言边界，不修改生产代码，不进入 S2 raw SQL helper 或 S3 fake/protocol consolidation 范围。

## Changed Files

- `tests/host/test_memory_projection.py`
  - 删除 `MemoryProjectionPolicy` / `ConversationMemorySnapshotVNext` 的 exact ordered tuple lock。
  - 改为 owner-level required field assertions。
  - 保留并加强 owner helper 消费断言：默认 policy、policy JSON 投影、policy digest 变化、empty snapshot build path、snapshot digest、JSON round-trip。
- `tests/contracts/test_tool_result_envelope.py`
  - 将 complete field-set equality 改为 required success/failure fields present。
  - 保留 forbidden awaiting fields absent 断言。
  - 保留 discriminant/runtime validation tests。
- `tests/host/test_run_input_builder.py`
  - 新增文件内私有 `_assert_resume_guidance_semantics(...)`。
  - helper 区分 production-owned guidance semantics 与 wait/result projection 派生的动态事实：tool name、status、result text。
  - 保留内部泄漏负面断言，且 helper 使用 exact line assertions，不使用 vague keyword helper。

## README Decision

已阅读 `tests/README.md` 的 `README 更新边界`。本 slice 未新增测试层级、测试运行方式或共享维护规则；resume guidance helper 是单文件私有 helper，没有引入跨模块测试约定。因此 `tests/README.md` 无需更新。

## Propagation Audit

- Memory policy / snapshot semantic owner: `dayu.host.memory`。
  - 测试现在只断言 owner-level 必需字段、owner JSON/digest/build/round-trip 行为，不再把测试文件作为完整字段 registry。
- Tool result envelope owner: `dayu.contracts.tool_result`。
  - 测试锁定 public discriminant、required result fields 和 forbidden awaiting fields，不再承诺完整闭合字段集合。
- Resume guidance owner: `dayu.host.run_input`。
  - 测试 helper 明确固定行来自 production-owned guidance semantics；动态 tool/status/result 来自 wait completion projection / result payload。
  - 内部 ref、digest、payload ref、event id、attempt/execution id 仍禁止进入 LLM-facing guidance。

## Validation

```bash
source .venv/bin/activate && pytest tests/host/test_memory_projection.py tests/contracts/test_tool_result_envelope.py tests/host/test_run_input_builder.py -q
```

Result: `166 passed in 1.24s`.

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Result: `0 errors, 0 warnings, 0 informations`. Pyright also printed an available-version notice: `v1.1.409 -> v1.1.411`.

```bash
git diff --check
```

Result: passed with no output.

Source scan:

- Concrete scan for removed policy/snapshot tuple names and exact ordered dataclass field tuple lock patterns returned no matches.
- Concrete scan for vague resume keyword helper patterns returned no matches.

## Residual Risks

- No unclassified residual risk in S1.
- Raw SQL helper coupling remains intentionally untouched and is covered by approved S2.
- Cancellation / compaction fake consolidation remains intentionally untouched and is covered by approved S3.
- Resume guidance wording is still mirrored in a test helper because the production owner does not expose public constants; this is acceptable for S1 because the helper documents ownership and asserts exact semantic lines rather than scattered prose fragments.

## Completion Status

S1 implementation complete. No commit, push, PR, code review gate, S2, or S3 work was performed.
