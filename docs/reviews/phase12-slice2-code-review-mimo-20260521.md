# Code Review

## Scope

- Mode: current changes
- Branch: `docs/phase12-design-discussion`
- Base: `main`
- Output file: `docs/reviews/phase12-slice2-code-review-mimo-20260521.md`
- Included scope:
  - `dayu/runtime/tools_discovery.py` — digest helpers、source ref normalization、reserved framework tool name validation
  - `tests/runtime/test_tools_discovery.py` — source-ref assertion updates
  - `tests/runtime/test_tools_discovery_digest.py` — digest / source-ref / reserved-name coverage
  - `docs/host/implementation-control.md` — status update 和 implementation artifact 作为 evidence
- Excluded scope: Host durable state、Host command path、ToolRuntime accept barrier、Engine、Service、UI、Fins、ConfigLoader、ScenePrepare、prompt assets、config schema、业务工具
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- `SERVICE_COMPOSITION` source kind 未在 `test_source_refs_preserve_kind_id_version_and_replace_digest` 中显式测试；`_normalize_source_refs_with_digest` 对所有 source kind 使用相同 copy-and-replace 逻辑，行为隐式正确，但显式覆盖可增强回归保护。
- `tests/runtime/test_import_boundary.py` 没有针对 `tools_discovery.py` 的显式覆盖断言（不像 `lane.py` 和 `filelock.py` 各有专门断言）；递归 AST 扫描实际覆盖了该文件，但显式断言可防止扫描范围意外缩小。

## Validation Commands & Results

```text
source .venv/bin/activate && pytest tests/runtime/test_tools_discovery.py tests/runtime/test_tools_discovery_digest.py tests/host/test_tooling_options.py tests/host/test_package_exports.py -q
...................................                                      [100%]
35 passed in 0.82s
```

```text
source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q
......                                                                   [100%]
6 passed in 0.64s
```

```text
source .venv/bin/activate && python -m pyright dayu/contracts dayu/runtime dayu/host tests/runtime tests/host
0 errors, 0 warnings, 0 informations
```

```text
source .venv/bin/activate && git diff --check
(clean)
```

## Review Details

### Architecture Boundary

`dayu.runtime.tools_discovery` 只 import stdlib（`hashlib`、`importlib`、`importlib.metadata`、`json`、`collections.abc`、`dataclasses`、`types`、`typing`）和 `dayu.contracts`。未 import `dayu.host`、`dayu.engine`、`dayu.service`、`dayu.ui`、`dayu.fins` 或任何具体业务工具包。`tests/runtime/test_import_boundary.py` 的 AST 递归扫描覆盖了该文件。

### Digest Correctness

- digest 格式为 `sha256:<hex>`，输入为 `{"tools": [...]}` 的 canonical JSON。
- canonical JSON 使用 `sort_keys=True`、`separators=(",", ":")`、`ensure_ascii=False`、`allow_nan=False`，产出确定性 UTF-8 bytes 后 SHA-256。
- digest 投影只包含声明内容：tool name、LLM-facing schema（type、function.name、function.description、parameters.type、parameters.properties、parameters.required、parameters.additional_properties）、truncate spec（enabled、strategy、limits、target_field、field_path、ttl_seconds）、tags、display.name。
- digest 明确不包含 callable 引用、provider callable identity、模块路径对象身份、权限、lease、fencing、Host truth 或 owner。
- `_normalize_json_value` 正确处理 `bool`（先于 `int` 检查）、`None`、`int`、`float`、`str`、`list`、`Mapping`；对 `tuple` 等 `Sequence` 子类归一化为 `list`，对 `Mapping` 子类归一化为 `dict`，保证 JSON 序列化稳定性。
- `ToolTruncationStrategy.value` 返回 `str`，在 digest 投影中正确序列化。

### Source Ref Normalization

- `_normalize_source_refs_with_digest` 保留 `source_kind`、`source_id`、`version_ref`，用 discovery 计算的 provider digest 替换 `content_digest`。
- 同一 provider 的所有 source refs 共享同一 digest，符合 provider-level 声明摘要设计。
- provider 预填的 `content_digest` 被覆盖，discovery 是声明摘要真源。

### Reserved Framework Tool Name Validation

- `_validate_reserved_tool_names` 在 per-provider 循环内、`_validate_unique_tool_names` 之前执行，fail fast。
- `_RESERVED_FRAMEWORK_TOOL_NAMES` 包含 `fetch_more`，拒绝业务工具占用。
- 实现未修改 `ToolRuntime` framework tool 注入或 accept barrier。

### Test Coverage

- `test_tools_discovery_digest.py` 覆盖：digest 稳定性、callable identity 独立性、schema / truncate / tags / display 变化敏感性、source ref kind / id / version 保留 + digest 替换、`fetch_more` 拒绝。
- `test_tools_discovery.py` 更新了 source ref 断言，适配 discovery 现在填充 `content_digest` 的行为。
- 所有 35 个 focused tests 通过，6 个 import boundary / weak typing tests 通过，pyright 0 errors。

## Blocking Findings Count

0
