# WU-TOOLS-01 Slice S6 Re-Review (AgentDS)

Gate: re-review
Work unit: WU-TOOLS-01
Slice: S6 fix — Controller accepted finding A1 only
Reviewer: AgentDS
Verdict: **PASS**

## Re-Review Scope

仅复核 Controller accepted finding A1 的 fix 是否充分，以及是否引入新 blocking regression。不扩大 unrelated Host 行为失败。

A1 fix 变更范围（`git diff HEAD` 确认）：
- `tests/host/test_import_boundary.py`：+30/-4 行
- `tests/README.md`：+3/-1 行

未触碰任何 `dayu/` 生产代码。

## 独立验证

| 验证项 | 命令 | 结果 |
|--------|------|------|
| import boundary + combined acceptance | `pytest tests/host/test_import_boundary.py tests/tools/test_combined_tools_acceptance.py` | 21 passed, 0 failed |
| 类型检查 | `pyright` | 0 errors, 0 warnings, 0 informations |
| diff 格式 | `git diff --check` | clean |
| 外部 blocker 未扩散 | `pytest tests/host/test_dispatch_scheduler.py tests/host/test_effective_execution_config.py tests/host/test_phase7_waiting_integration.py tests/host/test_resolve_wait_command.py` | 11 failed (与 fix 前相同) |

## Finding-by-Finding 复核

### A1.1: FETCH_MORE_DEFENSIVE_ALLOWED_RELATIVE_FILES — PASS

**变更**: `test_import_boundary.py:44-50`，新增 `FETCH_MORE_DEFENSIVE_ALLOWED_RELATIVE_FILES`，包含：
- `tools/_legacy_adapter/__init__.py`
- `tools/_legacy_adapter/definition_adapter.py`
- `tools/_legacy_adapter/registry_collector.py`

**验证**:

1. **allowlist 不包含 business provider**：三个条目均位于 `tools/_legacy_adapter/`，这是迁移适配层，非业务 provider。业务 provider 路径（`tools/doc_provider.py`、`tools/doc_tools.py`、`tools/web/`、`fins/tools/`）均不在 defensive allowlist 中。若 business provider 新增 `fetch_more` 引用，仍会被 `FETCH_MORE_OWNERSHIP_TOKEN in source` 捕获为 violation。

2. **防御性引用均为合法语义**（独立源码审查确认）：
   - `definition_adapter.py:42`：`_RESERVED_FETCH_MORE_TOOL_NAME = "fetch_more"` — reserved-name 常量，用于在 adapter 逻辑中检测并拒绝 business tool 占用 `fetch_more`。
   - `definition_adapter.py:435,462`：`raise ValueError("legacy adapter must not expose fetch_more as a business tool")` — 显式拒绝 business 暴露。
   - `__init__.py:5`、`registry_collector.py:6`：docstring 中说明不注册/不暴露 `fetch_more`。

3. **allowlist 粒度正确**：三个条目精确到文件级别，不是目录级通配。`_legacy_adapter/` 目录下若有新增文件引用 `fetch_more` 但不在 allowlist 中，会被捕获。

**结论**: allowlist 窄且正确，不会导致 business provider 暴露 `fetch_more` 的漏检。

### A1.2: OLD_FETCH_MORE_PROJECTION_TOKENS 扫描 — PASS

**变更**: `test_import_boundary.py:52-56`，新增 `OLD_FETCH_MORE_PROJECTION_TOKENS`，对 `dayu/` 全量源码做 `token in source` 扫描：
- `fetch_more_args`
- `project_for_llm`
- `continuation_hint`

**验证**:

1. **扫描范围正确**：扫描 `dayu_root`（即 `dayu/` 源码目录），不扫描 `tests/` 自身，因此 token 常量定义不会自伤。

2. **无 allowlist 逃逸**：OLD token 扫描无任何 allowlist——即使 ToolRuntime owner 或 legacy adapter 文件也不豁免。这是正确的，因为没有任何当前代码应该引用 OLD projection token。

3. **子串匹配不会误伤常量自身**：token 常量（`"fetch_more_args"` 等）定义在 `tests/host/test_import_boundary.py` 中，该文件不在 `dayu_root` 扫描范围内。`dayu/` 下的源码不会定义这些常量名。

4. **误报风险评估**：三个 token 均为 OLD API surface 专用名称，非通用术语。在 `dayu/` 源码中意外出现的概率极低。即使出现在注释中，也应被标记——注释中的 OLD token 同样会造成混淆。

