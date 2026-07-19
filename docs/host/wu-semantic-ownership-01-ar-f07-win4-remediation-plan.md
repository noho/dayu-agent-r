# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-F01..03 Remediation Plan

## 0. Gate identity and decision

- Umbrella work unit：`WU-SEMANTIC-OWNERSHIP-01`。
- Continuation：`AR-F07` 第四轮真实 Windows evidence remediation。
- 当前 gate：同一remediation plan gate内的plan re-review finding fix；不是新WU。
- Baseline HEAD：`54e2dcbf653fb8c37b0206bd7aabbbf329ef040e`。
- 风险级别：High Risk。WIN4-F02 修改生产 Windows native process contract；WIN4-F01 与
  WIN4-F03 修改 release-gate/test-evidence contract。
- 当前结论：`PLAN_REREVIEW_FINDINGS_FIXED / READY_FOR_CONTROLLER_VALIDATION_AND_DUAL_COMPLETE_REREVIEW /
  IMPLEMENTATION_NOT_AUTHORIZED`。
- 本文不是新 WU、sub-WU、implementation artifact、accepted-plan commit 或 control-doc transition。

本轮动机成立，但三个 finding 的严重性不同：

1. WIN4-F01 不是未知的 Windows storage/Docling defect。直接 owner evidence 已把本次失败锁定为
   Windows real-smoke 构造了一个 `action=create` 且缺少 `company_name` 的无效请求；Fins 正确
   fail closed，通用 direct projection 只让表面原因变得不可见。
2. WIN4-F02 是真实生产缺陷。`setx` 的输出没有消费者，却被放入 capture pipe；native command
   又没有自己的 timeout。真实 evidence 证明 outer Python 已退出为 1 后 stdout reader 仍等不到
   EOF，说明 descendant handle lifetime 已越过 outer process lifetime。
3. WIN4-F03 是独立 test-evidence hygiene 缺陷。pytest/JUnit 展开 `subprocess` 内部 frame 时把
   `input` 参数中的随机 sentinel 写进失败证据。它必须修复，但不能把 WIN4-F02 从失败变成 skip、
   pass 或无 traceback 的模糊错误。

### 0.1 Plan-review disposition lock

Controller 对两路完整 plan review 与 plan re-review 的裁决是本 gate 的唯一 finding disposition
真源。本轮在保持 `WIN4-PR-F01..F04` 全部闭合和既有边界的前提下，只关闭
`WIN4-PR-RR-F01..F02`；不得把 rejected / already-satisfied candidate 重新引入 implementation：

- `TimeoutExpired` 已由 §2.2 与 WIN4-S2 锁定为不绑定、不格式化、不记录、不转抛 raw exception；
  保持该约束，不增加 exception inspection、logging、redaction shim 或 traceback repair。
- 不为 30 秒 owner budget 在真实 workflow 增加 timing instrumentation。
- 不枚举或逐一实现 `PIPE` / handle-table / process-tree 等替代方案。
- S2→S3 现有依赖已经是必须先后关系，不新增 dependency framework。
- `tests/README.md` 与 S3 保持同一 slice 的提交/回滚边界，不新增 docs transaction 机制。
- `_SetxRecorder` 仍按实际受影响测试扫描并更新，不在 plan 冻结易漂移的测试数量。
- unexpected WIN4-F01 recurrence 继续按 §9.1 / §10 进入
  `NEEDS_MORE_EVIDENCE / DIAGNOSTIC_FIRST PLAN AMENDMENT REQUIRED`；它阻塞 closure，不成为当前
  root cause 的第二种解释。
- 保持用户指定的 S1→S2→S3 串行顺序，不改为并行实施。

DS 对临时文件的 named-path 建议只接受“必须明确 cleanup contract”这一风险事实；`mkstemp`、
`NamedTemporaryFile`、pytest `tmp_path`、retained-path warning、显式 unlink 与新的 cleanup framework
均被拒绝。§2.3 锁定 anonymous handle lifetime，不建立 durable test-artifact path 语义。

## 1. Inputs and immutable evidence

### 1.1 Governing inputs

- `AGENTS.md`
- `docs/host/issues-implementation-control.md`
- `docs/phaseflow-umbrella-optimization-control.md`
- `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`
- `docs/reviews/wu-semantic-ownership-01-ar-f07-fourth-windows-evidence-controller-adjudication.md`
- `docs/fins/design.md`
- `docs/ui/design.md`
- `docs/host/design.md` 中 trusted-local Config/Host durable secret 与 public/trace/audit 禁止明文边界
- `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`
- `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`

R12 原计划 §5.3 曾锁定 `setx(..., capture_output=True)`。第四轮真实 Windows evidence 已直接
证伪 capture pipe 是无害实现细节；本计划只替换这项失效的 native stdio 决定，不重开 R12
其它 transaction、registry authority、secret persistence 或 reset 设计。

### 1.2 Remote evidence roots

- R11：
  `workspace/tmp/wu-semantic-ownership-01-ar-f07-r11-29695780994/r11-windows-upload-script-29695780994`
- R12：
  `workspace/tmp/wu-semantic-ownership-01-ar-f07-r12-29695780992/r12-init-windows-29695780992`

Accepted hashes：

| Evidence | SHA-256 |
| --- | --- |
| R11 JUnit | `ad93c02307272bf9a1fcd3da10863ffc3621978f435b73ab8951d8c0d09076b7` |
| R11 pytest stdout | `bb4250e89da3f66815fca1485a9ded5a312391e9f7132bc11fc0ad51214d8fad` |
| R12 init JUnit | `8a66c5f29785d371ca3e8ae2e02133fb5a9019e2536a63db046644f97f708004` |
| R12 embedded-R11 JUnit | `495cda81c6b7a3f2337157cf6831cd0681ab7e28e7944a0ad026b32747e79812` |
| R12 source hashes | `1dfc56fd75f36573aa4c3847ce35ccedf985b4e4d7b06d2d78ed7147b98a64c3` |

