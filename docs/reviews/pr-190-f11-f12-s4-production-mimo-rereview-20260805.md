# PR 190 F11/F12 S4.1 Production Fix Re-Review (AgentMiMo)

## Scope

- Mode: current changes
- Branch: `codex/interactive-oracle`
- Base: `c824ea9038ecb4084621117c6806764cd63e9a20`
- Output file: `docs/reviews/pr-190-f11-f12-s4-production-mimo-rereview-20260805.md`
- Included scope:
  - `dayu/host/compact_pipeline.py` (workspace unstaged)
  - `dayu/host/context_fallback.py` (workspace unstaged)
  - `tests/host/test_compact_pipeline.py` (workspace unstaged)
  - `tests/host/test_dispatch_scheduler.py` (workspace unstaged)
- Excluded scope: 其他未修改文件
- Parallel review coverage: 无
- Input artifacts:
  - `docs/reviews/pr-190-f11-f12-s4-production-mimo-review-20260805.md` (原始 MiMo review)
  - `docs/reviews/pr-190-f11-f12-s4-production-review-adjudication-20260805.md` (controller 裁决)
  - `docs/reviews/pr-190-f11-f12-s4-production-review-fix-20260805.md` (fix artifact)

## Verification Checklist

### 001 已关闭：跨模块私有 helper import ✅ PASS

| 验证项 | 结果 | 证据 |
|---|---|---|
| `_fallback_current_input_material_block` 已从 `compact_pipeline.py` 删除 | ✅ | `rg` 确认源文件无此符号，仅 review docs 中有历史引用 |
| `_current_input_material_block_for_fallback` 已从 `context_fallback.py` 删除 | ✅ | `rg` 确认源文件无此符号 |
| `compact_pipeline.py` 不再 import `context_fallback` 私有符号 | ✅ | 剩余 import 均为公共符号：`FALLBACK_ACTION_DISPATCH`、`RecentWindowFallbackBudgetResult`、`build_recent_window_fallback_selection` 等 |
| 两个 producer 均直接调用 `compact_material.run_input_material_block` | ✅ | `compact_pipeline.py:1123` 调用 `run_input_material_block`；`context_fallback.py:482` 调用 `run_input_material_block` |
| 无新增公共导出、compatibility wrapper 或 re-export | ✅ | 未修改 `__all__`，未新增模块级函数 |
| 无新增 public surface | ✅ | 只删除了私有函数，未暴露新接口 |

**代码走读**：

`compact_pipeline._fallback_material_blocks`（`compact_pipeline.py:1123-1130`）现在直接调用 `run_input_material_block`，传入 block_id、section、kind、text、canonical_source_refs 和 event_sequence。`size_units` 和 `content_digest` 由 owner 派生，不再手工构造。

`context_fallback._fallback_material_blocks_for_window`（`context_fallback.py:480-490`）同样直接调用 `run_input_material_block`，传入相同模式的参数。两路 producer 的 current-input block 构造逻辑现在完全委托给同一 owner。

### 002 按裁决不改，理由成立 ✅ PASS

| 验证项 | 结果 | 证据 |
|---|---|---|
| 002 保持 `rejected-with-reason` | ✅ | fix artifact 明确记录不改变 |
| 裁决理由成立 | ✅ | selection 使用冻结 `CompactPipelineSourceSnapshot`（`compact_pipeline.py:1114`），durable replay 从 EventLog 重建（`context_fallback.py:460-478`）；生命周期不同，不是第二语义 owner |

**理由分析**：

我的原始 002 finding 指出 proactive 和 reactive 使用不同 material block 构造路径。裁决正确识别：proactive 在 selection 阶段使用 frozen source snapshot，reactive 在 durable replay 阶段从 canonical EventLog 重新读取。这是生命周期要求，不是语义分歧。两路已通过同一 `run_input_material_block` owner 收敛。

### 003 按裁决不改，理由成立 ✅ PASS

| 验证项 | 结果 | 证据 |
|---|---|---|
| 003 保持 `rejected-with-reason` | ✅ | fix artifact 明确记录不改变 |
| 裁决理由成立 | ✅ | `_AlwaysQualityRejectingCompactor` 是 deterministic input，验证 Host fallback state machine，不承担真实 provider conformance |

**理由分析**：

我的原始 003 finding 指出测试使用 fake compactor 可能掩盖真实行为。裁决正确识别：这是 owner-level deterministic input，测试目的是验证 Host exhausted-fallback 状态机与 material replay，不是验证 compactor 质量检查逻辑。真实 provider 必须在 fresh evidence root 单独验证。

### Controller docstring finding 已关闭 ✅ PASS

| 验证项 | 结果 | 证据 |
|---|---|---|
| `ActiveRecentWindowFallback.material_blocks` docstring 已更新 | ✅ | `context_fallback.py:243-244` 写为 "valid proactive 或 reactive durable loader 均从 EventLog-backed source 重建并填充" |
| 旧 "仅 proactive" 已删除 | ✅ | `rg "仅 proactive"` 返回空 |
| 未修改 dataclass 类型或 schema | ✅ | 只更新了 docstring 文本，字段定义不变 |

