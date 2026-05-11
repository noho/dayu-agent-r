# P8.5 Tool Truncation Contract Cleanup Code Review

- review gate name: `code review`
- reviewed target: current workspace diff against `d0ab366 gateflow: accept host p8.5 slice 6`
- implementation artifact: `docs/host/phase8.5-tool-truncation-contract-cleanup-implementation-report.md`
- reviewer conclusion: fail; 1 finding requires controller decision
- artifact path: `docs/host/phase8.5-tool-truncation-contract-cleanup-code-review.md`

## Scope Checked

- Public contract boundary: `dayu.contracts`, `dayu.engine`, `ToolResultSuccess`.
- Engine boundary: ordinary JSON projection and Host-private truncation type isolation.
- Host runtime behavior: truncated result value injection, `fetch_more` next chunk, no-more path, object/scalar payloads.
- Serializer/schema: new ordinary value shape and legacy top-level truncation handling.
- Memory / RunInput: raw cursor, raw scope token, reusable `fetch_more_args` exclusion.
- Trace/analyzer: ordinary payload truncation/fetch_more diagnostics.
- Credential scrub: explicit credential scrub only.
- Tests/docs sync.

## Validation Commands

- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: passed, `0 errors, 0 warnings, 0 informations`.
- `source .venv/bin/activate && pytest tests/contracts tests/engine -q`
  - Result: passed, `327 passed`.
- `source .venv/bin/activate && pytest tests/host -q`
  - Result: passed, `376 passed`.
- `source .venv/bin/activate && pytest tests/utils/test_analyze_tool_trace_host.py -q`
  - Result: passed, `17 passed`.
- `rg "ToolTruncationInfo|truncation=" dayu tests`
  - Result: only negative export tests mention `ToolTruncationInfo`; no `truncation=` constructor use remains.
- `rg "ToolTruncationInfo" dayu/contracts dayu/engine dayu/host dayu/host/README.md tests/README.md docs/host/design.md docs/host/migration-plan.md`
  - Result: only `docs/host/migration-plan.md` records the fixed residual.
- `git diff --check d0ab366 --`
  - Result: passed.
- Additional serializer probe with an old top-level `ToolResultSuccess.truncation` payload:
  - Result: current decoder returned `ToolResultAcceptedData(...)` and silently dropped old `truncation`.

## Findings

### 1-未修复-[中]-serializer 仍接受旧 top-level ToolResultSuccess.truncation 行并静默丢弃
- **入口/函数**: `deserialize_run_event_data(...) -> _decode_outcome(...) -> _decode_result_success(...)`
- **文件(行号)**: `dayu/host/_run_event_serializer.py:85`, `dayu/host/_run_event_serializer.py:748`, `dayu/host/_run_event_serializer.py:776`, `dayu/host/_run_event_serializer.py:800`
- **输入场景**: durable EventLog 中存在 P8.5 follow-up 前写出的 `TOOL_RESULT_ACCEPTED` raw JSON，`outcome.result` 仍是旧形状：`{"ok": true, "value": ..., "truncation": {"cursor": ..., "scope_token": ..., "scope_hash": ..., "has_more": true, ...}, "meta": null}`，且外层 `schema_version` 仍为当前的 `1`。
- **实际分支**: `deserialize_run_event_data` 只校验外层 `schema_version/type_name/fields`；`_decode_outcome` 对 `kind == "completed"` 调用 `_decode_result_success(value.get("result"))`；`_decode_result_success` 只读取 `meta` 和 `value.get("value")`，没有校验 success result 的允许字段集合，也没有拒绝旧 top-level `truncation`。
- **预期行为**: 按本 work unit intent 和 serializer 模块约束，`ToolResultSuccess.truncation` 已不是当前 schema；schema 变化按全新起库处理，不应兼容读取旧 top-level truncation 行。旧形状至少应 fail-fast，而 ordinary value 内的 `value["truncation"]` 才应 roundtrip 保留。
- **实际行为**: 旧 top-level `truncation` raw payload 会被成功反序列化为 `ToolResultSuccess(ok=True, value=..., meta=...)`，旧 truncation 被静默丢弃。额外验证探针返回了 `ToolResultAcceptedData(...)`，没有抛错。
- **直接证据**: 模块头声明 `schema_version` 当前固定为 `1` 且 schema 变化时“按全新起库处理，禁止旧库兼容读取”；`CURRENT_SCHEMA_VERSION` 仍是 `1`（line 85）；encoder 只写 `ok/value/meta`（lines 784-797）；decoder 未检查旧 `truncation` 键并直接返回 `ToolResultSuccess(value=value.get("value"), meta=meta)`（lines 808-826）。现有 serializer 测试只覆盖 ordinary `value["truncation"]` roundtrip（`tests/host/test_phase6_run_event_serializer.py:139-190`），没有覆盖旧 top-level truncation reject。
- **影响**: 旧库或混入旧 schema row 时不会暴露为 schema mismatch，read model / projection 会继续运行但丢失截断诊断；这削弱“全新 schema 起库、不做旧兼容读取”的边界，也可能让旧 public contract residue 在 durable 数据层被误判为已清理。
- **建议改法和验证点**: 在 `_decode_result_success` 对 success result 字段做封闭校验，当前仅允许 `ok/value/meta`，遇到 top-level `truncation` 或其他未知字段 fail-fast；补 `tests/host/test_phase6_run_event_serializer.py` 用旧 top-level truncation raw payload 断言 `deserialize_run_event_data` 抛 `ValueError`，并保留 ordinary `value["truncation"]` roundtrip 测试。
- **修复风险（低/中/高）**: 中。新增封闭字段校验可能暴露其它历史宽松 decoder 行为；但影响面集中在 serializer schema 边界，符合当前全新 schema 约束。
- **严重程度（低/中/高/严重）**: 中
- **Controller decision status**: pending-controller-decision

## Pass Evidence

- `ToolTruncationInfo` 已从 `dayu.contracts.__all__`、`dayu.engine.__all__` 和 Engine imports 删除；负向 export 测试覆盖 `dayu.contracts` / `dayu.engine`。
- `ToolResultSuccess` 当前只有 `ok/value/meta` 字段，未保留 `truncation` 字段。
- Engine `_project_tool_success_for_llm` 只对 Mapping 做普通 JSON 透传，对非 Mapping 包装为 `{"content": value}`，没有 Host truncation 类型 import 或分支。
- `RuntimeTruncateManager` 通过 Host 私有 `_tool_result_truncation.inject_truncation_hint` 把 LLM-facing hint 注入 ordinary value；`fetch_more` no-more path 返回无 hint 的普通 value。
- Serializer roundtrip 测试保留 ordinary value 内 `truncation.fetch_more_args` 的 cursor / scope token，并继续 scrub 显式凭证。
- Memory 从 ordinary value 提取 truncation，只保留 cursor fingerprint / has_more，不保存 raw cursor、raw scope token 或可复用 `fetch_more_args`。
- Trace projection 从 ordinary value 提取 truncation 维度，analyzer 基于 ordinary `tool_name=="fetch_more"` 诊断，不依赖旧专属 projection 字段。
- Credential scrub 测试覆盖 `cursor`、`scope_token`、普通 `token` 不被误 scrub。
- README / design / migration-plan 当前描述与代码主路径一致；未发现恢复 public fetch_more/truncation/cursor contract 的文档表述。

## Open Questions And Residual Risk

- Open questions: none for review; finding 1 needs controller decision.
- Residual risk: real-provider smoke scripts were not run in this review; implementation report也标明未运行该非请求范围。