本计划不复制随机 sentinel、registry value、configured secret、raw source content 或用户绝对路径。

## 2. First-principles ownership judgment

### 2.1 WIN4-F01 — root cause established

#### Direct evidence chain

1. R11 主 job 与 R12 embedded R11 都已通过生成、真实 `cmd.exe` argv round-trip、CLI strict
   UTF-8 和 test strict UTF-8；两处都在执行真实 `upload_filing` 后返回 exit 1。
2. R11 artifact `cli-storage/cli-generated-upload.cmd` 的业务 argv 是：
   `upload_filing --action create --ticker AAPL --files <one filing> --fiscal-year 2024
   --fiscal-period FY`。它没有 `--company-name`。
3. `tests/cli/test_upload_filings_from_command.py::test_windows_generated_script_runs_real_cli_into_temp_storage`
   生成该脚本时也没有传 `--company-name`；storage root 是 fresh temp directory。
4. Fins owner `dayu/fins/pipelines/upload_company_meta.py::upsert_company_meta_for_upload()` 只在已有
   current resolver-version company meta 时允许省略 company arguments。fresh create/update 必须通过
   `_require_company_meta_field(..., option_name="--company-name")` 提供公司名，否则抛 `ValueError`。
5. 现有 SEC workflow 在包含 company-meta、Docling prepare 与 storage publish 的大 try block 捕获异常，
   生成 `status="failed", message=str(exc)`；随后
   `FinsUploadPipelineResult.from_pipeline_json()` 和 `FinsUploadResultSummary` 丢弃 message，direct runtime
   因而只能投影固定“上传运行时返回失败状态”。这是原因不可见的传播证据，不是根因本身。
6. 使用下载自 R11 的真实 source artifact、同样不传 company name，在 baseline Linux public
   CLI→Service→Fins 路径稳定复现同一 typed failure；直接读取现有 pipeline owner result 得到安全原因
   `create/update` 缺少 `--company-name`。
7. R11 source artifact SHA-256 是
   `7473d33d2b53e02753e0f52f82ac57f72a653e0d3cdd513e25f95d34943a96e6`；仓库 fixture
   SHA-256 是 `24a830a0f1256e371d36a1f7f72e5e85a38037d1de2f6f966eb8457db42ff6d6`。
   前者只是 8 个 LF 被 Windows checkout 转成 CRLF；CRLF→LF 后逐字节相同。
8. 对 LF 与 CRLF 两份 bytes 直接调用当前 Docling owner，两者都成功返回 `ConversionResult`。
   因此 CRLF、Docling conversion 与 storage publication 都不是本次失败根因。
9. 既有 POSIX real workflow 明确传 `--company-name "Apple Inc."`，并在 baseline 通过；它和 Windows
   smoke 的关键业务输入并不等价。

#### Unique owners

- “fresh create/update 是否需要公司名”的唯一业务 owner：
  `dayu/fins/pipelines/upload_company_meta.py`。
- “R11 Windows real-smoke 是否向公共 CLI 提交满足 owner contract 的请求”的唯一 test owner：
  `test_windows_generated_script_runs_real_cli_into_temp_storage`。
- CLI renderer 只机械投影 `UploadBatchPlan` 中已有的 `company_name`；它不拥有默认公司名，不得访问 storage
  猜 fresh/existing，也不得从 ticker 推导公司名。

#### What remains unproved

- 现有 generic direct projection 仍不足以诊断任意新的 storage/Docling/third-party failure；本轮没有证据证明
  当前 R11/R12 还存在第二个这类失败。
- 不能仅凭通用 `status=failed` 证明 production projection 应新增通用 failure-stage schema、异常类型
  schema、diagnostic artifact store 或 LLM-facing detail。
- 下一轮在补齐合法 company-name 输入后若仍失败，该新 evidence 不能被归入当前已证明 root cause；必须
  触发 §10 的 diagnostic-first stop gate，不得继续猜 storage/Docling。

#### Minimal remediation decision

只修正 Windows real-smoke 的无效输入，使其与既有 POSIX real workflow 一样显式传
`--company-name "Apple Inc."`，并在生成脚本 oracle 中证明该字段被机械保留。保留 Fins 对缺字段的
fail-closed 行为和已有 owner test；不修改 CLI/Fins production code，不增加默认值、FMP/network infer、
preseeded company meta、message parsing、fallback 或 diagnostic schema。

### 2.2 WIN4-F02 — root cause boundary established, OS implementation detail not overclaimed

#### Direct evidence chain

1. strict UTF-8 consumer 修复后，R12 init 9 nodes 中只有真实 setx node 失败；这证伪 decode 单因。
2. R12 JUnit 的 `subprocess._communicate()` evidence 显示 outer Popen 已有 `returncode: 1`，但
   `stdout_thread.is_alive()` 仍为真并在 180 秒后抛 `TimeoutExpired`。
3. 因此已直接证明：outer CLI process 已退出，至少一个 descendant/继承者仍持有 outer stdout pipe 的
   writer handle，阻止 EOF。不能把它解释为“outer init 仍在运行 180 秒”。
4. init 产品路径的唯一显式 native process 创建点是
   `dayu/cli/init_environment.py::_persist_windows_environment()` 中的 `setx`；FIRST/RESET prewarm 只做
   Python import，并且 setx failure 在 prewarm 前终止 init。
5. 当前 setx call 使用 `capture_output=True, text=False`，但代码只读取 `returncode`。stdout/stderr bytes
   没有任何生产消费者、错误消费者、日志消费者或测试 oracle。
6. 当前 setx call 没有 native-command timeout。outer test 的 180 秒是测试总预算，不是产品 native
   process contract，也不能负责清理 descendant handle。

#### Unique owner

Windows `setx` executable、argv、stdio、handle inheritance、单次 process timeout 与 returncode→typed
names-only result 的唯一 owner 是 `dayu/cli/init_environment.py::_persist_windows_environment()`。
Registry round-trip/cleanup 是真实 smoke 的验证 owner，不是 production persistence authority。

