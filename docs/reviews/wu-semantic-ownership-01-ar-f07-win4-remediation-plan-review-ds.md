# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4 Remediation Plan — Adversarial Plan Review

## Identity

- **Review type**：adversarial plan review（非新 WU、非 implementation、非 control transition）
- **Reviewer**：AgentDS
- **Target plan**：`docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`
  - SHA-256：`a290f4184b42ce841f7002f7fab179b12caa42c70ca41e5ee8c60c03c3ee2cf6`
- **Codex artifact**：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-remediation-plan-codex.md`
  - SHA-256：`4cff2eeb1bed842a796be5ac6cea974c2d2116fd6f0df2c1be5b3b714786cf71`
- **Controller validation**：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-remediation-plan-controller-validation.md`
- **Evidence adjudication**：`docs/reviews/wu-semantic-ownership-01-ar-f07-fourth-windows-evidence-controller-adjudication.md`
- **Baseline**：`54e2dcbf653fb8c37b0206bd7aabbbf329ef040e`
- **AGENTS.md**：已完整读取并作为审查依据
- **日期**：2026-07-20

## 审查范围与方法

本 review 对 plan 进行结构化对抗审查，覆盖 plan 全部 12 个章节、3 个 slice、validation matrix、negative cases、forbidden paths、README decision 与 next closure matrix。逐项挑战 plan assumption 与 evidence chain，产出带具体反例、owner、严重度与修复建议的 finding，并给出综合结论 pass / pass-with-risks / fail。

---

## 1. F01 根因链与 S1 完备性挑战

### 1.1 根因链审查

**Plan claim**：WIN4-F01 根因是 Windows real-smoke 构造了 `action=create` 且缺少 `company_name` 的无效请求；CRLF/Docling/storage 均非根因。

**Evidence chain 逐项验证**：

| # | Evidence | 验证结果 | 依据 |
|---|----------|----------|------|
| 1 | R11/R12 embedded-R11 均通过生成→argv round-trip→strict UTF-8 后执行 upload 返回 exit 1 | **成立** | Controller 已直接读取 R11 artifact `cli-generated-upload.cmd` 确认无 `--company-name`（controller validation §WIN4-F01） |
| 2 | R11 `.cmd` 业务 argv 不含 `--company-name` | **成立** | Controller 独立确认 |
| 3 | `test_windows_generated_script_runs_real_cli_into_temp_storage` 生成脚本时未传 `--company-name` | **成立** | 代码 `test_upload_filings_from_command.py:844-860`，argv tuple 不含 `--company-name`；对比 POSIX 等价测试 `test_upload_filings_from_command.py:725-739` 显式传 `--company-name "Apple Inc."` |
| 4 | `upsert_company_meta_for_upload()` 对 fresh create 要求 `_require_company_meta_field(..., option_name="--company-name")` | **成立** | `upload_company_meta.py:68-70`，当 `existing_meta is None` 或 `_existing_company_meta_is_fresh` 返回 False 时必定调用 |
| 5 | SEC workflow 捕获异常后 `FinsUploadResultSummary` 丢弃 message | **成立** | Plan 正确识别这是"原因不可见的传播证据"而非根因本身 |
| 6 | Linux public CLI 同输入复现同一 typed failure，pipeline owner result 安全原因是缺 `--company-name` | **成立** | Codex 在 planning gate 已复现（Codex artifact L62-65） |
| 7 | R11 source artifact 与仓库 fixture 只差 8 个 LF→CRLF；CRLF→LF 后逐字节相同 | **成立** | SHA-256 证据由 Controller 计算并匹配 |
| 8 | LF/CRLF 两份 bytes 直调 Docling 均成功 | **成立** | Codex 在 planning gate 已对照（Codex artifact L65-66） |
| 9 | POSIX real workflow 传 `--company-name "Apple Inc."` 并通过 | **成立** | `test_posix_generated_script_runs_real_cli_into_temp_storage` 代码行 738-739 |

**根因链评分**：无逻辑跳跃，无间接证据替代。逐项有直接 artifact 或代码行号支撑。

### 1.2 S1 Oracle 精确性挑战

**Finding 1.2a — Oracle 解析粒度未在 plan 中显式指定（严重度：MEDIUM）**

**反例**：plan §4 WIN4-S1 说"从生成脚本做结构化/精确 oracle，证明 `upload_filing` 命令只出现一个 `--company-name` 且值保持 argv boundary"，但未指定如何区分 regeneration comment 与业务命令。

Windows `.cmd` 脚本格式（由 `render_upload_script(platform="windows")` 生成）：
```
@echo off
chcp 65001 >nul
setlocal DisableDelayedExpansion
# Regenerate: python -m dayu.cli upload_filings_from AAPL --action create --ticker AAPL ... --company-name "Apple Inc."
python -m dayu.cli upload_filing --ticker AAPL --action create ...
```

若 oracle 使用 `"--company-name" in script_content`（简单子串匹配），会在 regeneration comment 行命中，不证明业务命令真正携带该字段。反之，若只搜索非注释行，且 regeneration comment 中的 `--company-name` 被误当作业务命令证据，oracle 给出假阳性。

**Owner**：S1 implementation 的 oracle 解析逻辑，owner 在 `test_windows_generated_script_runs_real_cli_into_temp_storage`。

