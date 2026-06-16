# WU-CLI-FINS-OBS-01 S4 Fix Re-Review

## Scope

- Mode: scoped re-review of S4 fix gate deliverables
- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: `S4-cli-fins-live-ui`
- Fix artifact: `docs/reviews/wu-cli-fins-obs-01-s4-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-cli-fins-obs-01-s4-code-review-adjudication-20260615-195111.md`
- Original reviews: `docs/reviews/code-review-20260615-194943.md` (AgentMiMo), `docs/reviews/code-review-20260615-193940.md` (AgentDS)
- Re-review scope:
  - `dayu/cli/output.py` — S4-FIX-01 dead-code removal + S4-FIX-02 path redaction enhancement
  - `tests/cli/test_fins_commands.py` — S4-FIX-02 focused tests for embedded path redaction
  - `tests/README.md` — test coverage sync
  - Fix artifact claims vs. actual code
- Excluded scope: full S4 re-review; only S4-FIX-01 / S4-FIX-02 closure and non-action compliance

## Verification Summary

| # | Checkpoint | Result |
|---|-----------|--------|
| 1 | `rg -n "render_fins_direct_terminal_result" dayu tests` | **NO_MATCHES_FOUND** — dead code fully removed |
| 2 | `git diff --check` | **clean** |
| 3 | `pytest tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py -q` | **32 passed** (existing edgar deprecation warnings only) |
| 4 | `python -m pyright dayu/cli/commands/fins.py dayu/cli/output.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py` | **0 errors, 0 warnings, 0 informations** |
| 5 | Changed files boundary audit | CLI + tests + docs only; no Service / Fins runtime / Host / Engine touched |

## Findings

### S4-FIX-01: `render_fins_direct_terminal_result` 死代码移除 — **已关闭**

| 核对项 | 证据 | 结论 |
|--------|------|------|
| 函数定义已移除 | `git diff -- dayu/cli/output.py` 显式删除 `def render_fins_direct_terminal_result(...)` (6 lines removed) | ✅ |
| `__all__` 不再导出 | `dayu/cli/output.py:442-449` 的 `__all__` 不包含该符号 | ✅ |
| 全仓无 caller | `rg -n "render_fins_direct_terminal_result" dayu tests` 无匹配 | ✅ |
| 未添加兼容 wrapper | `output.py` 当前 449 行，无任何别名、wrapper、facade 或 comment-retained fallback | ✅ |
| 未添加替代 public dead API | `__all__` 仅包含当前路径使用的 6 个 renderer，无新增 public export | ✅ |
| 仅供旧 renderer 使用的常量已移除 | `_FINS_SUCCEEDED_TEMPLATE`、`_FINS_CANCELLED_TEMPLATE` 已从 diff 删除行中确认移除 | ✅ |

无新增 dead code、无兼容性 re-export、无 public API 逃逸。FIX-01 完全关闭。

### S4-FIX-02: 嵌入绝对路径脱敏强化 — **已关闭**

| 核对项 | 证据 | 结论 |
|--------|------|------|
| `path=/tmp/a` 脱敏 | `_ABSOLUTE_PATH_PATTERN` (output.py:53-56) 的 prefix 组包含 `=`；`test_fins_progress_payload_redacts_embedded_absolute_paths:371` 断言 `<redacted>` 出现且 `/tmp/a` 不出现 | ✅ |
| `key=/Users/a/b` 脱敏 | 同上正则覆盖；`test_fins_terminal_summary_redacts_embedded_absolute_paths:391` 覆盖 | ✅ |
| `error=C:\tmp\a` 脱敏（Windows） | 正则的 Windows 分支 `[A-Za-z]:[\\/]` 匹配；`test_fins_failure_message_redacts_embedded_windows_absolute_path:412` 覆盖 | ✅ |
| progress message/payload 测试 | `test_fins_progress_payload_redacts_embedded_absolute_paths:371` 覆盖 progress event 的 message 字段与 payload 字典 | ✅ |
| terminal success summary 测试 | `test_fins_terminal_summary_redacts_embedded_absolute_paths:391` 覆盖 SUCCEEDED 终态的 result_summary | ✅ |
| failure message 测试 | `test_fins_failure_message_redacts_embedded_windows_absolute_path:412` 覆盖 FAILED 终态的 failure_summary | ✅ |
| `_redact_absolute_path_match` helper | `output.py:401-409`，保留 prefix 分隔符并替换路径为 `<redacted>` | ✅ |
| stdout/stderr 分配正确 | progress/success 用例断言 `captured.err == ""`；failure 用例断言 `captured.out == ""` 且脱敏文本在 `captured.err` | ✅ |