#### What remains unproved

- 当前 artifact 没有 process-tree/handle-table dump，不能证明 handle 的最终 Windows implementation owner
  是 `setx.exe` 本体、console host 还是它创建的 descendant。
- 不需要为最小修复证明该 OS 私有细节：产品 contract 只需不把无消费者的 pipe 暴露给 native tree，
  不继承 outer stdin/stdout/stderr，并为直接 `setx` process 提供自己的 bound。
- 不能从 returncode 1 猜 registry 写入失败原因；registry value 仍由 real round-trip owner验证，不能改成
  Python registry write/query authority。

#### Minimal remediation decision

把每次 setx invocation 固定为：

- argument tuple `("setx", entry.name, entry.value)`；
- `shell=False`；
- `stdin=subprocess.DEVNULL`；
- `stdout=subprocess.DEVNULL`；
- `stderr=subprocess.DEVNULL`；
- `close_fds=True`；
- `text=False`；
- `check=False`；
- `timeout=_WINDOWS_SETX_TIMEOUT_SECONDS`，模块级常量固定为 `30.0` 秒。

理由：setx output 无消费者，pipe 没有语义价值；DEVNULL 让 native tree 即使继续持有继承 stdio，也只持有
DEVNULL，不再阻塞 outer CLI capture EOF。`close_fds=True` 禁止继承其它不必要 handle。30 秒是单个本机
registry command 的 owner bound，并在 outer 180 秒 smoke budget 内留下明确清理/报告空间；它不是通过增加
outer timeout 掩盖 hang。

`subprocess.TimeoutExpired` 必须在该 owner 内与 `OSError` 一样收口为当前 index 的 names-only
failure/partial-failure；不得绑定、格式化、记录或转抛 raw exception，因为 exception args 含完整 setx argv/value。
`subprocess.run` 对 direct child 执行 timeout kill/wait；没有 stdout/stderr pipe 后其 cleanup 不再等待 descendant
pipe EOF。禁止 retry：`setx` 是否已产生 durable side effect 在 timeout 后不明，重试会扩大不确定写入。

### 2.3 WIN4-F03 — safe test failure projection

#### Direct evidence chain

1. test 使用随机 `secrets.token_urlsafe(32)` 作为 API-key sentinel，并通过
   `_run_init(..., input_text=f"6\n{sentinel}\ny\n")` 传给 `subprocess.run(input=...)`。
2. `subprocess.run` 把该值继续作为 `Popen.communicate(input, timeout)` 和
   `_communicate(input, endtime, timeout)` 的局部参数。
3. pytest JUnit failure traceback 展开 `input = ...`，因此把 sentinel 完整复制到 workflow artifact。
4. 该值不是用户 configured secret，但测试 contract 明确承诺 failure evidence 只显示 env name；当前 harness
   自己破坏了这一承诺。

#### Unique owner

`tests/cli/test_init_smoke.py::_run_init()` 及其 test-local timeout renderer 是 outer CLI subprocess failure
projection 的唯一 owner。production CLI、`init_environment`、JUnit plugin 和 workflow log 不得各自加 redact
fallback。

#### Minimal remediation decision

把 `_run_init()` 改为显式、strict UTF-8 的 `subprocess.Popen[bytes]` lifecycle，并用三个
`tempfile.TemporaryFile(mode="w+b")` context handle 承载 stdin/stdout/stderr：

1. 在同一 context lifetime 内创建 stdin/stdout/stderr 三个 anonymous binary handle。启动 subprocess 前把
   `input_text` 用 strict UTF-8 编码后写入 stdin handle、flush 并 rewind；随后立即把调用 frame 中的
   text/bytes 变量清空。Popen 只接收 handle，不接收 secret-bearing `input=`。
2. stdout/stderr 分别写入其 anonymous handle。二者有真实测试消费者，因此不能像 setx 一样改 DEVNULL；
   普通文件不需要等待 descendant 关闭 writer pipe，outer process lifetime 与 output EOF 不再耦合。
3. 启动时保留现有 command/cwd/env，固定 `shell=False`、`close_fds=True`，不启用 text mode；wait helper只调用
   `wait(timeout=180)`，不接收 input，不调用 `communicate()`。三个 handle 必须覆盖 child execution 与
   bounded cleanup 的完整生命周期。
4. 成功时 rewind并读取两个 output临时文件，用 `bytes.decode("utf-8", errors="strict")` 解码后返回 test-local
   typed result `returncode/stdout/stderr`；result不保留 argv/path/input。
5. timeout时先 `poll()` 记录 `returncode_at_timeout`；若仍运行则 kill direct outer process并 bounded wait，记录
   `cleanup_returncode` 与 cleanup state。若 bounded cleanup 再次 timeout，只额外调用一次非阻塞 `poll()`：
   `None` 投影为 `process_state_after_cleanup_timeout=running` 与
   `cleanup_returncode=not_available`；integer 投影为
   `process_state_after_cleanup_timeout=exited` 并把该 integer 记录为 `cleanup_returncode`。此后不得再次等待、
   再次 kill、递归治理 process tree，或把 poll 观察到的状态伪装成 deadline 前自然退出。failure path不读取
   stdout/stderr内容。
6. 用唯一 test-local renderer产生：
   `category=dayu_cli_init_timeout timeout_seconds=180 returncode_at_timeout=<int|not_exited>
   cleanup=<completed|timeout> cleanup_returncode=<int|not_available>`；仅在 cleanup timeout 时追加
   `process_state_after_cleanup_timeout=<running|exited>`。不得包含 args、cwd、workspace path、stdin、stdout、
   stderr或exception repr。
7. 通过 `pytest.fail(safe_message, pytrace=False)` 保留明确失败而不让 pytest展开持有 process/input的内部frames。
   它不skip、不swallow、不返回success；若 S2 尚未修复，WIN4-F02仍会以 timeout/category/returncode失败。