**修复建议**：plan 应显式要求 oracle 实现以下至少一项：
- (A) 按行解析 `.cmd`，跳过以 `# ` 起始的行，在剩余行中精确匹配 `upload_filing` 命令的 argv token `--company-name` 且下一 token 为 `Apple Inc.`（token-based，非子串）；
- (B) 从 generated script 中提取 `upload_filing` 行，并做 `shlex.split` 等价解析后按 index 验证 `--company-name` 与其值。

plan §5.1 已有 negative case "explicit company name必须进入 generated command一次，不能只进入 regeneration comment"，但未对应到具体 oracle 实现约束。建议在 plan §4 WIN4-S1 "Exact changes" 中增加 oracle 实现的具体策略。

**严重度**：MEDIUM。不阻止 plan 通过，但若实现用简单子串匹配会导致 oracle 不可信。

**验证**：实现后检查 oracle 代码是否区分 comment 行与命令行的 `--company-name` 匹配；构造含 `--company-name` 在 comment 但不在命令行的恶意 `.cmd` 作为 oracle 的 negative input。

---

**Finding 1.2b — Oracle 被错误放置在 post-execution success path（严重度：LOW）**

**反例**：当前 Windows test（L886-904）在 `assert execution.returncode == 0` 之后才写 `cli-grammar-oracle.json`。若 upload 失败（returncode != 0），oracle 不会被写入，但 `--company-name` 是否在 generated script 中的验证也一并跳过。Plan §4 WIN4-S1 step 2 说"在执行 `.cmd` 前"验证 oracle —— 这一点正确，但需要确保 oracle 验证在 execution 失败时不被跳过。

**Owner**：S1 test oracle placement。

**修复建议**：plan 应明确：pre-execution oracle 断言（验证 generated script 包含 `--company-name`）必须在 `subprocess.run` 执行 `.cmd` 之前执行且失败时直接 fail test，不依赖 post-execution success 才写入的 JSON oracle。

**严重度**：LOW。plan 已说"在执行 .cmd 前"，但措辞可以更精确。

**验证**：实现后检查 pre-execution oracle 断言是否在 `subprocess.run` 调用之前且不受 execution returncode 影响。

### 1.3 S1 不会变成 test shim 的证明

**Challenge**：S1 是否为"test shim"——即只在测试中加 `--company-name` 而掩盖了 production 默认工作流缺陷？

**Response**：不成立。理由：

1. Fins owner（`upload_company_meta.py`）**明确要求** fresh create 必须提供 company name。这不是测试约定，是 production contract。
2. POSIX real workflow 已传 `--company-name "Apple Inc."`——这说明 production 正常工作流本来就传该字段。Windows smoke 是唯一缺该字段的调用方。
3. plan 明确禁止了所有 production code 修改：不改 CLI、不改 Fins、不改 storage、不启用 infer、不加默认值、不 preseed。
4. 保留 Fins owner 对缺 company name 的 fail-closed 行为——这证明 S1 没有软化 production contract。

**结论**：S1 是修正 test input 使其匹配 production contract，不是 test shim。

### 1.4 F01 综合结论

**PASS**。根因链充分，S1 方向正确。Finding 1.2a（oracle 解析粒度）和 1.2b（oracle placement）为 implementation-level 注意事项，不改变 plan 有效性。

---

## 2. F02 DEVNULL / close_fds / Timeout 语义挑战

### 2.1 DEVNULL + close_fds 在 Python 3.11 Windows 的语义

**Plan claim**：`stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True` 消除无消费者 pipe，阻止 descendant handle 阻塞 outer CLI capture EOF。

**技术验证**：

| 维度 | 验证 | 依据 |
|------|------|------|
| DEVNULL 与 PIPE 的本质区别 | DEVNULL 打开 `NUL` 设备，`subprocess.run` 不创建 OS pipe 也不启动 reader thread | `subprocess.Popen` 源码：`stdout=DEVNULL` 时 `p2cread`/`c2pwrite` 等 pipe fd 不会被创建 |
| `close_fds=True` Windows 语义 | 子进程只继承显式传入的 stdin/stdout/stderr handle（此处均为 DEVNULL），其余 handle 标记为不可继承 | Python 3.11 `subprocess` 在 Windows 使用 `STARTF_USESTDHANDLES` + `PROC_THREAD_ATTRIBUTE_HANDLE_LIST` |
| `TimeoutExpired` 后的 cleanup | `subprocess.run` 对 direct child 执行 kill→wait；没有 stdout/stderr pipe 时 cleanup 不等待 pipe EOF | `Popen.__exit__` 和 `Popen.wait` 的超时处理中，pipe reader thread 只存在于有 PIPE 时 |
| `text=False` 且无 `capture_output` | 无 PIPE → 无 reader thread → `TimeoutExpired` 的 `output`/`stderr` 为 `None` | `subprocess.TimeoutExpired` 的 `output`/`stderr` 仅在 `stdout=PIPE`/`stderr=PIPE` 时填充 |

**结论**：DEVNULL + close_fds 在 Python 3.11 Windows 上的行为与 plan 描述一致。不产生 pipe，不发生 reader thread 阻塞。

### 2.2 TimeoutExpired 是否可能泄漏 argv/value

**Finding 2.2a — TimeoutExpired.cmd 包含完整 setx argument tuple（严重度：CRITICAL）**

**反例**：`subprocess.TimeoutExpired` 的构造函数为 `__init__(self, cmd, timeout, output=None, stderr=None)`。其中 `cmd` 参数是传给 `subprocess.run` 的 args tuple，即 `("setx", entry.name, entry.value)`。即使 `output` 和 `stderr` 为 None（因 DEVNULL），**`cmd` 字段始终包含完整 argv，其中包括 secret value**。

