# Code Re-review — WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4-S1

## Scope

- Mode: current changes (deepreview re-review)
- Branch: `phaseflow/host-issues-control`
- Base: accepted plan commit `15979f5d32738148bf53daf9defe2dca59b8360c`
- Output file: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-code-rereview-ds.md`
- Review date/time: 2026-07-20T03:00:31+08:00
- Included scope: `tests/cli/test_upload_filings_from_command.py`（working-tree diff vs HEAD=15979f5d）
- Excluded scope: `docs/host/issues-implementation-control.md`（Controller control-doc status）；S2/S3 未实施文件；workflow yml；README
- Parallel review coverage: 无（单文件完整走读，主 reviewer 全量覆盖）
- This is: S1 final DS re-review gate，在 Controller zero-change validation 后、accepted local commit 前

## Evidence chain integrity

### Immutable target lock

| Item | Expected | Actual | Match |
|---|---|---|---|
| `HEAD` | `15979f5d32738148bf53daf9defe2dca59b8360c` | `15979f5d32738148bf53daf9defe2dca59b8360c` | ✓ |
| Test diff SHA-256 | `9c16a8c737eac8f0bdc816dd8e400a4987957fcbc03b1d70bcf661e0a00712e6` | `9c16a8c737eac8f0bdc816dd8e400a4987957fcbc03b1d70bcf661e0a00712e6` | ✓ |
| Staged tree | empty | empty | ✓ |
| `git diff --check` | PASS | PASS | ✓ |
| Production diff | 零输出 | 零输出 | ✓ |
| README/workflow diff | 零输出 | 零输出 | ✓ |

### Zero-change chain vertical verification

逐 gate 锁定输入与输出，验证每步的输入 SHA-256 精确等于上一步的输出 SHA-256：

| Gate | Artifact | Output SHA-256 | Consumed by next gate |
|---|---|---|---|
| Implementation | `...-implementation-codex.md` | `ee0a7143...` | Controller validation |
| Controller validation | `...-controller-validation.md` | `e904ab8e...` | MiMo + DS review |
| MiMo review | `...-code-review-mimo.md` | `30ff26a8...` | Controller adjudication |
| DS review | `...-code-review-ds.md` | `bbb537c3...` | Controller adjudication |
| Controller adjudication | `...-controller-adjudication.md` | `c195949a...` | AgentCodex zero-change |
| AgentCodex zero-change | `...-code-review-fix-codex.md` | `907628e5...` | Controller zero-change validation |
| Controller zero-change validation | `...-code-review-fix-controller-validation.md` | （已验证） | 本 re-review |

所有 gate 的 accepted finding 均为 `0`；未出现 disposition 漂移、新增 finding、open question 或 deferred fix。

### Live rerun verification

本 re-review 独立重跑了关键 gates（非依赖既有 review 缓存）：

| Check | Result |
|---|---|
| `pytest tests/cli/test_upload_filings_from_command.py -q` | `20 passed, 2 skipped, 3 warnings` |
| `pyright tests/cli/test_upload_filings_from_command.py` | `0 errors, 0 warnings, 0 informations` |
| `git diff --cached --name-only` | 零输出 |
| `git diff --name-only -- dayu/` | 零输出 |
| `git diff --check` | PASS |

2 skipped 为 Windows-only real `cmd.exe` nodes（`os.name != "nt"` skip）；3 warnings 为既有 `edgar` deprecation。pytest 结果与两路 initial review 及 implementation validation 一致。

## Findings

未发现实质性问题。

### 1. Full-line Windows batch splitter 逐字正确性重审

`_parse_windows_batch_fixed_argv`（行 1087–1130）经本轮逐 token 状态机走读，覆盖以下全部场景且均正确：

#### 1.1 Token 边界语义

Renderer 输出格式为 `" ".join(^"arg1^", ^"arg2^", ...) %*`（`upload_script.py` 行 199–200）。Parser 先 `endswith(" %*")` 再逐 token 扫描 `^"` 对：

- **Opening `^"`**：每 token 始于 `assert fixed_command.startswith('^"', index)`（行 1100）。Renderer 保证每个 argument 被 `_quote_windows_batch_argument` 包裹为 `^"...^"`；此断言若 Renderer 产出非预期格式则 fail closed。
- **Closing `^"` 判定**：`slash_count % 2 == 0`（行 1110）。偶数 backslash → 该 `^"` 是 closing delimiter；奇数 backslash → 是 escaped quote（token 内部），`continue` 继续扫描。这与 Renderer 的 quoting 契约精确一一对应：Renderer 对 closing `"` 产生 `\\`*(2n)+`^"`（偶数），对内嵌 `"` 产生 `\\`*(2n+1)+`^"`（奇数）。
- **Token 间空格**：`assert fixed_command[index] == " "`（行 1120）后 `index += 1`，再 `assert index < len(fixed_command)`（行 1122）确保空格后仍有内容（即下一 token）。

