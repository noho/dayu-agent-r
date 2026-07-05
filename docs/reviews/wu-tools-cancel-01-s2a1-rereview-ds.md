# WU-TOOLS-CANCEL-01 S2A1 Fix Re-Review — AgentDS

## 审查范围

- Trigger: `docs/reviews/wu-tools-cancel-01-s2a1-fix-codex.md` 关闭 DS F01 advisory
- Base commit: `8eddd26b`
- 审查对象: 当前未提交 working tree diff 中 `utils/` 三个文件的 fix
- 原审 artifact: `docs/reviews/wu-tools-cancel-01-s2a1-code-review-ds.md`

## 检查项

### 1. `utils/` 三个 smoke 文件是否已显式 `execution=AsyncDirectToolExecutionCapability()`

| 文件 | 行号 | `execution=` | import |
|------|------|-------------|--------|
| `utils/smoke_host_public_conversation_memory.py` | 743 | ✅ `execution=AsyncDirectToolExecutionCapability()` | ✅ line 30: `from dayu.contracts import ... AsyncDirectToolExecutionCapability` |
| `utils/smoke_host_public_conversation_memory_scenarios.py` | 3433 | ✅ `execution=AsyncDirectToolExecutionCapability()` | ✅ line 39: `from dayu.contracts import ... AsyncDirectToolExecutionCapability` |
| `utils/smoke_host_public_multiturn.py` | 649 | ✅ `execution=AsyncDirectToolExecutionCapability()` | ✅ line 31: `from dayu.contracts import ... AsyncDirectToolExecutionCapability` |

**结论：✅ PASS** — 三个站点均已显式传入 execution，import 路径正确，导入符号已存在于 `dayu/contracts/__init__.py`（S2A1 主变更已添加）。

### 2. 是否仍有 `ToolDefinition(...)` 构造缺 execution

**方法：** 对 `utils/`、`dayu/`、`tests/` 下全部 34 个 `ToolDefinition(` 构造站点做否定扫描——查找含 `ToolDefinition(` 但无 `execution=` 的文件。

```
rg -l "ToolDefinition\(" utils/ dayu/ tests/ -g '*.py' | while read f; do
  if rg -q "ToolDefinition\(" "$f" && ! rg -q "execution=" "$f"; then
    echo "MISSING: $f"
  fi
done
```

**结果：零命中。** 所有含 `ToolDefinition(` 的文件均包含 `execution=`。

**额外确认：** `dayu/tests/utils` 目录不存在，不存在"隐藏在 tests 子目录下的遗漏站点"。

**结论：✅ PASS** — 无遗漏站点。

### 3. fix 是否引入导入错误、README/测试义务遗漏或越界到 S2A2

#### 3a. 导入正确性

三个 smoke 文件的变更仅增加两行：
- 1 行 `import`：`AsyncDirectToolExecutionCapability` 从 `dayu.contracts` 导入——该符号已在 S2A1 主变更中加入 `dayu/contracts/__init__.py` 的 `__all__`，导入路径有效。
- 1 行 kwarg：`execution=AsyncDirectToolExecutionCapability()`——与所有 `dayu/` 和 `tests/` 站点的迁移方式完全一致。

#### 3b. README/测试义务

- `utils/` 目录下的脚本在 CLAUDE.md 中明确规定"默认无需测试、无覆盖率要求"。
- README 触发规则不覆盖 `utils/` 目录——变更不触发任何 README 更新义务。
- 此 fix 是纯机械迁移（在已有 `ToolDefinition` 调用中添加一个已存在的 kwarg），不引入新语义、新接口或新模块。

**结论：✅ 无遗漏义务。**

#### 3c. S2A2 越界检查

`git diff 8eddd26b --stat` 确认：
- 无 `dayu/host/dispatch.py` 变更（S2A2 Host factory wiring）
- 无 `dayu/engine/` 变更（Engine contract）
- 无 `dayu/runtime/interruptible_process` 变更
- 无 Host cancel API / EventLog / durable schema 变更
- 唯一含 "dispatch" 的文件是 `tests/host/test_dispatch_scheduler.py`，属于 S2A1 原有的测试站点迁移，不涉及 dispatch 逻辑变更

**结论：✅ 无越界。**

---

## Verdict

**PASS**

DS F01 advisory 已被完整关闭。三个 `utils/` smoke 文件的 `ToolDefinition(` 站点与 `dayu/`、`tests/` 全部 31 个站点保持一致，均显式传入 `execution=AsyncDirectToolExecutionCapability()`。全量否定扫描确认无遗漏站点。fix 不引入导入错误、README/测试义务遗漏或 S2A2 越界。