当前代码（`init_environment.py:416-422`）的 `except OSError` 分支（L432-433）不访问 exception 的 args/cmd/output/stderr，只调用 `_windows_failure_result()`。但 plan 要求在 `except subprocess.TimeoutExpired` 分支中也使用同样方式，**且必须确保 exception object 本身不逃逸出 except block**。

具体风险路径：
1. **str/repr 逃逸**：若 handler 中写 `logger.error(f"setx timed out: {exc}")`，`exc.__str__` 包含 `cmd` tuple 从而泄漏 value。
2. **隐式 propagation**：若 except block 中有其他可能抛异常的代码，导致 TimeoutExpired 被链接为 `__context__`，value 进入 traceback。
3. **test 中构造 TimeoutExpired**：测试需构造 `TimeoutExpired(("setx", "NAME", "secret_value"), 30.0)` 来触发 timeout handler，此构造本身在测试代码中包含 secret-like 字符串。若测试失败，pytest 可能将此字符串写入 JUnit。

**Owner**：`dayu/cli/init_environment.py::_persist_windows_environment()` 的 TimeoutExpired handler。

**修复建议**：plan §2.2 已有相关约束——"不得绑定、格式化、记录或转抛 raw exception"。但建议 plan 增加以下显式约束：
- TimeoutExpired handler 的 except block 内第一行应为 `_names = _collect_unwritten_names(...)` 风格调用，且不将 `exc` 绑定到任何超出 except block 生命周期的变量。
- 测试中的 TimeoutExpired 构造使用显式占位符值（如 `"REDACTED_IN_PRODUCTION"`）而非模拟 secret，以证明 handler 的输出不包含 `exc.cmd[2]`。
- 在 plan §5.2 negative cases 中增加："TimeoutExpired handler 的 except block 内只有 names-only result 构造，不含 logging/format/re-raise/f-string/str(exc)/repr(exc)"。

**严重度**：CRITICAL——若实现违反此约束，API key 明文进入 Tool Trace/audit/JUnit，触发 security gate fail（plan §9.3）。

**验证**：实现后，用随机 sentinel 调真实 setx timeout case（或 mock timeout），`rg` 扫描 JUnit/test stdout/stderr/workflow log 零命中。

---

**Finding 2.2b — 30 秒 timeout 的 magic number 缺乏直接证据（严重度：LOW）**

**反例**：plan 将 `_WINDOWS_SETX_TIMEOUT_SECONDS` 固定为 `30.0`，理由是"单个本机 registry command 的 owner bound"。30 秒对 registry 写入极为充裕（典型 <100ms），但目前没有真实 setx 执行时间测量作为锚定依据。

**Owner**：`_WINDOWS_SETX_TIMEOUT_SECONDS` 常量 owner 在 `init_environment.py`。

**修复建议**：不影响 plan 通过。但在 implementation 完成后、真实 R12 Windows rerun 前，应在真实 Windows runner 记录一次 setx 耗时（可通过 `time.monotonic()` around `subprocess.run`），作为 30 秒合理的经验证据。

**严重度**：LOW。30 秒是保守上界，且 plan 已说明这不是"通过增加 outer timeout 掩盖 hang"。

### 2.3 names-only partial truth 与 no retry 的一致性

**Plan claim**：`TimeoutExpired` 收口为 names-only failure/partial-failure，不 retry。

**验证**：

1. **names-only**：当前 `_windows_failure_result()`（L446-472）只携带 written_names 和 unwritten_names。TimeoutExpired handler 应复用同一函数。一致。
2. **no retry**：plan §2.2 明确禁止 retry，理由正确——timeout 后 setx 的 durable side effect 不确定，retry 扩大不确定性。
3. **partial failure 语义**：若 index 0 的 setx 成功、index 1 的 setx timeout，result 应为 `partial_failure, written=(name0), unwritten=(name1, name2, ...)`。与现有 partial failure 语义一致。

**结论**：一致性成立。无矛盾。

### 2.4 F02 综合结论

**PASS-WITH-RISKS**。DEVNULL/close_fds/timeout 方案正确。Finding 2.2a（TimeoutExpired.cmd 泄漏风险）为 CRITICAL 级 implementation 风险——若 handler 实现不当会触发 security gate fail。plan 已在 §2.2 提出约束但建议加强。

---

## 3. F03 匿名临时文件 + Popen[bytes] 方案挑战

### 3.1 方案复杂度评估

**Plan approach**：用 3 个匿名临时文件承载 stdin/stdout/stderr，`Popen[bytes]` + `wait(timeout=180)` 替代 `subprocess.run(input=..., capture_output=True, text=True)`。

**对比更朴素的替代方案**：

| 方案 | stdin | stdout/stderr | 优点 | 缺点 |
|------|-------|---------------|------|------|
| A（plan） | 匿名 temp file | 匿名 temp files | 完全不依赖 pipe；sentinel 不进入 communicate；descendant pipe EOF 不影响 wait | 代码量较大；需管理 3 个 temp file 生命周期 |
| B | 匿名 temp file | `subprocess.PIPE` + `close_fds=True` | 更少文件管理 | 仍依赖 pipe read；若 descendant 持有 writer handle（尽管理论上 close_fds 阻止），reader 仍阻塞 |
| C | `subprocess.PIPE`（write+close 后 communicate 无 input） | `subprocess.PIPE` + `close_fds=True` | 与当前代码最接近 | sentinel 不在 communicate input 中，但 communicate 仍使用 pipe reader threads |
| D | 匿名 temp file | `subprocess.DEVNULL` | 极简 | 无法读取 stdout/stderr，破坏 success path assertions |

