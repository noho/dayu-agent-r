# P8.5 Tool Truncation Contract Cleanup Re-review

- review gate name: `re-review`
- reviewed target: P8.5 follow-up fix for accepted Finding 1
- source review artifact: `docs/host/phase8.5-tool-truncation-contract-cleanup-code-review.md`
- fix artifact: `docs/host/phase8.5-tool-truncation-contract-cleanup-fix-report.md`
- reviewer conclusion: accepted finding fixed; no new blocker identified
- artifact path: `docs/host/phase8.5-tool-truncation-contract-cleanup-rereview.md`

## Re-review Scope

- Finding 1: serializer 仍接受旧 top-level `ToolResultSuccess.truncation` 行并静默丢弃，应按新 schema fail-fast。
- 检查 `dayu/host/_run_event_serializer.py` 是否显式拒绝旧 top-level `result.truncation`。
- 检查 `tests/host/test_phase6_run_event_serializer.py` 是否覆盖旧 schema fail-fast，并保留 ordinary `value["truncation"]` roundtrip。
- 检查修复是否没有恢复 `ToolTruncationInfo`、`ToolResultSuccess.truncation` 或旧专属 `RunEventType`。
- 判断 validation 是否足以关闭该 finding；不裁决最终 commit gate。

## Evidence

- `dayu/host/_run_event_serializer.py:98` 定义 Host serializer 私有旧 schema 键名 `_RESULT_SUCCESS_TOP_LEVEL_TRUNCATION_KEY = "truncation"`。
- `dayu/host/_run_event_serializer.py:801-832` 的 `_decode_result_success(...)` 在成功结果 JSON 顶层发现该键时抛出 `ValueError("... legacy top-level truncation")`，因此旧 `outcome.result.truncation` 不再被成功反序列化，也不会静默丢弃。
- `dayu/host/_run_event_serializer.py:777-798` 的 `_encode_result_success(...)` 仍只写出 `ok`、`value`、`meta`，没有重新引入 success result 顶层 `truncation`。
- `tests/host/test_phase6_run_event_serializer.py:139-190` 保留 ordinary `value["truncation"]` roundtrip，并断言 `fetch_more_args.cursor` / `scope_token` 仍保留。
- `tests/host/test_phase6_run_event_serializer.py:193-227` 新增旧 top-level `result.truncation` payload 负测，断言 `deserialize_run_event_data(...)` 抛出匹配 `legacy top-level truncation` 的 `ValueError`。
- `dayu/contracts/tool_result.py:40-52` 的 `ToolResultSuccess` 仍只有 `ok`、`value`、`meta` 字段，没有 `truncation` 字段。
- `dayu/host/contracts.py:40-70` 的 `RunEventType` 未出现截断专属事件类型；截断继续作为 ordinary tool payload 内部 JSON 处理。

## Finding Status

### Finding 1 — serializer 仍接受旧 top-level ToolResultSuccess.truncation 行并静默丢弃

- status: fixed
- reason: 旧 schema 的 `outcome.result.truncation` 现在在 `_decode_result_success(...)` 入口 fail-fast；当前 ordinary `value["truncation"]` roundtrip 仍被保留并由测试覆盖。
- validation sufficiency: sufficient for this accepted finding。指定测试覆盖了旧 top-level schema 负路径和当前 ordinary payload 正路径；指定 `rg` 也确认未恢复 `truncation=` 构造参数或 public `ToolTruncationInfo` 使用。

## Validation Commands And Results

- `source .venv/bin/activate && pytest tests/host/test_phase6_run_event_serializer.py -q`
  - result: passed, `12 passed in 0.11s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - result: passed, `0 errors, 0 warnings, 0 informations`
- `rg "ToolTruncationInfo|truncation=" dayu tests`
  - result: passed for expected boundary; only negative export tests mention `ToolTruncationInfo`:
    - `tests/engine/test_package_exports.py`
    - `tests/contracts/test_package_exports.py`

## Contract Leakage Check

- `ToolTruncationInfo`: not restored in production code. Remaining hits are negative export tests only.
- `ToolResultSuccess.truncation`: not restored. `ToolResultSuccess` dataclass has no `truncation` field, and `rg "truncation=" dayu tests` returned no constructor usage.
- Old dedicated RunEventType: not restored. Review of `RunEventType` and `rg "TOOL_.*TRUNC|TRUNC.*TOOL|TRUNCATION" dayu tests` found no old truncation-specific run event type; hits are ordinary truncation payload constants and trace fields.

## New Blockers, Open Questions, Residual Risk

- new blockers: none identified.
- open questions: none for this re-review scope.
- residual risk: `_decode_result_success(...)` rejects the accepted finding's old top-level `truncation` key specifically, but does not implement a general unknown-field closed-schema validator for every success result key. That broader closure was a suggested hardening path in the original review, not necessary to close the accepted finding as scoped here.

## Conclusion

Finding 1 is fixed. The fix fails fast on legacy top-level `result.truncation`, preserves current ordinary `value["truncation"]` roundtrip, does not restore public `ToolTruncationInfo` / `ToolResultSuccess.truncation` / old truncation-specific event types, and passes the requested validation. This re-review does not decide the final commit gate; controller remains responsible for that decision.