#### 1.2 逐场景 round-trip 验证

以 Renderer→parser→decoder→CRT 完整 pipeline 对每个 adversarial 输入做端到端 trace：

| 输入 | Renderer 产出 | Tokenizer 提取 | Batch decode | CRT parse | 结果 |
|---|---|---|---|---|---|
| `Apple Inc.` | `^"Apple Inc.^"` | `^"Apple Inc.^"` | `"Apple Inc."` | `Apple Inc.` | ✓ |
| `""` | `^"^"` | `^"^"` | `""` | `""` | ✓ |
| `say "hello"` | `^"\^"hello\^"^"` | `^"\^"hello\^"^"` | `"\"hello\""` | `"hello"` | ✓ |
| `C:\test` | `^"C:\\test^"` | `^"C:\\test^"` | `"C:\\test"` | `C:\test` | ✓ |
| `100%` | `^"100%%^"` | `^"100%%^"` | `"100%"` | `100%` | ✓ |
| `a^b` | `^"a^^b^"` | `^"a^^b^"` | `"a^b"` | `a^b` | ✓ |
| `\^^` | `^"\^^^^"` | `^"\^^^^"` | `"\\^\\^"` | `\^^` | ✓ |

（注：上表中 batch decode 结果以 Python string literal 表示，CRT parse 结果为最终 argv。）

#### 1.3 非 `\` 非 `^"` 单字符跳过

Parser 内层循环对非 `\` 非 `^"` 字符执行 `assert index < len(fixed_command); index += 1`（行 1113–1114）。此路径跳过 caret-escaped metacharacter 的 `^X` 对中的首字符 `^` 以及后续被保护字符——均被正确包含在 raw token 中，再由 `_decode_windows_batch_fixed_token` 统一解码。

本轮额外验证：`^^`（caret-escaped `^`）在 tokenizer 中被两次 single-char skip 处理，在 decoder 中 `^X`→`X` 恢复为 `^`。Unicode 多字节字符（如 `中文`）在 Python string code point 索引下正确处理。✓

#### 1.4 While-else fail-closed

```python
while index < len(fixed_command):
    ...
else:
    raise AssertionError("Windows batch fixed token is not closed")
```

若扫描到字符串末尾仍未通过 `break` 找到 closing `^"`，`while...else` 的 `else` 分支抛出 `AssertionError`。不静默返回部分结果。✓

#### 1.5 空 token 列表

```python
assert rendered_tokens  # 行 1124
```

若输入被 `removesuffix` 后为空（无业务 token），此断言 fail closed。✓

### 2. `_assert_single_windows_upload_company_name` 结构验证重审

#### 2.1 CRLF 物理行完整性（行 1060–1063）

```python
script_text = script_path.read_bytes().decode("utf-8", errors="strict")
assert script_text.endswith("\r\n")
physical_lines = tuple(script_text.removesuffix("\r\n").split("\r\n"))
assert all("\r" not in line and "\n" not in line for line in physical_lines)
```

三步检查：strict UTF-8 decode（拒绝任何编码错误）、末尾 CRLF（拒绝截断文件）、逐行无 stray CR/LF（拒绝混合换行）。每一步都 fail closed。✓

#### 2.2 固定结构验证（行 1064–1071）

```python
header_size = len(_WINDOWS_BATCH_HEADER_ORACLE)
assert physical_lines[:header_size] == _WINDOWS_BATCH_HEADER_ORACLE
assert len(body_lines) == 1 + 1 + len(_WINDOWS_POST_COMMAND_LINES)
regeneration_line, business_line, *post_command_lines = body_lines
assert regeneration_line.startswith(_WINDOWS_REGENERATION_PREFIX)
assert tuple(post_command_lines) == _WINDOWS_POST_COMMAND_LINES
```

- Header 3 行精确匹配 `@echo off` / `chcp 65001 >nul` / `setlocal DisableDelayedExpansion`（与 `upload_script.py::_WINDOWS_HEADER` 一致）
- Body line count：1（regeneration）+ 1（业务命令）+ 2（post-command）= 4。若 Renderer 产出多条业务命令，line count 不匹配 → fail
- Post-command lines 精确匹配：`if errorlevel 1 exit /b %errorlevel%` / `exit /b 0` ✓

#### 2.3 Token 级业务验证（行 1073–1083）