**Finding 3.1a — Plan 选择方案 A 的理由充分但未在 plan 中显式排除方案 B（严重度：LOW）**

方案 B（temp file for stdin + PIPE for stdout/stderr with close_fds=True）在理论上可行，因为：
- stdin 用 temp file 避免了 `input=` 参数（F03 目标）
- `close_fds=True` 阻止子进程的子进程继承 stdout/stderr pipe（F02 目标的防御层）
- `subprocess.run` 的 `wait()` 不读 pipe，只在 `__exit__` 时清理

但方案 B 的风险在 Windows 上更大：`close_fds=True` 在 Windows 的实现不是完美的 handle 关闭，而是通过 `PROC_THREAD_ATTRIBUTE_HANDLE_LIST` 白名单方式。若 `init` 或其依赖的库使用 `subprocess` 的特定参数组合绕过了 handle 继承控制，pipe hang 仍可能复现。Plan 选择方案 A 是更保守、更稳健的决策。

**建议**：plan 可在 §2.3 增加一段"为什么不用 PIPE + close_fds"的简短说明。不影响 plan 通过。

**严重度**：LOW。

### 3.2 cleanup timeout 与 returncode 状态混淆挑战

**Finding 3.2a — Plan 正确区分了四种终止状态，但 cleanup timeout 的行为未指定 completion gate（严重度：MEDIUM）**

Plan §2.3 定义了以下状态：

| 状态 | `returncode_at_timeout` | `cleanup` | `cleanup_returncode` | 测试结果 |
|------|------------------------|-----------|---------------------|---------|
| deadline 前自然退出 0 | N/A（wait 正常返回） | N/A | N/A | pass |
| deadline 前自然退出 1 | N/A（wait 正常返回） | N/A | N/A | fail（`_assert_init_result` 断言 returncode=0 失败） |
| deadline 时仍在运行 → kill 成功 | `not_exited` | `completed` | 负值（Windows kill signal） | fail |
| deadline 时仍在运行 → kill 后 bounded wait timeout | `not_exited` | `timeout` | `not_available` | fail |
| deadline 时已退出（wait 正常返回 1 但接近 deadline） | **未覆盖** | N/A | N/A | 取决于 `wait()` 是否在 180 秒内返回 |

需要区分的边界 case：进程在 wait(180) 的最后 1ms 退出 → `wait()` 返回 returncode → 这是"deadline 前自然退出"，不是 timeout。正确。

但 cleanup timeout 的 completion gate 未指定：若 kill 后 bounded wait timeout，进程可能仍在运行。plan 说"failure path不读取 stdout/stderr内容，只关闭临时文件"。但 temp file handle 关闭后，仍在运行的进程可能因写入已关闭的 handle 而崩溃——这是 acceptable 的（进程已被 kill），但需确认不会产生 zombie。

**Owner**：`tests/cli/test_init_smoke.py::_run_init()` 的 timeout cleanup logic。

**修复建议**：plan §2.3 step 5 应增加：cleanup timeout 后必须调用 `process.poll()` 确认 process 状态（仍运行/已退出），并将此状态记录在 failure message 中（如 `process_state_after_cleanup_timeout=running|exited_<code>`）。不等待、不二次 kill。

**严重度**：MEDIUM。当前 plan 的 cleanup 描述缺少"cleanup timeout 后 process 仍在运行"的终态描述。

### 3.3 sentinel 不泄漏的充分性

**Challenge**：方案能否保证 sentinel 在任何路径下不进入 JUnit/workflow log？

**验证每一条泄漏路径**：

| 泄漏路径 | 防御 | 充分性 |
|----------|------|--------|
| `subprocess.run(input=sentinel)` → `TimeoutExpired.input` | plan 不再使用 `input=` 参数 | **充分** |
| `subprocess._communicate(input, ...)` frame → pytest traceback 展开 locals | plan 不再调用 `communicate()` | **充分** |
| stdin temp file 内容 → pytest `tmp_path` fixture cleanup 时文件被读取 | plan 使用"匿名临时文件"，`close_fds=True`，且 Popen 后清空调用 frame 中的 text/bytes 变量 | **部分**：plan 说"清空本地变量"但未指定文件本身的清理策略（是否在 close 后立即 unlink，还是依赖 pytest tmp_path cleanup） |
| `pytest.fail(safe_message, pytrace=False)` 的 message 中包含 sentinel | plan 明确 renderer 只输出 category/timeout/returncode/cleanup | **充分** |
| `str(exc)` / `repr(exc)` 在 except 块中意外包含 temp file path（进而可能包含 sentinel——虽然 path 本身不含 sentinel） | temp file path 由 `tempfile.mkstemp` 生成，不含 sentinel | **充分** |
| 编码问题时 `UnicodeDecodeError` 包含部分 stdout/stderr 内容 | plan 使用 `errors="strict"`，若出现 decode error，异常 message 只含位置不含内容 | **充分** |
| `cleanup_returncode` 值（如 Windows 上的负值 signal 表示）进入 failure message | renderer 只输出 int 或 not_available | **充分** |

**Finding 3.3a — stdin 匿名临时文件的 unlink 时机未显式指定（严重度：MEDIUM）**

