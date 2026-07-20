# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-RW S1+S2 Aggregate Deepreview（AgentMiMo 第一路）

## Verdict

**PASS / 未发现实质性问题**

本次 aggregate deepreview 是既有 `WU-SEMANTIC-OWNERSHIP-01` / `AR-F07 WIN4-RW` 的第一路完整 aggregate deepreview，不是新 WU。AgentMiMo 独立从零复核 S1 与 S2 全部 implementation、Controller、review、fix、rereview、accepted-commit artifacts 与 control，direct 读取两个 Windows workflows、全部 code/tests/README，fresh 执行 tests/pyright/ruff/scans，未发现 blocker、new findings、backflow findings 或 semantic ownership drift。

## Scope

- Mode: Current Changes Mode（aggregate）
- Umbrella: `WU-SEMANTIC-OWNERSHIP-01`
- Continuation: `AR-F07` WIN4 real-Windows S1+S2
- Branch: `phaseflow/host-issues-control`
- Aggregate base: `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9`
- Current HEAD: `d4e092d1c3ae2110cec2d72a49013130843f7e21`
- Output file: `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-aggregate-deepreview-mimo.md`
- Included scope（six product/test/README paths）:
  - `dayu/cli/commands/init.py` — S2 `_read_secret_input()` owner 及其两个 call sites
  - `tests/cli/test_init_command.py` — S2 secret-input owner exact nodes + S1 fixture 迁移
  - `tests/cli/test_prompt_command.py` — S2 `test_prompt_command_uses_init_generated_workspace_config` fixture 迁移
  - `tests/cli/test_upload_filings_from_command.py` — S1 display dependency 删除 + public repository contracts
  - `README.md` — S2 用户可见 TTY/redirected 行为说明
  - `tests/README.md` — S1+S2 owner test 矩阵说明
- Excluded scope:
  - `.github/workflows/r11-upload-script-windows.yml`、`.github/workflows/r12-init-windows.yml` — 零 diff
  - `tests/cli/test_init_smoke.py`、`dayu/cli/output.py`、`dayu/cli/init_environment.py` — 零 diff
  - `dayu/fins/**` — 零 diff
  - `docs/host/` control/plan/review artifacts — 已读取用于审查依据，不纳入 payload
- Parallel review coverage: 无（scope 有限，单 reviewer 可完整覆盖）

## Immutable State Verification

| Item | Expected | Fresh Actual | Status |
|---|---|---|---|
| Current HEAD | `d4e092d1c3ae2110cec2d72a49013130843f7e21` | `d4e092d1c3ae2110cec2d72a49013130843f7e21` | ✓ MATCH |
| Aggregate base | `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9` | `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9` | ✓ MATCH |
| Six-path aggregate binary diff SHA-256 | `c7be312a39f9aa3ad6e1643db65ad5fdb2f31064b0af13da7421b5477e8ea361` | `c7be312a39f9aa3ad6e1643db65ad5fdb2f31064b0af13da7421b5477e8ea361` | ✓ MATCH |
| `README.md` content SHA-256 | `7cf41485076a96ba80f9ebeb7969c951f18e7478fe789db7a74adc8fde274cce` | `7cf41485076a96ba80f9ebeb7969c951f18e7478fe789db7a74adc8fde274cce` | ✓ MATCH |
| `dayu/cli/commands/init.py` content SHA-256 | `b0601a962034d322f82edef2fbab7ce49e4b4a212b55bd81bbf276823d97e4c4` | `b0601a962034d322f82edef2fbab7ce49e4b4a212b55bd81bbf276823d97e4c4` | ✓ MATCH |
| `tests/README.md` content SHA-256 | `c5de013136b2c816f26d685511921dac9852775df7c0afed0352e2061d1b25fe` | `c5de013136b2c816f26d685511921dac9852775df7c0afed0352e2061d1b25fe` | ✓ MATCH |
| `tests/cli/test_init_command.py` content SHA-256 | `1541fb84398339b202c1ae0f623e85f85c89bd4adc411083183456197bf9e5f8` | `1541fb84398339b202c1ae0f623e85f85c89bd4adc411083183456197bf9e5f8` | ✓ MATCH |
| `tests/cli/test_prompt_command.py` content SHA-256 | `8b9f7df20ebcd36f71c9639e52b42e22d8f8b3511ed44d1f75f918a5ee0ec60a` | `8b9f7df20ebcd36f71c9639e52b42e22d8f8b3511ed44d1f75f918a5ee0ec60a` | ✓ MATCH |
| `tests/cli/test_upload_filings_from_command.py` content SHA-256 | `71855b783ae1191ed764c69c938f2ca29d0c51ae575f501a431e33615ebb4d3d` | `71855b783ae1191ed764c69c938f2ca29d0c51ae575f501a431e33615ebb4d3d` | ✓ MATCH |
| Staged tree | empty | empty | ✓ PASS |
| `git diff --check` | pass | pass | ✓ PASS |