正则实现正确：prefix 组捕获 `^`、`\s`、`=`、`,`、`:`、`;`、`(`、`[`、`{`、`"`、`'`，然后 path 组匹配 POSIX 或 Windows 绝对路径。`_redact_absolute_path_match` 保留 prefix 字符串并输出 `<redacted>`。`_safe_text_value` 流程先做 full-value 绝对路径判断（`_looks_like_absolute_path`），再走正则嵌入替换，两层防线覆盖 standalone 与 embedded 两种情况。

FIX-02 完全关闭。

### FIX-03: 新测试与 helper 遵守 AGENTS.md — **通过**

| 核对项 | 证据 | 结论 |
|--------|------|------|
| 中文 docstring | 三个新增测试函数均以中文描述意图与覆盖范围 | ✅ |
| 无 `Any` | 全文件 AST 扫描：helper 签名 `message: str \| None`、`payload: dict[str, JsonValue] \| None`、`result_summary: dict[str, JsonValue] \| None`、`failure_summary: dict[str, JsonValue] \| None` | ✅ |
| 无 `object` | 同上 | ✅ |
| 无裸容器 | 所有 `dict` / `tuple` 均有类型参数 | ✅ |
| 无无类型签名 | 所有新增/修改函数均有完整类型注解 | ✅ |

### FIX-04: Non-actions 未越界 — **通过**

| 核对项 | 证据 | 结论 |
|--------|------|------|
| 未改 Service | `git diff --name-only` 不包含 `dayu/service/` | ✅ |
| 未改 Fins runtime | 不包含 `dayu/fins/` | ✅ |
| 未改 Host | 不包含 `dayu/host/` | ✅ |
| 未改 Engine | 不包含 `dayu/engine/` | ✅ |
| 未实现 S5 logging assembly | diff 中无 logging 装配代码 | ✅ |
| 未把 `upload_filings_from` 变成 live job | `test_unsupported_flags_and_s6_command_fail_fast:627` 仍断言 `upload_filings_from` 为 EXIT_USAGE_ERROR fail fast | ✅ |

### FIX-05: Controller 验证复跑 — **确认通过**

| 核对项 | 控制器要求 | 独立复跑结果 |
|--------|-----------|-------------|
| pytest 32 passed | `pytest tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py -q` | **32 passed** |
| pyright 0 errors | `python -m pyright dayu/cli/commands/fins.py dayu/cli/output.py tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py` | **0 errors, 0 warnings, 0 informations** |
| git diff --check clean | `git diff --check` | **clean (no output)** |

## Open Questions

无。

## Residual Risk

1. **`_ABSOLUTE_PATH_PATTERN` 正则边界**：当前正则在绝对路径后遇到 `)`、`]`、`}`、`"`、`'`、`,`、`;`、空白时终止匹配。若未来出现 `(path=/tmp/a)`、`[path=/tmp/a]` 这类嵌套括号场景，外层括号的终止字符可能与内层 embedding 冲突。当前 S4 scope 内 Fins runtime 产出的 payload/summary 不包含此类嵌套，风险为 speculative。
2. **`_FakeFinsDirectService.wait_for_terminal` 残留**：与原 review 一致，controller 已裁定为有意保留的测试负向断言。若未来 Service interface 移除此方法，测试 double 需同步清理。

## Review Conclusion

**PASS — 2/2 fixed**

S4-FIX-01 和 S4-FIX-02 已完全关闭。`render_fins_direct_terminal_result` 已从代码、`__all__` 和全仓引用中彻底移除，无兼容 wrapper 或替代 public dead API。嵌入绝对路径脱敏覆盖 `path=/tmp/a`、`key=/Users/a/b`、`error=C:\tmp\a` 三种格式，测试覆盖 progress message/payload、terminal success summary 和 failure message。新代码遵守 AGENTS.md 类型与文档约束。Non-actions 边界未越界：未触及 Service、Fins runtime、Host 或 Engine，未实现 S5，未改动 `upload_filings_from` 行为。所有 controller 要求的验证项独立复跑通过。