**反例**：plan §2.3 step 1 说"把 `input_text` 用 strict UTF-8 编码后写入 stdin 临时文件并 rewind；随后立即把调用 frame 中的 text/bytes 变量清空"。若 temp file 在 process 仍在运行时被 unlink，Windows 会阻止 unlink（文件被打开）；若 temp file 在 process 退出后才 unlink（正确），但 unlink 失败（权限、av 扫描等），secret-bearing 文件保留在磁盘上。

**Owner**：`tests/cli/test_init_smoke.py::_run_init()`。

**修复建议**：plan 应明确 stdin temp file 的清理契约：
- 启动 Popen 后立即 close parent 端的 stdin file handle（Popen 已 dup 该 handle 给子进程）
- close 后立即 unlink stdin temp file（在 POSIX 上即使子进程仍持有 handle 也可 unlink；Windows 上需在子进程退出后 unlink）
- unlink 失败不吞掉异常，但异常 message 只含 filename（不含 content）
- 工具函数退出前，所有 temp file 必须已 close；unlink 失败时 retained path 记录在 test-local warning 中（不含 content）

**严重度**：MEDIUM。不影响 plan 的逻辑正确性，但影响 F03 安全目标的完整性。

### 3.4 F03 综合结论

**PASS-WITH-RISKS**。方案 correct，成功阻止 sentinel 进入 communicate/TimeoutExpired/pytest traceback。Finding 3.2a（cleanup timeout completion gate）和 3.3a（temp file unlink 时机）为 implementation-level 风险，建议补充到 plan。

---

## 4. Slice 划分、依赖、allowlist、owner 唯一性审查

### 4.1 Slice 结构

| Slice | 文件 | Owner | 依赖 | 独立可验证 | 独立可回滚 |
|-------|------|-------|------|-----------|-----------|
| WIN4-S1 | `tests/cli/test_upload_filings_from_command.py` | Test input/oracle | 无 | ✓ | ✓（git checkout 该文件） |
| WIN4-S2 | `dayu/cli/init_environment.py`; `tests/cli/test_init_environment.py` | Production setx contract | 无（S1 无生产依赖） | ✓（owner tests 独立验证） | ✓（git checkout 两个文件） |
| WIN4-S3 | `tests/cli/test_init_smoke.py`; `tests/README.md` | Test failure projection + docs | S2（S3 不能替代 S2 的 product fix） | ✓（但 real setx smoke 依赖 S2） | S3 自身可回滚；README 需同步回滚 |

**Finding 4.1a — S3 对 S2 的依赖是硬依赖但 plan 未显式标注此为 hard dependency（严重度：LOW）**

**反例**：plan §4 WIN4-S3 说"Dependencies：S2。S3 不得通过 harness cleanup 替代 S2 product fix；owner test 必须能单独证明 S2 kwargs"。这是正确的。但若实现顺序为 S3→S2（例如两 slice 并行开发），S3 的 real setx smoke（`test_windows_real_setx_round_trip_is_name_safe_and_cleaned`）会因 S2 未修复而 timeout。

**建议**：plan §4 的 slice ordering 应明确标注 S2→S3 为 **hard dependency**（S3 不能在没有 S2 的情况下通过 real smoke），而不只是"必须在 S3 前完成"。

**严重度**：LOW。plan 已有显式 ordering，只是措辞可更精确。

### 4.2 Allowlist 合规

**验证**：plan §3.1 allowlist 覆盖了 3 个文件组，共 5 个具体文件路径。plan §3.2 forbidden paths 覆盖了所有不允许修改的路径类别。每个 slice 在 §4 中均有 exact changes 描述和 stop condition。

**结论**：allowlist 充分且与 slice 一一对应。无遗漏。

### 4.3 Owner 唯一性

**验证**：

| 语义 | Plan 指定的 owner | 代码位置 | 是否唯一 |
|------|------------------|---------|---------|
| fresh create 需要 company name | Fins pipeline | `upload_company_meta.py::_require_company_meta_field` | ✓ 唯一 |
| R11 Windows smoke 是否提交满足 owner contract 的请求 | Test input | `test_windows_generated_script_runs_real_cli_into_temp_storage` | ✓ 唯一 |
| setx stdio/timeout | `init_environment.py::_persist_windows_environment` | 同文件 `_persist_windows_environment()` L402-443 | ✓ 唯一 |
| outer CLI subprocess failure projection | `test_init_smoke.py::_run_init()` | 同文件 `_run_init()` L162-199 | ✓ 唯一 |
| CLI renderer（company-name 投影） | CLI renderer | Plan 明确 CLI renderer 不拥有默认公司名 | ✓ |

**结论**：每个语义有唯一 owner，无重复 ownership。无消费者从 raw fields 反推语义的路径。

### 4.4 每 slice 独立验证与回滚风险

**S1 验证**：修改后单独运行 `test_windows_generated_script_runs_real_cli_into_temp_storage` 和 `test_posix_generated_script_runs_real_cli_into_temp_storage`。若失败，`git checkout` 该文件即可回滚。独立、可执行。

**S2 验证**：修改后运行 `tests/cli/test_init_environment.py` 全部 owner tests + 新增 timeout/DEVNULL tests。若失败，`git checkout` 两个文件即可回滚。独立、可执行。

**S3 验证**：修改后运行 `tests/cli/test_init_smoke.py`（real smoke 依赖 S2）。若 S3 自身失败但 S2 已正确，只回滚 S3 文件即可。但若 S3 暴露了 S2 的未发现缺陷，需回到 S2 修复。Plan 已有 stop condition 处理此情况。