所有六个 product/test/README payload 的 content SHA-256 均由 reviewer fresh 执行 `shasum -a 256` 验证。Six-path aggregate binary diff SHA-256 由 fresh `git diff --binary | shasum -a 256` 验证。

## Fresh Verification Results

| Check | Result |
|---|---|
| `pytest tests/cli/test_init_command.py -x -q` | 41 passed |
| `pytest tests/cli/test_prompt_command.py -x -q` | 45 passed |
| `pytest tests/cli/test_upload_filings_from_command.py -x -q` | 20 passed, 2 skipped（platform marker） |
| `pyright dayu/cli/commands/init.py` | 0 errors, 0 warnings, 0 informations |
| `pyright tests/cli/test_init_command.py` | 0 errors, 0 warnings, 0 informations |
| `pyright tests/cli/test_prompt_command.py` | 0 errors, 0 warnings, 0 informations |
| `pyright tests/cli/test_upload_filings_from_command.py` | 0 errors, 0 warnings, 0 informations |
| `ruff check` (四个文件) | All checks passed! |

## Findings

未发现实质性问题。

## Adversarial Review Detail

### 1. S1: Display Success Dependency 彻底删除

**审查目标**：`assert "Fins result" in execution.stdout` 已彻底删除，未用任何 stdout/stderr/word/parser/regex/count 替代。

**直接证据**：

| 检查项 | 旧代码（已删除） | 当前代码 | 判断 |
|---|---|---|---|
| stdout 内容断言 | `assert "Fins result" in execution.stdout`（旧 line 879） | 已删除（diff `-` 行） | ✓ 彻底删除 |
| stdout 引用 | — | `execution.stdout` 在 `test_windows_generated_script_runs_real_cli_into_temp_storage` 中零引用 | ✓ 无替代 |
| stderr 替代 | — | `assert execution.returncode == 0, execution.stderr`（line 981）— stderr 仅作断言失败诊断，不作成功判断 | ✓ 非替代 |
| `str.find` / `in` / `.count()` 替代 | — | 零此类操作 | ✓ 无替代 |
| `shlex` / `json.loads(stdout)` / regex 解析输出 | — | 零引用 | ✓ 无替代 |

**逐行走读确认**：完整走读 `test_windows_generated_script_runs_real_cli_into_temp_storage`（lines 912–1030），确认成功判断完全依赖 `execution.returncode == 0`（line 981）→ public repository typed contracts（lines 982–1006）。stdout/stderr 不参与业务判断。

**结论**：display dependency 已彻底清除，零回流。**PASS**。

### 2. S1: Exit → Public Storage Facts → Physical Integrity → Oracle 顺序

**直接证据**（line-by-line sequence）：

```
Line 981:  assert execution.returncode == 0, execution.stderr     ← process exit 先验
Line 982:  company_meta = FsCompanyMetaRepository(storage).get_company_meta("AAPL")
Line 983:  assert company_meta.ticker == "AAPL"
Line 984:  assert company_meta.company_name == _WINDOWS_REAL_SMOKE_COMPANY_NAME
Line 985:  source_repository = FsSourceDocumentRepository(storage)
Line 986-990: list_source_document_ids → len == 1 → document_id
Line 992-1006: read_source_snapshot → with block → identity/descriptor assertions
Line 1007-1010: rglob("*") → assert source_artifacts                  ← physical integrity
Line 1011-1030: oracle artifact 写入                                   ← 最后
```

