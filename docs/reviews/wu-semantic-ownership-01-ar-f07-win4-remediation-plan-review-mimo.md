# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-F01..03 Remediation Plan — AgentMiMo Adversarial Review

## Gate identity

- Work unit：既有 `WU-SEMANTIC-OWNERSHIP-01` umbrella。
- Continuation：`AR-F07` 第四轮真实 Windows evidence remediation。
- Gate：完整 adversarial plan review。
- Baseline HEAD：`54e2dcbf653fb8c37b0206bd7aabbbf329ef040e`。
- Plan SHA-256：`a290f4184b42ce841f7002f7fab179b12caa42c70ca41e5ee8c60c03c3ee2cf6`。
- AgentCodex artifact SHA-256：`4cff2eeb1bed842a796be5ac6cea974c2d2116fd6f0df2c1be5b3b714786cf71`。
- 本 artifact 不是 implementation、不是 control transition、不 stage/commit/push。

## 固定输入完整性确认

| 输入 | SHA-256 / 路径 | 状态 |
| --- | --- | --- |
| Plan | `a290f418...` | 已完整读取，528 lines |
| AgentCodex artifact | `4cff2eeb...` | 已完整读取，80 lines |
| Controller validation | `docs/reviews/...-controller-validation.md` | 已完整读取 |
| Evidence adjudication | `docs/reviews/...-controller-adjudication.md` | 已完整读取 |
| AGENTS.md | `AGENTS.md` | 已完整读取 |
| Controller discussion | `docs/reviews/...-overdesign-controller-discussion.md` | 已完整读取 |
| `init_environment.py` | `dayu/cli/init_environment.py` | 已完整读取，836 lines |
| `test_init_smoke.py` | `tests/cli/test_init_smoke.py` | 已完整读取，963 lines |
| `test_init_environment.py` | `tests/cli/test_init_environment.py` | 已完整读取，1246 lines |
| `test_upload_filings_from_command.py` | `tests/cli/test_upload_filings_from_command.py` | 已完整读取，1012 lines |
| Remote evidence roots | §1.2 R11/R12 | SHA 与 Controller adjudication 匹配 |

## 逐项对抗审查

### 1. WIN4-F01 根因链充分性

#### 1.1 根因是否仅是 Windows real-smoke fresh create 漏传 company-name

**结论：PASS。**

直接证据链完整且逻辑/数据同源：

1. R11 主 job 与 R12 embedded R11 都在 `upload_filing` 后返回 exit 1（evidence adjudication §Positive closure 4）。
2. R11 artifact `cli-generated-upload.cmd` 的业务 argv 缺 `--company-name`（Controller validation §F01 独立检查）。
3. `upsert_company_meta_for_upload()` 对 fresh create/update fail closed 要求 `--company-name`（`init_environment.py` 无关，这是 Fins owner）。
4. 在 baseline Linux public CLI 路径用 R11 真实 source 复现同一 typed failure，直接读 pipeline owner result 得到缺 company-name 原因。
5. LF/CRLF 两份 bytes 直调 Docling 均成功，排除 CRLF/Docling/storage 作为 root cause。
6. 既有 POSIX real workflow 显式传 `Apple Inc.` 并通过。

没有间接迹象替代根因判断。唯一 owner 正确锁定为 `test_windows_generated_script_runs_real_cli_into_temp_storage` 的 input 构造。

#### 1.2 S1 是否会变成 test shim、简单字符串计数、掩盖 production 默认工作流或漏掉 regeneration comment/body 区分

**结论：PASS_WITH_RISK — RISK-1。**

**正面**：
- S1 只修改 test 文件的 generation argv，不修改 production CLI/Fins。
- POSIX real workflow (L712-768) 已经有 `--company-name "Apple Inc."`，Windows test (L832-904) 缺失 — 修复方向正确。
- Plan §4 S1.2 要求 "从生成脚本做结构化/精确 oracle"，§5.1 要求 "explicit company name 必须进入 generated command 一次，不能只进入 regeneration comment"。

**风险 RISK-1**：Plan 对 S1 oracle 的实现方法只有 "结构化/精确 oracle" 的措辞，没有明确禁止简单字符串计数。Windows `.cmd` 文件包含 regeneration comment（`@REM python -m dayu.cli upload_filings_from ...`）和实际业务命令行。如果实施者用 `content.count("--company-name")` 做 oracle，可能误匹配 regeneration comment 行。

**反例**：假设 `.cmd` 内容为：
```
@echo off
@REM python -m dayu.cli upload_filings_from --ticker AAPL --company-name Apple Inc.
python -m dayu.cli upload_filing --action create --ticker AAPL --files ...
```
简单计数会说 `--company-name` 出现 1 次，但实际业务命令没有。

