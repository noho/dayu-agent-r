# Phase 12.3 Slice 3 Implementation - AgentCodex - 2026-05-22

## 改动摘要

- `dayu/config/execution_profiles.json` 将默认 profile 改为 `standard-256k`，并新增 `standard-1m`、`wechat-256k`、`wechat-1m`。四个 profile 均显式声明 `context_window_class`、`min_context_window_tokens`，并内嵌完整 `agent_policy`。
- `dayu/runtime/config_loader.py` 为 `ExecutionProfileConfig` 新增 `context_window_class: str` 与 `min_context_window_tokens: int`，解析时只允许 `256k` / `1m`，并要求最小窗口为正整数。
- `dayu/runtime/assembly.py` 新增层中立 `ExecutionProfileCompatibilityDiagnostic` 与 `validate_execution_profile_context_window(profile, model)`。helper 只做兼容性校验和诊断，不读取 catalog 默认、不返回替代 profile id、不自动切换 profile。
- `dayu/service/host_assembly.py` 在 ordinary selection 与 compactor selection 后调用 compatibility helper；`ServiceOpenHostAssemblyDiagnostics` 记录 ordinary / compactor profile compatibility diagnostic，包含 profile id、selected model id、窗口 token 和 status。
- 更新 runtime / service 测试，覆盖默认 profile 分档、非法 schema fail fast、1m profile 搭配 256k 模型失败、256k profile 搭配 1m 模型 conservative、默认选择不因模型窗口自动切换。

## 验证结果

- `source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/runtime/test_assembly_helpers.py tests/service/test_host_assembly.py -q`
  - 结果：`51 passed in 0.82s`
- `source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q`
  - 结果：`13 passed in 0.81s`
- `source .venv/bin/activate && python -m pyright dayu/runtime dayu/service tests/runtime tests/service`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无 whitespace error。

## README 决策

- 已更新 `dayu/config/README.md`：同步 execution profile 默认 id、上下文窗口分档字段、compatibility helper 只校验不切换的语义。
- 已更新 `tests/README.md`：同步 config loader 测试覆盖 execution profile 上下文窗口分档校验。
- 未更新根目录 `README.md`、`dayu/README.md`、Host / Engine README：本 slice 未改变用户手册入口、整体分层关系、Host public API 或 Engine public contract。

## Residual Risk

- 未运行全量测试；本 slice 只运行 gate 要求的 runtime / service / boundary / pyright 验证。
- 修复前 `tests/runtime/test_smoke_host_public_multiturn_assembly.py` 存在旧 `standard` profile id 断言和 override；该风险已在下方 Fix Addendum 的 F1 中按 Controller 授权修复。
- `standard-*` 与 `wechat-*` 第一版使用同一 baseline 策略，仅通过 profile id、`policy_ref` 与 context window 分档区分；当前没有额外 WeChat 业务参数依据，因此没有硬编码无来源的行为差异。

## Fix Addendum

### 修复摘要

- F1：已将 `tests/runtime/test_smoke_host_public_multiturn_assembly.py` 中旧 `execution_profile_id="standard"` 与对应断言迁移为 `standard-256k`；未新增 `standard` 兼容 alias。
- F2：已将 `ExecutionProfileCompatibilityDiagnostic` 与 `validate_execution_profile_context_window` 加入 `dayu/runtime/assembly.py` 的 `__all__`。
- F3：`ConfigLoader` 已增加 `context_window_class` 与 `min_context_window_tokens` 交叉校验，要求 `256k` 精确对应 `262144`，`1m` 精确对应 `1000000`；补充 focused tests 覆盖矛盾配置 fail fast。

### Fix 验证结果

- `source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/runtime/test_assembly_helpers.py tests/service/test_host_assembly.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q`
  - 结果：`56 passed in 1.45s`
- `source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q`
  - 结果：`13 passed in 0.88s`
- `source .venv/bin/activate && python -m pyright dayu/runtime dayu/service tests/runtime tests/service`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无 whitespace error。

### Fix 后 Residual Risk

- 未运行全量测试；本 fix pass 只运行 controller 要求的 focused tests、runtime boundary、pyright 与 whitespace 检查。
- F1 中记录的 smoke assembly 旧 `standard` profile id 残留已修复，不再作为 residual risk 保留。
