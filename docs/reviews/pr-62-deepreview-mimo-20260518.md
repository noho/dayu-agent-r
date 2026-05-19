# PR 62 Deep Review

## Scope

- Mode: PR Review
- PR: 62
- Title: Host P10.5 ordinary local multi-turn public contract freeze
- Author: noho
- Head branch: feat/host-p10-5-public-contract-freeze
- Base branch: main
- URL: https://github.com/noho/dayu-agent-r/pull/62
- Output file: docs/reviews/pr-62-deepreview-mimo-20260518.md
- Included scope: PR 62 相对 main 的完整 diff；dayu/host 生产代码、tests/host 测试、README、docs/host 总控文档
- Excluded scope: dayu/engine、dayu/fins、dayu/service、dayu/ui、dayu/config、utils/
- Parallel review coverage: 无

## Verification Commands

| Command | Result |
|---------|--------|
| `pytest tests/host/test_package_exports.py -q` | 8 passed |
| `pytest tests/host -q` | 696 passed, 1 skipped |
| `python -m pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `git diff --check main...HEAD` | 仅 docs/reviews/ 有 trailing whitespace，无生产代码问题 |

## Findings

### 1-NM-MEDIUM-test_public_smoke 使用内部 API 做 preconditions seeding

- **入口/函数**: `test_public_steer.py:test_steer_waiting_run_creates_new_attempt_public_path`；`test_public_cancel_session_runs.py` 多个测试
- **文件(行号)**: `tests/host/test_public_steer.py:17,90`；`tests/host/test_public_cancel_session_runs.py:28-54`
- **输入场景**: public smoke 测试需要 pre-seed 一个 WAITING / RUNNING 状态 Run 作为 steer / cancel 前置条件
- **实际分支**: 测试 import `create_host_command_handle`、`start_run`、`StartRunRequest`、`HostCommandHandle` 等已从包根移除的内部符号
- **预期行为**: public smoke 测试只使用 `open_host` / `Host` public path
- **实际行为**: 测试需要低层 handle 做 durable seeding，因为 public API 不提供"创建 WAITING Run"或"创建 RUNNING Run"的入口
- **直接证据**: `test_public_steer.py:17` `from dayu.host.command import create_host_command_handle`；`test_public_steer.py:90` `seed_handle = create_host_command_handle(_command_options(tmp_path))`
- **影响**: 测试正确性无影响（内部 API 仍存在于 `dayu.host.command`），但 public smoke 的"纯 public path"声明不完全成立。若 `dayu.host.command` 内部签名变更，这些测试会连带 break。
- **建议改法和验证点**: 当前无阻塞，可接受为 Phase 11 test hardening 范围。后续可考虑提供 internal test helper 或 `dayu.host._test_support` 模块收口 seeding 路径。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 2-NM-MEDIUM-FollowupSnapshot 字段重命名 current_cursor -> command_watermark

- **入口/函数**: `FollowupSnapshot.__post_init__`
- **文件(行号)**: `dayu/host/api.py:2241-2251`
- **输入场景**: 下游 Service 代码引用 `FollowupSnapshot.current_cursor`
- **实际分支**: 字段已重命名为 `command_watermark`，旧名移除
- **预期行为**: P10.5 公共契约冻结应明确记录 breaking change
- **实际行为**: 重命名已执行，README 已更新说明 `command_watermark` 不是 `watch_session_events` 的 watch cursor
- **直接证据**: `api.py:2251` `command_watermark: HostStreamCursor`；`command.py:495` `command_watermark=run_snapshot_from_row(result.run).event_cursor`
- **影响**: 下游代码需更新字段名。这是 intentional contract freeze breaking change。
- **建议改法和验证点**: 无需修改；PR 描述应明确列出此 breaking change。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 3-NM-MEDIUM-SubmitFollowupRequest 字段结构变更 input -> flat fields

- **入口/函数**: `SubmitFollowupRequest.__post_init__`
- **文件(行号)**: `dayu/host/api.py:1870-1876`
- **输入场景**: 下游 Service 代码构造 `SubmitFollowupRequest`
- **实际分支**: `input: HostInput` 已移除，替换为 `system_prompt`、`user_prompt`、`tool_names`、`runner_spec`、`runner_options`、`agent_policy` 六个 flat typed 字段
- **预期行为**: P10.5 公共契约冻结应明确记录 breaking change
- **实际行为**: 新字段有完整 `__post_init__` 校验，admission 路径已适配
- **直接证据**: `api.py:1870-1876`；`admission.py:_resolve_followup_effective_facts` 从 flat fields 构造 effective facts
- **影响**: 下游代码需更新构造方式。这是 intentional contract freeze breaking change。
- **建议改法和验证点**: 无需修改；PR 描述应明确列出此 breaking change。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无。

## Residual Risk

| 风险 | Owner | Phase |
|------|-------|-------|
| Recovery / startup crash recovery / positive orphan proof | Phase 11 | 11 |
| ToolsDiscovery / ScenePrepare | Phase 12 | 12 |
| Audit / Tool Trace / Outbox 与离线 terminal delivery | Phase 13 | 13 |
| RemoteProxy | Phase 14 | 14 |
| Retention / Purge production hardening | Phase 15 | 15 |
| 跨测试模块私有 helper 依赖、scheduler 私有方法测试依赖 | Phase 11 test hardening | 11 |
| provider / compactor quota、rate-limit 或外部模型 finish_reason=length | 环境 residual | N/A |

## Verdict

**PASS**

Blocking findings: 0
High findings: 0
Medium findings: 3 (均为 contract freeze breaking change 或 test helper 依赖，非 correctness defect)

PR 62 的公共契约冻结实现完整：`open_host` / `Host` async handle 替代了低层 `create_host_command_handle` / `start_run` 入口；`HostEvent` typed terminal view 覆盖 SUCCEEDED / FAILED / CANCELLED；`watch_session_events` 按 public path 验证；retry / replay / steer / cancel / resolve_wait / compact smoke 均通过 `open_host` public handle 执行；package export test 确认低层符号不再暴露于包根 `__all__` 或模块属性。所有验证命令通过。