8. 三个 handle 在 helper 的 `finally` / context unwind 中统一关闭；不记录 path，不使用 `mkstemp`、
   `NamedTemporaryFile` 或 pytest `tmp_path` 承载 sentinel，不增加显式 unlink、retained-path warning 或新的
   cleanup framework。安全 contract 是 anonymous handle lifetime 与 evidence 零泄漏，不是 durable path 清理。

为使真实 evidence non-disclosure gate 可由 Controller 独立执行，真实 Windows setx test 还必须使用固定的
run-specific non-secret canary contract：

1. R12 workflow环境只读取公开 `GITHUB_RUN_ID`。先要求该值是正十进制整数，再用其 canonical decimal text
   `str(int(GITHUB_RUN_ID))` 作为纯函数输入；`GITHUB_ACTIONS=true` 时缺失或非法必须在启动被测 CLI 前 fail closed。
2. Domain separator 的唯一真值是 Python bytes literal
   `b"dayu-ar-f07-win4-r12-canary-v1\x00"`。该 literal 求值后是完整 31 bytes，末字节是单一 NUL
   `0x00`；不得实现为包含 backslash + zero 的 `b"dayu-ar-f07-win4-r12-canary-v1\\0"`，也不得
   实现为包含字面 backslash + `x00` 的 `b"dayu-ar-f07-win4-r12-canary-v1\\x00"`。计算
   `sha256(domain_separator + canonical_run_id.encode("ascii")).hexdigest()`，最终 canary 为
   `sk-dayu-test-<64 lowercase hex digest>`。已知向量冻结为 canonical run id `"1"` 必须产生
   `sk-dayu-test-b8f2210d1ead3aac3a52408adb9de03c4e848d4c101f790e218ecc76e3350b97`。该函数无
   secret/key/salt、无时间或随机输入；prefix只让输入保持 API-key-shaped，不表示真实
   credential。
3. 本地非 GitHub Actions 路径继续使用 `secrets.token_urlsafe(32)`，不要求 Controller扫描本地随机值。
4. R12 setx test 的 owner tests 必须锁定第 2 项的完整 domain-separator bytes、末字节 single NUL
   `0x00` 和已知 run-id→canary 向量；任一 byte、canonicalization、prefix 或 digest 算法漂移都必须失败。
   R12 setx test继续断言实际选中的 canary/sentinel 不进入 stdout、stderr或safe failure text。R12 workflow
   不得把canary写入辅助 artifact来帮助Controller取得needle。
5. 不读取GitHub Secrets或configured production values，也不把它们加入scan范围；当前workflow没有把这些值作为
   本 test input。该限制不改变trusted-local Config/Host durable secret与Tool Trace/audit零明文裁决。
6. Test owner 与 Controller owner 必须分别仅依据本节冻结的 bytes/formula/vector 实现与独立重算；
   禁止共享 production helper、test helper、生成的 needle artifact 或其它共享实现真源。

timeout cleanup 只治理 test outer process，不成为 production setx fix，不杀任意 process tree，不引入 Windows
job object/process-isolation framework，也不实施 Issue 175。

## 3. Allowed and forbidden paths

### 3.1 Slice allowlist

| Slice | Allowed paths | Ownership purpose |
| --- | --- | --- |
| WIN4-S1 | `tests/cli/test_upload_filings_from_command.py` | 修正 R11/R12 embedded-R11 real-smoke 的无效 company-meta 输入与安全 oracle |
| WIN4-S2 | `dayu/cli/init_environment.py`; `tests/cli/test_init_environment.py` | setx native stdio/timeout owner与 owner-level tests |
| WIN4-S3 | `tests/cli/test_init_smoke.py`; `tests/README.md` | outer process safe failure projection、真实 smoke说明与最终验证入口 |

`tests/README.md` 只在 S3 统一更新，避免多个 slice 共享写 owner。

### 3.2 Explicitly forbidden paths and changes

- 不修改 `docs/host/issues-implementation-control.md`；本 plan gate 不做 control transition。
- 不修改 `.github/workflows/r11-upload-script-windows.yml` 或
  `.github/workflows/r12-init-windows.yml`；现有 triggers、locked install、JUnit 和 always-upload 已足够。
- 不修改 `dayu/cli/commands/fins.py`、`dayu/cli/upload_script.py`、`dayu/fins/upload_batch.py`、
  Fins pipeline/storage/Docling production code或 direct result schema。
- 不给缺失 company name 增加 ticker-derived default、Apple 特例、FMP infer、network request、preseeded
  storage、CLI/test fallback 或 message parsing。
- 不把 setx 改为 `shell=True`、command string、PowerShell、`reg.exe`、`winreg`、profile file、registry
  fallback、retry 或 test skip。
- 不增加 outer 180 秒 timeout，不把 real setx node改成 mock，不放宽 strict UTF-8。
- 不记录 setx stdout/stderr，不把 value 写进 exception、log、JUnit、workflow artifact 或 review artifact。
- 不修改 Config/Host trusted-local secret裁决，不新增 secret infrastructure或统一 authorization。
- 不实施 Issue 142、151、175、177、178 或 Web/WeChat/render deferred 能力。
- 不 stage、commit、push、dispatch workflow、创建/修改 PR、merge、mark ready、关闭 issue。

## 4. Ordered implementation slices

### WIN4-S1 — Valid R11 create input and deterministic evidence

Objective：让 Windows real CLI storage smoke 提交满足现有 Fins owner contract 的 create 请求。

Exact changes：

1. 在 Windows real-smoke 的 `upload_filings_from` generation argv 显式追加
   `--company-name`, `Apple Inc.`，与 POSIX real workflow 对齐。
2. 在执行 `.cmd` 前运行并 fail closed 的 pre-execution oracle：按 CRLF physical line 识别生成脚本，排除
   `REM Regenerate:` 注释与 renderer 固定 batch header，只允许并提取唯一非 `REM` 的 `upload_filing` 业务命令；
   再使用现有 Windows batch/CRT argv oracle或等价的 Windows 语义逐 token解析，断言
   `--company-name` token恰好一个且其下一 token精确等于 `Apple Inc.`。不得使用 whole-file `count`、
   substring presence、POSIX loose parser、从 execution result反推输入，或只证明 regeneration comment含该参数。