```python
business_argv = _parse_windows_batch_fixed_argv(business_line)
assert business_argv[:4] == ("python", "-m", "dayu.cli", "upload_filing")
company_name_indexes = tuple(
    index for index, argument in enumerate(business_argv)
    if argument == "--company-name"
)
assert len(company_name_indexes) == 1
company_name_index = company_name_indexes[0]
assert company_name_index + 1 < len(business_argv)
assert business_argv[company_name_index + 1] == expected_company_name
```

- 命令前缀精确 token 匹配（非 substring）
- `--company-name` 恰好出现一次（精确 token 比较 `==`，`--no-company-name` 不会误匹配）
- `company_name_index + 1 < len(business_argv)` 防止 `--company-name` 是最后一个 token 时越界
- 下一 token 精确等于预期公司名 ✓

#### 2.4 回归注释隔离验证

`body_lines` unpacking 为 `regeneration_line, business_line, *post_command_lines`。`regeneration_line` 作为 `REM Regenerate:` 注释被单独取出并通过 `_WINDOWS_REGENERATION_PREFIX` 识别，其内容不进入业务 argv 解析。因此即使 regeneration comment 包含 `--company-name Apple Inc.`，也不会被误认为业务参数。✓

### 3. 负例 fail-closed 重审

`test_windows_upload_company_oracle_fails_closed_on_non_business_evidence`（行 497–560）：

| # | 输入 | 失败判定位置 | 断言 |
|---|---|---|---|
| 1 | 缺 `--company-name` | `len(company_name_indexes) == 1`（行 1080）→ 0≠1 | `AssertionError` |
| 2 | `upload_material` 替代 `upload_filing` | `business_argv[:4] == (...)`（行 1074）→ `upload_material` ≠ `upload_filing` | `AssertionError` |
| 3 | 两条 `valid_command` | `len(body_lines) == 4`（行 1068）→ 6≠4 | `AssertionError` |
| 4 | 重复 `--company-name` | `len(company_name_indexes) == 1`（行 1080）→ 2≠1 | `AssertionError` |

隐式覆盖：

- **comment-only**：Renderer 拒绝空 `commands`（`ValueError`，`upload_script.py` 行 91–92）。即使绕过 Renderer，oracle 的 body line count 检查也会失败。
- **零业务行**：同上。
- **comment 含 company-name 但业务命令不含**：负例 1 直接覆盖（业务命令缺 `--company-name` → fail）。
- **空 company-name 值**（如 `--company-name ""`）：空字符串作为 argv 会通过 oracle 的 `== expected_company_name` 检查。但 `expected_company_name = "Apple Inc."`，空字符串 ≠ `"Apple Inc."` → fail。

每个负例都验证 `pytest.raises(AssertionError)` 且使用与正例相同的 `upload_script.render_upload_script` 生成脚本。不依赖 mock、monkeypatch 或 fake renderer。✓

### 4. Pre-execution 时序重审

`test_windows_generated_script_runs_real_cli_into_temp_storage`（行 910–989）执行顺序：

```
行 922–947: generation = subprocess.run(...)     # 生成 .cmd 脚本
行 948:      script_path = ...                     # 路径解析
行 949:      assert generation.returncode == 0     # 确认生成成功 ← 从执行后移到执行前
行 950–953:  _assert_single_windows_upload_company_name(...)  # Oracle 解析
行 954–962:  execution = subprocess.run(("cmd.exe", ...))     # 执行脚本
行 964:      assert execution.returncode == 0
```

关键变更：
1. `assert generation.returncode == 0` 从执行后移到执行前（行 949 vs 原行 878）。此移动不改变断言语义，但提供 fail-fast：若脚本生成失败，在尝试执行前即终止。
2. Oracle 在 generation 成功后、`cmd.exe` 执行前运行。若 oracle 失败（`AssertionError`），pytest 终止，`cmd.exe` 不被调用。不依赖 execution result、stdout 或 storage 状态反推输入。✓

### 5. Semantic ownership 重审

每个业务事实的 owner 未漂移：

- "fresh create/update 是否需要 company-name" → `dayu/fins/pipelines/upload_company_meta.py::_require_company_meta_field`（未修改）
- "Windows real-smoke 是否提交合法请求" → `test_windows_generated_script_runs_real_cli_into_temp_storage`（S1 修正输入）
- "生成脚本中 company-name 的逐 token 证明" → `_assert_single_windows_upload_company_name`（S1 新增 test-local oracle）
- "CLI renderer" → `dayu/cli/upload_script.py`（未修改，仍只机械投影 typed batch plan）
- "company_name_supplied artifact" → 同一 `_assert_single_windows_upload_company_name` 的返回值（`True`），由 `company_name_supplied` 字段写入 artifact（行 982），不从 execution result 反推

无跨层 fallback、`hasattr`/`getattr`、loose parsing、兼容 shim、测试固化或多真源状态。✓

### 6. Overdesign 重审

