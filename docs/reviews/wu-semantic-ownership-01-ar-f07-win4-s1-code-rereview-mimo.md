# Code Re-Review — WU-SEMANTIC-OWNERSHIP-01 AR-F07 WIN4-S1

## Scope

- Mode: current changes (deepreview)
- Branch: `phaseflow/host-issues-control`
- Base: `15979f5d32738148bf53daf9defe2dca59b8360c` (accepted plan commit = current HEAD)
- Output file: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-code-rereview-mimo.md`
- Included scope:
  - `tests/cli/test_upload_filings_from_command.py`（S1 immutable slice，unstaged working-tree diff）
  - `docs/host/issues-implementation-control.md`（Controller control doc，outside S1 ownership）
  - `dayu/cli/upload_script.py`（production renderer，read-only reference for oracle 逆向验证）
- Excluded scope:
  - `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-implementation-codex.md`（implementation artifact，非 review target）
  - `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-controller-validation.md`（controller validation artifact）
  - `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-code-review-mimo.md`（initial review artifact）
  - `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-code-review-ds.md`（initial review artifact）
  - `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-code-review-controller-adjudication.md`（adjudication artifact）
  - `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-code-review-fix-codex.md`（zero-change artifact）
  - `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-code-review-fix-controller-validation.md`（zero-change validation）
  - production zero diff 已独立核验
- Parallel review coverage: 无（单文件，主 reviewer 全量走读）

## Locked hashes

- Test diff SHA-256（`git diff --binary -- tests/cli/test_upload_filings_from_command.py`）：`9c16a8c737eac8f0bdc816dd8e400a4987957fcbc03b1d70bcf661e0a00712e6` ✓ verified
- `git rev-parse HEAD`：`15979f5d32738148bf53daf9defe2dca59b8360c` ✓ verified
- `git diff --cached --name-only`：零输出；staged tree empty ✓ verified
- `git diff --check`：PASS；零输出 ✓ verified

## Verification matrix

| Gate | 结果 | 证据 |
|---|---|---|
| Focused tests | `20 passed, 2 skipped, 3 warnings` | pytest 输出。2 skipped 为 Windows-only real cmd.exe nodes；3 warnings 为既有 edgar deprecation |
| pyright | `0 errors, 0 warnings, 0 informations` | 针对 changed file 的独立运行 |
| Production diff | 零输出 | `git diff 15979f5d...HEAD -- dayu/` |
| README diff | 零输出 | 不涉及 |
| Staged tree | empty | `git diff --cached --name-only` 零输出 |
| `git diff --check` | PASS | 零输出 |

## Findings

未发现实质性问题。

经过对以下维度的逐行代码走读、手动 trace 与独立验证，未发现 correctness、Windows argv/CRLF oracle、negative fail-closed、pre-execution 时序、semantic owner、overdesign、security 或 contract 层面的 material finding：

### 1. `_parse_windows_batch_fixed_argv` — batch full-line splitter 正确性

逐行走读 renderer 输出格式（`_render_windows_script` 行 178–203 → `_quote_windows_batch_argument` 行 206–236）与 parser 解码逻辑（行 1087–1130）：

**Renderer 产出格式**：每条业务命令渲染为 `^"token1^" ^"token2^" ... %*`，CRLF 行终止。`_quote_windows_batch_argument` 对每个 argv 执行：
- `^"` 开闭 caret-quote
- `%%` 转义 `%`
- `^X` 转义 `&|<>()` 等 batch body metacharacter
- `\\` 双倍化 quote 前的 backslash
- `\"` 转义 argument 内嵌 `"`

**Parser 解码链**（行 1087–1130）：
1. `removesuffix(" %*")` 去除 renderer 固定后缀
2. 逐 token 扫描 `^"` 对：找 opening `^"` → 跳过 `\\` 序列 → 找 closing `^"` (偶数 backslash 后)
3. token 间必须是单空格
4. `_decode_windows_batch_fixed_token`：`%%` → `%`, `^X` → `X`
5. `_parse_single_windows_crt_argument`：Windows CRT backslash-quote 语义