3. 成功 oracle 增加布尔事实 `company_name_supplied=true`，不把它误写成 Fins upload root-cause schema。
4. 保留 exit 0、terminal success、source artifact count 与 real `cmd.exe /d /c` 证明。

Dependencies：无代码依赖；先于 S2/S3实施，便于独立确认 F01 不再污染 R12 embedded-R11。

Stop condition：若 adding explicit company name 需要修改 production CLI/Fins、启用 infer/network、预置 storage
或解析错误 message，立即停止并回 Controller。

### WIN4-S2 — Windows setx native stdio and timeout owner

Objective：删除无消费者 pipe，封闭 handle inheritance，并让每个 native setx call 自有 bound。

Exact changes：

1. 增加模块级 `_WINDOWS_SETX_TIMEOUT_SECONDS: Final[float] = 30.0`。
2. 按 §2.2 固定 subprocess kwargs；禁止 `capture_output`。
3. 精确捕获 `subprocess.TimeoutExpired`，不绑定 exception，复用 `_windows_failure_result()` 的
   written/unwritten names truth。
4. 更新 `_SetxRecorder` 严格签名/记录字段；fake output删除，因为生产不再拥有输出。
5. 新增 success、nonzero、OSError、TimeoutExpired、KeyboardInterrupt 的 argv/stdio/timeout/no-retry/
   no-env-injection断言；timeout exception即使构造时带 raw argv/value，也不得出现在 result/repr/capture。

Dependencies：S1无生产依赖；S2必须在 S3 real harness最终验证前完成。

Stop condition：如果 DEVNULL+close_fds+native timeout 仍要求 process tree kill、Win32 handle enumeration、
job object、registry authority替换或 outer timeout增加，停止并回 Controller；不得在本 slice扩域。

### WIN4-S3 — Timeout-safe outer harness and final docs

Objective：测试失败继续暴露 F02，同时任何路径都不把 stdin sentinel复制到 JUnit/workflow log。

Exact changes：

1. 按 §2.3 建立 test-local typed process result、三个
   `tempfile.TemporaryFile(mode="w+b")` context handles、wait/cleanup 与 safe failure renderer；不引入
   named path / unlink framework。
2. 新增 deterministic timeout negative cases，至少覆盖 `returncode=1` 与 `returncode=not_exited`；失败文本必须
   保留 category、timeout、returncode、cleanup state；cleanup timeout 后还必须覆盖单次 non-blocking poll 的
   `running` 与 `exited` 投影，且不含 sentinel、argv、cwd、path、stdout/stderr。
3. 按 §2.3 的冻结纯函数选择R12真实Windows setx canary：GitHub Actions路径只从公开`GITHUB_RUN_ID`确定性派生，
   workflow缺失/非法run id时fail closed；本地非workflow路径可随机。增加纯函数determinism、完整
   domain-separator bytes、末字节single NUL、已知run-id向量、API-key-shaped输出、workflow fail-closed与
   local-random owner tests，并断言canary不进入stdout/stderr/safe failure。Test 与 Controller 不共享
   helper、constant module或artifact needle。
4. 保留所有现有 success-path strict UTF-8、returncode、stdout/stderr断言。
5. 更新 `tests/README.md`：setx native output不被产品捕获，outer real CLI仍 strict UTF-8 capture；timeout
   artifact只记录 category/timeout/returncode/cleanup与变量名，不记录 input value。

Dependencies：S2。S3 不得通过 harness cleanup替代 S2 product fix；owner test必须能单独证明 S2 kwargs。

Stop condition：如果需要修改 pytest/JUnit plugin、workflow redact、全局 subprocess helper、生产 CLI error
projection或 skip real test，停止并回 Controller。

## 5. Required negative cases

### 5.1 WIN4-F01

- fresh `action=create` 且 company name 缺失仍由 Fins owner fail closed；不得变成功。
- stale resolver-version company meta且缺 company name仍失败；不得用旧 meta fallback。
- explicit company name必须进入 generated command一次，不能只进入 regeneration comment。
- pre-execution oracle遇到“comment含 company name、唯一业务命令不含”或多条/零条 `upload_filing` 业务命令时
  必须在执行前 fail closed；不得用 whole-file count或 execution success替代逐 token证明。
- no `--infer`、no FMP call、no API key requirement。
- 不预创建 company meta，不从 ticker/fixture/path推导公司名。
- LF/CRLF source均不是 company-name缺失的修复输入；不得通过 newline normalization掩盖错误。

### 5.2 WIN4-F02

- success：所有 setx returncode 0后才整批注入当前 `os.environ`。
- first/middle nonzero：保持 failure/partial-failure names truth且零进程内注入。
- `OSError`：保持同一 names-only failure contract。
- `TimeoutExpired`：不 retry，不输出 exception/argv/value，保持已经确认和未确认 names。
- first/middle/last `KeyboardInterrupt`：保持既有 interrupted names truth。
- `stdin/stdout/stderr` 必须都是 DEVNULL；`capture_output` 必须不存在；`close_fds=True`、`shell=False`。
- fake stdout/stderr不得成为判断输入；任何 output内容变化不影响 result。
- timeout后不得声称 registry write 已回滚。

### 5.3 WIN4-F03

- sentinel作为 stdin写入值时，timeout exception `str/repr`、pytest failure text与 capture均不含 sentinel；三个
  `TemporaryFile(mode="w+b")` handles在 child execution和bounded cleanup期间保持有效，并在helper退出时关闭。
- deadline前已退出 1保持 `returncode_at_timeout=1`；尚未退出保持
  `returncode_at_timeout=not_exited`；cleanup产生的 returncode只能放在 `cleanup_returncode`，不能伪造成自然退出0。
- cleanup timeout必须保持 `cleanup=timeout` 并继续失败；其后恰好一次非阻塞 `poll()` 必须区分
  `process_state_after_cleanup_timeout=running|exited`，可用 integer 只进入 `cleanup_returncode`，不得再次 wait/kill。