- **Render 格式常量**：`_WINDOWS_BATCH_HEADER_ORACLE` 等 5 个 `Final` 常量与 Renderer 的 `_WINDOWS_HEADER` 等 module-private 常量逐项一致。此耦合是 oracle 锁定 Renderer 输出格式的固有需求——不硬编码就无法独立验证。替代方案（import 私有常量）违反计划"不复用 renderer helper"约束，且会让 oracle 依赖被测代码。
- **`_parse_windows_batch_fixed_argv`**：~44 行完整 tokenizer，不复制 Renderer logic（decoder 而非 encoder）。复用既有 `_decode_windows_batch_fixed_token` 和 `_parse_single_windows_crt_argument` 独立 oracle。新增代码量是正确解析 Renderer 输出格式的最小必要量。
- **无新 test framework**：使用标准 `pytest.raises(AssertionError)`。`_assert_single_windows_upload_company_name` 返回 `True` 供 artifact 同源记录。
- **无 test-only production seam**：未 monkeypatch、未 mock renderer、未新增 fixture。✓

### 7. 安全与 deferred 边界重审

- `shell=True`：零新增。既有 `capture_output=True` 在 unchanged 行，均属于既有 POSIX/Windows `subprocess.run` 调用，非 S1 新增。
- `errors=replace`：零新增。所有新增/修改路径使用 `errors="strict"`。
- `.count()` / `shlex`：零新增。S1 oracle 不使用 substring count 或 POSIX parser。
- Deferred issues（142/151/175/177/178）：零涉及。S1 scope 不覆盖。
- Secret / key / configured value：不读取、不产生、不记录。
- 生产零 diff 已独立验证。✓

### 8. Accepted finding=0 裁决验证

Controller adjudication（`...controller-adjudication.md` SHA-256 `c195949a...`）的裁决矩阵：

| Disposition | 当前值 | 本轮独立复核 |
|---|---|---|
| Accepted code finding | `0` | 0（未发现新 material finding） |
| Rejected finding | `0` | 0 |
| Needs-evidence finding | `0` | 0 |
| Design contradiction | `0` | 0 |
| Local blocker | `0` | 0 |
| Current-slice fix requirement | 无 | 无 |

两路 initial review（MiMo + DS）的 locked hash、结论与 finding count 均未漂移。AgentCodex zero-change 和 Controller zero-change validation 的 evidence 完整自洽。本轮独立重审确认：无新的 material finding 需要处置，accepted finding=0 的裁决成立。✓

## Open Questions

无。

## Residual Risk

- **真实 Windows R11/R12 embedded-R11 closure**：本地 macOS pytest 中两个 real `cmd.exe` nodes 按 `os.name != "nt"` skip。此状态是 accepted plan §8 的预期——S1/S2/S3 全部 accepted 后才由 Controller dispatch 真实 Windows closure。S1 的 pre-execution oracle 正确性已通过本地 round-trip 与 adversarial 输入独立验证，但最终 `cmd.exe` 下的 argv 行为仍需真实 Windows evidence 确认。这不是 S1 defect。
- **WIN4-S2（setx native stdio/timeout owner）与 WIN4-S3（outer process safe failure projection）**：尚未实施。它们是 accepted plan 的后续串行切片，S1 不依赖它们。它们未完成前整体 AR-F07 closure 不可声称。这不是 S1 finding。
- **Oracle 与 Renderer 格式耦合**：若 Renderer 的 batch header、quoting 策略或 `%*` 后缀发生变化，S1 oracle 会 fail closed（正确行为）。这不是 risk 而是 contract——oracle 正确锁定了当前 Renderer 的格式真源。

## Verdict

**PASS / 0 material findings / ZERO_CHANGE_CHAIN_VERIFIED / READY_FOR_ACCEPTED_LOCAL_COMMIT**

本轮 DS 最终 re-review 对 immutable S1 implementation diff 完成了：

1. `_parse_windows_batch_fixed_argv` tokenizer 的逐状态机正确性验证（7 个 adversarial 输入端到端 trace）
2. `_assert_single_windows_upload_company_name` 的结构验证、token 级验证与 fail-closed 语义
3. 四个负例的逐场景原因分析
4. Pre-execution 时序与 assertion reordering 的安全语义
5. Semantic ownership 真源不漂移确认
6. Overdesign / test-only seam 审查
7. Security / deferred boundary scan
8. Zero-change evidence chain 逐 gate 纵向验证
9. Controller accepted finding=0 裁决的独立复核

S1 immutable slice 实现正确、最小且所有权清晰。Accepted finding=0 的裁决成立，zero-change 链完整无漂移。未发现 pending 真实 Windows 或未实施 S2/S3 之外的新 material finding、blocker 或 needs-evidence。