**结论**：顺序正确：process exit → public repository typed facts → snapshot identity → physical integrity → oracle artifact。**PASS**。

### 3. S1: Public Repository 构造与断言正确性

**直接证据**：lines 982-1006。

- `FsCompanyMetaRepository(storage)` 与 `FsSourceDocumentRepository(storage)` 是 `dayu.fins.storage` 公开导出的具体实现。
- Company facts：`get_company_meta("AAPL")` 返回 `CompanyMeta`，断言 exact ticker `"AAPL"` 与 company name `_WINDOWS_REAL_SMOKE_COMPANY_NAME`（`"Apple Inc."`）。
- Source inventory：`list_source_document_ids("AAPL", SourceKind.FILING)` 返回 list，`len == 1` 断言唯一性。
- Snapshot：`read_source_snapshot("AAPL", document_id, SourceKind.FILING, materialize_files=False)` 作为 context manager 进入，`with` 块内断言 `snapshot.ticker`、`snapshot.document_id`、`snapshot.source_kind is SourceKind.FILING`、`snapshot.files` 非空、`snapshot.primary_filename == source_path.name`、primary filename 在 descriptor names 中。
- 所有断言在 `with` 块内执行，snapshot 资源生命周期正确闭合。

**结论**：public repository 构造正确，断言覆盖 identity/ticker/company/唯一 id/SourceKind/primary filename/descriptors。**PASS**。

### 4. S1: Storage Snapshot Lifetime

**直接证据**：lines 992-1006。

```python
with source_repository.read_source_snapshot(
    "AAPL", document_id, SourceKind.FILING, materialize_files=False,
) as snapshot:
    assert snapshot.ticker == "AAPL"
    # ... all assertions inside `with` block
```

- `materialize_files=False` 避免不必要的临时文件物化。
- 所有 snapshot 属性断言在 `with` 块内执行。
- `with` 块结束时 snapshot 资源自动清理。
- 块后只有 `rglob("*")`（physical artifact count）和 oracle 写入，不访问 snapshot。

**结论**：snapshot lifetime 在 `with` 块内闭合，无泄漏。**PASS**。

### 5. S2: stdin Capability Owner 逐行走读

**入口**: `dayu/cli/commands/init.py:468-493` — `sys.stdin.isatty()` 唯一分流点。

**TTY 路径** (`init.py:478-482`):
- `getpass.getpass(prompt)` — 标准库隐藏输入，`init.py:480` 唯一命中点。
- `EOFError` → `CliInitOperationError("secret input ended before completion")` — value-free，`init.py:481-482`。
- `KeyboardInterrupt` 不捕获，原样透传。
- `OSError` 不捕获，原样透传。

**Redirected 路径** (`init.py:484-493`):
- `sys.stderr.write(prompt)` + `sys.stderr.flush()` — prompt 先于读取可见，`init.py:484-485`。
- `sys.stdin.readline()` — 精确一次逐行读取，`init.py:486`。
- `value == ""` → EOF 收敛为同一 value-free `CliInitOperationError`，`init.py:487-488`。
- `value.endswith("\n")` → 移除一个 LF，`init.py:489-490`。
- `value.endswith("\r")` → 移除 LF 前的 CR（CRLF），`init.py:491-492`。
- bare CR 与其它尾随空白保持，不引入 loose normalization。

**结论**：owner boundary 清晰，capability 分流由 `sys.stdin.isatty()` 唯一决定。没有 `hasattr/getattr`、`sys.__stdin__`、platform-specific shim 或 production fallback。**PASS**。

### 6. S2: Call Sites 复用

**直接证据**: `init.py:510, 522` — 两个 call sites 复用同一个 `_read_secret_input()` owner。

- Required (line 510): 空值由 caller `_collect_environment_persistence_plan()` 拒绝 (`init.py:511-512`)。
- Optional (line 522): 空值由 caller 跳过 (`init.py:523`)。
- Input capability owner 不管业务规则；空值判断留在 caller boundary。

**结论**：职责分离清晰，无 owner 重叠。**PASS**。

### 7. S1+S2 组合行为

