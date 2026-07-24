# WU-CTX-01 Slice 2 Implementation Review Controller Adjudication

## 1. Scope

- Work Unit：`WU-CTX-01`
- Gate：Slice 2 implementation review
- Base：accepted Slice 1 protected commit `b6f297b4`
- Implementation artifact：
  `docs/reviews/wu-ctx-01-slice-2-implementation-codex.md`
- AgentMiMo review：
  `docs/reviews/code-review-20260724-055928.md`
- AgentDS review：
  `docs/reviews/code-review-20260724-055648.md`
- Controller-owned `docs/host/issues-implementation-control.md`、implementation
  artifact 与既有 review artifacts 均不计入 implementation scope。

## 2. Review Results

- AgentMiMo：`pass`，无 actionable finding。
- AgentDS：`PASS（有条件）`，提出 1 个中风险、2 个低风险 finding。
- Controller 独立复读：
  - canonical fact、producer transaction ordering、startup strict replay、
    Host→Service public projection 与 Slice 2/3 边界没有 correctness blocker；
  - 发现 `tests/host/test_durable_schema.py` 的 schema version 测试已经断言
    `HOST_SCHEMA_VERSION == 24`，但测试名和 docstring 仍把当前版本描述为
    queue-policy CHECK schema 23，形成直接的 stale contract。

## 3. Finding Adjudication

### DS-F1：anchored result 的 `fallback_reason=None` 会在 builder 中提前访问 `.value`

裁决：**当前 Slice 2 驳回，不作为本 gate finding；保留为 accepted Slice 3 计划内
必做项，不新增 residual risk。**

直接依据：

1. accepted plan §8.3 Exact changes #1 要求 Slice 2 复用 Slice 1 的 sizing result
   typed contract，并明确本 slice producer 固定为
   `conservative_fallback`，不得导入 anchor resolver。
2. 当前 `ContextSizingResult.fallback_reason` 是非 optional typed field，且
   `__post_init__` 明确拒绝非 conservative method；因此 reviewer 构造的
   `fallback_reason=None` 输入在当前 production type contract 中不可成立。
3. Slice 3 才会同时扩展 `ContextSizingResult` anchored branch、构造
   `ContextAnchorDiagnostic` 并让 canonical builder 序列化 JSON `null`。只在 Slice 2
   给 `.value` 增加 unreachable `None` 分支，既不能形成可用 anchored fact，又会把两项
   独立修改混在一起。

Slice 3 implementation/review 必须按 accepted plan 同时验证 anchored builder
roundtrip；该要求已存在于计划，不需要新增 tracking item。

### DS-F2：typed exhaustive branch 使用 `AssertionError`

裁决：**驳回。**

raw payload 的 unknown enum 已在 `_required_enum` 边界统一以 `ValueError` fail
closed。后续若代码显式扩展 `ContextEstimateMethod` 却遗漏 typed exhaustive branch，
属于开发期不完整穷举，使用 `AssertionError` 与项目现有 typed mapper/state-machine
风格一致；把它改成 `ValueError` 不增加当前 schema 的安全性。

### DS-F3：public projector 未在 parser 前重复做 `Mapping` 检查

裁决：**驳回。**

`parse_context_budget_evaluated_payload` 是 canonical payload shape 的唯一 owner，其
入口已显式检查 `Mapping`；`_context_usage_activity` 捕获 `TypeError | ValueError`
并转换为 `HostDurableError`。在 read projector 重复 shape validation 会产生第二份
边界规则，违背唯一 owner 约束。

### MiMo residual risks

裁决：

- 两个新增 sizing helper 已由 canonical roundtrip 与各 producer owner-level tests
  覆盖，且 changed-file branch coverage 均达到要求；不新增孤立 unit-test finding。
- 本项目 schema 变更按 fresh schema 起库，version 24 不要求旧库迁移；不新增
  migration finding。
- `ContextSizingResult` 与 canonical payload 的 anchored 类型扩展属于已冻结的
  Slice 3 工作，不新增重复 residual risk。

### CTRL-S2-IMPL-01：schema version 测试名/docstring 已过期

裁决：**接受，低风险，必须在本 gate 修复。**

直接证据：

- `tests/host/test_durable_schema.py` 当前函数名仍为
  `test_host_schema_version_is_queue_policy_check_version`；
- docstring 仍写“当前 committed Host schema version 是 queue policy CHECK schema
  23”；
- 同一函数断言已改为 `HOST_SCHEMA_VERSION == 24`，本 slice 的直接 owner 是新增
  `CONTEXT_BUDGET_EVALUATED` canonical fact contract。

影响：

- 不影响运行时 correctness；
- 但测试名/docstring 与断言和当前 schema owner 不同源，会误导后续 schema 变更审计，
  并使 implementation artifact 的 stale-doc audit 结论不完整。

修复要求：

1. 只在 `tests/host/test_durable_schema.py` 更新该测试名与中文 docstring，使其准确描述
   version 24 的 context budget canonical fact contract；
2. 不修改 production、public contract、control doc 或 Slice 3 代码；
3. 运行该单测、focused Slice 2 tests、full pyright 与 `git diff --check`；
4. 写
   `docs/reviews/wu-ctx-01-slice-2-implementation-review-fix-codex.md`，
   记录修复和验证，不 commit。

## 4. Decision

**`needs-fix`**

Slice 2 production semantics 保持通过；唯一 accepted finding 是
`CTRL-S2-IMPL-01`。修复完成后必须由 AgentMiMo 与 AgentDS 进行双路 implementation
re-review，确认没有 production/test/control scope drift，Controller 再作最终裁决。
