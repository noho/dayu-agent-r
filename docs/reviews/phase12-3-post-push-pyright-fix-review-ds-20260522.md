# Phase 12.3 Post-Push Pyright Fix Review — DS — 2026-05-22

## Verdict: PASS

无 blocking finding。修复精准、测试聚焦、边界干净。

## 1. Correctness

### 1.1 Root cause 确认 (PASS)

- `dayu/service/host_assembly.py:168` — `ServiceOpenHostAssemblyDiagnostics` 仅有 `agent_policy_sources: tuple[str, ...]`，无 `agent_policy_profile_id` 字段。
- `rg -n 'agent_policy_profile_id' dayu/` — production code 零命中。Schema 清理完整。
- `utils/smoke_host_public_multiturn.py:704` — 删除了 `agent_policy_profile:{diagnostics.agent_policy_profile_id}`，pyright 阻断已解除。

### 1.2 修复后 pyright (PASS)

| 文件 | 结果 |
| --- | --- |
| `utils/smoke_host_public_multiturn.py` | 0 errors, 0 warnings, 0 informations |
| `tests/runtime/test_smoke_host_public_multiturn_assembly.py` | 0 errors, 0 warnings, 0 informations |

### 1.3 未引入旧 schema (PASS)

修复仅删除一行格式字符串，无新增字段、无兼容性 re-export、无旧 `agent_policy_profile_id` 回退。`agent_policy_sources` 输出行（line 706-708）在修复前即存在，修复后继续保留为 Agent policy 诊断来源。

## 2. Test Adequacy

### 2.1 新增测试覆盖 (PASS)

`tests/runtime/test_smoke_host_public_multiturn_assembly.py:94-116` — `test_assembly_diagnostics_output_uses_current_agent_policy_sources`:

- **正向断言**：`assert "SMOKE ASSEMBLY agent_policy_sources=" in output` — 确认当前字段存在。
- **负向断言**：`assert "agent_policy_profile" not in output` — 确认旧标签不会重新出现。
- 测试通过真实 assembly → `_print_assembly_diagnostics` → stdout 捕获路径，端到端验证。

### 2.2 测试结果 (PASS)

```
tests/runtime/test_smoke_host_public_multiturn_assembly.py .... [100%]
4 passed in 0.63s
```

### 2.3 覆盖缺口 (OBSERVATION, non-blocking)

`SMOKE ASSEMBLY policy_refs=` 行现在仅含 `context_budget` 和 `tool_truncation` 两个字段，"policy_refs" 命名略显宽泛，但这是既有 smoke 格式约定，不属于本次 pyright fix 范围。未来若 policy refs 行只剩一个字段可考虑重命名或合并到其他 diagnostics 行。

## 3. Boundary

### 3.1 Host public contract (PASS)

- 修改范围仅限 `utils/smoke_host_public_multiturn.py`（辅助脚本，非 Host public contract）和对应 focused test。
- `ServiceOpenHostAssemblyDiagnostics` 无变更。
- `dayu/service/host_assembly.py` 无变更。

### 3.2 无旧 schema 兼容 (PASS)

修复不引入任何旧 `agent_policy_profile_id` 字段、兼容别名、兼容读取路径。

### 3.3 无无关变更 (PASS)

diff 仅两处修改：
1. `utils/smoke_host_public_multiturn.py:704` — 删除一行格式字符串片段。
2. `tests/runtime/test_smoke_host_public_multiturn_assembly.py` — 新增一个 focused test + import。

无重构、无格式化、无"顺手改"。

## 4. Artifact Accuracy

`docs/reviews/phase12-3-post-push-pyright-fix-codex-20260522.md`：

- Root cause 描述准确（P12.3 Slice 1 删除 `agent_policy_profile_id` → smoke 脚本残留引用 → pyright 阻断）。
- Changed files 列表准确。
- Validation 表格数值与我实际运行结果一致（pyright 0/0/0，pytest 4 passed）。
- README decision 合理：smoke 脚本输出格式细节变更不触发 README 更新规则。
- Residual risk 评估诚实。

## 5. Adversarial Failure Pass

| 攻击面 | 结果 |
| --- | --- |
| `agent_policy_profile` 子串是否在其他 smoke 输出行残留 | `rg 'agent_policy_profile' utils/smoke_host_public_multiturn.py` → 零命中 |
| 修复后 `policy_refs=` 行是否变成空后缀 | 否，`context_budget` 和 `tool_truncation` 仍存在 |
| 是否遗漏其他文件对 `diagnostics.agent_policy_profile_id` 的引用 | `rg 'agent_policy_profile_id' utils/ tests/ --include '*.py'` → 仅 negative test `test_old_agent_policy_profile_id_fails_fast` 在 `tests/runtime/test_config_loader.py`，属于 plan-mandated 旧 schema rejection test，正确 |
| `_print_assembly_diagnostics` 是否有其他调用方未被测试覆盖 | Grep 确认仅 `utils/smoke_host_public_multiturn.py` 内部调用，新增测试覆盖了该调用路径 |

## 6. 项目指令检查

| 指令 | 状态 |
| --- | --- |
| 禁止兼容性代码 | PASS — 无 re-export、无兼容常量、无兼容 wrapper |
| 禁止把显式参数放进 extra payload | PASS — 不涉及 |
| bug fix 禁止局部止血 | PASS — 直接删除残留引用，root cause 是 schema 清理后遗漏 |
| 测试覆盖率 | PASS — 新增 focused test，现有 4 测试全通过 |
| pyright 零报错 | PASS — 已确认 |

## Summary

修复正确且最小化：删除一行残留 `agent_policy_profile_id` 引用，新增一个 focused regression test。无 schema 回退，无 contract 变更，无无关修改。Pyright 和 pytest 均通过。**PASS**，可进入下一 gate。