**Finding 4.4a — S3 回滚后 tests/README.md 回滚的一致性（严重度：LOW）**

`tests/README.md` 在 S3 中更新。若 S3 回滚但 README 未同步回滚，docs 与实际行为不一致。但这是标准 Git 回滚行为——`git checkout` 两个文件即可。plan 可注明 README 与代码变更在同一 commit 中。

**严重度**：LOW。标准实践。

### 4.5 逐 slice gate 可执行性

**验证 plan §4 各 slice 的 stop condition**：

| Slice | Stop condition | 触发时动作 | 可执行性 |
|-------|---------------|-----------|---------|
| S1 | "若 adding explicit company name 需要修改 production CLI/Fins..." | 停止并回 Controller | **可执行**：条件具体，可判定 |
| S2 | "如果 DEVNULL+close_fds+native timeout 仍要求 process tree kill..." | 停止并回 Controller | **可执行**：条件涉及验证结果 |
| S3 | "如果需要修改 pytest/JUnit plugin、workflow redact..." | 停止并回 Controller | **可执行**：条件具体 |

**结论**：每个 slice 有明确的 gate 和 stop condition。可独立验证、独立决策是否继续。

### 4.6 Slice 综合结论

**PASS**。Slice 划分合理，依赖清晰，owner 唯一，gate 可执行。

---

## 5. Coverage / Pyright / Ruff / README / Security 闭合矩阵审查

### 5.1 Coverage

**Plan §6.3 要求**：`dayu/cli/init_environment.py` 单文件 line coverage ≥ 80%。

**评估**：当前 `test_init_environment.py` 已对 `_persist_windows_environment()` 覆盖：
- success（两个 setx 都 returncode 0）→ `test_windows_uses_argument_tuple_binary_capture_and_injects_only_after_all_success`
- partial failure（returncode nonzero）→ `test_windows_partial_failure_reports_names_only_and_injects_nothing`
- first failure → `test_windows_first_failure_has_failure_status_and_no_injection`
- OSError → `test_windows_partial_failure_reports_names_only_and_injects_nothing`（failure_mode="os-error"）
- KeyboardInterrupt（first/middle/last）→ `test_windows_interrupt_reports_written_and_unwritten_names_without_values`

**新增覆盖需求**：
- `TimeoutExpired` handler → 需要新增 test case
- `_WINDOWS_SETX_TIMEOUT_SECONDS` 常量的使用 → 需要 test case 验证 timeout=30.0 被传入 `subprocess.run`
- DEVNULL/close_fds/shell=False 等 kwargs → 需要更新 `_SetxRecorder` 签名并断言

**Finding 5.1a — `_SetxRecorder` 的当前签名不匹配 plan 的新 kwargs（严重度：MEDIUM）**

**反例**：当前 `_SetxRecorder.__call__` 的签名包含 `capture_output: bool, text: bool` 参数（L60-63），且断言 recorder 收到 `capture_output=True, text=False`（L1034-1036）：
```python
assert recorder.calls == [
    (("setx", first.name, first.value), False, True, False, False),
    (("setx", second.name, second.value), False, True, False, False),
]
```

Plan 要求移除 `capture_output`，改用 `stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL, close_fds=True, timeout=30.0, text=False`。`_SetxRecorder` 的签名需相应更新（移除 `capture_output`，增加 `stdin`/`stdout`/`stderr`/`close_fds`/`timeout`），且所有现有 test 需同步更新断言。

这不仅是 S2 的 add，也是 S2 的 modify——需更新现有 test 的 fake signature 和断言。

**Owner**：`tests/cli/test_init_environment.py::_SetxRecorder`。

**修复建议**：plan §4 WIN4-S2 "Exact changes" step 4 已提到"更新 `_SetxRecorder` 严格签名/记录字段；fake output 删除，因为生产不再拥有输出。"这覆盖了本 finding。但 plan 应明确：现有 7 个 test 函数的 recorder 断言均需同步更新（涉及 `test_windows_uses_argument_tuple_binary_capture_and_injects_only_after_all_success`、`test_windows_partial_failure_*`、`test_windows_first_failure_*`、`test_windows_interrupt_*`、`test_windows_environment_injection_interrupt_*`），而非仅新增 test。

**严重度**：MEDIUM。plan 已有提及但未量化影响面。

### 5.2 Pyright

**Plan §6.4 要求**：`python -m pyright dayu/ tests/ utils/` 零诊断。

**评估**：plan 的修改不引入 Any、object 或无类型签名。新增代码（TimeoutExpired handler、temp file 管理、test-local typed result）预计不会引入类型问题。但需注意：
- `tempfile.mkstemp` 返回 `tuple[int, str]`，类型明确
- `os.fdopen` 返回 `BinaryIO`
- `subprocess.Popen[bytes]` 的泛型参数需显式提供

**结论**：plan 范围内无已知 pyright 风险。

### 5.3 Ruff

**Plan §6.4 要求**：scoped Ruff 零诊断，full Ruff baseline 精确比较零差异。

**评估**：无新依赖、无复杂逻辑引入。scoped Ruff 覆盖文件少（4 个），风险低。

**结论**：无已知 Ruff 风险。

### 5.4 README

**Plan §7 决策**：只更新 `tests/README.md`。

**验证**：
- 根 `README.md`：plan 认为"public init grammar、交互步骤、输出通道与最终用户工作流不变"——成立，S1-S3 均为内部修复不改变用户可见行为
- `dayu/fins/README.md`：Fins production contract 不变——成立
- `dayu/config/README.md`、`dayu/README.md`、设计 docs：无 schema/layer/assembly 变化——成立