- ordinary nonzero process仍返回 typed test result，由 `_assert_init_result` 按 returncode失败；不得转 timeout。
- strict UTF-8 decode error仍是独立失败；不得改 `errors="replace"`。
- success path继续允许 tests消费 stdout/stderr；不得改 DEVNULL。
- 不产生、记录或清理 named temp path；不得用 `mkstemp`、`NamedTemporaryFile`、pytest `tmp_path`、unlink failure
  或 retained-path warning建立第二套 cleanup 语义。

### 5.4 WIN4-PR-F04 closure canary

- `GITHUB_ACTIONS=true` 时，R12真实Windows setx test只能从合法`GITHUB_RUN_ID`按§2.3冻结纯函数派生canary；缺失、空值、
  非十进制或非正值必须在启动CLI前fail closed，不得回退随机值。
- Owner test必须断言 §2.3 唯一 Python bytes literal 的完整bytes、末字节single NUL `0x00`与该节冻结的
  已知run-id→canary向量；包含backslash + zero或字面backslash + `x00`的实现必须失败。相同
  canonical run id必须产生相同canary，不同run id必须产生不同canary；prefix、digest算法或canonicalization任一
  漂移也必须失败。
- workflow canary保持API-key-shaped但明确非秘密；不得写入stdout、stderr、safe failure、JUnit辅助字段或专门needle
  artifact。测试内部可以把它写入预期registry owner并做round-trip，但cleanup后不得把值作为evidence发布。
- 本地`GITHUB_ACTIONS`未启用时可继续随机；该随机值只由本地test assertion消费，不进入Controller真实closure scan。
- Controller必须按 §9.3 使用dispatch response返回的唯一R12 `run_id`，验证workflow identity/path、
  event、branch/ref与accepted implementation commit `head_sha`，再独立重算workflow canary并扫描同一run的
  完整log和全部downloaded artifacts，包含同一R12 artifact bundle中的embedded R11 evidence。不得读取、
  请求、导出或扫描GitHub Secrets、configured production values，也不得假设这些未作为test input的值可被
  验证。standalone R11没有消费该canary，不进入本scan，也不得声称由本scan证明其non-disclosure。

## 6. Validation matrix

所有命令都必须先执行：

```bash
source .venv/bin/activate
```

### 6.1 Focused owner tests

```bash
pytest \
  tests/cli/test_init_environment.py \
  tests/cli/test_init_smoke.py \
  tests/cli/test_upload_filings_from_command.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_fins_ingestion_runtime.py \
  -q
```

必选节点另行单跑，便于 evidence 定位：

```bash
pytest \
  tests/fins/test_sec_pipeline_upload_filing_stream.py::test_upload_filing_stream_stale_company_meta_requires_company_name \
  tests/cli/test_upload_filings_from_command.py::test_posix_generated_script_runs_real_cli_into_temp_storage \
  -q
```

在非 Windows 本地，两个 real Windows nodes 的 skip只能记录为平台事实，不得作为 closure。

### 6.2 Broader regression

```bash
pytest tests/cli -q
pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_sec_pipeline_upload_filing_stream.py -q
```

### 6.3 Coverage

```bash
pytest tests/cli/test_init_environment.py \
  --cov=dayu.cli.init_environment \
  --cov-branch \
  --cov-report=term-missing \
  --cov-report=json:workspace/tmp/win4-init-environment-coverage.json \
  -q
```

`dayu/cli/init_environment.py` 单文件 line coverage必须 `>=80%`；新增 timeout、DEVNULL与每个 failure branch
必须被 owner tests直接命中。不能用 pragma、omit或删测试降低分母。

### 6.4 Type and lint

```bash
python -m pyright dayu/ tests/ utils/
python -m ruff check \
  dayu/cli/init_environment.py \
  tests/cli/test_init_environment.py \
  tests/cli/test_init_smoke.py \
  tests/cli/test_upload_filings_from_command.py
```

full pyright必须零诊断。scoped Ruff必须零诊断。另在 implementation entry与最终 tree用同一 Ruff版本运行：

```bash
python -m ruff check dayu tests utils --output-format json
```

full Ruff既有 baseline按 `(filename, location, code, message, fix-applicability)` 精确比较；新增或扩散为零。
不得用总数相同替代逐项比较，也不得借 WIN4清理 unrelated baseline。

### 6.5 Diff, allowlist and formatting

```bash
git diff --check
git status --short
git diff --name-only 54e2dcbf653fb8c37b0206bd7aabbbf329ef040e
git diff --cached --name-only
```

implementation结束前 staged tree必须为空。product/test/docs diff只能属于 §3.1 allowlist；当前用户已有 control-doc与
fourth-evidence artifact不得被覆盖、格式化或纳入 implementation ownership。

### 6.6 Owner/security scans

```bash
rg -n 'capture_output\s*=\s*True' dayu/cli/init_environment.py
rg -n 'shell\s*=\s*True|errors\s*=\s*[^,)]*replace' \
  dayu/cli/init_environment.py tests/cli/test_init_smoke.py
rg -n 'winreg|reg\.exe|PowerShell|Start-Process|CREATE_NEW_PROCESS_GROUP|JobObject' \
  dayu/cli/init_environment.py tests/cli/test_init_environment.py tests/cli/test_init_smoke.py
rg -n 'Issue 142|Issue 151|Issue 175|Issue 177|Issue 178|web_tools_storage_states' \
  dayu/cli/init_environment.py tests/cli/test_init_environment.py tests/cli/test_init_smoke.py \
  tests/cli/test_upload_filings_from_command.py
```

第一、二、三条要求零输出；第四条只允许既有 README/测试说明，不得出现实现 diff。另由动态 negative test 使用
每次随机 sentinel验证 `str/repr/captured/JUnit-safe message` 零命中；不能用固定 blacklist代替。