**审查目标**：S1（test_upload_filings_from_command.py 的 public repository contracts）与 S2（init.py 的 secret-input owner）是否存在交叉回归、overcoupling 或 semantic ownership drift。

**直接证据**：

| 维度 | S1 | S2 | 交叉影响 |
|---|---|---|---|
| 文件 | `test_upload_filings_from_command.py` | `init.py`, `test_init_command.py`, `test_prompt_command.py` | 零重叠 |
| Owner | public repository contracts (`FsCompanyMetaRepository`, `FsSourceDocumentRepository`) | stdin capability owner (`_read_secret_input()`) | 独立 |
| 生产代码改动 | 无（仅测试） | `init.py` 32 行改动 | 无交叉 |
| Import 关系 | S1 imports `dayu.fins.storage` | S2 imports `sys`, `getpass` | 无交叉 |
| Fins/storage | 使用 public contracts | 不涉及 | 无交叉 |
| 诊断输出 | S1 不涉及 | S2 只输出 variable names | 无交叉 |

**结论**：S1 与 S2 是完全独立的 change slice，无交叉回归、无 overcoupling、无 semantic ownership drift。**PASS**。

### 8. R11/R12 Workflow 零 Diff

**直接证据**：
- `git diff 8fafe9ba..HEAD -- .github/workflows/` 为空。
- `.github/workflows/r11-upload-script-windows.yml` 和 `.github/workflows/r12-init-windows.yml` 未被修改。

**结论**：R11/R12 workflow 的 test collection、argv、setx、redirected handle、artifact、canary contract 均未被本次改动影响。**PASS**。

### 9. LLM/Public/Audit/Tool Trace 不泄密

**直接证据**:

| 输出路径 | 内容 | 含 secret value? | 证据 |
|---|---|---|---|
| `sys.stderr.write(prompt)` (redirected) | `"{VAR_NAME}（输入隐藏，不写日志）: "` | 否 | `init.py:484` |
| `getpass.getpass(prompt)` (TTY) | 隐藏输入，OS 级不回显 | 否 | `init.py:480` |
| `CliInitOperationError` | 固定 value-free 文本 | 否 | `init.py:482,488` |
| `CliInitOperationError` (required) | 仅变量名 | 否 | `init.py:512` |
| `print(...)` 确认 | 仅变量名 | 否 | `init.py:537-540` |
| `_environment_failure_message()` | 仅 names | 否 | `init.py:598-610` |
| `_report_persisted_environment_names()` | 仅 names | 否 | `init.py:613-628` |
| `_format_operation_error()` | stage/error/public states | 否 | `init.py:778-796` |
| S1 oracle artifact | `test_node`, `result`, `generated_script_sha256`, `source_artifact_count`, `cmd_invocation`, `company_name_supplied` | 否 | `test_upload_filings_from_command.py:1011-1030` |

**结论**：secret value 不进入 stdout、stderr、exception message、confirmation output、persistence diagnostic、oracle artifact、Tool Trace、audit 或 LLM-facing 文本。**PASS**。

### 10. SQLite/EventLog/Config Trusted-Local 裁决

**直接证据**：
- 本 aggregate 未新增 durable store 或 projection。
- Config、Host internal SQLite/EventLog 继续属于 trusted-local domain。
- 只维持 Tool Trace、audit、public/LLM-facing/operator diagnostics 不得出现 API key/header 明文的现有裁决。

**结论**：trusted-local 边界未被突破。**PASS**。

### 11. 无 Display 成功 Oracle

**直接证据**：
- S1 删除了 `assert "Fins result" in execution.stdout`。
- 当前成功判断完全依赖 `execution.returncode == 0` + public repository typed contracts。
- 不依赖 stdout/stderr display 文案、prefix、substring、regex 或 parser。

**结论**：无 display 成功 oracle。**PASS**。

### 12. 无 Production pytest/mock Fallback

**直接证据**：
- `rg -n 'pytest|mock|capture' dayu/cli/commands/init.py` 为零语义命中。
- `rg -n 'sys\.__stdin__|hasattr|getattr|msvcrt' dayu/cli/commands/init.py` 为零命中。
- `getpass.getpass` 只在 `_read_secret_input()` TTY 分支命中一次。

