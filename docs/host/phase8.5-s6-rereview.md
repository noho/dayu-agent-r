# P8.5 Slice 6 Re-review

## Review Gate

- review gate name: `code re-review`
- work-unit name: P8.5 — P8 Stabilization / ToolRuntime Event Model
- assigned slice id: Slice 6 — Documentation / Migration Registry Closeout
- current gate: re-review
- source review artifact: `docs/host/phase8.5-s6-code-review.md`
- fix artifact: `docs/host/phase8.5-s6-fix-report.md`
- reviewed findings: `S6-CR-01`, `S6-CR-02`
- reviewed target: accepted findings and their fixes only
- artifact path: `docs/host/phase8.5-s6-rereview.md`

## Reviewer Conclusion

本次 re-review 只复核 accepted findings 及其 fixes，未在复核范围内发现新 blocker。
`S6-CR-01` 已修复：Engine metadata boundary 测试现在直接断言当前
`partial_tool_calls` 契约；package export guard 在纳入 `PartialToolCallSummary` 后仍保持严格相等白名单。

`S6-CR-02` 已修复：migration residual registry 已把完成的 provider protocol error diagnostic 覆盖与仍
deferred 的 transport-layer read failure 覆盖拆开，剩余项有明确 destination：`P16 interface freeze`。

本 artifact 不裁决最终 gate pass；最终裁决由 controller 完成。

## Finding Re-review

### S6-CR-01 — fixed

- original finding：Engine contract/export tests 未同步 accepted
  `partial_tool_calls` / `PartialToolCallSummary` 契约，导致
  `pytest tests/contracts tests/engine -q` 失败。
- fix evidence：
  - `tests/engine/test_metadata_boundary.py:45` 现在要求 `ProviderProtocolErrorData`
    字段严格等于包含 `partial_tool_calls` 的显式字段集合。
  - `tests/engine/test_metadata_boundary.py:59` 现在要求 `RunnerProtocolErrorData`
    字段严格等于包含 `partial_tool_calls` 的显式字段集合。
  - `tests/engine/test_metadata_boundary.py:72` 新增 `PartialToolCallSummary` 边界断言；
    断言字段只包含有界诊断字段，并在 line 88 明确拒绝 raw `arguments`。
  - `tests/engine/test_package_exports.py:47` 将 `PartialToolCallSummary` 纳入
    `EXPECTED_EXPORTS`。
- semantic review：
  - protocol error dataclass 字段测试仍使用严格集合相等，不允许任意 metadata 或额外字段。
  - package export 测试仍把 `dayu.engine.__all__` 与固定 `EXPECTED_EXPORTS` 集合做严格相等比较，
    export guard 没有被放宽。
  - 新增 summary 断言匹配 `dayu/engine/contracts/partial_tool_call.py` 当前契约：暴露 index / id /
    name fragment / arguments size / arguments hash，不暴露 raw argument payload。
- result：fixed。

### S6-CR-02 — fixed

- original finding：provider protocol error partial diagnostics 完成后，migration residual registry 没有给
  transport-layer read failure 覆盖明确 owner/destination。
- fix evidence：
  - `docs/host/migration-plan.md:178` 将 provider protocol error partial diagnostic coverage 记录为
    `P8.5 Slice 4 | fixed, validated for provider protocol errors`。
  - `docs/host/migration-plan.md:179` 将 transport-layer read failure coverage 单独记录为
    `P16 interface freeze | deferred-with-owner`。
- semantic review：
  - 剩余 transport-layer read failure 项没有被写成 P8.5 已完成内容。
  - `P16 interface freeze` 是明确的 later phase / work-unit destination，用于 provider adapter coverage
    recheck。
- result：fixed。

## README Sync Review

- `tests/README.md:23` 将当前类型检查命令记录为
  `python -m pyright dayu/ tests/ utils/`，与 fix report 和本次 re-review 使用的验证命令一致。
- `tests/README.md:77` 到 `tests/README.md:87` 仍在测试手册职责内：只说明 `tests/engine/` 覆盖的测试分层，
  包括 provider protocol error `partial_tool_calls` 有界摘要；没有写用户工作流、Host 内部实现说明或未来设计。
- result：`tests/README.md` 同步在职责范围内。

## Validation

```bash
source .venv/bin/activate && pytest tests/contracts tests/engine -q
```

Result: passed, `327 passed in 1.06s`.

```bash
source .venv/bin/activate && pytest tests/host -q
```

Result: passed, `376 passed in 2.87s`.

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Result: passed, `0 errors, 0 warnings, 0 informations`.

```bash
git diff --check
```

Result: passed.

```bash
rg "TOOL_FETCH_MORE|TOOL_CURSOR_|TOOL_RESULT_TRUNCATED|ToolFetchMore|ToolCursor.*Data|ToolResultTruncatedData" dayu tests dayu/host/README.md tests/README.md
```

Result: 符合预期；仅命中 Host public surface 负向测试中的 guard，不命中 current README。

```bash
rg "TOOL_FETCH_MORE|TOOL_CURSOR_|TOOL_RESULT_TRUNCATED|ToolFetchMore|ToolCursor.*Data|ToolResultTruncatedData" docs/host/migration-plan.md docs/host/phase8.5-plan.md
```

Result: 符合预期；仅命中 historical / plan guard 文档上下文。

## New Blocker Check

- fixes 引入 new blocker：no。
- reviewed scope 内发现 new plan deviation：no。
- fix 后仍未关闭的 accepted finding：no。
- residual risk：transport-layer read failure partial diagnostic coverage 按
  `docs/host/migration-plan.md` 继续 deferred 到 `P16 interface freeze`。

## Conclusion

两个 reviewed accepted findings 在 re-review scope 内均已修复。当前 validation 足以在 re-review 层面关闭
`S6-CR-01` 和 `S6-CR-02`；最终 gate 裁决仍由 controller 完成。
