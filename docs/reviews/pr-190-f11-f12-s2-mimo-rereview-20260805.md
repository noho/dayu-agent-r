# PR 190 F11/F12 S2 Fix Re-Review — MiMo 独立路线

## Review metadata

- Reviewer：AgentMiMo
- Gate：`fix -> re-review`
- Work unit：PR 190 F11/F12 Interactive Memory 收口
- Slice：S2 — Engine generic structured output 与 config capability
- Baseline HEAD：`c8be3e5184b8b797c59458027e991f0284cbb3b5`
- Review scope：review-fix artifact + 当前完整 S2 diff
- Artifact path：`docs/reviews/pr-190-f11-f12-s2-mimo-rereview-20260805.md`

## Reviewer interference audit

本轮 re-review 严格遵守只读约束，未执行任何 Git state mutation（无 stash/checkout/reset/clean/stage/commit/push）。工作树状态与 fix artifact 记录一致。

## 逐项裁决

### Finding 1：DS-LOW-01 — build_request_payload structured_output default

**裁决：PASS — fix 正确且完整**

验证证据：

1. **签名已修正**：`payload.py:408` 当前签名为 `structured_output: StructuredOutputRequest | None`，无 `= None` default。与 fix artifact 声明一致。
2. **owner test 锁定签名**：`test_no_extra_payload_bag.py:45-59` 通过 `inspect.signature` 断言：
   - `build_request_payload` 恰好五个 keyword-only 参数：`messages`, `options`, `tools`, `spec`, `structured_output`
   - 所有参数 kind 为 `KEYWORD_ONLY`
   - `structured_output` 的 default 为 `inspect.Parameter.empty`
3. **所有 production/direct callers 显式传参**：diff 确认 `test_payload_build.py` 中每个 `build_request_payload(...)` 调用均显式传入 `structured_output=...`。
4. **未引入 wrapper/fallback/overload**：payload.py 无新增 helper、无 `@overload`、无 `if structured_output is None` 兼容分支。

### Finding 2：DS-LOW-02 — config/Engine capability enum drift guard

**裁决：PASS — fix 正确且完整**

验证证据：

1. **Service owner test 存在且完整**：`test_host_assembly.py:204-222` 函数 `test_structured_output_capability_enums_map_mechanically_by_value` 断言：
   - `StructuredOutputCapabilityConfig` 完整 value 集合 `==` `StructuredOutputCapability` 完整 value 集合
   - 遍历每个 runtime value，机械构造 Engine enum，断言 `.value` 相等
2. **无反向依赖/第三 enum**：test 只 import `StructuredOutputCapabilityConfig`（runtime）和 `StructuredOutputCapability`（Engine），通过 `.value` 字符串机械映射。无 production helper、无第三份 enum。
3. **runtime 不 import Engine**：`dayu/runtime/config_loader.py` 独立定义 `StructuredOutputCapabilityConfig`，不 import Engine。
4. **Service 机械投影**：`dayu/service/host_assembly.py` 通过 `StructuredOutputCapability(model.structured_output_capability.value)` 完成 enum→enum by value 映射。

### Finding 3：S1 deterministic import-boundary regression

**裁决：PASS — fix 正确且完整**

验证证据：

1. **policy 改为精确 workspace-relative paths**：`test_import_boundary.py:53-70` 从旧的 basename-only `tuple` 改为 `frozenset[str]`，每个条目为精确的 `dayu/host/xxx.py` 路径。
2. **原允许集合无丢失**：diff 逐条比对，旧的 12 个 basename 全部保留（映射为完整路径），只新增两个 design-required 文件：
   - `dayu/host/durable/tool_trace.py`
   - `dayu/host/tool_trace_analysis_contracts.py`
3. **不能因 basename 放宽**：policy 用 `file_path.relative_to(repo_root).as_posix()` 生成 workspace-relative path 进行精确匹配，不会误放行同名不同位置的文件。
4. **两 Host nodes PASS**：
   - `test_cancel_session_replay_after_watchdog_does_not_append_or_propagate`：PASS
   - `test_host_engine_imports_stay_on_allowed_boundary_modules`：PASS
   - 稳定重跑 `2 passed in 0.83s`

### 额外验证：Tool Trace production identity 未变

**裁决：PASS**

- `dayu/host/durable/tool_trace.py` vs baseline：diff 为空，无变更
- `dayu/host/tool_trace_analysis_contracts.py` vs baseline：diff 为空，无变更
- `dayu/engine/contracts/runner_identity.py` vs baseline：diff 为空，无变更

fix 只修改了 import-boundary test policy（允许列表），未触碰 production identity 类型或 import。

### 额外验证：S3 scope 未扩大

**裁决：PASS**

fix artifact 声明"不扩张 structured-output schema、Host Tool Trace production contract、provider 行为或 S3/S4 scope"。diff 验证：所有变更文件均在 S2 allowed scope 内，无 S3/S4 文件被触碰。

## Static analysis

- pyright（5 个 modified files）：`0 errors, 0 warnings, 0 informations`

## 总体结论

**PASS** — 三项 finding 的 fix 均正确且完整，无新 finding。

| Finding | 裁决 | 理由 |
| --- | --- | --- |
| DS-LOW-01 | PASS | `build_request_payload.structured_output` 无 default，owner test 通过 `inspect.signature` 锁定 |
| DS-LOW-02 | PASS | Service owner test 完整锁定 runtime/Engine enum value 集合与逐值机械构造，无反向依赖 |
| S1 import-boundary regression | PASS | policy 改为精确 workspace-relative paths，原允许集合无丢失，只精确新增两个 design-required 文件 |

fix 未改变 Tool Trace production identity，未扩大 S3 scope，reviewer interference 已正确记录与剔除。