**修复建议**：S1 oracle 应解析 `.cmd` 文件，区分 `@REM` 注释行和实际命令行，验证 `--company-name` 只出现在业务命令中。或者验证生成的 `.cmd` 文件经 `cmd.exe /d /c` 执行后 exit 0 — 这已经是现有 oracle 的一部分。

**验证**：re-review 时检查 S1 实现的 oracle 是否区分 comment 和 command。

**严重度**：Low。Plan 的意图正确，只是实现指导不够具体。且现有 test 已经验证 execution returncode=0，如果 company-name 确实缺失，Fins 会 fail closed 导致 exit 1。

---

### 2. WIN4-F02 DEVNULL/close_fds/Python 3.11 Windows stdio handle 语义和 30 秒 direct timeout

#### 2.1 DEVNULL + close_fds 是否正确

**结论：PASS。**

1. 当前 `capture_output=True, text=False` → stdout/stderr pipe 零消费者 → pipe lifetime 越过 outer process → descendant handle 阻塞 EOF。
2. 改为 `stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL` → native tree 持有 NUL 设备 handle → NUL 的 EOF 不被阻塞。
3. `close_fds=True` 在 Windows 上当不使用 PIPE 时默认就是 True，显式声明更安全。
4. Python 3.11 `subprocess.run` 对 DEVNULL 的实现是打开 `os.devnull`，正确。

#### 2.2 30 秒 direct timeout 是否正确

**结论：PASS。**

1. setx 是简单 registry 写入命令，正常执行 <1 秒。30 秒是合理上界。
2. outer smoke budget 180 秒，30 秒留出充足清理/报告空间。
3. `subprocess.run(timeout=30)` 对 direct child 执行 timeout kill/wait。
4. 没有 stdout/stderr pipe 后，kill 后 wait 不等待 descendant pipe EOF。

#### 2.3 TimeoutExpired 是否可能泄漏 argv/value

**结论：PASS。**

1. Plan §2.2 明确要求 "TimeoutExpired 必须在该 owner 内与 OSError 一样收口为当前 index 的 names-only failure/partial-failure；不得绑定、格式化、记录或转抛 raw exception，因为 exception args 含完整 setx argv/value"。
2. `_windows_failure_result()` (L446-472) 只返回 written/unwritten names，不含 value。
3. `EnvironmentPersistenceEntry` 的 `value` 字段 `repr=False` (L102)，`EnvironmentPersistenceResult` 不含 value。
4. `EnvironmentPersistenceInterrupted` 继承 `KeyboardInterrupt`，`result` 只含 names。

#### 2.4 names-only partial truth 与 no retry 是否一致

**结论：PASS。**

1. Timeout 后 setx 是否已产生 durable side effect 不明。
2. Plan 禁止 retry — 正确，重试会扩大不确定写入。
3. names-only truth 正确区分 "已确认写入" (written_names) 和 "未确认写入" (unwritten_names)。
4. `partial_failure` 状态正确表达 "部分成功、部分未确认"。

---

### 3. WIN4-F03 匿名 temporary files + Popen[bytes] + wait 而非 communicate(input)

#### 3.1 是否真能在 Windows 避免 descendant pipe EOF hang 与 sentinel 进入 pytest/JUnit

**结论：PASS。**

1. **sentinel 泄漏解决**：input_text 编码后写入匿名临时文件，Popen 用 `stdin=file_handle`。即使 pytest 展开 Popen frame，stdin 参数是 file handle，不是 secret-bearing string。
2. **descendant pipe EOF hang 解决**：stdout/stderr 写入普通文件（不是 pipe）。`wait()` 只等进程退出，不等 pipe EOF。即使 descendant 持有文件 writer handle，文件的读取不受 pipe EOF 语义约束。
3. **Plan §2.3.5 timeout path**：先 `poll()` 记录 `returncode_at_timeout`，若仍运行则 kill + bounded wait，记录 `cleanup_returncode`。failure path 不读取 stdout/stderr 内容，只关闭临时文件。正确。

#### 3.2 success、ordinary nonzero、deadline 时 returncode、kill 后 returncode、cleanup timeout 是否不混淆

**结论：PASS。**

1. **success**：`wait()` 返回 0 → rewind + read output files + decode。
2. **ordinary nonzero**：`wait()` 返回非 0 → 正常读取 returncode，由 `_assert_init_result` 按 returncode 失败。
3. **deadline 时已退出**：`poll()` 返回非 None → `returncode_at_timeout=<int>`。
4. **deadline 时未退出**：`poll()` 返回 None → `returncode_at_timeout=not_exited` → kill → `cleanup_returncode=<int>`。
5. **cleanup timeout**：bounded wait 也超时 → `cleanup=timeout`。
6. Plan 明确要求 "cleanup 产生的 returncode 只能放在 cleanup_returncode，不能伪造成自然退出 0"。正确区分。

