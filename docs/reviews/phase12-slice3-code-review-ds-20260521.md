# Code Review — Phase 12 Slice 3: ConfigLoader Runtime Assembly

## Scope

- Mode: current changes
- Branch: `docs/phase12-design-discussion`
- Base: HEAD (未提交改动)
- Output file: `docs/reviews/phase12-slice3-code-review-ds-20260521.md`
- Reviewer role: AgentDS
- Included scope:
  - 新增 `dayu/runtime/config_loader.py`（主实现）
  - 新增四个配置文件 `models.json`, `execution_profiles.json`, `host_runtime.json`, `tool_discovery.json`
  - 新增测试 `tests/runtime/test_config_loader.py`, `tests/engine/test_config_models.py`
  - 修改 `dayu/runtime/__init__.py`, `tests/runtime/test_import_boundary.py`
  - 删除 `dayu/config/llm_models.json`, `dayu/config/run.json`, `tests/engine/test_config_llm_models.py`
  - 修改 README 文件（根、dayu、config、tests）
  - 修改 `docs/host/implementation-control.md`
- Excluded scope:
  - 预存文档 `docs/reviews/phase12-slice3-implementation-codex-20260521.md`（仅作参照，不 review）
  - 未在本 slice scope 内的 `dayu.engine`, `dayu.host`, `dayu.service`, `dayu.ui`, `dayu.fins` 模块
- Parallel review coverage: 无（单 reviewer）

## 验证执行摘要

| 命令 | 结果 |
|------|------|
| `pytest tests/runtime/test_config_loader.py tests/runtime/test_import_boundary.py tests/engine/test_config_models.py -q` | 18 passed |
| `python -m pyright dayu/runtime/config_loader.py tests/runtime/test_config_loader.py tests/engine/test_config_models.py` | 0 errors, 0 warnings, 0 informations |
| `grep "llm_models\|run\.json" dayu/config/README.md` | 仅一处"已删除，不再提供兼容读取路径"声明 |
| `grep -r "llm_models\|run\.json" dayu/ --include="*.py" \| grep -v config_loader.py \| grep -v __pycache__` | 仅在 `dayu/engine/contracts/runner_spec.py` docstring 中以 "OLD" 前缀注释残留（非代码路径） |

## Findings

### 1-未修复-中-extends 父项缺失场景无测试覆盖

- **入口/函数**: `_resolve_record` → `_parse_extends_field` → 父项 `records.get(record_id)` 返回 `None` 分支与 `parent_id not in records` 分支
- **文件(行号)**: `dayu/runtime/config_loader.py:819-832`
- **输入场景**: 配置文件中 record 声明 `"extends": "nonexistent_parent"`，父 id 在 records map 中不存在
- **实际分支**: `parent_id not in records` 为 `True`，抛出 `ConfigExtendsError("extends missing parent: nonexistent_parent")`
- **预期行为**: 抛出结构化错误，fail fast
- **实际行为**: 代码逻辑正确（行 830-833），但无任何测试输入覆盖此分支
- **直接证据**: 对 `tests/runtime/test_config_loader.py` 全文搜索无 `missing.*parent`、`parent.*not.*found` 等匹配；`_resolve_record` 行 830-833 分支在 `pytest --cov` 下应显示未覆盖
- **影响**: 继承父项缺失的错误处理在静态代码阅读中正确，但缺少回归保护。未来修改 `_resolve_record` 的参数传递或条件顺序时，可能意外进入错误分支或产生误导错误消息
- **建议改法和验证点**: 新增 `test_extends_parent_not_found_fails_fast`，在 models.json 中声明 `extends: "nonexistent"`，断言 `ConfigExtendsError` 且 match "missing parent"
- **修复风险（低）**: 仅新增测试，不修改生产代码
- **严重程度（中）**: 已有正确实现但缺少测试，属于测试缺口，影响可维护性

### 2-未修复-低-extends 字段为非字符串非列表非法类型无独立测试

- **入口/函数**: `_parse_extends_field`
- **文件(行号)**: `dayu/runtime/config_loader.py:862-865`
- **输入场景**: 配置中 `"extends": 123` 或 `"extends": true` 或 `"extends": {}`
- **实际分支**: 不命中`isinstance(value, list)`，命中 `not isinstance(value, str)`，抛出 `ConfigExtendsError`
- **预期行为**: fail fast
- **实际行为**: 代码逻辑正确（行 864-865），但无单独测试；现有 `test_multiple_extends_fails_fast` 仅覆盖 list 类型
- **直接证据**: `test_multiple_extends_fails_fast` 的 extends 值为 `["base-model", "other-model"]`（list），无 int/bool/object 类型测试
- **影响**: 轻微。非法类型场景被现有代码路径正确覆盖，但缺少回归保护
- **建议改法和验证点**: 可选新增参数化测试覆盖 `extends: 123`, `extends: true`, `extends: {}`
- **修复风险（低）**: 仅测试
- **严重程度（低）**: 现有实现正确，代码路径简单不易回归