**结论**: OLD projection token 扫描有效、无自伤、无逃逸。

### A1.3: compaction_operation.py allowlist — PASS

**变更**: `test_import_boundary.py:61`，在 `HOST_ENGINE_CONTRACT_ALLOWED_MODULES` 中新增 `compaction_operation.py`。

**验证**:

1. **Engine 依赖为 contracts，非 implementation**：`dayu/host/compaction_operation.py:23-24` 导入的是 `dayu.engine.contracts.agent_run` 和 `dayu.engine.contracts.engine_events`，属于 Engine 公共契约层，非 Engine 实现层。这与 Host -> Engine contract 的合法依赖方向一致。

2. **与已有 allowlist 模式一致**：`dispatch.py`、`llm_compaction.py`、`local_proxy.py` 等已 allow 的模块同样是 Host 本地执行边界模块，沿依赖方向调用 Engine contracts。`compaction_operation.py` 的模块定位（"Host 内部 context compaction operation helper"）完全符合此模式。

3. **边界不扩大**：allowlist 新增仅此一个文件，没有放宽到目录级或放宽 import 前缀检查逻辑（`_matches_prefix(module, ("dayu.engine",))` 逻辑不变）。

**结论**: `compaction_operation.py` 的 Host -> Engine contract 依赖合法，allowlist 更新正确。

### A1.4: tests/README.md 更新 — PASS

**变更**: `tests/README.md` 两处修改：
1. `tests/tools/` 段落新增 combined tools acceptance 一行描述。
2. `tests/host/` import boundary 段落更新，反映 defensive allowlist、OLD projection token 扫描和 compaction operation allowlist。

**验证**:

1. **触发规则正确**：`tests/` 变更 → 更新 `tests/README.md`。变更内容属于 `tests/README.md` 职责范围（测试分层与覆盖描述）。

2. **描述准确**：combined tools acceptance 描述与 `test_combined_tools_acceptance.py` 的 8 个测试用例实际覆盖一致。import boundary 描述准确反映了 `FETCH_MORE_DEFENSIVE_ALLOWED_RELATIVE_FILES`、`OLD_FETCH_MORE_PROJECTION_TOKENS` 和 `compaction_operation.py` allowlist 的变更。

3. **不越界**：仅更新 `tests/README.md`，不触碰其他 README。与 S6 未修改生产代码的事实一致。

**结论**: README 更新准确、合规。

## 外部 Blocker 状态

| Group | Count | 状态 |
|-------|-------|------|
| Proactive compaction (missing proposal manifest ref) | 7 | 未变，仍为 external blocker |
| Effective execution config (system prompt envelope mismatch) | 2 | 未变，仍为 external blocker |
| Wait/Resume (resume request text mismatch) | 2 | 未变，仍为 external blocker |

A1 fix 未引入新失败，外部 blocker 数量从 13 降至 11（import boundary 2 个已修复）。

## Adversarial Pass

| 攻击面 | 问题 | 结论 |
|--------|------|------|
| Business provider 伪装为 defensive 文件 | `_legacy_adapter/` 是迁移适配层，新增 business provider 不会放入此目录；即使放入，code review gate 会阻止 | 风险极低，非 blocking |
| OLD token 子串误报 | token 均非通用术语，在 `dayu/` 中意外命中的概率极低；即使误报也是 safe-fail（拒绝而非放行） | 非 blocking |
| OLD token 子串漏报 | 子串匹配比词边界匹配更保守，不会漏报 | 无漏报风险 |
| compaction_operation.py 后续引入 Engine implementation 依赖 | 该文件当前仅导入 Engine contracts；若将来引入 Engine implementation import，本次 allowlist 不会阻止（因为已经在 allowlist 中） | 理论风险，但该文件的实际职责不需要 Engine implementation；且其他 gate（code review、deepreview）会阻止 |

## 结论

A1 fix 充分解决了 Controller accepted finding：
- `_legacy_adapter` 的防御性 `fetch_more` 引用通过窄 allowlist 正确处理，business provider 防线未被削弱。
- OLD fetch-more projection token 扫描有效且无自伤。
- `compaction_operation.py` 的 Host -> Engine contract 依赖合法，allowlist 更新符合既有模式。
- `tests/README.md` 更新准确。

未引入新 blocking regression。其余 11 个 Host 失败保持 external blocker / separate Host follow-up 状态，与 fix scope 一致。

**Verdict: PASS**
