# Phase 12 Aggregate Fix Digest Codex

## Gate

- Gate: Phase 12 aggregate fix
- Worker: AgentCodex aggregate fix worker
- Accepted finding: P12-AGG-F1
- Source adjudication: `docs/reviews/phase12-aggregate-deepreview-controller-adjudication-20260521.md`

## Scope

本次只处理 P12-AGG-F1：抽取 `dayu/runtime/tools_discovery.py` 与
`dayu/runtime/scene_prepare.py` 中重复的 canonical JSON SHA-256 digest
与 JSON value normalization 逻辑。

## Changed Files

- `dayu/runtime/_digest.py`
  - 新增层中立私有 helper 模块。
  - 提供 `canonical_json_digest` 与 `normalize_json_value`。
  - 仅依赖标准库与 `dayu.contracts.JsonValue`。
- `dayu/runtime/tools_discovery.py`
  - 删除本地 `_canonical_json_digest` 与 `_normalize_json_value`。
  - 工具声明 digest 与 schema properties 规范化改为复用 `dayu.runtime._digest`。
- `dayu/runtime/scene_prepare.py`
  - 删除本地 `_canonical_json_digest` 与 `_normalize_json_value`。
  - manifest、prepared scene、assembly input 的 canonical JSON digest 改为复用
    `dayu.runtime._digest`。
  - 保留本地 `_text_digest`，因为 fragment 原文摘要不是本次重复 canonical JSON
    helper 抽取目标。

## Public API And Output Preservation

- 未修改 public API 名称。
- 未修改 dataclass 输出结构。
- 未修改 digest 输入投影字段。
- canonical JSON dump 参数保持为 `sort_keys=True`、`separators=(",", ":")`、
  `ensure_ascii=False`、`allow_nan=False`，摘要前缀保持 `sha256:`。
- 公开 digest 输出由既有稳定性与敏感性测试继续保护：
  `tests/runtime/test_tools_discovery_digest.py`、`tests/runtime/test_scene_prepare.py`
  已在本次验证中通过。

## Validation Results

- `source .venv/bin/activate && pytest tests/runtime/test_tools_discovery_digest.py tests/runtime/test_tools_discovery.py tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py tests/runtime/test_scene_assets_migration.py -q`
  - Result: passed
  - Evidence: `48 passed in 0.29s`
- `source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q`
  - Result: passed
  - Evidence: `9 passed in 0.72s`
- `source .venv/bin/activate && pytest tests/runtime -q`
  - Result: passed
  - Evidence: `174 passed in 3.84s`
- `source .venv/bin/activate && python -m pyright dayu/runtime tests/runtime`
  - Result: passed
  - Evidence: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed

## Docs Decision

未更新 README。原因：本次变更是 `dayu.runtime` 私有 helper 抽取，不改变用户入口、
开发手册边界说明、公共契约、schema、命令或配置入口；用户 handoff 也禁止除非直接
需要时修改 README。

## Residual Risks

- 未新增私有 helper 直测；原因是现有 digest 稳定性、敏感性、runtime 边界、弱类型与
  完整 runtime 测试已覆盖本次行为不变要求。
- 未覆盖无效 JSON 运行时错误消息完全一致性；该路径不是公开契约，本次保证合法
  `JsonValue` 的 canonical digest 输出不变。
