# WU-CLI-DEBUG-STREAM-01 Plan Re-Review

## Metadata

- Work unit: WU-CLI-DEBUG-STREAM-01
- Gate: re-review
- Date: 2026-06-20
- Plan artifact: `docs/host/host-issues/wu-cli-debug-stream-01-debug-stream-plan.md`
- Plan fix artifact: `docs/reviews/plan-fix-wu-cli-debug-stream-01-20260620.md`
- Adjudication artifact: `docs/reviews/plan-review-wu-cli-debug-stream-01-adjudication-20260620.md`
- Prior review artifacts:
  - `docs/reviews/plan-review-wu-cli-debug-stream-01-mimo-20260620.md`
  - `docs/reviews/plan-review-wu-cli-debug-stream-01-ds-20260620.md`
- Re-review scope: verify accepted findings are fixed in plan; no implementation, no code change, no commit, no push

---

## Verdict

**PASS**

所有 accepted findings 已在 plan artifact 中修复，plan 可进入 implementation gate。

---

## Accepted Finding Verification

### Finding 1: `--debug-stream` precedence is explicit (DS F-1 / MiMo F-1)

**Status: 已修复**

**Adjudication requirement**: `debug_stream=True` entering runtime logging resolves to `STREAM_DEBUG` before any parsed `log_level` value. CLI help / README plan says `--debug-stream` enables ordinary DEBUG plus stream diagnostics and discourages contradictory log flags.

**Plan evidence (lines 101-107)**:

- `set_level_from_flags()` must resolve `debug_stream=True` to `LogLevel.STREAM_DEBUG` before any parsed `log_level` value.
- `--debug-stream` is the explicit most-verbose diagnostic request once it reaches runtime logging, including when argparse has already resolved `--debug`, `--verbose`, `--info`, `--quiet`, or `--log-level <level>` into a `log_level` value.
- CLI help and README wording must describe: `--debug-stream` enables ordinary DEBUG diagnostics plus high-frequency stream delta / SSE / per-delta ingest diagnostics. Users should not combine mutually contradictory log-level flags.

**Verification**: Plan 的 precedence rule 与 adjudication 裁决完全一致。`before any parsed log_level value` 与 adjudication 的 `before any parsed log_level value` 逐字对应。CLI help 要求也已包含。

**Note**: MiMo 原始 review 曾建议更精细的优先级链（quiet > debug_stream > debug），但 adjudication 明确选择了更简单的规则——`debug_stream=True` 总是最强诊断请求。Plan 忠实执行了 adjudication 的裁决，这是正确的。实施时应确保 `_resolve_level()` 中 `debug_stream` 的判断位于 `log_level` 解析之前。

---

### Finding 2: Old Host logging test name becomes misleading (DS F-2)

**Status: 已修复**

**Adjudication requirement**: Slice 2 需要求重命名 `test_engine_ingest_delta_events_use_debug_log_level` 为 stream-debug-specific 名称。

**Plan evidence (line 190)**:

> Rename the old `tests/host/test_logging.py` test `test_engine_ingest_delta_events_use_debug_log_level` to a stream-debug-specific name, for example `test_engine_ingest_delta_events_use_stream_debug_log_level`.

**Verification**: Slice 2 Exact changes 中已明确列出重命名要求，给出了具体示例名。满足 adjudication 要求。

---

### Finding 3: Missing combined `--debug --debug-stream` test (DS F-3)

**Status: 已修复**

**Adjudication requirement**: Slice 1 需要求 combined `--debug` + `--debug-stream` 的 parsing / runtime resolution 测试。

**Plan evidence (lines 164, 168)**:

- Parsing: `parse_cli_args(("prompt", "x", "--debug", "--debug-stream"))` accepts both flags, keeps `debug_stream is True`, and resolves the ordinary debug flag into the parsed log-level field.
- Runtime: `set_level_from_flags(log_level="debug", debug_stream=True, ...) is LogLevel.STREAM_DEBUG`, covering combined `--debug` and `--debug-stream` runtime resolution.

**Verification**: Slice 1 Expected assertions 同时包含 parsing 层和 runtime 层的 combined flag 测试。满足 adjudication 要求。

---

### Finding 4: Cleanup path lacks explicit `debug_stream` assertion (MiMo F-2)

**Status: 已修复**

**Adjudication requirement**: Slice 1 需要求 both initial 和 cleanup `set_level_from_flags(...)` calls carry `debug_stream`。

**Plan evidence (lines 158-159, 166)**:

- Exact changes: "In `cli/main.py`, preserve `debug_stream_for_cleanup` and pass it into both `set_level_from_flags()` calls."
- Exact changes: "Update CLI main spy structures and expectations to include `debug_stream`."
- Expected assertions: "`main(("prompt", "x", "--debug-stream"))` passes `debug_stream=True` and `log_level="info"` to runtime log assembly for both the initial configuration call and the cleanup reconfiguration call."

**Verification**: Plan 明确要求 spy 结构新增 `debug_stream` 字段，且两处 `set_level_from_flags` 调用（initial + cleanup）均需携带 `debug_stream=True`。满足 adjudication 要求。

---

## Deferred Findings (not required for this gate)

| Finding | Status | Owner |
|---|---|---|
| DS F-4: `ParsedCliArgs` construction sites | deferred-with-owner | implementation gate |
| DS F-5 / MiMo residual: README `critical` mismatch | deferred-with-owner | separate cleanup WU |

---

## Residual Risks

1. **`--debug-stream` 与 quiet flag 的优先级细节**: Plan 选择了 adjudication 的简化规则（`debug_stream` 总是最强），而非 MiMo 原始 review 建议的分层优先级。实施时 `_resolve_level()` 的具体实现需确保 `debug_stream` 判断在 `log_level` 解析之前。这不是 plan 级问题，是实现细节。

2. **Future stream diagnostics at wrong level**: Slice 2 测试覆盖可缓解。

3. **README `critical` mismatch**: 已知 pre-existing 问题，deferred。

---

## Completion Report

- **Artifact path**: `docs/reviews/plan-rereview-wu-cli-debug-stream-01-mimo-20260620.md`
- **Verdict**: PASS
- **Accepted finding final statuses**:
  1. `--debug-stream` precedence: 已修复
  2. Test rename: 已修复
  3. Combined flag test: 已修复
  4. Cleanup path assertion: 已修复
- **Residual risks**: 实现时需确保 `_resolve_level()` 正确放置 `debug_stream` 判断顺序；README `critical` mismatch deferred。
- **Uncovered areas**: 无。Plan 的 deferred findings 已有明确 owner。
