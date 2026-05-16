# Host Phase 8 P8-S2 Code Review Controller Adjudication - 2026-05-16

## Gate

当前 gate：P8-S2 `Host Event Stream Cursor Truth / Fanout Boundary` code review。

Implementation artifact：

- `docs/reviews/host-phase8-implementation-s2-event-stream-cursor-20260516.md`

Code review artifacts：

- `docs/reviews/host-phase8-code-review-s2-mimo-20260516.md`
- `docs/reviews/host-phase8-code-review-s2-ds-20260516.md`

Truth plan：

- `docs/host/phase8-projection-core-event-stream-plan.md`

## Controller Verdict

PASS。P8-S2 implementation 可以进入 accepted slice commit gate。

MiMo review PASS，无 finding。DS review PASS，提出 1 个低严重度 test-maintenance finding；controller 裁决为
rejected-as-non-blocking，当前不进入 fix gate。

## Accepted Findings

无。

## Rejected Findings

### P8S2-CR-DS-001: read_api forbidden-token guard may false-positive comments/docstrings

来源：DS finding 1。

裁决：rejected-as-non-blocking。

理由：`test_read_api_stream_does_not_reference_projection_or_fanout_truth` 的 token guard 是刻意保守的边界测试，用于防止
`read_api.py` 在实现或说明中把 projection、fanout、repair 重新解释为 stream truth。即便未来注释中自然语言提到这些词导致
失败，修复方式也是把说明移动到 Host README / plan 或重新审视是否正在向 read API 引入 truth 语义。当前保守性不会影响生产
行为、不会造成 false negative，也不值得为低严重度维护摩擦引入更复杂的 AST 字符串过滤规则。

## Deferred Findings

- P8-S3 新增 `host_run_results` / `host_session_timeline_items` 后，需要继续证明 `stream_run_events` 不写 read model projection
  表。Owner：P8-S3 implementation / review。
- 后续 fanout / wakeup 若获批准接入，需要保留 `stream_run_events` EventLog cursor truth。Owner：后续 fanout / wakeup owner。

## Validation

AgentCodex 与 DS 均复跑以下验证并通过：

```bash
source .venv/bin/activate && pytest tests/host/test_public_event_stream.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
```

Result：18 passed。

```bash
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

Result：0 errors。

```bash
git diff --check
```

Result：clean。

Controller 在 accepted slice commit 前需复跑上述验证。
