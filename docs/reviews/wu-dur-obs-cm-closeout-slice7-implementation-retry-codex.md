# WU-DUR / WU-OBS / WU-CM Closeout Slice 7 Implementation Retry

## Gate

- gate: implementation retry
- work unit: WU-CM-01-F01 public smoke correctness closeout
- slice: Slice 7 Public Smoke Correctness Closeout
- status: blocked by production runner message shape
- artifact path: `docs/reviews/wu-dur-obs-cm-closeout-slice7-implementation-retry-codex.md`

## First-Principles Judgment

Slice 7 的动机成立。Public smoke 不能只证明 `open_host` / `submit_followup` 返回成功，还必须证明真实 public path 投影给 Engine / Runner 的 LLM-facing messages 可解释。新增断言只能读取 public smoke 已记录的 `AgentRunRequest.messages` 或 scripted runner `messages`，没有读取 private durable table，也没有伪造 Host path。

当前不能继续在 Slice 7 allowed files 内完成 closeout。直接证据显示，真实 `open_host -> submit_followup -> worker/runner` 路径仍会生成多条 `system` role message；root cause 位于生产 RunInput / memory projection message construction，而不是 smoke helper 或 utility CLI。按边界要求，不能为了通过 smoke 修改生产行为，也不能用 smoke 私有入口掩盖该 production shape。

## Changed Files

- `tests/host/public_smoke_support.py`
  - 新增 `assert_at_most_one_system_message()`，集中校验 public smoke 观测到的 Engine request / Runner call messages 至多一条 `system` role message。
- `tests/host/test_public_tool_wiring_smoke.py`
  - 对 mock tool wiring scripted runner 记录到的 runner-call messages 增加 one-system-message 断言。
  - 对 `tool_names` 子集 / 空集合冻结场景记录到的 request messages 增加 one-system-message 断言。
- `tests/host/test_public_open_host_multiturn_smoke.py`
  - 对 deterministic 两轮 continuity 与 per-run override 场景记录到的 request messages 增加 one-system-message 断言。
- `tests/host/test_public_compact_smoke.py`
  - 对 focused compact public smoke 记录到的 request / fake compactor messages 增加 one-system-message 断言。
  - 对 compactor material JSON 扩大内部术语检查，覆盖 Python schema 名、EventLog / payload ref / vNext 术语。
  - 对 compactor runner-call manifest 增加 `message_count`、`message_entries` 数量与 `role_sequence_digest` 同源断言。
- `tests/README.md`
  - 同步测试手册中 public-path smoke 的稳定断言边界。

未修改生产 Host / Engine / compact instruction contract，也未修改四个 utility smoke CLI 行为。

## Direct Evidence

定向测试在修改前通过：

```text
13 passed, 1 skipped
```

加入 Slice 7 one-system-message 断言后，定向测试失败，失败来自 public path 记录到的真实 messages：

```text
tests/host/test_public_tool_wiring_smoke.py::test_mock_tool_result_feeds_same_run_and_later_run_continuity
tool wiring runner call 2 expected at most one system message, got 2;
roles=('system', 'user', 'system', 'assistant', 'user')
```

该失败使用 `ToolCallingWorkerFactory` 中 scripted `AsyncRunner.call()` 记录的 `messages`，是实际 runner-call messages，不是测试私有 durable reconstruction。

Focused compact public smoke 还显示 ordinary Engine request shape 中存在更多 system blocks：

```text
tool evidence request 1 expected at most one system message, got 5;
roles=('system', 'system', 'system', 'user', 'system', 'assistant', 'system', 'user')
minimum preserve request 0 expected at most one system message, got 2;
roles=('system', 'system', 'user')
multi compact request 0 expected at most one system message, got 2;
roles=('system', 'system', 'user')
```

生产代码直接证据：

- `dayu/host/run_input.py` 仍有多个 production `SystemMessage(...)` 构造点。
- `dayu/host/run_input.py` 的 Host execution context、Session Summary Memory、Evidence / Fact Memory、answer anchor、forward intent、reference continuity 与 compact artifact block 均可能以独立 system message 进入 RunInput。
- 因此 root cause 不在 Slice 7 allowed files；只修改 tests / utils 无法让 public runner-call messages 收敛为至多一条 system message。

Compactor prompt / material 方面：

- 已接受的 S6-R1 前置确实关闭了 runtime `instruction.output_schema_name=ConversationCompactOutputVNext` 暴露问题。
- 本轮新增 material 断言未成为首个失败点；当前 blocker 是 public ordinary runner-call system message shape。

## Utility Smoke Audit

| entry | runner call | compact | audit result |
|---|---|---|---|
| `utils/smoke_host_public_conversation_memory.py` | applicable when run normally | applicable through compact pressure path | `--help` passed；帮助说明默认 fresh `workspace/tmp` smoke workspace，`--reuse-session` 才复用稳定 slot。 |
| `utils/smoke_host_public_diagnostics.py` | not applicable | not applicable | 精确 N/A：该文件是共享 diagnostics printer，无 argparse/main，不调用 `open_host`，不触发 runner call 或 compact；`python ... --help` 退出 0 且无输出。 |
| `utils/smoke_host_public_conversation_memory_scenarios.py` | applicable when run normally | applicable for long / pressure scenarios | `--help` passed；帮助包含 fresh workspace、suite、long rounds 与 pressure mode 参数。 |
| `utils/smoke_host_public_multiturn.py` | applicable when run normally | applicable through second-round compact pressure path | `--help` passed；帮助说明默认 fresh workspace，并保留 Service-like runtime assembly inputs。 |

## Validation

Commands run:

```bash
git branch --show-current
git status --short
source .venv/bin/activate && pytest tests/host/test_public_tool_wiring_smoke.py tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_compact_smoke.py
source .venv/bin/activate && python utils/smoke_host_public_conversation_memory.py --help
source .venv/bin/activate && python utils/smoke_host_public_diagnostics.py --help
source .venv/bin/activate && python utils/smoke_host_public_conversation_memory_scenarios.py --help
source .venv/bin/activate && python utils/smoke_host_public_multiturn.py --help
source .venv/bin/activate && pyright
git diff --check
```

Results:

- branch: `phaseflow/wu-dur-obs-cm-closeout`
- initial working tree before implementation: clean
- targeted pytest before added assertions: `13 passed, 1 skipped`
- targeted pytest after added assertions: `9 passed, 4 failed, 1 skipped`
- four utility `--help` commands: passed; diagnostics helper is N/A with no CLI output
- `pyright`: `0 errors, 0 warnings, 0 informations`
- `git diff --check`: passed

## README Decision

- `tests/README.md` updated because `tests/` behavior changed and the test manual already owns public-path smoke boundaries.
- Root `README.md` not updated because utility CLI usage, output diagnostics contract, project-level workflow and trace/render entry points did not change.
- No `dayu/README.md` / Host / Engine README update because no production architecture, public contract, layering boundary or implementation behavior changed in this retry.

## Remaining Risk

- Blocking: public ordinary runner-call messages still contain multiple system messages on real public Host path. Owner should be a production RunInput / memory projection shape rescope outside Slice 7 allowed files.
- Focused compact public smoke now contains the intended manifest count / digest and material terminology assertions, but full acceptance cannot proceed while the one-system-message blocker remains.
- Utility full smoke runs were not executed because the current blocker is already proven by deterministic focused public tests and full runs may require provider/runtime configuration.

## Completion Status

blocked; ready for implementation review / controller adjudication of the blocker evidence.
