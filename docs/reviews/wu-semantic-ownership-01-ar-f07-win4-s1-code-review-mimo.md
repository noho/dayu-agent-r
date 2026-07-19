# Code Review — WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4-S1

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `15979f5d32738148bf53daf9defe2dca59b8360c` (accepted plan commit)
- Output file: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-code-review-mimo.md`
- Included scope:
  - `tests/cli/test_upload_filings_from_command.py` (S1 immutable slice)
  - `docs/host/issues-implementation-control.md` (Controller control doc, outside S1 ownership)
  - `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-implementation-codex.md` (implementation artifact)
  - `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-controller-validation.md` (controller validation)
  - `dayu/cli/upload_script.py` (production renderer, read-only reference)
- Excluded scope: `dayu/fins/`, `dayu/cli/commands/fins.py`, `dayu/cli/init_environment.py`, `tests/README.md`, workflows
- Parallel review coverage: 无

## Locked hashes

- Test diff SHA-256: `9c16a8c737eac8f0bdc816dd8e400a4987957fcbc03b1d70bcf661e0a00712e6` ✓ verified
- Implementation artifact SHA-256: `ee0a714359388de70f2ef991341f512b89d46455b90e53d9c986c7ccd98532f5`

## Verification matrix

| Check | Result |
|---|---|
| Pyright | 0 errors, 0 warnings, 0 informations |
| Ruff | All checks passed |
| pytest target file | 20 passed, 2 skipped, 3 warnings (edgar deprecation, not from S1) |
| Fins production diff | 零 diff |
| README diff | 零 diff |
| Staged tree | empty |
| git diff --check | PASS |

## Findings

未发现实质性问题。

## Detailed review

### 1. `_parse_windows_batch_fixed_argv` — batch full-line splitter

逐行走读 renderer 输出格式与 parser 解码逻辑：

**Renderer 产出格式** (`_render_windows_script`, line ~178): 每条业务命令渲染为 `^"token1^" ^"token2^" ... %*`，CRLF 行终止。`_quote_windows_batch_argument` 对每个 argv 执行：
- `^"` 开闭 caret-quote
- `%%` 转义 `%`
- `^X` 转义 `&|<>()` 等 batch body metacharacter
- `\\` 双倍化 quote 前的 backslash
- `\"` 转义 argument 内嵌 `"`

**Parser 解码链** (lines 1087-1130):
1. `removesuffix(" %*")` 去除 renderer 固定后缀
2. 逐 token 扫描 `^"` 对：找 opening `^"` → 跳过 `\\` 序列 → 找 closing `^"` (偶数 backslash 后)
3. token 间必须是单空格
4. `_decode_windows_batch_fixed_token`：`%%` → `%`, `^X` → `X`
5. `_parse_single_windows_crt_argument`：Windows CRT backslash-quote 语义

**场景验证**:
- **Spaces**: `"Apple Inc."` → `^"Apple Inc.^"` → CRT `"Apple Inc."` → `Apple Inc.` ✓
- **Backslashes**: `"C:\test"` → `^"C:\\\\test^"` (偶数 backslash 前 `^"`) → CRT `"C:\\test"` → `C:\test` ✓
- **Embedded quotes**: `"say \"hello\""` → `^"say \\\\\"hello\\\\\"^"` → CRT `"say \\"hello\\""` → `say "hello"` ✓
- **Carets**: `"a^b"` → `^"a^^b^"` → decode → `a^b` ✓
- **Percent**: `"100%"` → `^"100%%^"` → decode → `100%` ✓
- **Closing quote edge**: 奇数 backslash 前 `^"` 不是 closing（CRT 中 `\"` 是转义），偶数 backslash 前 `^"` 是 closing。Parser 的 `slash_count % 2 == 0` 条件正确 ✓

**`%%*` 假阳性分析**: 若 argument 包含 `%*`（如 `test%*`），renderer 输出 `^"test%%*^" %*`。`removesuffix(" %*")` 只去掉末尾 ` %*`，剩余 `^"test%%*^"` 正确。Batch 把 `%%` 解释为字面 `%`，CRT 收到 `test%*`。不会误截 ✓

### 2. `_assert_single_windows_upload_company_name` — pre-execution oracle

