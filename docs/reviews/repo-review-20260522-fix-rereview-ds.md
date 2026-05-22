# Full Repository Review — Accepted-Fix Scoped Re-Review (AgentDS)

## Scope

- Mode: scoped re-review of controller-accepted fixes A1-A6 only.
- Branch: `docs/phase12-design-discussion`
- Date: 2026-05-22 09:48:56
- Output file: `docs/reviews/repo-review-20260522-fix-rereview-ds.md`
- Source review artifacts: `repo-review-20260522-070034.md`, `repo-review-20260522-070045.md`
- Controller adjudication: `repo-review-20260522-controller-adjudication.md`
- Fix artifact: `repo-review-20260522-fix-codex.md`

### Included scope (A1-A6 only)

| Item | Files |
|------|-------|
| A1 | `tests/contracts/test_tool_schema.py` |
| A2 | `tests/host/test_import_boundary.py` |
| A3 | `dayu/contracts/tool_schema.py`, `tests/contracts/test_tool_schema.py` |
| A4 | `dayu/host/open_host.py` |
| A5 | `dayu/runtime/assembly.py`, `tests/runtime/test_assembly_helpers.py` |
| A6 | `dayu/runtime/config_loader.py`, `tests/runtime/test_config_loader.py` |

### Excluded scope

Engine findings, durable layer dependency split, `host/api.py` module split, `LaneController` refactoring, README dead-link fixes, and all other deferred items from the controller adjudication.

---

## Per-Item Verification

### A1 — ToolTruncateSpec 测试同步 ✓

- **入口**: `tests/contracts/test_tool_schema.py`
- **变更**:
  - `test_truncate_spec_rejects_inconsistent_enabled_strategy_limits` 的 parametrize 不再包含 `(True, TEXT_CHARS, {})` 失败用例（旧期望已移除）。
  - 新增 `test_enabled_truncate_spec_allows_empty_limits_for_runtime_policy_fill`（line 27-39），显式证明 `enabled=True, strategy=TEXT_CHARS, limits={}` 构造成功且 `spec.limits == {}`。
- **合约对齐**: `tool_schema.py:170` 使用 `issubset({expected_limit_key})`，空 dict 是合法子集；`tool_schema.py:181-182` 对 `limit is None` 直接 return，允许声明期省略 limit 由 runtime assembly policy default fill。
- **结论**: 测试已同步到 Phase 12.1 合约，无误报。

### A2 — fetch_more ownership allowlist ✓

- **入口**: `tests/host/test_import_boundary.py:42`
- **变更**: `FETCH_MORE_ALLOWED_RELATIVE_FILES` 从 `{"host/tool_runtime.py", "host/tooling.py"}` 扩展为 `{"host/tool_runtime.py", "host/tooling.py", "runtime/tools_discovery.py"}`。
- **合约对齐**: `dayu/runtime/tools_discovery.py:28` 定义 `_RESERVED_FRAMEWORK_TOOL_NAMES: frozenset[str] = frozenset({"fetch_more"})` 是 layer-neutral 的框架保留工具名声明，`ToolsDiscovery` 在 line 580 检查并拒绝业务工具占用保留名。该文件是 `fetch_more` 语义的正确所有权 owner 之一。
- **结论**: allowlist 更新准确，边界测试不再误报。

### A3 — Disabled ToolTruncateSpec fail-fast ✓

- **入口**: `dayu/contracts/tool_schema.py:161-171`
- **变更**: disabled 分支（`not self.enabled`）新增三个 fail-fast 检查：
  - line 166-167: `if self.target_field is not None: raise ValueError("disabled ToolTruncateSpec must not define target_field")`
  - line 168-169: `if self.field_path is not None: raise ValueError("disabled ToolTruncateSpec must not define field_path")`
  - line 170-171: `if self.ttl_seconds is not None: raise ValueError("disabled ToolTruncateSpec must not define ttl_seconds")`
- **测试覆盖**: `tests/contracts/test_tool_schema.py:84-107` 新增 parametrized 测试 `test_disabled_truncate_spec_rejects_target_or_ttl_fields`，覆盖 `(target_field="content")`, `(field_path=("items",))`, `(ttl_seconds=60)` 三种场景，均断言 `ValueError` 且匹配 `"disabled ToolTruncateSpec"`。
- **结论**: disabled spec 携带 target/TTL 字段时正确 fail-fast，测试完备。

### A4 — `_PublicHostHandle._closed` bool 注解 ✓

- **入口**: `dayu/host/open_host.py:161`
- **变更**: `__init__` 中 `self._closed: bool = False`（此前无类型注解）。
- **验证**: `__slots__` 包含 `"_closed"`（line 133），注解行位于 `__init__` 赋值处，`_raise_if_closed`（line 388-396）和 `_watch_session_events_after`（line 346）均以 `bool` 语义读取 `self._closed`。
- **结论**: 类型注解补全正确，无行为变化。

### A5 — `MergedAgentPolicyConfig.field_sources` runtime-immutable ✓

- **入口**: `dayu/runtime/assembly.py:545-560`
- **变更**:
  - `assembly.py:14` 新增 `from types import MappingProxyType`
  - `merge_agent_policy_config` 返回的 `field_sources` 从裸 `dict[str, str]` 改为 `MappingProxyType({...})`
  - Public 类型 `field_sources: Mapping[str, str]` 不变（line 208）
