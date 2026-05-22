# Accepted Fix Scoped Re-Review - AgentMiMo

## Scope

- Mode: accepted-fix scoped re-review
- Branch: `docs/phase12-design-discussion`
- Base: `main`
- Output file: `docs/reviews/repo-review-20260522-fix-rereview-mimo.md`
- Included scope: A1-A6 fix items only
- Excluded scope: Engine findings, durable split, host/api.py split, LaneController refactor, README dead links (all deferred)
- Parallel review coverage: 无

## Reviewed Artifacts

- Source reviews: `repo-review-20260522-070034.md`, `repo-review-20260522-070045.md`
- Controller adjudication: `repo-review-20260522-controller-adjudication.md`
- Fix artifact: `repo-review-20260522-fix-codex.md`

## Findings

未发现实质性问题。

### A1-A6 逐项验证

#### A1: ToolTruncateSpec 测试同步 - PASS

- **实现验证**: `dayu/contracts/tool_schema.py:180-182` — enabled spec 空 limits 时 `limit is None` 触发 early return，不报错。符合 Phase 12.1 合约：声明期可省略 limit，由 runtime assembly policy default 补齐。
- **测试覆盖**: `tests/contracts/test_tool_schema.py:27-39` `test_enabled_truncate_spec_allows_empty_limits_for_runtime_policy_fill` 验证 enabled + strategy + 空 limits 构造成功。
- **收口**: 正确。旧测试中 `(enabled=True, strategy=TEXT_CHARS, limits={})` 期望失败的 case 已移除。

#### A2: fetch_more ownership allowlist - PASS

- **实现验证**: `tests/host/test_import_boundary.py:41-43` allowlist 为 `frozenset({"host/tool_runtime.py", "host/tooling.py", "runtime/tools_discovery.py"})`。
- **测试覆盖**: `test_fetch_more_token_stays_inside_toolruntime_owner_modules` 扫描 `dayu/` 下所有 `.py`，仅 allowlist 内文件可包含 `fetch_more` token。
- **收口**: 正确。`runtime/tools_discovery.py` 作为层中立 reserved tool-name 拒绝 owner，被 boundary test 认可。

#### A3: disabled ToolTruncateSpec fail-fast - PASS

- **实现验证**: `dayu/contracts/tool_schema.py:166-171` — disabled spec 对 `target_field`、`field_path`、`ttl_seconds` 各有独立 `ValueError` 检查，错误消息包含 `"disabled ToolTruncateSpec"`。
- **测试覆盖**: `tests/contracts/test_tool_schema.py:84-107` `test_disabled_truncate_spec_rejects_target_or_ttl_fields` parametrize 覆盖 `(target_field, None, None)`、`(None, field_path, None)`、`(None, None, ttl_seconds)` 三种 case。
- **收口**: 正确。disabled spec 携带任何 target/TTL 字段均 fail-fast。

#### A4: _PublicHostHandle._closed bool 注解 - PASS

- **实现验证**: `dayu/host/open_host.py:161` — `self._closed: bool = False`，显式 `bool` 注解。
- **行为影响**: 无运行期行为变更，纯类型安全加固。
- **收口**: 正确。

#### A5: MergedAgentPolicyConfig.field_sources runtime-immutable - PASS

- **实现验证**: `dayu/runtime/assembly.py:14` 导入 `MappingProxyType`，`assembly.py:545` 使用 `MappingProxyType({...})` 包装 field_sources dict。公开类型仍为 `Mapping[str, str]`，运行期不可变。
- **测试覆盖**: `tests/runtime/test_assembly_helpers.py:175-191` `test_merge_agent_policy_config_field_sources_is_runtime_immutable` 验证 mutation 抛出 `TypeError`。
- **收口**: 正确。`MappingProxyType` 阻止直接 mutation；值类型为 `str` 无需深冻结。

#### A6: ConfigLoader 非空 guard - PASS

- **实现验证**:
  - `config_loader.py:728-729`: `host_runtime.runtimes` 空 → `ConfigFieldError`
  - `config_loader.py:767-768`: `runtime_lanes.lanes` 空 → `ConfigFieldError`
  - `config_loader.py:1525-1528`: `agent_policy_profiles` 空 → `ConfigFieldError`
  - `config_loader.py:811-812`: `tool_discovery.providers` 空 → `ConfigFieldError`
- **测试覆盖**:
  - `test_host_runtime_catalog_must_not_be_empty` (L591-605)
  - `test_runtime_lanes_catalog_must_not_be_empty` (L608-626)
  - `test_agent_policy_profiles_must_not_be_empty` (L568-588)
  - `test_tool_discovery_providers_must_not_be_empty` (L629-642)
- **收口**: 正确。四个顶层 catalog 空配置均在加载期 fail-fast，不泄漏到 assembly 阶段。

## Open Questions

无。

## Residual Risk

- `MappingProxyType` 阻止浅层 mutation，但 `field_sources` 值类型为 `str`（不可变），无需深冻结。
- A6 guard 覆盖四个顶层 catalog；子 catalog（如 `models.models`、`execution_profiles.execution_profiles`）的非空 guard 由既有 `load_models` 和 `_parse_execution_profile_map` 处理，不在本次 fix scope。
- 本次 fix 不触及 Engine 行为、Host 持久化层或 broader runtime refactor，无跨层回归风险。

## Conclusion

**PASS**

A1-A6 全部正确收口，无新增 blocker。blocking finding count: 0。

Controller 验证结果（fix artifact 记录）：
- pytest focused: 56 passed
- pytest tests/runtime: 213 passed
- pytest tests/contracts + tests/host/test_import_boundary.py: 64 passed
- pyright: 0 errors
- git diff --check: clean
