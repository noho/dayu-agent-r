# Phase 12.3 Slice 3 Re-Review — AgentDS — 2026-05-22

## Verdict: PASS

所有三项 Controller accepted findings（P12.3-S3-F1/F2/F3）均已正确修复，无新增 regression。

---

## Finding-by-Finding Re-Verification

### F1: Smoke assembly test 从 `standard` 迁移到 `standard-256k`

**PASS。**

证据：
- `tests/runtime/test_smoke_host_public_multiturn_assembly.py:62` — 断言 `assembly.diagnostics.execution_profile_id == "standard-256k"`（原为 `"standard"`）
- `tests/runtime/test_smoke_host_public_multiturn_assembly.py:127` — 传参 `execution_profile_id="standard-256k"`（原为 `"standard"`）
- `rg '"standard"' dayu/config/execution_profiles.json` → 无命中，未新增 `standard` 兼容 alias
- `rg 'profile_id.*=.*"standard"[^-]' dayu/` → 无命中，production code 无裸 `"standard"` profile id 引用
- 该测试已通过：56 passed（含该 smoke test）

### F2: `ExecutionProfileCompatibilityDiagnostic` 与 `validate_execution_profile_context_window` 加入 `__all__`

**PASS。**

证据：
- `dayu/runtime/assembly.py:953` — `"ExecutionProfileCompatibilityDiagnostic"` 在 `__all__` 中
- `dayu/runtime/assembly.py:968` — `"validate_execution_profile_context_window"` 在 `__all__` 中
- 程序化验证：`python -c "from dayu.runtime.assembly import __all__; assert 'ExecutionProfileCompatibilityDiagnostic' in __all__"` 通过
- `__all__` 中符号总数从 16 增长到 18，无遗漏

### F3: ConfigLoader 交叉校验 `context_window_class` 与 `min_context_window_tokens`

**PASS。**

证据：
- `dayu/runtime/config_loader.py:58-61` — 新增映射常量：
  ```python
  _EXECUTION_PROFILE_MIN_CONTEXT_WINDOW_TOKENS_BY_CLASS = {
      "256k": 262_144,
      "1m": 1_000_000,
  }
  ```
- `dayu/runtime/config_loader.py:1320-1342` — 新增 `_validate_execution_profile_context_window_pair()` 校验 helper，在 `min_context_window_tokens != expected` 时抛出 `ConfigFieldError`
- `dayu/runtime/config_loader.py:1242-1246` — 在 `_parse_execution_profile` 中调用交叉校验，早于字段解析后、构造 dataclass 前
- `tests/runtime/test_config_loader.py:657-682` — `test_execution_profile_context_window_pair_must_be_consistent` 参数化覆盖两个矛盾组合：
  - `("1m", 262144)` → 期望 fail fast
  - `("256k", 1000000)` → 期望 fail fast
- 程序化验证确认默认 config 中 `standard-256k` 为精确 `262144`，`standard-1m` 为精确 `1000000`

---

## 未新增 Host Public API、Engine Code 或自动 Profile 切换

**PASS。**

- `git diff` 中无 `dayu/host/`、`dayu/engine/` 文件变更
- `_select_execution_profile_id` 逻辑不变：只接受 `explicit_profile_id` 或 `default_execution_profile_id`
- 无新增 `standard` alias、无 profile 自动切换逻辑

---

## 验证结果汇总

| 验证项 | 命令 | 结果 |
|---|---|---|
| Focused tests + smoke | `pytest tests/runtime/test_config_loader.py tests/runtime/test_assembly_helpers.py tests/service/test_host_assembly.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q` | **56 passed** |
| Boundary tests | `pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q` | **13 passed** |
| Pyright | `python -m pyright dayu/runtime dayu/service tests/runtime tests/service` | **0 errors, 0 warnings** |
| Whitespace | `git diff --check` | **通过** |
| Old alias scan | `rg '"standard"' dayu/config/execution_profiles.json; rg 'profile_id.*"standard"[^-]' dayu/` | **干净** |
| F2 `__all__` | programmatic assert | **通过** |
| F3 交叉校验值 | programmatic assert | **通过** |

---

## Residual Risk

与 Fix Addendum 一致：全量测试未运行，本 re-review 仅运行 focused tests + boundary tests + pyright + whitespace。未触及 Host public API、Engine code 或禁止修改清单。