### Pure equality test 与两条 dispatch 回归 ✅ PASS

| 测试 | 结果 | 证据 |
|---|---|---|
| `test_fallback_decision_input_dispatch_and_fail_closed` | ✅ 1 passed | 含连续空白输入，断言 `selected_current == expected_current`（pure equality） |
| `test_proactive_exhausted_fallback_normalizes_current_input_for_replay` | ✅ 1 passed | 断言 `expected_current_block.text != current_input`（whitespace digest）、`compactor.calls == 2`、`CONTEXT_COMPACTION_FAILED == 1`、fallback dispatch/manifest/cleanup |
| `test_reactive_compact_failure_fallback_dispatch_uses_failed_view` | ✅ 1 passed | 断言 protected recent replay、digest、recovery Attempt/Run terminal、cleanup |

**测试走读**：

pure equality test（`test_compact_pipeline.py:870-885`）注入含连续空白与空行的 source snapshot，构造 `expected_current` 通过 `run_input_material_block`，然后断言 `selected_current == expected_current`。这直接证明 selection current block 与 owner expected dataclass 完全相等，覆盖 block id、section、kind、normalized text、size_units、content_digest、canonical source refs、EventLog sequence 及 dataclass 其余默认字段。

proactive 回归（`test_dispatch_scheduler.py:8277`）验证两次 rejected 后 fallback dispatch，断言 `expected_current_block.text != current_input` 证明规范化生效，`window["selected_material_view_digest"]` 与 `selected_material_view_digest((expected_current_block,))` 一致证明 digest 同源。

reactive 回归（`test_dispatch_scheduler.py:9052`）验证 recovery 对空白输入与 protected recent view 同源 replay，断言 `expected_current_block.text != current_input`、`"recent protected\nreplay material" in second_contents`、recovery Attempt SUCCEEDED、Run SUCCEEDED。

### Scope drift 检查 ✅ PASS

| 检查项 | 结果 | 证据 |
|---|---|---|
| 无新增公共导出 | ✅ | 未修改 `__all__` |
| 无新增 compatibility wrapper | ✅ | 只删除了私有函数 |
| 无新增模块 | ✅ | 只修改现有文件 |
| 无跨私有 import | ✅ | `compact_pipeline.py` 从 `context_fallback` 只导入公共符号 |
| 无 policy/caps/terminal/schema 变更 | ✅ | 只修改内部 owner 调用边界和 docstring |
| `git diff --check` 通过 | ✅ | 无 whitespace error |
| pyright 通过 | ✅ | 0 errors, 0 warnings, 0 informations |

### 额外验证：`load_context_fallback_in_transaction` trigger_source 扩展 ✅ PASS

fix artifact 未提及此项，但代码变更中 `context_fallback.py:407-411` 将 trigger_source 检查从仅 `PROACTIVE` 扩展为 `PROACTIVE` 或 `REACTIVE`，并统一调用 `_fallback_material_blocks_for_window`。这是正确的：reactive durable loader 现在也通过同一函数重建 material blocks，与 proactive 同源。此变更不在 adjudication findings 中，但属于 fix 的自然组成部分，未引入 scope drift。

## Findings

未发现实质性问题。

## Open Questions

- 无。

## Residual Risk

- `assigned to later work unit`：RunInput / ContextFallback contract 仍允许注入式 `material_blocks is None` 分支。按 adjudication，本 slice 不扩大；若 aggregate deepreview 找到真实 production 可达反例，由 RunInput / ContextFallback contract owner 升级处理。
- `covered by later approved slice`：Mimo-first、DeepSeek-only-fallback 的真实 provider evidence 必须在本 review loop 通过后使用 fresh evidence root 重跑。
- `test coverage gap`：测试使用 `_AlwaysQualityRejectingCompactor`（fake），不覆盖真实 compactor 的质量检查逻辑。按 adjudication 裁决，这是 owner-level deterministic input，真实 provider 必须在 fresh evidence root 单独验证。
- `non-breaking space (U+00A0)`：`normalized_material_text` 使用 `split()` 按 Python 文档会处理 Unicode 空白字符包括 U+00A0，但测试未覆盖。逻辑应正确，属于 residual coverage gap 而非 correctness risk。

## Conclusion

Fix artifact 中声称的修复均已通过独立 re-review 验证：

1. **001 已关闭**：跨模块私有 helper import 已消除，两个 producer 均直接调用 `compact_material.run_input_material_block`，无新增公共导出或 wrapper。
2. **002 按裁决不改**：proactive/reactive 来源不同是生命周期要求，理由成立。
3. **003 按裁决不改**：deterministic rejecting compactor 验证 fallback state machine，理由成立。
4. **Controller docstring finding 已关闭**：`ActiveRecentWindowFallback.material_blocks` docstring 已更新。
5. **Pure equality test 与两条 dispatch 回归正确**：3/3 passed。
6. **无 scope drift**：无新增 public surface、wrapper、re-export 或跨私有 import。

Gate 状态：**PASS**。