**结论**：README decision 正确。

### 5.5 Security

**Plan §6.6 要求**：4 条 `rg` 扫描零输出（除 README 允许的说明性引用）。

**评估**：plan 的 security boundary 清晰：
- Config/Host internal SQLite/EventLog 可含 API key/header（trusted local）
- Tool Trace/audit/public/LLM-facing/operator log 禁止明文
- S1-S3 不碰这些 durable stores，也不新增它们的 projection
- Gemini low-budget 保持 NO_CODE_ACTION

**Finding 5.5a — Plan 未覆盖 real R11/R12 Windows run 的 secret scan（严重度：MEDIUM）**

**反例**：plan §9.3 定义了 security gate（任一 sentinel/configured value 出现在 JUnit/workflow log → gate fail），且 plan §8 的 closure matrix 要求"JUnit/stdout/stderr always-upload；不得含 configured/test secret value"。但 plan 未指定 WHO 执行此 scan 和 HOW。

**Owner**：Controller（gate 执行者）。

**修复建议**：plan §8 closure matrix 应增加一行 "Secret scan" gate，包含：
- 执行者：Controller 或其委派的 Agent
- 方法：对 R11/R12 全部 uploaded artifact 执行 `rg` 扫描，使用每次 run 的唯一 sentinel
- 通过条件：零命中（不含 sentinel 的 base64/URL-safe 表示、不含 `input_text` 字面量）

**严重度**：MEDIUM。不影响 plan 本身，但影响 AR-F07 最终 closure 的可执行性。

### 5.6 真实 R11/R12 closure matrix 审查

**Plan §8** 定义了 7 个 gate + 1 个 overall success condition。

**Finding 5.6a — "R11 real upload: pass" gate 的两个可能状态需要在 plan 中建立清晰的裁决树（严重度：MEDIUM）**

Gate 要求："generated command含一次 company-name；exit 0；terminal success；portfolio source artifact >0"。但若 S1 合法化输入后 upload 仍失败：

- plan §10 定义了 diagnostic-first stop gate
- 但不清楚此 gate 的 result 是 "R11 real upload: failed"（阻塞 R11 overall success）还是 "R11 real upload: needs-diagnostic, see §10"（要求 plan amendment 但不一定阻塞其他 gate）

**修复建议**：plan §8 matrix 的 "R11 real upload" gate 应增加第三种可能结果：`NEEDS_MORE_EVIDENCE`，对应 §10 流程。此结果不自动等价于 gate fail——它表示需要先执行 diagnostic-first 步骤再判定。

**严重度**：MEDIUM。不影响 plan 的 implementation 执行，但影响 Controller 的 closure 判定。

### 5.7 Matrix 综合结论

**PASS-WITH-RISKS**。覆盖矩阵充分，命令均可执行。Finding 5.1a（_SetxRecorder 签名更新影响面）、5.5a（secret scan 执行者未指定）和 5.6a（R11 upload gate 状态完整性）为 implementation-level 注意事项。

---

## 6. Forbidden Paths 合规审查

### 6.1 逐条验证

plan §3.2 列出 10 类禁止修改的路径和变更。逐条验证 plan 自身是否遵守：

| # | Forbidden | Plan 自身是否违反 | 证据 |
|---|-----------|-----------------|------|
| 1 | 不修改 `issues-implementation-control.md` | ✓ 遵守 | plan §0 明确"不是 control-doc transition" |
| 2 | 不修改 `.github/workflows/r11-*.yml` / `r12-*.yml` | ✓ 遵守 | plan §3.2 明确禁止 |
| 3 | 不修改 Fins/CLI production code | ✓ 遵守 | allowlist 只含 test files（S1）、init_environment（S2）、test_init_smoke（S3） |
| 4 | 不加 default company name、FMP infer、network、preseed | ✓ 遵守 | plan §2.1 明确"保留 Fins 对缺字段的 fail-closed 行为" |
| 5 | 不换 setx 为 shell/PowerShell/reg.exe/winreg/retry/skip | ✓ 遵守 | plan §2.2 固定 argument tuple `("setx", ...)` 且 `shell=False` |
| 6 | 不增加 outer 180s timeout、不 mock real setx、不放宽 strict UTF-8 | ✓ 遵守 | plan §2.2 明确不增加 outer timeout；§2.3 保留 strict UTF-8 |
| 7 | 不记录 setx stdout/stderr/value 到 exception/log/JUnit/artifact | ✓ 遵守 | plan §2.2 明确"不得绑定、格式化、记录或转抛 raw exception" |
| 8 | 不修改 Config/Host trusted-local secret 裁决、不新增 secret infra | ✓ 遵守 | plan §11 明确 zero unified authorization/secret infra |
| 9 | 不实施 Issue 142/151/175/177/178 或 Web/WeChat/render | ✓ 遵守 | plan §11 明确禁止；§10 明确不借 diagnostic-first 进入 Issue 175 |
| 10 | 不 stage/commit/push/dispatch workflow/PR/merge | ✓ 遵守 | plan §0 和 §11 多次明确 |

**结论**：plan 自身完全遵守 forbidden paths。无越界。

### 6.2 用户特别禁止项验证

用户明确禁止：
- default company name
- FMP/network
- preseed meta
- Fins/Docling/storage/direct schema
- registry 替换
- outer timeout 增加
- skip/xfail
- Issue 142/151/175/177/178
- Web/WeChat/render
- 统一 authorization 或 secret infrastructure