Configured secret boundary保持：Config/Host internal SQLite/EventLog可含 effective API key/header；Tool Trace、audit、
public/LLM-facing/operator log不得含明文。本计划不读写这些 durable stores，也不新增它们的 projection。

真实R12 closure另有Controller-owned canary scan gate。Controller必须按 §9.3 锁定dispatch response返回的唯一
`run_id`，先验证workflow identity/path、event、branch/ref与accepted implementation commit `head_sha`，再按
§2.3冻结contract独立重算non-secret canary。JUnit、source-hash、workflow log、全部downloaded artifacts
（包含embedded R11 evidence及其它文件）与canary exact-value scan必须全部属于该同一`run_id`。任一
metadata mismatch、ambiguous、missing，artifact缺失或无法证明同run lineage，当前gate立即失败；不得猜测
“最近一次成功run”或混用其它run证据。只有同run递归exact-value扫描零命中才通过。Controller不得与
test/production共享派生helper，不得从test output/artifact取得needle，也不得读取或扫描GitHub Secrets/
configured production values。若命中，只记录R12 `run_id`、artifact-relative locator、
`match_category=test_canary` 与 gate status，不复制canary或matched content；扫描命令、review artifact和control doc
同样不得回显canary。standalone R11仍按其原artifact integrity与无secret-input contract验收；它没有消费该canary，
不进入canary scan，也不声称该scan提供non-disclosure证明。

## 7. README and design decision

- `tests/README.md`：需要更新。其职责包含真实 Windows gate、artifact组成与排障方式；必须准确说明 setx output
  不捕获、outer CLI timeout evidence是 name-safe。
- 根 `README.md`：预计不更新。public init grammar、交互步骤、输出通道与最终用户工作流不变；若实现产生新用户
  可见文案或排障步骤，立即停止回 plan review，不得机械同步。
- `dayu/fins/README.md`：不更新。WIN4-S1不改变 Fins production contract；缺 company name仍按当前 owner fail closed。
- `dayu/config/README.md`、`dayu/README.md`、`docs/fins/design.md`、`docs/ui/design.md`、
  `docs/host/design.md`：不更新。无 schema、分层、装配、Host/Engine或稳定设计变化。

修改任何 README 前必须重新读取其 `Agent更新约束`；若实际 diff超出上述决定，停止并回 Controller。

## 8. Next real R11/R12 closure matrix

真实 Windows rerun必须 checkout accepted implementation commit，使用 Python 3.11与现有 locked constraints；本地
skip、mock、renderer unit或历史 run不能替代。

| Gate | Required result | Required positive evidence | Failure evidence contract |
| --- | --- | --- | --- |
| R11 capability | pass | `cmd.exe /d /c ver` exact 0；`cmd.exe /?` exact 1 | 只记录 command category和exit；不扩展 PowerShell skip |
| R11 four nodes | `4/4 passed`, workflow exit 0 | non-POSIX run keys、adversarial argv、real CLI storage、parser action全部通过 | JUnit/stdout/stderr always-upload；standalone R11不接收本canary或configured production secret，按无secret-input contract验收，不声称canary证明 |
| R11 argv | pass | fixed/appended argv逐元素相同，no injection marker | 记录 script/oracle hash；不打印 source content |
| R11 real upload | pass | generated command含一次 company-name；exit 0；terminal success；portfolio source artifact >0 | 若仍失败，记录 generation/execution returncode、script hash、source basename/hash、typed status；不猜新 root cause |
| R12 init | `9/9 passed`, workflow exit 0 | real setx round-trip成功、精确 registry value cleanup、其余8 nodes继续通过 | timeout必须只显示 category/180/returncode-at-timeout/cleanup/cleanup-returncode；stdin/stdout/stderr值不得进入 JUnit |
| R12 embedded R11 | `2/2 passed` | adversarial argv与real upload都通过 | 同R11 safe evidence；其log/artifacts随R12 bundle进入R12 canary scan |
| Artifact integrity | pass | §9.3 dispatch返回的同一R12 `run_id` 下，新JUnit/source-hash/全部artifact SHA-256由Controller重新计算 | workflow metadata、run lineage、hash/path/artifact任一mismatch/ambiguous/missing即gate fail，不从workflow summary或最近成功run猜结果 |
| R12 Controller canary scan | pass | Controller按§9.3验证dispatch返回的`run_id`与accepted implementation commit，使用§2.3冻结contract独立重算non-secret canary，递归扫描与JUnit/source-hash/artifacts同run的完整workflow log与全部downloaded artifacts（含embedded R11），零命中 | standalone R11不在scan范围；不共享helper，不读/扫GitHub Secrets或configured production值；command/review/control只记录R12 run、artifact-relative locator、`test_canary` category与status，不回显canary/matched content |

只有 R11 overall success、R12 overall success、R12 embedded R11 success、所有 required artifacts存在且 R12 canary scan通过，
才能关闭 WIN4-F01/F02/F03 和 AR-F07。Gemini low-budget保持
`EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`，不进入上述矩阵。

standalone R11的closure evidence只来自其capability/four-node/argv/real-upload结果、artifact integrity与无secret-input
contract；R12 canary scan不为standalone R11提供或声称额外non-disclosure证明。

## 9. Safe evidence on any failure

### 9.1 R11 failure

保留：test node、operation name、action、company-name-present布尔值、source basename和 SHA-256、generated script
SHA-256、generation/execution returncode、typed Fins status/error kind（若 owner已经提供）、artifact相对 locator。

禁止：raw source content、绝对 path、raw exception、configured secret、FMP key、环境 snapshot、generic message→root
cause推断。合法 company-name补齐后仍失败时，状态为
`NEEDS_MORE_EVIDENCE / DIAGNOSTIC_FIRST PLAN AMENDMENT REQUIRED`。

### 9.2 R12 setx failure

保留：env name、setx command category、调用序号、written/unwritten name集合、native timeout、outer timeout、outer
returncode、cleanup status、registry cleanup结果。