**关键场景验证**：
- **Spaces**: `"Apple Inc."` → `^"Apple Inc.^"` → space 在 `^"` 对内部，不受 splitter 影响 ✓
- **Backslashes**: `"C:\test"` → `^"C:\\\\test^"` → 偶数 backslash 前 `^"` 正确 ✓
- **Embedded quotes**: renderer 对内部 `"` 产生 `\`*(2n+1)+`^"`，parser 的 `slash_count % 2 == 0` 条件正确区分 escaped quote 与 closing quote ✓
- **Carets**: `_decode_windows_batch_fixed_token` 将 `^X` 解码为 `X` ✓
- **Percent**: `100% Inc.` → `^"100%% Inc.^"` → `"100% Inc."` → `100% Inc.` ✓
- **Closing quote edge**: 奇数 backslash 前 `^"` 不是 closing（CRT 中 `\"` 是转义），偶数 backslash 前 `^"` 是 closing。Parser 的 `slash_count % 2 == 0` 条件正确 ✓
- **`%%*` 假阳性分析**: 若 argument 包含 `%*`（如 `test%*`），renderer 输出 `^"test%%*^" %*`。`removesuffix(" %*")` 只去掉末尾 ` %*`，剩余 `^"test%%*^"` 正确 ✓
- **空 token**: renderer 对 `""` 产生 `^"^"`。parser 正确识别第一个 `^"` 为 open、立即跟随的 `^"`（slash_count=0，偶数）为 close ✓
- **未闭合 token**: `while...else: raise AssertionError("...not closed")` 确保 fail closed ✓
- **Token 间空格**: `fixed_command[index] == " "` 断言 + `index += 1` 跳过，若多空格或非空格字符则 AssertionError ✓

### 2. `_assert_single_windows_upload_company_name` — pre-execution oracle

**CRLF/结构验证**（行 1060–1071）：
- `read_bytes().decode("utf-8", errors="strict")` — 严格 UTF-8 ✓
- `endswith("\r\n")` + `split("\r\n")` — CRLF 物理行 ✓
- `all("\r" not in line and "\n" not in line)` — 无 stray CR/LF ✓
- header 3 行精确匹配 `_WINDOWS_BATCH_HEADER_ORACLE` ✓
- `body_lines == 1 + 1 + len(_WINDOWS_POST_COMMAND_LINES)` — 精确一行 regeneration + 一行业务 + 固定 post-command ✓
- regeneration 行 prefix 匹配 ✓
- post-command 行精确匹配 ✓

**Token 级验证**（行 1073–1084）：
- `business_argv[:4] == ("python", "-m", "dayu.cli", "upload_filing")` — 命令 token 精确 ✓
- `len(company_name_indexes) == 1` — 恰好一个 `--company-name` ✓
- `business_argv[company_name_index + 1] == expected_company_name` — 下一 token 精确匹配 ✓

**Oracle 常量与 production 一致性**：
- `_WINDOWS_BATCH_HEADER_ORACLE` 三行值与 renderer `_WINDOWS_HEADER` 逐项一致 ✓
- `_WINDOWS_REGENERATION_PREFIX` = `"REM Regenerate: "` 与 renderer 生成格式一致 ✓
- `_WINDOWS_RENDERED_COMMAND_SUFFIX` = `" %*"` 与 renderer `{fixed} %*` 一致 ✓
- `_WINDOWS_POST_COMMAND_LINES` 与 renderer 循环内 `if errorlevel 1` + 循环后 `exit /b 0` 一致 ✓

### 3. Negative fail-closed 覆盖

`test_windows_upload_company_oracle_fails_closed_on_non_business_evidence`（行 497–560）：

| 负例 | 输入 | 失败位置（行号） | 预期 |
|---|---|---|---|
| 缺 company-name | `command_prefix` 不含 `--company-name` | `len(company_name_indexes) == 1`（行 1080）→ 0≠1 | fail closed |
| 非 upload_filing 命令 | `upload_material` 替代 | `business_argv[:4]`（行 1074）不匹配 | fail closed |
| 多条业务命令 | `(valid_command, valid_command)` | `len(body_lines)`（行 1068）→ 6≠4 | fail closed |
| 重复 --company-name | `*valid_command, "--company-name", ...` | `len(company_name_indexes) == 1`（行 1080）→ 2≠1 | fail closed |

