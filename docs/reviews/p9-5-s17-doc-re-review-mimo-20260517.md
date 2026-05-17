# P9.5 S17 Documentation Re-Review — F1 Fix Verification

## Review Context

- Reviewer: AgentMiMo
- Scope: F1 fix verification only
- Original artifact: `docs/reviews/p9-5-s17-doc-review-mimo-20260517.md`
- F1 original description: `tests/README.md` Engine import boundary "memory" 精度略高于测试粒度

## Verdict: F1 FIXED

`tests/README.md:104` 已从：

> 阻止 Engine 反向依赖 Host、Service、UI、Fins、**memory**、工具声明 owner、...

改为：

> 阻止 Engine 反向依赖 **Host（含 memory）**、Service、UI、Fins、工具声明 owner、...

**验证**：`tests/engine/test_import_boundary.py:24-31` 的 `ENGINE_CORE_FORBIDDEN_PREFIXES` 包含 `"dayu.host"`，覆盖 `dayu/host/memory.py`、`dayu/host/memory_repair.py`、`dayu/host/durable/memory.py`。括号说明准确表达了 memory 约束通过 `dayu.host` 前缀禁令间接覆盖的测试粒度。

**判定**：修复正确，概念与粒度一致。F1 closed。