禁止：entry.value、stdin、setx argv repr、setx stdout/stderr、registry value、raw `TimeoutExpired` repr、Popen args/cwd。

### 9.3 Security gate

按公开R12 `run_id`确定性派生的test canary出现在同一R12 run的JUnit、workflow log、downloaded
artifact（包括embedded R11 artifact）、review artifact或control doc，即本轮真实evidence security gate fail；即使
R12测试计数为绿也不得关闭AR-F07。

本 gate 的执行 owner 是Controller，程序顺序和失败语义冻结如下：

1. 必须使用能在本次dispatch response中返回确切R12 `run_id`的调用方式，并立即锁定该`run_id`。
   response未返回、返回多个candidate或无法唯一对应本次dispatch时，当前gate fail；禁止从“最近
   一次run”、“最近一次成功run”、workflow summary、时间戳或artifact名反推`run_id`。
2. 在下载、读取或扫描任何evidence前，必须用该`run_id`查询GitHub workflow-run metadata，并同时断言：
   workflow identity/name精确为`R12 init Windows gate`；workflow path精确为
   `.github/workflows/r12-init-windows.yml`；event精确为`workflow_dispatch`；branch/ref精确等于dispatch
   target branch/ref，且该ref承载accepted implementation commit；`head_sha`精确等于accepted implementation
   commit SHA。任一field missing、mismatch或ambiguous都使当前gate fail；只能重新dispatch并取得其response
   返回的正确`run_id`，不得用历史run或其它branch/commit替代。
3. Workflow status/conclusion、完整log、JUnit、source-hash、artifact列表、全部artifact下载与哈希、
   embedded R11 evidence以及canary scan必须全部使用第1项同一`run_id`和第2项同一metadata tuple。
   任一required JUnit/source-hash/artifact missing、下载不完整、无法证明run lineage或与其它run混用都是
   gate fail，不得用workflow summary或其它run的green status补齐。
4. Metadata与run lineage通过后，Controller才能仅根据公开`run_id`与§2.3文字冻结的bytes/formula/vector
   独立重算canary。禁止与production/test共享helper、constant module或生成实现；禁止从test output/
   artifact取得needle。只有对第3项同run完整log与全部downloaded artifacts的递归exact-value scan零命中
   才可通过。
5. 命中evidence只允许包含R12 `run_id`、accepted `head_sha`、artifact-relative locator、
   `match_category=test_canary`和failed status；不得包含canary/matched content。扫描命令、review artifact与
   control doc同样零回显。

Controller不得读取、请求、导出或扫描GitHub Secrets/configured production values；当前R12 workflow没有把这些值作为
本test input，因此它们不是本canary gate可验证的needle。standalone R11没有消费R12 canary，继续按artifact integrity与
无secret-input contract验收，不进入scan。本限制不放宽既有设计：Config/Host internal SQLite/EventLog仍属trusted-local
domain，Tool Trace/audit/public/LLM-facing/operator log仍禁止API key/header明文。

## 10. Diagnostic-first stop gate for unexpected WIN4-F01 recurrence

当前 root cause已知，因此 implementation不应预先增加通用 diagnostic infrastructure。若 S1 后真实 R11/R12 upload仍失败：

1. 立即停止后续 root-cause修复；不得把 generic message当原因。
2. 先用 §9.1 safe facts判断 failure发生在 invocation precondition、conversion、storage transaction还是publication的
   哪个 existing owner boundary；无 owner fact就返回 plan correction，不就地编码。
3. 允许的 diagnostic-first correction必须是 Fins owner-local typed category/code，并证明不进入 Tool Trace/audit/public/
   LLM-facing raw detail；禁止 raw exception/path/content/value。
4. 只有新的真实 Windows evidence锁定唯一逻辑/数据同源 root cause后，才能补写最小 remediation slice并重新完整
   plan review/fix/re-review。
5. 不得借 diagnostic-first进入 Issue 175 Docling process isolation、通用 error framework、artifact store、authorization或
   secret infrastructure。

## 11. No fallback, compatibility or deferred-scope invariant

- 零 compatibility re-export/wrapper/alias/old field/read path。
- 零 platform fallback、loose parsing、`hasattr/getattr`、默认 company name、registry fallback或 timeout retry。
- 零 test-only production seam、mock替代真实 runner、skip/xfail、timeout增加或 errors=replace。
- 零 duplicate owner：company-meta requirement仍在 Fins；setx stdio仍在 init_environment；failure projection仍在 test helper。
- 零 Issue 142/151/175/177/178、Web/WeChat/render、unified authorization或 secret infra实现。
- Tool Trace/audit继续禁止 API key/header明文；trusted-local Config/Host durable裁决不变。
- 任何 deviation都触发 stop，不得在 implementation中“顺手修复”。

## 12. Completion report contract for the later implementation gate

后续 AgentCodex implementation artifact必须报告：

1. umbrella/WU/gate/baseline identity；
2. 每个 slice实际 changed paths与 owner；
3. WIN4-F01 direct root-cause proof及为什么不是 test fallback；
4. WIN4-F02 stdio/handle/timeout contract及没有 output consumer的证明；
5. WIN4-F03 timeout/category/returncode与 canary/sentinel non-disclosure证明；
6. focused/broader/coverage/pyright/Ruff/diff/README/security结果，以及真实closure时 §9.3 Controller procedure
   锁定的dispatch-returned public R12 `run_id`、workflow identity/path、event、branch/ref、accepted implementation
   `head_sha`、冻结派生contract、同run JUnit/source-hash/全部artifact范围、零命中结论与value-free evidence
   locator；明确无metadata mismatch/ambiguous/missing、无跨run混用、未使用共享helper，standalone R11不在scan
   范围，且未读取/扫描GitHub Secrets或configured production values；
7. staged tree empty与用户既有 dirty paths未触碰；
8. local Windows skip与真实 Windows pending状态，不得误报 closure；
9. residual risks、owner/destination；
10. 明确 stop在当前 implementation gate，不 commit/push/workflow dispatch/进入review，除非当轮另有授权。