#### 3.3 是否引入不必要复杂度或更朴素安全方案

**结论：PASS。必要复杂度。**

1. 更朴素方案（stdin 临时文件 + stdout/stderr pipe + communicate）不能解决 descendant pipe EOF hang。
2. 更朴素方案（stdin 临时文件 + stdout/stderr DEVNULL）不能满足测试消费者需要读取 stdout/stderr 的需求。`_assert_init_result` 检查 `result.stdout` 中的 `mode=`，`test_posix_real_profile_mode_marker_and_redaction` 检查 stdout/stderr 中的 secret 不泄漏。
3. 3 个匿名临时文件是必要且充分的方案。

#### 3.4 "清空本地变量" 的安全边界

**结论：PASS。已有明确定义。**

Plan §2.3 说 "启动后立即把调用 frame 中的 text/bytes 变量清空"。Controller validation §5 说 "'清空本地变量'只能用于降低 failure-frame 持有，不得被写成内存擦除保证；安全 acceptance 是 sentinel 不进入 JUnit/workflow/review evidence"。Plan 已经正确框定了边界。

---

### 4. 三 slice 划分、依赖、allowlist、owner 唯一性、逐 slice 完整 gate

**结论：PASS_WITH_RISK — RISK-2。**

#### 4.1 划分合理性

| Slice | 目的 | Allowlist | Owner | 依赖 |
| --- | --- | --- | --- | --- |
| S1 | 修正 R11 输入 | `test_upload_filings_from_command.py` | test | 无 |
| S2 | setx native stdio/timeout | `init_environment.py`, `test_init_environment.py` | production + test | 无（与 S1 独立） |
| S3 | outer harness safe failure | `test_init_smoke.py`, `tests/README.md` | test harness | S2 |

- S1 独立于 S2/S3，可先行验证 F01 不再污染 R12 embedded-R11。
- S2 修改 production，必须在 S3 前完成（S3 的 harness 改动依赖 S2 的 setx 修复）。
- S3 不通过 harness cleanup 替代 S2 product fix — Plan §4 S3.3 明确禁止。

#### 4.2 Owner 唯一性

- S1: `test_windows_generated_script_runs_real_cli_into_temp_storage` — 唯一 test owner。
- S2: `_persist_windows_environment()` — 唯一 production owner。
- S3: `_run_init()` — 唯一 test harness owner。
- `tests/README.md` 只在 S3 统一更新 — 避免多 slice 共享写 owner。

#### 4.3 每 slice 独立验证/回滚

- 每 slice 有独立 negative cases (§5)、stop condition (§4) 和 validation matrix (§6)。
- allowlist 确保每个 slice 的改动范围不越界。

#### 4.4 风险 RISK-2：S1 与 S2 的并行可能性

Plan 说 S1 "先于 S2/S3 实施"，但 S1 与 S2 无生产依赖。如果实施者串行执行 S1→S2→S3，总时间 = S1 + S2 + S3。如果 S1 与 S2 可并行（不同文件），总时间 = max(S1, S2) + S3。Plan 没有明确禁止并行，但 "先于" 的措辞暗示串行。

**严重度**：Negligible。串行执行更安全，且 S1 很小（只改一个 test 文件的几行）。

---

### 5. coverage/pyright/Ruff/README/source/security/真实 R11/R12 closure matrix

**结论：PASS。**

#### 5.1 Coverage

- `dayu/cli/init_environment.py` line coverage >= 80%，新增 timeout/DEVNULL/failure branch 被 owner tests 直接命中。
- 不用 pragma、omit 或删测试降低分母。
- 可执行：`pytest tests/cli/test_init_environment.py --cov=dayu.cli.init_environment --cov-branch --cov-report=term-missing`。

#### 5.2 pyright

- full pyright 零诊断。
- S2 新增 `_WINDOWS_SETX_TIMEOUT_SECONDS: Final[float] = 30.0` 类型安全。
- `subprocess.TimeoutExpired` 捕获类型安全。
- S3 的 `Popen[bytes]` 类型安全。

#### 5.3 Ruff

- scoped Ruff 零诊断。
- full Ruff 既有 baseline 按 `(filename, location, code, message, fix-applicability)` 精确比较。
- 不用总数相同替代逐项比较。

#### 5.4 README

- 只更新 `tests/README.md`。
- 根 `README.md`、`dayu/fins/README.md`、`dayu/config/README.md`、`dayu/README.md`、design docs 不更新。
- 与 AGENTS.md README 触发规则一致。

#### 5.5 Source/security scans