### 3-未修复-低-lane 容量 claim_ttl ≤ heartbeat 错误场景无测试

- **入口/函数**: `_parse_lane_capacity`
- **文件(行号)**: `dayu/runtime/config_loader.py:1535-1536`
- **输入场景**: lane capacity 配置中 `claim_ttl_seconds: 5.0` 且 `heartbeat_interval_seconds: 10.0`（claim_ttl 不大于 heartbeat）
- **实际分支**: `claim_ttl_seconds <= heartbeat_interval_seconds` 为 `True`，抛出 `ConfigFieldError`
- **预期行为**: fail fast
- **实际行为**: 代码逻辑正确，但无测试覆盖
- **直接证据**: 所有测试 fixture 中 `claim_ttl_seconds > heartbeat_interval_seconds`（如默认配置 30.0 > 5.0，test fixture 10.0 > 2.0）；无法找到触发此分支的测试
- **影响**: 轻微。当前默认值和 fixture 值均满足条件，但缺少边界条件回归
- **建议改法和验证点**: 可选新增 `test_lane_capacity_claim_ttl_must_exceed_heartbeat`，在 workspace fixture 中设置非法值
- **修复风险（低）**: 仅测试
- **严重程度（低）**: 实现正确，场景触发概率低，影响面小

## Open Questions

- `RunnerKind` 当前仅定义 `OPENAI_COMPATIBLE`，若后续接入 Anthropic Messages API 或 Gemini API 作为 runner，需扩展枚举。当前实现通过 `RunnerKind(value)` 在 parse 时 reject 未识别值（fail fast），属于合理设计，不需要提前添加占位枚举。
- 工具发现 provider 仅允许 `EXPLICIT_PROVIDER`、`CONFIG_BINDING`、`PACKAGE_ENTRYPOINT` 三种 source_kind，排除了 `SERVICE_COMPOSITION`。实现报告说明这是刻意的（工具发现不需要 service composition），若后续需要此 kind，需同步修改 `_TOOL_DISCOVERY_SOURCE_KINDS`。

## Residual Risk

- **extends 自循环（`extends` 指向自身）**：代码在 `_resolve_record` 行 816-818 通过 `visiting` 栈可检测自循环，但无独立测试覆盖。
- **extends 空字符串**：`_parse_extends_field` 行 866-867 拒绝空字符串，无独立测试。
- **workspace 顶层未知字段静默忽略**：`_overlay_roots` 不对顶层 object 做 `_require_exact_fields`，workspace 中拼写错误（如 `default_profiles_id` 误作 `default_profile_id`）会被静默忽略，不会报错。当前每个 `load_*` 方法通过 `_require_str_field` 单独读取顶层字段，若 typo 导致该字段缺失，会触发必填字段错误；但若 typo 命中map_fields 导致意外的 map overlay，则可能产生难以排查的静默行为。
- **empty collections 边界**：`_parse_model_config` 和 `_parse_execution_profile_map` 对空 models/profiles map 有显式拒绝（行 529-530, 962-963），但无对应测试；当前包内默认配置和服务测试 fixture 均不触发此分支。
- **双浮点相等性**：`_require_float_field` (行 2083) 将 int 值转为 float，在 `claim_ttl_seconds <= heartbeat_interval_seconds` 比较中使用浮点 `<=`，理论上有浮点精度风险。但在 JSON 解析路径中，两值均为配置文件字面量解析结果，整数字面量不会产生精度误差，实际风险极低。
- **旧文件名在 `_LEGACY_CONFIG_FILES` 常量中保留**：`config_loader.py:24-26` 定义了 `_LEGACY_CONFIG_FILES` 并导出 `legacy_config_file_names()` 函数。这是故意保留的诊断工具（详见实现报告），不是兼容读取路径，不违反旧配置删除约束。

## Verdict

**PASS** — blocking findings count = 0

所有架构边界、schema/typed view、overlay/extends、secret/env 保留、旧配置删除、项目硬约束（中文 docstring、严格类型、禁止 Any/object）均通过审查。三个 findings（2 low, 1 medium）均为测试覆盖缺口，不涉及生产代码缺陷。

- 已验证：所有测试 18 passed，pyright 0 errors，import boundary 扫描覆盖 `config_loader.py`，旧文件已物理删除且无代码读取路径
- 未运行（无需）：端到端集成测试（Service 层 mapping 属后续 slice），workspace 实际目录 overlay 集成测试（需完整 workspace 环境）
