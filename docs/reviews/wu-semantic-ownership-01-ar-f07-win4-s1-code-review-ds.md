# Code Review — WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4-S1

## Scope

- Mode: current changes (deepreview)
- Branch: `phaseflow/host-issues-control`
- Base: accepted plan commit `15979f5d32738148bf53daf9defe2dca59b8360c`
- Output file: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-code-review-ds.md`
- Included scope: `tests/cli/test_upload_filings_from_command.py`（unstaged working tree diff vs accepted plan commit）
- Excluded scope: `docs/host/issues-implementation-control.md`（control-doc status update，非 S1 implementation ownership）；`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-implementation-codex.md`（implementation artifact，非 review target）；production zero diff 已独立核验
- Parallel review coverage: 无（单文件，主 reviewer 全量走读）
- Locked artifacts:
  - Test diff SHA-256: `9c16a8c737eac8f0bdc816dd8e400a4987957fcbc03b1d70bcf661e0a00712e6` ✓（已核验）
  - Implementation artifact SHA-256: `ee0a714359388de70f2ef991341f512b89d46455b90e53d9c986c7ccd98532f5` ✓（已核验）
- Controller validation: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-controller-validation.md`（SHA-256 `e904ab8e...`）→ PASS / READY_FOR_DUAL_COMPLETE_CODE_REVIEW

## Findings

未发现实质性问题。

经过对以下维度的逐行代码走读、手动 trace 与自动化验证，未发现 correctness、semantic ownership、overdesign、security 或 contract 层面的 material finding：

### 1. Full-line Windows batch splitter 正确性

`_parse_windows_batch_fixed_argv`（行 1087–1130）的完整正确性已验证：