**验证**：plan §2.1、§2.2、§3.2、§10、§11 逐项禁止。未在 allowlist 或任何 slice 的 exact changes 中出现上述路径。

**结论**：完全合规。

### 6.3 用户裁决验证

用户裁决两条：
1. Config/Host internal SQLite/EventLog trusted local 可含 API key/header
2. Tool Trace/audit 禁止明文
3. Gemini 低预算 NO_CODE_ACTION

**验证**：plan 在 §2.1、§2.2、§6.6、§8、§9。未修改这些裁决，未新增 Tool Trace/audit projection，Gemini 保持 NO_CODE_ACTION。

**结论**：完全合规。

---

## 7. 综合结论

### 7.1 逐挑战领域结论

| # | 挑战领域 | 结论 | 关键 finding |
|---|---------|------|-------------|
| 1 | F01 根因链 | **PASS** | Finding 1.2a：oracle 解析粒度待实现时明确 |
| 2 | F02 DEVNULL/close_fds/timeout | **PASS-WITH-RISKS** | Finding 2.2a（CRITICAL）：TimeoutExpired.cmd 含 secret value，handler 实现不当会触发 security gate fail |
| 3 | F03 temp files/Popen 方案 | **PASS-WITH-RISKS** | Finding 3.2a：cleanup timeout completion gate 未指定；Finding 3.3a：temp file unlink 时机 |
| 4 | Slice 划分/依赖/gate | **PASS** | Finding 4.1a：S2→S3 硬依赖措辞可精确化 |
| 5 | Coverage/pyright/Ruff/README/security | **PASS-WITH-RISKS** | Finding 5.1a：_SetxRecorder 签名更新影响面；Finding 5.5a：secret scan 执行者未指定；Finding 5.6a：R11 upload gate 状态完整性 |
| 6 | Forbidden paths | **PASS** | 无违反 |
| 7 | 用户裁决 | **PASS** | 无违反 |

### 7.2 总体结论

**PASS-WITH-RISKS**

Plan 的三个 slice 方案在技术上是正确的：
- WIN4-F01 根因链充分，S1 修正 test input 而非 production code
- WIN4-F02 的 DEVNULL+close_fds+30s timeout 是正确的 production fix，不是增加 outer timeout 掩盖 hang
- WIN4-F03 的匿名 temp files + Popen[bytes] + wait 方案正确阻止 sentinel 进入 communicate/TimeoutExpired/pytest traceback

Slice 划分合理，owner 唯一，forbidden paths 完全合规，用户裁决得到遵守。

**4 个 CRITICAL/HIGH 级 implementation 风险**（不阻止 plan 通过，但必须在 implementation 和 review 中逐项验证）：

1. **CRITICAL — Finding 2.2a**：`subprocess.TimeoutExpired.cmd` 包含完整 setx argv（含 entry.value）。S2 的 TimeoutExpired handler 必须确保 exception object 不逃逸出 except block，不被 format/log/re-raise/f-string。违反则 API key 明文进入 Tool Trace/audit/JUnit，触发 security gate fail。

2. **MEDIUM — Finding 3.2a**：cleanup timeout 后 process 状态未在 plan 中显式建模。需增加 `process_state_after_cleanup_timeout` 字段以确保 cleanup timeout 不被静默忽略。

3. **MEDIUM — Finding 3.3a**：stdin temp file 的 unlink 时机和失败处理未在 plan 中显式指定。sentinel-bearing temp file 残留在磁盘上会破坏 F03 安全目标。

4. **MEDIUM — Finding 5.1a**：`_SetxRecorder` 签名需更新以匹配 plan 的新 kwargs（移除 capture_output，增加 stdin/stdout/stderr/close_fds/timeout），影响现有至少 7 个 test 函数的断言。plan 已提及但应量化影响面。

### 7.3 推荐补充到 Plan 的约束

建议在 plan §2.2（F02）、§2.3（F03）、§4（WIN4-S2）、§8（closure matrix）中增加以下约束（非强制，但可减少 implementation review 的往返次数）：

1. **§2.2**：增加 "TimeoutExpired handler 的 except block 内禁止 logging/format/re-raise/f-string/str(exc)/repr(exc)；exception 引用不逃逸出 except block 作用域"。
2. **§2.3 step 5**：增加 "cleanup timeout 后调用 process.poll() 记录终态，不等待、不二次 kill"。
3. **§2.3 step 1**：增加 "stdin temp file 在 Popen 启动后立即 close+unlink（Windows 上需在 process 退出后 unlink）；unlink 失败记录 retained path 不含 content"。
4. **§4 WIN4-S1 Exact changes step 2**：增加 oracle 实现策略——按行解析 `.cmd`，跳过 `# ` 注释行，在命令行中做 token-based `--company-name` 匹配。
5. **§8 closure matrix**：增加 "Secret scan" gate 行，指定执行者和通过条件。

---

## Artifact 信息

- **路径**：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-remediation-plan-review-ds.md`
- **SHA-256**：`cb3f796fa49f9075821fb4f19fc3ee29037ddcde0bb8cbc10966c6a23373f4e6`
- **基线 HEAD**：`54e2dcbf653fb8c37b0206bd7aabbbf329ef040e`
- **审查结论**：`PASS-WITH-RISKS`
- **下一 gate**：AgentMiMo 完成并发 plan review 后，由 Controller 汇总 findings 并裁决是否进入 implementation