**结论**：production code 是纯 capability-based router，不识别测试框架、不保留 fallback 路径。**PASS**。

### 13. 无 Unified Secret/Authorization Infrastructure

**直接证据**：
- `rg -n 'unified.*secret|unified.*authorization|secret.*framework|authorization.*framework' dayu/cli/commands/init.py tests/cli/test_init_command.py` 为零命中。
- 本 WU 只修复 stdin capability routing，不引入统一 authorization 框架。

**结论**：未实施 unified secret/authorization infrastructure。**PASS**。

### 14. Deferred Issues 142/151/175/177/178 与 Web/WeChat/render 无渗漏

**直接证据**：
- `rg -n 'issue.*(142|151|175|177|178)' dayu/cli/commands/init.py tests/cli/test_init_command.py tests/cli/test_prompt_command.py tests/cli/test_upload_filings_from_command.py` 为零命中。
- `rg -n 'Web|WeChat|render' dayu/cli/commands/init.py tests/cli/test_init_command.py` 为零命中（`test_prompt_command.py` 和 `test_upload_filings_from_command.py` 中的 `render` 引用是诊断输出变量名，不是 Web/WeChat/render infrastructure）。
- 未实施 setx redesign、console/PTY/process isolation 或 Fins generic diagnostic schema。

**结论**：deferred scope 正确，未越界。**PASS**。

### 15. Semantic Ownership Drift

| 语义 | Owner | 位置 | 独占性 |
|---|---|---|---|
| stdin capability 检测与分流 | `_read_secret_input()` | `init.py:468-493` | 唯一 |
| prompt 内容格式 | caller (`_collect_environment_persistence_plan`) | `init.py:510,522` | 唯一 |
| 空值业务规则 | `_collect_environment_persistence_plan()` | `init.py:511-512,523-524` | 唯一 |
| EOF 收敛消息 | `_read_secret_input()` | `init.py:482,488` | 唯一 |
| 上传成功判断 | public repository contracts | `test_upload_filings_from_command.py:982-1006` | 唯一 |
| Display 文案 | 已删除 | — | 无 owner |

无 owner 重叠。无下游 fallback 修补上游语义。无跨层穿透调用。无反向依赖。

**结论**：semantic ownership drift 未发生。**PASS**。

### 16. Overcoupling

**直接证据**：
- S1 仅修改一个测试文件，不涉及生产代码。
- S2 仅修改 `init.py` 的一个函数和两个 call sites，加上对应的测试和文档。
- 两个 slice 的文件集合零重叠。
- 无 shared helper、无 shared fake、无跨文件 import。
- `test_prompt_command.py` 和 `test_init_command.py` 各自独立定义 `_TtySecretInput`。

**结论**：无 overcoupling。**PASS**。

### 17. Edge Case 矩阵

| Case | Behavior | Evidence |
|---|---|---|
| Redirected stdin 多行 | `readline()` 只读第一行，后续行留给下一次调用 | `init.py:486` |
| 空行作为 required value | `""` (LF stripped) → `CliInitOperationError` | `init.py:489-490, 511-512` |
| bare CR | 保留为值的一部分 | `init.py:491-492` |
| CRLF | CR+LF 均移除 | `init.py:489-492` |
| stdin 为 `None` | `AttributeError` → 外层 `except Exception` → `EXIT_FAILURE` | `init.py:235-240` |
| stderr 写入失败 | `OSError` 透传，无 secret 已读取 | `init.py:484` |
| Secret EOF (TTY) | `EOFError` → `CliInitOperationError`，value-free | `init.py:481-482` |
| Secret EOF (redirected) | `readline()` 返回 `""` → `CliInitOperationError`，value-free | `init.py:487-488` |
| KeyboardInterrupt (TTY) | 原样透传 | `init.py:224-225` |
| KeyboardInterrupt (redirected) | 原样透传 | `init.py:224-225` |
| Exit code 130 (interrupt) | CLI exit 130，不发布 workspace | test evidence |

**结论**：所有 edge case 有直接证据支撑，行为正确。**PASS**。

### 18. Test Fixture 审查

