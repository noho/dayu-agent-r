# WU-CLI-FINS-OBS-01 S4 Scoped Re-Review

## Scope

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: `S4-cli-fins-live-ui`
- Gate: fix re-review
- Controller artifact: `docs/reviews/wu-cli-fins-obs-01-s4-code-review-adjudication-20260615-195111.md`
- Fix artifact: `docs/reviews/wu-cli-fins-obs-01-s4-fix-codex.md`
- Review artifacts under re-review:
  - `docs/reviews/code-review-20260615-194943.md` (AgentMiMo)
  - `docs/reviews/code-review-20260615-193940.md` (AgentDS)
- Re-review date: 2026-06-15T19:58:47

## Re-Review Scope

只复核 S4-FIX-01 和 S4-FIX-02 两个 accepted findings 是否正确关闭。不重新审整个 S4，除非 fix 引入直接矛盾。

## 核对结果

### S4-FIX-01: remove obsolete direct terminal renderer — ✅ CLOSED

| 核对项 | 结论 | 证据 |
|--------|------|------|
| `render_fins_direct_terminal_result` 函数已移除 | ✅ | `output.py` 中无该函数定义；diff 确认该函数体被替换为 `render_fins_direct_event` |
| `__all__` 不再导出 | ✅ | `output.py:442-449` 的 `__all__` 仅含 6 个符号，无 `render_fins_direct_terminal_result` |
| 全仓无当前 caller | ✅ | `grep -rn "render_fins_direct_terminal_result" dayu tests` 返回空；仅 `fins.py` import 列表已改 |
| 未添加兼容 wrapper 或替代 public dead API | ✅ | 无 wrapper、无 deprecated 注释、无替代 public API |
| 旧模板常量已移除 | ✅ | `_FINS_CANCELLED_TEMPLATE` 和 `_FINS_SUCCEEDED_TEMPLATE` 已从 `output.py` 移除 |

### S4-FIX-02: strengthen embedded absolute path redaction — ✅ CLOSED

| 核对项 | 结论 | 证据 |
|--------|------|------|
| `_ABSOLUTE_PATH_PATTERN` 增强 | ✅ | `output.py:53-56`：pattern 增加 `prefix` 命名组，覆盖 `=`, `,`, `:`, `;`, `(`, `[`, `{`, `"`, `'` 后的路径 |
| `path=/tmp/a` 脱敏 | ✅ | regex 测试：`path=/tmp/a` → `path=<redacted>`；测试 `test_fins_progress_payload_redacts_embedded_absolute_paths` 覆盖 |
| `key=/Users/a/b` 脱敏 | ✅ | regex 测试：`key=/Users/a/b` → `key=<redacted>`；同上测试的 payload 分支覆盖 |
| `error=C:\tmp\a` 脱敏 | ✅ | regex 测试：`error=C:\tmp\a` → `error=<redacted>`；测试 `test_fins_failure_message_redacts_embedded_windows_absolute_path` 覆盖 |
| `_redact_absolute_path_match` helper | ✅ | `output.py:401-409`：保留 prefix 分隔符，替换路径为 `<redacted>`，中文 docstring，完整类型签名 |
| 测试覆盖 progress message/payload | ✅ | `test_fins_progress_payload_redacts_embedded_absolute_paths`：message=`path=/tmp/a`，payload=`{"detail": "key=/Users/a/b"}` |
| 测试覆盖 terminal success summary | ✅ | `test_fins_terminal_summary_redacts_embedded_absolute_paths`：result_summary 含 `path=/tmp/a` 和 `key=/Users/a/b` |
| 测试覆盖 failure message | ✅ | `test_fins_failure_message_redacts_embedded_windows_absolute_path`：failure_summary message=`error=C:\tmp\a` |

### 新测试和 helper 遵守 AGENTS.md — ✅ COMPLIANT

| 核对项 | 结论 | 证据 |
|--------|------|------|
| 中文 docstring | ✅ | 所有新测试函数和 helper 均有中文 docstring |
| 无 Any/object/裸容器/无类型签名 | ✅ | `_redact_absolute_path_match(match: re.Match[str]) -> str`；测试 helper `_progress_event` / `_terminal_event` 均有完整类型签名；pyright 0 errors 确认 |

### Non-actions 未越界 — ✅ COMPLIANT

| 核对项 | 结论 | 证据 |
|--------|------|------|
| 未改 Service | ✅ | `dayu/service/` 在 S4 fix working tree 无变更 |
| 未改 Fins runtime | ✅ | `dayu/fins/` 在 S4 fix working tree 无变更 |
| 未改 Host/Engine | ✅ | `dayu/host/`、`dayu/engine/` 在 S4 fix working tree 无变更 |
| 未实现 S5 | ✅ | 无 logging assembly 变更 |
| 未把 `upload_filings_from` 变成 live job | ✅ | 无相关变更 |

### Controller 验证 — ✅ PASSED

| 验证项 | 结论 | 证据 |
|--------|------|------|
| pytest | ✅ | `32 passed` |
| pyright 目标文件 | ✅ | `0 errors, 0 warnings, 0 informations`（`dayu/cli/output.py`、`tests/cli/test_fins_commands.py`） |
| `git diff --check` | ✅ | 无 whitespace 错误 |

## Findings

未发现实质性问题。

## Open Questions

- 无

## Residual Risk

- 无新增 residual risk。S4 原有 residual risk（stream 无 terminal 边界、`_FakeFinsDirectService.wait_for_terminal` 残留、`_FINS_SENSITIVE_KEY_PARTS` 覆盖面）均由 adjudication 已明确 owner，不在本次 re-review scope。

## Conclusion

**PASS**

2/2 fixed。S4-FIX-01 和 S4-FIX-02 两个 accepted findings 均已正确关闭。