- **测试覆盖**: `tests/runtime/test_assembly_helpers.py:175-191` 新增 `test_merge_agent_policy_config_field_sources_is_runtime_immutable`，通过 `cast(MutableMapping, merged.field_sources)["key"] = "mutated"` 断言 `TypeError`。
- **安全性**: 值为 `str` 类型，无嵌套可变数据，`MappingProxyType` 足以保证运行时不可变。
- **结论**: 实现正确，测试完备。

### A6 — ConfigLoader 非空 guard ✓

- **入口**: `dayu/runtime/config_loader.py`
- **变更**（四个 guard 点）:

| Guard | 位置 | 错误消息 |
|-------|------|----------|
| `host_runtime.runtimes` | line 728-729 | `"host_runtime runtimes must not be empty"` |
| `execution_profiles.agent_policy_profiles` | line 1525-1528 | `"execution_profiles agent_policy_profiles must not be empty"` |
| `tool_discovery.providers` | line 811-812 | `"tool_discovery providers must not be empty"` |
| `runtime_lanes.lanes` | line 767-768 | `"runtime_lanes.json lanes must not be empty"` (已有，未改) |

- **测试覆盖** (`tests/runtime/test_config_loader.py`):

| 测试 | 行号 | 覆盖 guard |
|------|------|-----------|
| `test_agent_policy_profiles_must_not_be_empty` | 568-588 | agent_policy_profiles |
| `test_host_runtime_catalog_must_not_be_empty` | 591-605 | host_runtime.runtimes |
| `test_runtime_lanes_catalog_must_not_be_empty` | 608-626 | runtime_lanes.lanes (regression) |
| `test_tool_discovery_providers_must_not_be_empty` | 629-642 | tool_discovery.providers |

- **验证**: 每个测试构造空 catalog 的独立 fixture，断言 `ConfigFieldError` 且匹配对应错误消息。所有 guard 都在 `ConfigLoader.load_*` 方法内、typed config 返回前触发，符合 controller 要求的 "fail during config load rather than later assembly"。
- **结论**: 四个 guard 全部到位，测试完备，guard 位置正确。

---

## Cross-Cutting Check: No New Blockers

| 检查项 | 结果 |
|--------|------|
| 分层 import 方向 | 无新增违规。A5 仅新增 `types.MappingProxyType`（标准库），A3 仅修改已有 `__post_init__` 分支。 |
| 类型安全 | Controller 确认 `pyright dayu/contracts dayu/runtime dayu/host tests/contracts tests/runtime tests/host` → 0 errors。 |
| 测试通过 | Controller 确认全部相关测试套件 passed（56 + 213 + 64）。 |
| 行为回归 | A1 移除旧失败期望、新增通过测试；A2 扩展 allowlist 无功能影响；A3 新增 fail-fast 不改变已合法路径；A4 纯注解；A5 `MappingProxyType` 阻止写入，此前无代码写入该字段；A6 新增 fail-fast 仅影响此前静默通过的空 catalog 配置。 |
| 跨项冲突 | 无。A1-A6 修改的文件集合互不重叠（`tool_schema.py` 的 A3 改动与 A1 测试改动独立）。 |
| `MappingProxyType` 安全性 | `field_sources` 的 value 类型为 `str`，无嵌套可变数据，`MappingProxyType` 提供的浅层不可变足够。 |
| 非空 guard 一致性 | 四个 guard 风格统一：均在 `_resolve_record_map` 后、typed config 构造前检查，使用 `ConfigFieldError`，错误消息格式一致。 |

---

## Findings

未发现实质性问题。

---

## Open Questions

无。

## Residual Risk

1. **A5 `MappingProxyType` 对 pickle/copy 的兼容性**：`MappingProxyType` 不可 pickle。当前 `MergedAgentPolicyConfig` 是 frozen dataclass，未观察到跨进程传递需求。若未来需要序列化，需替换为 `tuple[tuple[str, str], ...]` 或其他可序列化不可变类型。
2. **A6 空 catalog guard 与 workspace overlay 的交互**：workspace overlay 可能通过删除所有 provider 来禁用工具发现。当前 A6 guard 会阻止这种用法。这是设计决策（controller 已裁决），但如果未来需要"全部禁用"语义，需要额外机制（如显式 `enabled: false` 顶层开关）。

---

## Conclusion

**PASS** — 0 blocking findings。

A1-A6 全部已正确收口：
- A1 测试已同步到 Phase 12.1 合约，不再误报。
- A2 allowlist 已包含 `runtime/tools_discovery.py`，边界测试通过。
- A3 disabled spec 携带 target/TTL 字段正确 fail-fast，测试覆盖三种场景。
- A4 `_closed` 已添加 `bool` 类型注解。
- A5 `field_sources` 通过 `MappingProxyType` 实现运行时不可变，测试验证 mutation 抛 `TypeError`。
- A6 四个非空 guard 全部到位，每个 guard 有对应测试。
- 未引入新 blocker、未扩散类型错误、未违反分层约束。