**CRLF/结构验证** (lines 1060-1071):
- `read_bytes().decode("utf-8", errors="strict")` — 严格 UTF-8 ✓
- `endswith("\r\n")` + `split("\r\n")` — CRLF 物理行 ✓
- `all("\r" not in line and "\n" not in line)` — 无 stray CR/LF ✓
- header 3 行精确匹配 `_WINDOWS_BATCH_HEADER_ORACLE` ✓
- `body_lines == 1 + 1 + len(_WINDOWS_POST_COMMAND_LINES)` — 精确一行 regeneration + 一行业务 + 固定 post-command ✓
- regeneration 行 prefix 匹配 ✓
- post-command 行精确匹配 ✓

**Token 级验证** (lines 1073-1084):
- `business_argv[:4] == ("python", "-m", "dayu.cli", "upload_filing")` — 命令 token 精确 ✓
- `len(company_name_indexes) == 1` — 恰好一个 `--company-name` ✓
- `business_argv[company_name_index + 1] == expected_company_name` — 下一 token 精确匹配 ✓

### 3. Negative tests — `test_windows_upload_company_oracle_fails_closed_on_non_business_evidence`

四个 invalid command set 覆盖计划 §5.1 的全部负例要求：

| 负例 | 输入 | 失败位置 |
|---|---|---|
| 缺 company-name | `command_prefix` 不含 `--company-name` | `len(company_name_indexes) == 1` |
| 非 upload_filing 命令 | `upload_material` 替代 | `business_argv[:4]` 不匹配 |
| 多条业务命令 | `(valid_command, valid_command)` | `len(body_lines)` 不匹配 |
| 重复 --company-name | `*valid_command, "--company-name", ...` | `len(company_name_indexes) == 1` |

**隐式覆盖**:
- comment-only: renderer 拒绝空 commands（`ValueError`），且 oracle body_lines 长度检查失败 ✓
- comment 含 company-name 但业务命令不含: 负例 1 直接覆盖 ✓
- 零业务命令: renderer 约束 + oracle 长度检查双重防御 ✓

### 4. Pre-execution ordering

Real smoke 中的执行顺序 (lines 949-964):
1. `generation = subprocess.run(...)` — 生成 .cmd 脚本
2. `assert generation.returncode == 0` — 确认生成成功
3. `_assert_single_windows_upload_company_name(script_path=...)` — oracle 解析脚本
4. `execution = subprocess.run(("cmd.exe", ...))` — 执行脚本

Oracle 在 `cmd.exe` 执行前运行 ✓。若 oracle 失败，pytest 抛出 `AssertionError`，不会执行 batch 脚本 ✓

### 5. Semantic owner

修改位于正确 owner。`test_windows_generated_script_runs_real_cli_into_temp_storage` 是 Windows real-smoke 输入构造的 owner。S1 没有修改：
- `dayu/fins/` — Fins production 仍是 company-name 必填的 owner
- `dayu/cli/upload_script.py` — renderer 仍是 batch quoting 的 owner
- `dayu/cli/commands/fins.py` — CLI command 仍是 argv 投影的 owner

`company_name_supplied` 从同一逐 token 断言结果写入 artifact，没有从 execution result 或 storage 反推 ✓

### 6. Overdesign / unnecessary test framework

新增 helper 是测试证据 owner 内的必要最小逻辑：
- `_parse_windows_batch_fixed_argv`：组合既有 `_decode_windows_batch_fixed_token` 与 `_parse_single_windows_crt_argument` 为 line-level proof
- `_assert_single_windows_upload_company_name`：结构验证 + token 级断言
- 两者不复制 production renderer（是 decoder 而非 encoder）
- 不引入新 test framework、新 fixture 或新 conftest
- 常量是 test-local，不从 production import（避免 coupling）

### 7. Control doc 与 implementation artifact

`docs/host/issues-implementation-control.md` 的 6 行变更属于 Controller 既有状态更新，不在 S1 ownership 内。Controller validation doc 已明确声明此点。Production 零 diff 已确认 ✓

### 8. Residual risks

- 真实 Windows R11/R12 测试未运行（本机 skip），不能宣称 AR-F07 closure
- S1 oracle 依赖 renderer 的 `^"` 对格式；若 renderer 变更 quoting 策略，oracle 会 fail closed（这是正确行为）

## Open Questions

无。

## Residual Risk

- 真实 Windows R11/R12 embedded-R11 closure 待 Controller dispatch 验证