- `capture_output=True` 在 `init_environment.py` 中零命中 — 正确。
- `shell=True`、`errors=replace` 在相关文件中零命中 — 正确。
- `winreg`、`reg.exe`、`PowerShell` 等在实现文件中零命中 — 正确。
- Issue 142/151/175/177/178 在实现文件中零命中 — 正确。
- 动态 sentinel 验证 `str/repr/captured/JUnit-safe message` 零命中 — 正确。

#### 5.6 真实 R11/R12 closure matrix

7 个 gate 定义完整：
- R11 capability、four nodes、argv、real upload — 正确。
- R12 init、embedded R11 — 正确。
- Artifact integrity — 正确。
- Gemini low-budget 保持 `NO_CODE_ACTION`，不进入 matrix — 正确。

#### 5.7 不可能命令检查

所有 validation 命令都是标准 Python/pytest/pyright/Ruff/git/rg 命令，可在 CI 和本地执行。没有不可能命令。

---

### 6. 禁区检查

**结论：PASS。**

Plan §3.2 和 §11 完整覆盖了所有禁区：

| 禁区 | Plan 状态 |
| --- | --- |
| default company name | 明确禁止 |
| FMP/network | 明确禁止 |
| preseed meta | 明确禁止 |
| Fins/Docling/storage/direct schema | 明确禁止修改 |
| registry 替换 | 明确禁止 |
| outer timeout 增加 | 明确禁止 |
| skip/xfail | 明确禁止 |
| Issue 142/151/175/177/178 | 明确禁止 |
| Web/WeChat/render | 明确禁止 |
| 统一 authorization/secret infrastructure | 明确禁止 |

---

### 7. 用户裁决遵守

**结论：PASS。**

| 裁决 | Plan 状态 |
| --- | --- |
| Config/Host internal SQLite/EventLog trusted local 可含 API key/header | §6.6 确认边界不变 |
| Tool Trace/audit 禁止明文 | §9.3 security gate fail 条件 |
| Gemini 低预算 NO_CODE_ACTION | §8 明确不进入 closure matrix |
| 不复制 sentinel/secret/raw content | §1.2、AgentCodex artifact §Validation 确认 |

---

## Finding 汇总

| ID | 类别 | 严重度 | Owner | 描述 | 修复建议 | 验证方法 |
| --- | --- | --- | --- | --- | --- | --- |
| RISK-1 | F01 oracle 质量 | Low | S1 实施者 | S1 oracle 实现指导不够具体，可能用简单字符串计数而非结构化解析区分 regeneration comment 和业务 command | S1 oracle 应解析 `.cmd` 文件区分 `@REM` 注释行和实际命令行；或验证 execution returncode=0（已有） | re-review 时检查 S1 实现 |
| RISK-2 | Slice 并行 | Negligible | Plan | S1 与 S2 无生产依赖但 Plan 暗示串行执行 | 串行执行更安全，无需修改 | 无需修改 |

## 逐项挑战证据总结

1. **F01 根因链**：6 条直接证据链完整，唯一 owner 正确锁定。RISK-1 是 oracle 实现质量风险，不是否定根因。
2. **F02 DEVNULL/timeout**：DEVNULL 在 Python 3.11 Windows 上的语义正确，30 秒 timeout 合理，TimeoutExpired 收口到 names-only failure 正确，no retry 正确。
3. **F03 Popen[bytes]/wait**：匿名临时文件解决 sentinel 泄漏，wait 替代 communicate 解决 frame 展开，普通文件替代 pipe 解决 descendant EOF hang，returncode 语义区分正确。
4. **三 slice 划分**：按 owner 和依赖切分，每个 slice 有唯一 owner、allowlist、negative cases、stop condition。
5. **Validation matrix**：完整且可执行，没有不可能命令。
6. **禁区检查**：Plan §3.2 和 §11 完整覆盖所有禁区。
7. **用户裁决**：Config/Host trusted-local、Tool Trace/audit、Gemini 低预算全部正确遵守。

## 结论

**PASS_WITH_RISKS。**

Plan 的 root cause 诊断基于直接证据，逻辑/数据同源；三 slice 划分合理且 owner 唯一；技术方案（DEVNULL、close_fds、direct timeout、匿名临时文件、Popen[bytes] + wait）在 Python 3.11 Windows 语义下正确；validation matrix 完整可执行；禁区和用户裁决全部遵守。

两个 risk 均为 Low/Negligible 级别，不构成 plan fail。RISK-1 的 oracle 质量可在 implementation re-review 时验证；RISK-2 无需修改。

**下一 gate**：implementation（S1→S2→S3），完成后 dual complete re-review。

---

## Artifact integrity

- 本 artifact 不含随机 sentinel、registry value、configured secret、raw source content 或用户绝对路径。
- 本 artifact 不修改 plan/control/production/tests，不 stage/commit/push。
- 本 artifact 路径：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-remediation-plan-review-mimo.md`。