- **Token 边界**：每个 token 必须始于 `^"`。内部 `^"` 之前若为奇数个 `\` 则为 escaped quote（属于 token），若为偶数个 `\` 则为 closing quote（token 结束）。此规则精确反向 renderer `_quote_windows_batch_argument` 的输出——renderer 对内部 `"` 产生 `\`*(2n+1)+`^"`，对 closing `"` 产生 `\`*(2n)+`^"`。
- **Spaces**：renderer 用 `" ".join(...)` 以单空格连接 token。token 内空格（如 `Apple Inc.`）在 `^"..."^"` 内部，不受 splitter 影响。token 间空格被正确消耗。
- **Backslashes**：token 内 `\` 计数在每次 `^"` 判断时正确使用。非 `\` 非 `^"` 字符时 `slash_count` 被下轮重新计数自然丢弃。
- **Quotes**：`^"` 在 batch 层解码为 `"`，再经 `_parse_single_windows_crt_argument` 按 CRT backslash/quote 规则解析。renderer→`_decode_windows_batch_fixed_token`→`_parse_single_windows_crt_argument` 的完整 pipeline 已通过 `test_windows_renderer_round_trips_fixed_argument_oracles`（行 467–494）对 7 种 adversarial 输入逐一验证，并通过本轮新增的完整脚本 round-trip 独立确认。
- **Carets**：`_decode_windows_batch_fixed_token` 将 `^X` 解码为 `X`。renderer 的 `_WINDOWS_BODY_METACHARACTERS = {'^', '&', '|', '<', '>', '(', ')'}` 中每个字符都被 caret-protected，decoder 逐字恢复。
- **Percent**：renderer 将 `%` 加倍为 `%%`；`_decode_windows_batch_fixed_token` 将 `%%` 解码为 `%`。已独立确认 `100% Inc.` → `^"100%% Inc.^"` → `"100% Inc."` → `100% Inc.` 完整 round-trip。
- **Closing quote**：parser 的 `while...else: raise AssertionError("...not closed")` 确保未闭合 token 必定 fail closed。
- **空 token**：renderer 对 `""` 产生 `^"^"`。parser 正确识别第一个 `^"` 为 open、立即跟随的 `^"`（slash_count=0，偶数）为 close。Batch decode 得到 `""`，CRT parse 得到 `""`。
- **`%*` 后缀**：`_WINDOWS_RENDERED_COMMAND_SUFFIX = " %*"` 在 parser 入口处 strip，不会被误认为 token 的一部分。

### 2. 负例覆盖

`test_windows_upload_company_oracle_fails_closed_on_non_business_evidence`（行 497–560）：

| 输入场景 | 业务命令特征 | 失败点（行号） | 预期 |
|---|---|---|---|
| `(command_prefix,)` | 零 `--company-name` | `len(company_name_indexes) == 1`（行 1080）→ 0≠1 | fail closed |
| `upload_material` | 非 `upload_filing` 命令 | `business_argv[:4] == ("python", "-m", "dayu.cli", "upload_filing")`（行 1074） | fail closed |
| `(valid_command, valid_command)` | 两条业务命令 | `len(body_lines) == 1+1+2`（行 1068）→ 6≠4 | fail closed |
| `(*valid_command, "--company-name", "Apple Inc.")` | 重复 `--company-name` | `len(company_name_indexes) == 1`（行 1080）→ 2≠1 | fail closed |

- comment-only：若脚本只有 `REM` 行，`len(body_lines)` 检查（行 1068）首先失败。
- 零业务行：同上，body 行数不匹配。
- 所有负例都通过 `pytest.raises(AssertionError)` 验证 fail closed，并使用与正例相同的 `render_upload_script` 生成脚本。

### 3. Oracle 时序

`test_windows_generated_script_runs_real_cli_into_temp_storage`（行 910–989）：

```python
# 行 949：generation 成功确认
assert generation.returncode == 0, generation.stderr
# 行 950–953：pre-execution oracle
company_name_supplied = _assert_single_windows_upload_company_name(...)
# 行 954：cmd.exe 执行
execution = subprocess.run(("cmd.exe", "/d", "/c", str(script_path)), ...)
```

Oracle 在 generation 成功后、`cmd.exe` 执行前运行。不依赖 execution result、stdout 内容或 storage 状态反推输入。✓

### 4. Overdesign 审查

- **Render 格式常量**（`_WINDOWS_BATCH_HEADER_ORACLE`、`_WINDOWS_REGENERATION_PREFIX`、`_WINDOWS_RENDERED_COMMAND_SUFFIX`、`_WINDOWS_POST_COMMAND_LINES`）：这些是 test-local 的预期值副本，与 renderer 的 `_WINDOWS_HEADER` 等 module-private 常量逐项一致。此耦合是 oracle 验证 renderer 输出的固有需求——不硬编码就无法锁定格式。替代方案（import renderer 私有常量）违反 plan 的"不复用 renderer helper"约束，且会让 oracle 依赖被测代码。
- **`_parse_windows_batch_fixed_argv`**：约 40 行的完整 tokenizer。它不复制 renderer 逻辑（不做 quoting/渲染），只做解析。复用了已有的 `_decode_windows_batch_fixed_token` 和 `_parse_single_windows_crt_argument` 独立 oracle。新增代码量是正确解析 renderer 输出格式的最小必要量——substring/count 方案无法正确处理 spaces、quotes、backslashes 和 caret。
- **无新 test framework**：使用标准 `pytest.raises(AssertionError)`。`_assert_single_windows_upload_company_name` 返回 `True` 供 artifact 同源记录，与既有 `company_name_supplied` 字段一致。
- **无 test-only production seam**：未 monkeypatch、未 mock renderer、未新增 fixture。

### 5. Fins production 零 diff

```bash
git diff 15979f5d...HEAD -- dayu/
# 零输出
```

`dayu/fins/pipelines/upload_company_meta.py::_require_company_meta_field` 仍是 fresh create/update 缺 company-name 的唯一 fail-closed owner。S1 只修正 test input，未在 production 增加默认值、fallback、FMP/network infer、preseeded meta 或 message parsing。

### 6. 核验结果汇总

| Gate | 结果 | 证据 |
|---|---|---|
| Focused tests | `20 passed, 2 skipped, 3 warnings` | pytest 输出。2 skipped 为 Windows-only real cmd.exe nodes；3 warnings 为既有 edgar deprecation |
| pyright | `0 errors, 0 warnings, 0 informations` | 针对 changed file 的独立运行 |
| Ruff | `All checks passed!` | 针对 changed file 的独立运行 |
| `git diff --check` | PASS | 零输出 |
| Production diff | 零输出 | `git diff 15979f5d...HEAD -- dayu/` |
| `shell=True` / `errors=replace` scan | 零新增 | 既有 `capture_output=True` 在 unchanged 行（454/822/832/899/943/958），均属于既有 POSIX/Windows subprocess.run 调用，非 S1 新增 |
| `.count(` / `shlex` scan | 零新增 | 既有 `.count()` 在 unchanged 行（333/334/840），S1 oracle 不使用 substring count 或 POSIX parser |
| Deferred scan（Issue 142/151/175/177/178） | 零新增 | S1 不涉及这些 scope |
| README | 不更新 | 按 plan §7，`tests/README.md` 归 WIN4-S3 |
| 真实 Windows | PENDING | 按 plan §8，S1 本地 skip 不构成 closure |

### 7. Semantic ownership 审查

- "fresh create/update 是否需要 company-name" → `dayu/fins/pipelines/upload_company_meta.py::_require_company_meta_field`（未修改）
- "Windows real-smoke 是否提交合法请求" → `test_windows_generated_script_runs_real_cli_into_temp_storage`（S1 修正）
- "生成脚本中 company-name 的逐 token 证明" → `_assert_single_windows_upload_company_name`（S1 新增，test-local oracle）
- CLI renderer → `dayu/cli/upload_script.py`（未修改，仍只机械投影 typed batch plan）
- 无跨层 fallback、`hasattr/getattr`、loose parsing、兼容 shim 或测试固化

## Open Questions

无。

## Residual Risk

- 真实 Windows R11 / R12 embedded-R11 尚未运行。本地 macOS `pytest` 中两个 real cmd.exe nodes 按 `os.name != "nt"` skip。此状态是 plan §8 的预期：S1/S2/S3 全部 accepted 后才由 Controller dispatch 真实 Windows closure。S1 的 pre-execution oracle 正确性已通过本地 round-trip 与 adversarial 输入独立验证，但最终 `cmd.exe` 下的 argv 行为仍需真实 Windows 证据确认。
- WIN4-S2（setx native stdio/timeout owner）与 WIN4-S3（outer process safe failure projection）尚未实施。S1 不依赖它们，但它们未完成前整体 AR-F07 closure 不可声称。

## Decision

**PASS** / 0 material findings / S1 immutable slice 实现正确、最小且所有权清晰。

S1 满足 plan §4 WIN4-S1 的全部 exact changes 要求：合法 company-name 输入、pre-execution CRLF/Windows token oracle、负例 fail closed、同源 boolean artifact、production/README/workflow 零 diff。测试、pyright、Ruff、diff-check、安全扫描均通过。下一 gate 可进入 AgentMiMo/AgentDS 并发完整 code review。