**隐式覆盖**：
- comment-only：renderer 拒绝空 commands（`ValueError: upload script requires at least one command`），且 oracle body_lines 长度检查会失败 ✓
- comment 含 company-name 但业务命令不含：负例 1 直接覆盖 ✓
- 零业务命令：renderer 约束 + oracle 长度检查双重防御 ✓

所有负例都通过 `pytest.raises(AssertionError)` 验证 fail closed，并使用与正例相同的 `render_upload_script` 生成脚本。

### 4. Pre-execution 时序

Real smoke 中的执行顺序（行 949–964）：
1. `generation = subprocess.run(...)` — 生成 .cmd 脚本
2. `assert generation.returncode == 0, generation.stderr` — 确认生成成功
3. `_assert_single_windows_upload_company_name(script_path=...)` — oracle 解析脚本
4. `execution = subprocess.run(("cmd.exe", ...))` — 执行脚本

Oracle 在 `cmd.exe` 执行前运行 ✓。若 oracle 失败，pytest 抛出 `AssertionError`，不会执行 batch 脚本 ✓。Oracle 不依赖 execution result、stdout 内容或 storage 状态反推输入 ✓。

### 5. Semantic owner 审查

- "fresh create/update 是否需要 company-name" → `dayu/fins/pipelines/upload_company_meta.py::_require_company_meta_field`（未修改）
- "Windows real-smoke 是否提交合法请求" → `test_windows_generated_script_runs_real_cli_into_temp_storage`（S1 修正）
- "生成脚本中 company-name 的逐 token 证明" → `_assert_single_windows_upload_company_name`（S1 新增，test-local oracle）
- CLI renderer → `dayu/cli/upload_script.py`（未修改，仍只机械投影 typed batch plan）
- 无跨层 fallback、`hasattr/getattr`、loose parsing、兼容 shim 或测试固化

`company_name_supplied` 从同一逐 token 断言结果写入 artifact，没有从 execution result 或 storage 反推 ✓。

### 6. Overdesign / unnecessary test framework 审查

- **Render 格式常量**（`_WINDOWS_BATCH_HEADER_ORACLE`、`_WINDOWS_REGENERATION_PREFIX`、`_WINDOWS_RENDERED_COMMAND_SUFFIX`、`_WINDOWS_POST_COMMAND_LINES`）：这些是 test-local 的预期值副本，与 renderer 的 `_WINDOWS_HEADER` 等 module-private 常量逐项一致。此耦合是 oracle 验证 renderer 输出的固有需求——不硬编码就无法锁定格式。替代方案（import renderer 私有常量）违反 plan 的"不复用 renderer helper"约束，且会让 oracle 依赖被测代码。
- **`_parse_windows_batch_fixed_argv`**：约 40 行的完整 tokenizer。它不复制 renderer 逻辑（不做 quoting/渲染），只做解析。复用了已有的 `_decode_windows_batch_fixed_token` 和 `_parse_single_windows_crt_argument` 独立 oracle。新增代码量是正确解析 renderer 输出格式的最小必要量——substring/count 方案无法正确处理 spaces、quotes、backslashes 和 caret。
- **无新 test framework**：使用标准 `pytest.raises(AssertionError)`。`_assert_single_windows_upload_company_name` 返回 `True` 供 artifact 同源记录，与既有 `company_name_supplied` 字段一致。
- **无 test-only production seam**：未 monkeypatch、未 mock renderer、未新增 fixture。

### 7. Fins production 零 diff

`git diff 15979f5d...HEAD -- dayu/` 零输出。`dayu/fins/pipelines/upload_company_meta.py::_require_company_meta_field` 仍是 fresh create/update 缺 company-name 的唯一 fail-closed owner。S1 只修正 test input，未在 production 增加默认值、fallback、FMP/network infer、preseeded meta 或 message parsing。

### 8. Control doc 与 implementation artifact

`docs/host/issues-implementation-control.md` 的 8 行变更属于 Controller 既有状态更新（gate 字段从 plan commit 指向 S1 re-review，next entry point 更新为当前 gate），不在 S1 ownership 内。未修改 product、tests、README、workflow。