**新增 fixtures** (`test_init_command.py`):
- `_TtySecretInput` (line 170): `isatty()` → `True`，`readline()` → `AssertionError`。Module-private，精确复制 owner capability check。
- `_FlushRecordingStderr` (line 194): 记录 flush count，不改变 `io.StringIO` 语义。
- `_InterruptingRedirectedSecretInput` (line 218): 在 readline 边界抛 interrupt，identity 保持。
- `_install_tty_getpass` (line 325): 组合 TTY stdin + getpass sequence。

**Integration consumer** (`test_prompt_command.py`):
- `_TtySecretInput` (line 104): 独立定义，不从 `test_init_command.py` 导入。Module-private。
- 注入点 (line 1244): `monkeypatch.setattr(init_command.sys, "stdin", _TtySecretInput())`。
- `readline()` fail-fast 确保 TTY path 漂移立即暴露。

**旧 test fixture 迁移** (5 处):
- `_GetpassSequence` → `_install_tty_getpass`：补齐缺失的 TTY capability 声明。
- `_install_ollama_inputs` 内部 (line 365): 同样迁移。
- 不改变 getpass value sequence 或业务断言。

**结论**：所有 fixtures 锁定 owner contract，不固化偶然行为。**PASS**。

### 19. README Boundary

- 根 `README.md`: 一句话解释 TTY vs redirected stdin 行为差异，面向最终用户，不暴露内部实现细节。
- `tests/README.md`: 一段描述 owner test 矩阵和真实 Windows destination，只记录当前事实。

**结论**：均符合各自更新边界。**PASS**。

## Open Questions

无。

## Residual Risk

| # | Risk | Severity | Owner | Destination |
|---|---|---|---|---|
| R1 | Darwin owner tests 不能证明 CPython 3.11 Windows console 与 redirected OS handle 组合行为差异 | 中 | WIN4-RW | Final plan §13.8 fresh R12 dispatch |
| R2 | caller-owned pipe/OS handle 与 CLI process memory 按输入本质暂存 secret value；本 WU 只承诺 CLI 不主动回显或投影 | 低 | 独立安全设计 WU | 不在本 WU scope |
| R3 | fresh R11 storage facts 失败或 fresh R12 在 secret 读取后出现新 failure | 低 | Controller diagnostic-first stop gate | §13.9；必须回 Controller |
| R4 | Full Ruff 142 项为 entry 既有 baseline | 信息 | 独立 Ruff cleanup WU | 本轮精确证明六元组集合与 digest 不变 |
| R5 | S1 `test_windows_generated_script_runs_real_cli_into_temp_storage` 被 `@pytest.mark.skipif(os.name != "nt")` 标记，本机 macOS 无法执行 | 中 | WIN4-RW | Fresh R11 闭合 |

## Review Conclusion

- **PASS/FAIL**: PASS
- **Severity**: 无
- **New findings**: 0
- **Backflow findings**: 0
- **Blocker**: 0
- **Open**: 0
- **Residual owner/destination**: 见 Residual Risk
- **Immutable state**: HEAD `d4e092d1c3ae2110cec2d72a49013130843f7e21`，aggregate base `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9`，staged empty，six-path aggregate binary diff SHA-256 `c7be312a39f9aa3ad6e1643db65ad5fdb2f31064b0af13da7421b5477e8ea361` MATCH
- **Next gate**: aggregate deepreview 完成后，push、fresh R11/R12 dispatch

## Review Metadata

- Reviewer: AgentMiMo
- Review type: aggregate deepreview（第一路，非新 WU）
- Review date: 2026-07-20
- Review time: 08:14:57 +0800
- Aggregate base: `8fafe9bad4828c83fa6cf80a1dc2199fe78472d9`
- Current HEAD: `d4e092d1c3ae2110cec2d72a49013130843f7e21`
- Six-path aggregate binary diff SHA-256: `c7be312a39f9aa3ad6e1643db65ad5fdb2f31064b0af13da7421b5477e8ea361`
- S1 code review (MiMo): PASS
- S1 code rereview (MiMo): PASS
- S2 code review (MiMo): PASS
- S2 code rereview (MiMo): PASS
- S2 plan drift review (MiMo): PASS
- S2 plan drift rereview (MiMo): PASS
- Aggregate deepreview (MiMo): PASS