### 9. Zero-change chain 验证

完整证据链逐项核验：

| 步骤 | artifact | SHA-256 | 结论 |
|---|---|---|---|
| 1. Implementation | `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-implementation-codex.md` | `ee0a7143...32f5` | 无漂移 |
| 2. Controller validation | `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-controller-validation.md` | `e904ab8e...49ec` | 无漂移 |
| 3a. AgentMiMo review | `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-code-review-mimo.md` | `30ff26a8...8d65` | PASS / 0 material finding |
| 3b. AgentDS review | `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-code-review-ds.md` | `bbb537c3...a3c6` | PASS / 0 material finding |
| 4. Controller adjudication | `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-code-review-controller-adjudication.md` | `c195949a...7562` | accepted=0, rejected=0, needs-evidence=0 |
| 5. AgentCodex zero-change | `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-code-review-fix-codex.md` | `907628e5...73e0` | PASS / ZERO_CHANGE_FIX_CONFIRMED |
| 6. Controller zero-change validation | `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-code-review-fix-controller-validation.md` | — | PASS / READY_FOR_DUAL_COMPLETE_CODE_REREVIEW |
| 7. This re-review | `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-code-rereview-mimo.md` | — | PASS / 0 material finding |

- Test diff SHA-256 `9c16a8c7...12e6` 在所有 artifact 中一致 ✓
- Implementation artifact SHA-256 `ee0a7143...32f5` 在所有 artifact 中一致 ✓
- Controller adjudication SHA-256 `c195949a...7562` 在 zero-change artifact 中一致 ✓
- `git rev-parse HEAD` = `15979f5d32738148bf53daf9defe2dca59b8360c` = accepted plan commit ✓
- Accepted finding = 0 的裁决成立：两路 review 均未发现 material finding，Controller 未接受任何 finding，zero-change confirmation 未发现漂移 ✓

### 10. Security / deferred 边界

- S1 added-lines scan 对 `.count(`、`shlex` 与 execution-result/company-name 反推模式：零输出 ✓
- `shell=True` / `errors=replace` scan：零新增 ✓
- Deferred-term scan（Issue 142/151/175/177/178）：零输出 ✓
- 未读取 GitHub Secrets 或 configured production values ✓
- 未产生或记录 raw source、registry value、sentinel、API key、FMP key 或环境 snapshot ✓

## Open Questions

无。

## Residual Risk

- 真实 Windows R11 与 R12 embedded-R11 尚未运行。本地 macOS `pytest` 中两个 real cmd.exe nodes 按 `os.name != "nt"` skip。此状态是 plan §8 的预期：S1/S2/S3 全部 accepted 后才由 Controller dispatch 真实 Windows closure。S1 的 pre-execution oracle 正确性已通过本地 round-trip 与 adversarial 输入独立验证，但最终 `cmd.exe` 下的 argv 行为仍需真实 Windows 证据确认。
- WIN4-S2（setx native stdio/timeout owner）与 WIN4-S3（outer process safe failure projection）尚未实施。S1 不依赖它们，但它们未完成前整体 AR-F07 closure 不可声称。
- Oracle 对 renderer 输出格式的逆向依赖是隐式 contract：若 renderer 修改 quoting 策略（如改变 `^"` 对格式、token 连接符或 `%*` 后缀），oracle 会 fail closed。这是正确行为——fail closed 意味着测试会立即暴露 renderer 变更。

## Decision

**PASS** / 0 material findings / S1 immutable slice 实现正确、最小且所有权清晰。

Zero-change chain 完整成立：implementation → controller validation → dual code review → controller adjudication → zero-change fix confirmation → controller zero-change validation → this re-review 的全部 SHA-256 锁定值无漂移，accepted finding = 0 的裁决经逐项复核确认。Test diff 二进制哈希、HEAD commit、staged tree、production diff、README diff 均精确命中。

S1 满足 plan §4 WIN4-S1 的全部 exact changes 要求：合法 company-name 输入、pre-execution CRLF/Windows token oracle、负例 fail closed、同源 boolean artifact、production/README/workflow 零 diff。测试、pyright、diff-check、安全扫描均通过。下一 gate 可经 Controller 裁决后进入 accepted local commit。
