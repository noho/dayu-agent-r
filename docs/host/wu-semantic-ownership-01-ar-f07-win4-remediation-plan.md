# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4 Remediation Plan

## 0. Gate identity and decision

- Umbrella work unit：`WU-SEMANTIC-OWNERSHIP-01`。
- Continuation：`AR-F07` 第四轮真实 Windows evidence remediation。
- 当前 gate：同一remediation plan gate内的fresh real-Windows success-oracle plan correction；不是新WU。
- 原始 WIN4 baseline HEAD：`54e2dcbf653fb8c37b0206bd7aabbbf329ef040e`；本 amendment 的冻结 remote
  code/evidence target：`b85def887e72dc69e972f42a82a18989523f8634`。
- 风险级别：High Risk。既有 WIN4-F01..03 已实施并进入真实 Windows closure；新增
  WIN4-RW-F01 修改 release-gate success oracle，WIN4-RW-F02 修改生产 CLI secret-input contract。
- 当前结论：`WIN4-RW-RF01_ACCEPTED / PRIMARY_OWNER_OVERREACH_REMOVED /
  CODE_GENERATION_READY_MINIMAL_PLAN_CORRECTION /
  READY_FOR_CONTROLLER_VALIDATION_AND_DUAL_COMPLETE_PLAN_REVIEW / IMPLEMENTATION_NOT_AUTHORIZED`。
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
- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-real-windows-fresh-windows-evidence-controller-adjudication.md`
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

最新 fresh evidence 锁定 dispatch-returned R11 `29709987970` 与 R12 `29709993229`；两者均匹配
accepted implementation head `b11eb95c8312e085755b81c630e9c359220d3ff1`。R12 init `9/9 passed`，
same-run canary gate对完整 logs/artifacts `19` files扫描零命中；R11为 `3/4 passed`，R12 embedded R11为
`1/2 passed`。两处唯一共同失败均是同一 test line把 Fins owner选择的 primary强制等同于原始 source basename，
而真实 public snapshot合法发布原始 HTML 与 Docling JSON两个 descriptors，并选择 Docling JSON为 primary。

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

## 13. Real-Windows diagnostic bounded amendment

### 13.0 Precedence, identity and authorization

本节是 R11 workflow_dispatch run `29703932798`、R12 workflow_dispatch run `29703933666` 在冻结 remote target
`b85def887e72dc69e972f42a82a18989523f8634` 上产生新 evidence 后的有界修订。两次 run 的 workflow identity、path、
event、branch/ref 与 head SHA 已由 Controller 在读取 evidence 前唯一验证；push 自动触发的 pull-request run 不属于本次
证据链。

本节只覆盖既有计划中已经被新 evidence 证伪或需要延伸的内容：§0 当前 gate/target、§3 allowlist、§4 slice 顺序、
§5 negative cases、§6 fresh validation、§7 README decision、§8 real-Windows closure、§9 failure/security gate、§11
deferred invariant 与 §12 completion report。发生文字冲突时以本节为准；既有 WIN4-S1/S2/S3 的 accepted contracts、
已关闭 findings 与非冲突约束继续有效，不重新实施、不回滚，也不建立新 WU/sub-WU。

原 amendment 的 `WIN4-RW-S1` 与 `WIN4-RW-S2` 已完成 implementation/review/accepted aggregate gates；它们是本次
correction 的 immutable implementation base，不是未来 diff allowlist。fresh R11 `29709987970` 与 R12 `29709993229`
进一步接受 `WIN4-RW-RF01`：amended plan §13.2.1 把“原始 source 已发布”与“Fins 选择哪个 descriptor 为 primary”
错误合并。当前 correction 不增加 product slice、schema 或公共契约，只把未来 implementation 收敛为一个 exact test node
内的 owner-oracle 更正。在 corrected plan 经 Controller validation、AgentMiMo/AgentDS 双路完整 plan review、finding fix、
双路完整 re-review并形成 accepted corrected-plan commit前，不得 implementation、stage、commit、push、dispatch 或进入
PR review。

### 13.1 First-principles motivation and root-cause lock

#### 13.1.1 WIN4-RW-F01 / WIN4-RW-RF01 — display与primary选择都不是test-owned success语义

动机成立，严重性限定为 release-gate/test contract blocker，不是 production upload defect：

1. R11 four-node gate为 `3 passed, 1 failed`，R12 embedded R11为 `1 passed, 1 failed`；唯一失败节点都是
   `test_windows_generated_script_runs_real_cli_into_temp_storage`。
2. 该 test 先得到真实 `cmd.exe` execution exit `0`，随后才断言旧字面量 `Fins result`。锁定 target 的
   `dayu/cli/output.py` 已由 output owner 把 terminal summary prefix 定义为 `Fins summary`；真实 stdout 同时包含
   typed `status="ok"` summary。展示词漂移不会推翻已经完成的业务运行。
3. 同一 standalone R11 artifact 的 Fins published tree 已包含 company meta、filing manifest、source meta、primary
   source 与 Docling result；失败只阻止随后写出 `cli-grammar-oracle.json`。因此 company-name、Windows argv quoting、
   CLI→Service→Fins、Docling、storage transaction/publication 都不是本轮根因。
4. `execution.stdout` 的 display grammar 属于 CLI output owner；真实上传 test 消费者无权选择某个 prefix 作为业务成功
   真源，也无权把旧词替换成当前或另一个硬编码词来继续耦合 display。

唯一 remediation owner 是 `tests/cli/test_upload_filings_from_command.py` 的真实 Windows smoke success oracle。
业务成功必须由两个同源事实共同证明：OS process exit `0` 与 `dayu.fins.storage` public repository 读取到的 published
company/source facts。生成脚本中的 company-name pre-execution oracle，以及 workflow 对 generated-script hash、
source artifact count 和 required artifact existence 的 integrity 校验继续保留。

fresh evidence 对同一 owner 增加第二个直接结论：

1. R11 `29709987970` 的四个 nodes为 `3 passed, 1 failed`；R12 `29709993229` init为 `9/9 passed`，embedded R11为
   `1 passed, 1 failed`。两处唯一共同失败都是 target test在真实 upload exit `0`、company/source public facts成立后，
   执行了把 Fins primary 与 `source_path` basename强制同一的越权 assertion。
2. `DoclingUploadService` 把原始 HTML 与转换后的 Docling JSON都作为 file entries发布，再由
   `_pick_primary_docling_file()` 选择 Docling JSON并把该值写入 `primary_document`。这是 Fins production owner truth，
   不是 CLI test可覆盖的选择。
3. `SourceSnapshotProtocol.primary_filename` 的 public contract只承诺返回值精确命中 `files` descriptor集合；
   `SourceSnapshotFileDescriptor` 已公开 exact `name` 与可选 `sha256`。因此 test应分别证明 primary contract与原始 source
   publication，不得从二者推导同一性。
4. 原始 source publication的充分 public evidence是：descriptor集合中 exact source basename恰好出现一次，且该
   descriptor的 public `sha256` 精确等于本次 fixture bytes的 SHA-256。不能以 raw meta、private path、物理 tree或
   “primary 恰好是谁”替代该证据。

`WIN4-RW-RF01` 的唯一 correction owner仍是
`tests/cli/test_upload_filings_from_command.py::test_windows_generated_script_runs_real_cli_into_temp_storage`；没有 Fins
production/storage contract defect，也没有把 Docling filename固化为新 expected primary的需求。

#### 13.1.2 WIN4-RW-F02 — redirected secret input is missing at the CLI owner boundary

动机成立，严重性是生产 CLI input-boundary 缺陷，不是 setx/native process defect：

1. R12 init gate为 `8 passed, 1 failed`；唯一失败 node 的 outer `180s` 到期时仍未退出，safe failure truth是
   `returncode_at_timeout=not_exited / cleanup=completed / cleanup_returncode=1`。
2. `_run_init()` 已在启动 child 前把完整交互逐行写入 anonymous redirected stdin handle；它没有使用 test-side
   input shim，且 canary 未进入失败文本。
3. 锁定 target 的 `dayu.cli.commands.init::_collect_environment_persistence_plan()` 对 required secret 和每个 optional
   secret 直接调用 `getpass.getpass()`。
4. CPython 3.11 Windows `win_getpass()` 只在 `sys.stdin is not sys.__stdin__` 时 fallback；OS-level redirected handle
   并不替换 Python 的 `sys.__stdin__` 对象。因此该分支仍调用 console `msvcrt.getwch()`，忽略传入 stream，预置的
   redirected stdin bytes 无消费者。
5. timeout 位于第一个 required secret input，发生在确认、workspace staging、`setx` 与 registry round-trip 之前；
   不能把它重新归因到 WIN4-S2 native timeout，也不能用 test harness 或 outer timeout掩盖。

唯一 remediation owner 是 `dayu/cli/commands/init.py` 的 secret-input boundary。输入能力，而不是 OS 名称或 test
身份，决定读取路径：interactive TTY 继续 hidden getpass；redirected stdin 明确一次读取一个 logical line。该边界只拥有
secret value 的读取和 EOF/interrupt 语义，不拥有 environment persistence、registry、Config、Host durable state、
authorization 或通用 secret lifecycle。

### 13.2 Exact owner contracts

#### 13.2.1 WIN4-RW-F01 / WIN4-RW-RF01 success oracle

1. 删除真实 Windows smoke 对 `"Fins result"` 的断言，不增加 `Fins summary`、`Fins succeeded` 或任何其它
   stdout/stderr display 文本、generic message、prefix、substring、regex 或 parser 断言。
2. 保留 `execution.returncode == 0`，且失败时只用既有 `execution.stderr` 帮助 test failure；不得从 stdout 文案推导
   success、document id、stage 或 root cause。
3. 通过 `dayu.fins.storage` public repository 实现读取 published tree，而不是 raw JSON、内部 core/private path 或
   `rglob` 反推业务事实：
   - `FsCompanyMetaRepository(storage).get_company_meta("AAPL")` 必须返回 exact ticker `AAPL` 与 company name
     `Apple Inc.`；
   - `FsSourceDocumentRepository(storage).list_source_document_ids("AAPL", SourceKind.FILING)` 必须返回唯一一个
     published filing document id；
   - 对该 id 必须使用 public context-manager lifecycle
     `with source_repository.read_source_snapshot(..., materialize_files=False) as snapshot:`，并且只在 `with` 块内读取和确认
     exact ticker、document id、`SourceKind.FILING`与非空的完整 public descriptor集合；
   - Fins-owned `snapshot.primary_filename` 必须在 descriptor集合中按 exact `name` 恰好命中一个 descriptor。test不得
     规定该 descriptor必须是原始 source，也不得把当前 Docling产物文件名、suffix或任何其它 filename硬编码成 expected
     primary；
   - 原始 source publication必须独立由同一 public descriptor集合证明：exact `source_path.name`恰好命中一个 descriptor，
     且该 descriptor的 public `sha256` 精确等于 `hashlib.sha256(fixture).hexdigest()`，其中 `fixture` 是本次写入
     `source_path` 的原始 bytes。primary命中与 raw-source命中是两个独立断言，允许它们指向不同 descriptors；
   - 只消费 `snapshot.files`、`snapshot.primary_filename` 与既有 public identity字段；不读取 raw source meta、meta JSON、
     private/core path，不 materialize或打开 source file，也不从物理 storage tree反推 publication业务事实。CLI test不重复
     测试 Fins owner自身的 close-after-use语义。
4. 既有 filesystem `source_artifact_count` 只保留为 uploaded evidence package 的物理 integrity count，不再承担业务
   success 语义；其值、generated-script SHA-256、`cmd_invocation`、`company_name_supplied=true` 与 test node/result
   继续写入现有 `cli-grammar-oracle.json`；本 correction不得增加、删除或改名任何 oracle字段。
5. 保留 `_assert_single_windows_upload_company_name()` 在执行前逐 token 证明唯一 company-name；不得改成 comment、
   whole-file substring、execution result或 storage反推输入。
6. 实现必须直接留在上述 exact test node现有 snapshot assertion block内；不得新增 helper、constant、schema、fixture字段、
   compatibility seam或 README说明。

#### 13.2.2 WIN4-RW-F02 secret-input boundary

在 `dayu/cli/commands/init.py` 增加一个模块级私有 helper `_read_secret_input(prompt: str) -> str`，由 required 与
optional secret 两处唯一复用；不新增 callback、factory、Protocol、class、runtime helper或跨模块 facade：

1. 先检查当前 `sys.stdin.isatty()`。为 `True` 时只调用 `getpass.getpass(prompt)`；不得把 TTY secret 改成
   `input()`/`readline()`，不得在 stdout/stderr 回显 value。
2. 为 `False` 时，不调用 `getpass`，只把 prompt 写到 `sys.stderr` 并 flush，然后对当前 `sys.stdin` 调用恰好一次
   `readline()`。非 EOF 返回值只移除一个 logical line ending：先判断并实际移除末尾单个 `\n`；只有该次确实移除了
   `\n`，且移除后新末尾是 `\r` 时，才继续移除该单个 `\r`。没有伴随已移除 `\n` 的孤立 trailing `\r` 必须原样
   保留；其它前导、尾随空白与字符也原样保留，由现有 required-empty/optional-empty contract决定。禁止使用会移除任意
   数量尾随字符的 `rstrip` 或其它 strip操作实现该 contract。
3. TTY path只捕获 `getpass.getpass()` 抛出的 `EOFError`；redirected path只把 `readline() == ""` 识别为 EOF。两者都在
   helper 内收敛为同一个 value-free `CliInitOperationError("secret input ended before completion")`，不得把 prompt、secret、
   raw buffer或 raw exception text投影到用户输出。`KeyboardInterrupt` 不捕获、不改写，继续由现有 CLI owner映射为 exit `130`。
4. `_collect_environment_persistence_plan()` 只把两处 direct `getpass.getpass()` 换成该 helper。required 空行继续
   value-free fail closed；optional 空行继续 skip；`OPTIONAL_ENVIRONMENT_NAMES` 顺序、已有环境跳过规则、names-only
   preview、最终 `_confirm()` 与 confirmed typed plan顺序不变。
5. 分流必须 capability-based 且平台中立；不得使用 `os.name`/`platform.system()` 特判 Windows，不得读取
   `sys.__stdin__` identity模拟 CPython私有分支，不得在 test/runtime判断 GitHub Actions。

### 13.3 Allowed and forbidden paths

后续 correction implementation 必须由 Controller 先冻结 `CORRECTED_PLAN_BASE`（accepted corrected-plan commit）。
原 `WIN4-RW-S1/S2` aggregate implementation、product、tests、README、design与 workflow全部是 immutable base；相对该
base的未来 diff只允许：

| Slice | Allowed paths | Ownership purpose |
| --- | --- | --- |
| WIN4-RW-RF01 | `tests/cli/test_upload_filings_from_command.py::test_windows_generated_script_runs_real_cli_into_temp_storage` 的现有 snapshot assertion block | 分离 Fins-owned primary membership与 raw-source public descriptor name/hash publication oracle |

该 exact node之外，同文件 imports、module constants、helpers、fixtures、其它 tests与 oracle JSON block都必须相对
`CORRECTED_PLAN_BASE` 零 diff。实现使用现有 `hashlib`、`fixture`、`source_path`、`descriptors`与 public descriptor字段，
不需要也不得新增 helper/import/schema/oracle字段。

明确禁止修改或新增：

- `dayu/` 下全部 product code，以及 target test之外的全部 tests；
- `dayu/fins/` 下任何 production code、schema、storage protocol/implementation、pipeline、Docling或 renderer；
- `.github/workflows/r11-upload-script-windows.yml`、`.github/workflows/r12-init-windows.yml`；
- `README.md`、`tests/README.md`、全部其它 README与 design doc；
- `docs/host/issues-implementation-control.md`、其它 control/review artifact；
- `dayu.runtime` secret helper、统一 secret/credential/authorization infrastructure、compatibility wrapper/alias/fallback；
- PowerShell、PTY、console wrapper、Win32 handle API、job object、process group、process-tree治理、test harness shim、
  timeout增加、skip/xfail、mock替代 real node。
- 新 test helper、snapshot wrapper、schema/public contract字段、oracle字段、raw meta/private-path读取、硬编码 Docling expected
  primary或任何 primary fallback。

若 implementation 发现必须越过上述 allowlist，立即停止并回 Controller 做新的 diagnostic-first plan amendment；不得自行
扩大本节。

### 13.4 Ordered implementation slices

#### WIN4-RW-RF01 — Public descriptor ownership correction

Objective：保留 process + public storage-owned upload success，同时删除 test对 Fins primary选择的越权约束，并用同一
public descriptor contract独立证明原始 source已发布。

Exact changes：只在 exact test node现有 snapshot assertion block内严格执行 §13.2.1：primary filename按 exact name
恰好命中 descriptor集合；exact source basename按 name恰好命中一个 descriptor且其 public SHA-256等于本次 fixture bytes
SHA-256。删除二者相等的断言，不以 Docling filename替代；不改 imports、docstring、生成、执行、company-name preflight、
artifact目录、helper或 oracle schema/字段。

Dependencies：既有 `WIN4-RW-S1/S2` accepted aggregate implementation是 immutable前置。当前 correction只有一个 test-owner
slice；经独立 review/fix/re-review与 accepted implementation commit后才允许 remote rerun。

Independent acceptance：target diff只修改该 snapshot assertion block；静态 inspection直接证明 primary/raw-source两个断言
彼此独立，且没有 display、Docling filename、raw meta/private path、helper/schema/oracle/README diff。非 Windows focused suite
中的 real Windows node skip只能记录为平台事实；真实 closure必须等待 §13.8 的 fresh R11 与 R12 embedded R11。

Stop condition：若 public `files` descriptors不能同时表达 Fins-owned primary membership与原始 source exact name/hash，或实现
需要硬编码 Docling expected primary、读取 raw meta/private path、修改 Fins production/storage contract、增加 helper/schema/
oracle字段、修改 README/workflow/其它 test node，立即停止并回 Controller；不得用 fallback或下游补偿继续。

#### WIN4-RW-S2 — TTY-hidden and redirected line-oriented secret input（已接受、当前零diff）

Objective：让 CLI input owner根据 stdin capability选择 hidden TTY或 redirected logical-line读取，并锁定安全 failure语义。

Exact changes：严格执行 §13.2.2；在 `tests/cli/test_init_command.py` 直接测试 owner。该文件所有受影响既有 getpass tests必须把
production实际读取的 `sys.stdin` 替换为 test-owned、严格 typed TTY fake：其 `isatty()` 恒为 `True`，`readline()` 一旦被调用
立即 assertion失败。direct integration consumer
`tests/cli/test_prompt_command.py::test_prompt_command_uses_init_generated_workspace_config` 只补同样严格的 test-owned
`sys.stdin` TTY fake并锁定误入 `readline()` 立即失败；保留既有 getpass value序列、prompt/runtime assembly业务断言与执行顺序，
不修改同文件其它 prompt tests。不得抽 compatibility/shared production seam或跨模块 facade，不得 mock production
`_read_secret_input`，不得修改或依赖 `sys.__stdin__`，也不得依赖本机/CI ambient TTY。redirected owner tests必须使用真实
`io.StringIO` 或等价的严格 typed stream，并显式保证 `isatty() == False`。不得在 `_run_init()`、workflow或 Windows-only
test注入 shim。

Dependencies：本 slice及其aggregate gates已接受。当前 correction不得重新实施或修改；只有 WIN4-RW-RF01 accepted后才允许
新的 aggregate validation和 remote rerun。

Independent acceptance：owner tests在非 Windows也能确定性证明 capability分流、消费顺序、EOF/interrupt与零回显；真实 Windows
closure仍必须由 §13.8 的 fresh R12 run证明。

Stop condition：若需要修改 setx、outer harness、console/PTY/process tree、增加 timeout、共享 secret infrastructure或 test-only
production seam，停止并回 Controller。

### 13.5 Owner-test and negative-case matrix

#### 13.5.1 WIN4-RW-RF01

- execution nonzero 必须在任何 storage success assertion和 oracle写入前失败；不得把已存在 artifact误报为本次成功。
- exit `0` 但 company meta缺失/非法、filing document id为零或多个、snapshot identity/source kind不一致时必须失败。
- Fins-owned primary filename在 public descriptor集合中 exact name零命中或多命中时必须失败；恰好命中时不得再约束它
  同时是原始 source，也不得约束它是某个 Docling filename/suffix。
- exact source basename在 public descriptor集合中零命中或多命中，或唯一命中的 descriptor public `sha256`为空/不同于
  本次 fixture bytes SHA-256时必须失败；即使 primary membership有效也不得通过。
- 当前真实反例必须通过：primary合法指向非原始 source descriptor，同时原始 source descriptor以 exact basename与 exact
  fixture SHA-256独立存在。该场景不得被 test误报失败。
- source snapshot的 identity/source kind/primary filename/descriptors只在 public `with` lifecycle内读取；CLI test不得重复增加
  Fins close-after-use owner test。
- test不得读取 raw source meta/meta JSON、private/core path或 materialized file来补证 descriptor，不得以物理 `rglob` count
  替代 raw-source public descriptor name/hash；既有 physical count只保留 artifact integrity语义。
- stdout 为空、prefix变化、summary字段顺序变化或新增 progress文案时，只要 exit与 storage owner facts成立，不得失败。
- stdout含任意看似成功词但 exit非零或 storage owner facts缺失时，不得通过。
- company-name pre-execution oracle仍必须证明 exact one `Apple Inc.`；comment-only、零条或多条业务命令继续 fail closed。
- generated-script hash、artifact count与必需 oracle文件必须继续由现有 workflow integrity gate复核；oracle JSON字段集合
  必须保持不变，不为 primary/raw-source新增字段。

#### 13.5.2 WIN4-RW-S2

- redirected stdin：使用真实 `io.StringIO` 或等价严格 typed stream显式证明 `isatty() == False` 时，
  `getpass.getpass()` 必须零调用；prompt可见，恰好一个 `readline()` 消费一行，secret value在 stdout/stderr/captured
  exception/diagnostic中零命中。
- TTY：受影响既有 getpass tests使用 test-owned严格 typed `sys.stdin` fake，`isatty()` 恒为 `True`，`readline()` 被调用即
  assertion失败；只调用 hidden getpass，prompt与返回值传递不漂移，不 mock `_read_secret_input`，不依赖 `sys.__stdin__`
  或 ambient TTY。
- direct integration consumer：
  `tests/cli/test_prompt_command.py::test_prompt_command_uses_init_generated_workspace_config` 必须使用同一 capability contract的
  test-owned strict typed TTY stdin fake，证明 init→prompt integration只走 hidden getpass且 `readline()` 误入立即失败；保留
  既有 getpass value序列、generated workspace config、prompt/runtime assembly与路径断言，同文件其它 tests零 diff。
- line endings：LF与CRLF各只移除一个 logical ending；空行得到空值；孤立 trailing `\r` 原样保留并有 bare-CR owner test；
  其它空白不 strip，禁止 `rstrip` 或等价的过度删除。
- EOF：TTY `getpass.getpass()` 抛出的 `EOFError`与 redirected `readline() == ""`都转成同一 value-free
  `CliInitOperationError`，不进入 optional、confirmation、persistence或 workspace publication。
- interrupt：TTY getpass与 redirected read的 `KeyboardInterrupt`都保持原类型；full CLI映射 exit `130`，后续输入与持久化零调用。
- required：缺少现有环境且输入非空时形成首个 entry；空行保持 required missing failure。
- optional：只按 `OPTIONAL_ENVIRONMENT_NAMES` 顺序询问缺失项；空行 skip，非空行按原顺序进入 entries，已有 env不消费输入。
- confirmation：所有 secret收集完成后才显示 names-only preview并消费一次现有 yes/no确认；拒绝/EOF保持现有不发布语义；
  confirmation不得提前、重复或读取 secret helper。
- non-disclosure：required/optional values不得进入 stdout、stderr、exception text/repr、pytest capture、README示例或 artifact。

### 13.6 Fresh local validation, coverage and source scans

所有 correction implementation验证必须在 accepted `CORRECTED_PLAN_BASE` 上 fresh执行；旧 WIN4-RW-S1/S2通过记录只作为
immutable baseline，不能替代本次 exact-node验证。命令先执行：

```bash
source .venv/bin/activate
```

#### 13.6.1 Per-slice focused tests

WIN4-RW-RF01：

```bash
pytest tests/cli/test_upload_filings_from_command.py -q
pytest \
  tests/cli/test_upload_filings_from_command.py::test_posix_generated_script_runs_real_cli_into_temp_storage \
  -q
pytest \
  tests/fins/test_fins_storage_atomicity.py::test_company_owner_reads_only_published_meta_inventory_and_aliases \
  tests/fins/test_fins_storage_provider.py::test_storage_repositories_list_and_read_fixture_documents \
  tests/fins/test_fins_storage_provider.py::test_snapshot_descriptor_meta_provenance_primary_and_files_share_one_revision \
  -q
```

非 Windows 对 real Windows node 的 skip只能记录为平台事实。实现 artifact必须分别报告 target file、POSIX real smoke、
三个 public repository owner nodes与 Windows exact node的结果；不得用已有 remote failure或 repository unit test代替新的
真实 Windows closure。

#### 13.6.2 Aggregate and broader regression

```bash
pytest \
  tests/cli/test_upload_filings_from_command.py \
  tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_fins_storage_provider.py \
  -q
pytest tests/cli -q
```

#### 13.6.3 Coverage

本 correction不修改 production Python，不产生新的 production line/branch coverage分母；因此不新增 coverage target或
coverage helper。既有 changed-production coverage evidence保持 immutable。若实现产生任何 product diff，立即按 §13.4 stop，
不得用 coverage运行把越界实现合理化。

#### 13.6.4 Pyright and Ruff

```bash
python -m pyright dayu/ tests/ utils/
python -m ruff check tests/cli/test_upload_filings_from_command.py
```

full pyright与 scoped Ruff必须零诊断。implementation entry与最终 tree使用同一 Ruff版本执行：

```bash
python -m ruff check dayu tests utils --output-format json
```

若 full Ruff存在 `CORRECTED_PLAN_BASE` 既有项，必须按
`(filename, location, code, message, fix-applicability)` 精确比较，新增/扩散为零；不得用总数相同或顺手清理 unrelated
baseline代替。

#### 13.6.5 Diff, allowlist and README checks

```bash
git diff --check
git status --short
git diff --name-only CORRECTED_PLAN_BASE
git diff --cached --name-only
```

implementation完成前 staged tree必须为空；相对 `CORRECTED_PLAN_BASE` 的 tracked diff只能包含
`tests/cli/test_upload_filings_from_command.py`，且只允许 exact target node现有 snapshot assertion block变化。必须显式证明
全部 product、其它 tests、README、design、workflow与 control paths零 diff，并做 function-level diff review：

```bash
git diff --unified=0 CORRECTED_PLAN_BASE -- tests/cli/test_upload_filings_from_command.py
git diff --name-only CORRECTED_PLAN_BASE -- dayu tests README.md ':(glob)**/README.md' \
  docs/fins/design.md docs/ui/design.md docs/host/design.md .github/workflows
```

第二条输出必须只有 target test file；所有 README diff必须为空。本 correction没有 README触发项，不得机械更新。

#### 13.6.6 Ownership and forbidden-source scans

```bash
git diff --unified=0 CORRECTED_PLAN_BASE -- tests/cli/test_upload_filings_from_command.py | \
  rg '^\+.*(Fins (result|summary|progress|succeeded|failure|cancelled)|execution\.(stdout|stderr))'
git diff --unified=0 CORRECTED_PLAN_BASE -- tests/cli/test_upload_filings_from_command.py | \
  rg '^\+.*(_docling[.]json|DOCLING_FILE_SUFFIX|primary_filename\s*==\s*source_path[.]name)'
git diff --unified=0 CORRECTED_PLAN_BASE -- tests/cli/test_upload_filings_from_command.py | \
  rg '^\+.*(source_meta|meta[.]json|private|_core|materialize_files\s*=\s*True|get_source\()'
git diff --unified=0 CORRECTED_PLAN_BASE -- tests/cli/test_upload_filings_from_command.py | \
  rg '^\+(async )?def |^\+class |^\+.*"[A-Za-z_]+"\s*:'
rg -n 'primary[ ]filename.*等于.*source[ ]basename|primary[_]filename == source_path[.]name' \
  docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md
```

五条 scan必须全部零输出。最后一条是 corrected plan旧错误措辞scan；它不得以“硬编码 Docling filename为expected primary”
替换旧等式。实现 review还必须直接确认新增断言只使用 public descriptor `name/sha256`，primary exact membership与 raw-source
exact name/hash彼此独立，且现有 oracle JSON key set没有 diff。

### 13.7 README and design decision

- `README.md` 与 `tests/README.md`：既有 WIN4-RW-S2更新已属于 accepted immutable base；本 WIN4-RW-RF01 correction
  不改变最终用户或 test runner工作流，future implementation必须零 README diff。
- `dayu/config/README.md`：不更新。Config schema、`api_key_ref`、environment persistence target与明文不入 config contract均不变。
- `dayu/fins/README.md`：不更新。WIN4-RW-RF01只纠正 test对既有 public snapshot contract的消费，不改 storage contract。
- `dayu/README.md`、`docs/fins/design.md`、`docs/ui/design.md`、`docs/host/design.md`：不更新。无分层、装配、Host/Engine、
  durable schema或 LLM-facing语义变化。

若实际实现触发任何 README、用户可见 grammar、参数、output channel、持久化目标或架构边界变化，立即停止并回 plan review，
不得机械扩写 README。

### 13.8 Fresh remote rerun and same-run canary closure

既有两个 slices与aggregate review已 accepted；fresh R11 `29709987970`、R12 `29709993229` 只用于接受
`WIN4-RW-RF01`，其失败 overall不能复用为 final closure。只有本 exact-node correction经 implementation review/fix/re-review、
aggregate validation/deepreview全部 accepted并形成新的唯一 accepted implementation commit后，Controller才可重新 dispatch。

| Gate | Fresh required result | Positive owner evidence | Failure/stop semantics |
| --- | --- | --- | --- |
| R11 identity | 本次 dispatch response返回唯一新 run id；metadata精确绑定 R11 workflow/path、`workflow_dispatch`、target ref 与 accepted implementation head SHA | 不从最近 run、时间或 artifact名反推 | 任一 missing/mismatch/ambiguous立即 fail |
| R11 four nodes | `4/4 passed`，workflow exit `0` | real upload exit `0`；company-name oracle；public snapshot identity/source kind；Fins primary按 exact name唯一命中 public descriptor；exact raw source basename唯一 descriptor的public SHA-256等于fixture bytes SHA-256；oracle存在且字段集合不变 | 任一 descriptor membership/name/hash失败即stop；不解析display/generic message，不读取raw meta/private path，不把raw或Docling filename强制为primary |
| R11 artifact integrity | pass | generated script SHA-256与 oracle一致；physical artifact count一致且 >0；required recorder/script/oracle/JUnit/stdout/stderr存在 | path/hash/count/missing任一失败即gate fail |
| R12 identity | 本次 dispatch response返回唯一新 run id；metadata精确绑定 R12 workflow/path、`workflow_dispatch`、target ref 与 accepted implementation head SHA | 与 R11 run独立锁定，不混用 | 任一 missing/mismatch/ambiguous立即 fail |
| R12 init | `9/9 passed`，workflow exit `0` | real redirected stdin被 owner消费；setx round-trip、exact registry cleanup与其余8 nodes继续通过 | timeout仍只使用既有 safe category/returncode/cleanup projection，不读取 raw input |
| R12 embedded R11 | `2/2 passed` | adversarial argv与 process+storage-owned real upload同时通过；primary membership与raw-source exact name/hash使用和R11相同的public contract | 同R11 descriptor failure/stop contract；不得硬编码Docling expected primary |
| R12 artifact integrity | pass | 同一 R12 run的 JUnit、source hashes、全部 downloaded artifacts与完整 workflow logs齐全并重新计算 hash | lineage不完整或跨 run混用即fail |
| R12 same-run canary gate | pass | Controller按既有 §2.3/§9.3 frozen text独立派生，仅在进程内 exact scan同一 R12 run的全部 artifact files与全部 workflow log files，零命中 | 不读取/回显/落盘 run-specific canary；命中只记录 run/head、relative locator、category与status |

R12 canary scan必须在读取 failure content前完成，且 scan、JUnit/source-hash/artifact integrity与 workflow conclusion必须属于
同一 fresh R12 run。Test/production/Controller不得共享派生 helper、constant module或 needle artifact；standalone R11未消费
R12 canary，仍只按自身 artifact integrity与无 secret input contract验收，不得声称由 R12 scan证明。

只有 fresh R11 overall success、fresh R12 overall success、R12 embedded R11 success、全部 required artifacts完整且同 run、
same-run canary gate通过，且 R11/R12 embedded R11都证明“Fins primary exact descriptor membership”与“raw source exact
basename/public SHA-256 publication”两个独立事实，才能关闭 `WIN4-RW-RF01`、把 `WIN4-RW-F01/F02` 的既有 positive
evidence纳入 clean aggregate closure，并关闭 WIN4 real-Windows blocker与 AR-F07。任一 run即使 primary当前仍选择
Docling JSON，也只作为 Fins owner事实消费，不能升级为未来 expected primary contract。

### 13.9 Security, deferred scope, residual risk and completion

Security boundary保持：Config与 Host internal SQLite/EventLog是 trusted-local domain；只有 Tool Trace/audit以及 public/
LLM-facing/operator diagnostics禁止 API key/header明文。本 amendment不读取、迁移、重写或扩大 durable secret范围，不把
redirected stdin伪装成 encrypted transport，也不新增 zeroization、credential broker、unified authorization或 secret infra。

明确 deferred/forbidden：Issue 142、151、175、177、178；Web/WeChat/render；通用 console/PTY/process isolation；
setx redesign；统一 authorization/secret management；Fins generic diagnostic schema。Gemini low-budget继续是
`EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`，不是 finding、blocker或验收输入。

Residual risks及 owner/destination：

1. 非 Windows本地无法证明 CPython 3.11 Windows console与 redirected handle的真实组合；owner unit tests只锁定 capability
   contract，最终证据唯一 destination是 §13.8 fresh R12。
2. caller-owned pipe、OS handle与当前 CLI process memory按输入本质会暂存 secret；本 WU只承诺 CLI不主动回显或投影，
   不承诺外部 shell/process inspection安全。扩大 transport threat model需独立安全设计，不得在本 amendment实现。
3. 若 fresh R11/R12 embedded R11的 primary无法精确命中 public descriptor，或 raw-source exact name/hash publication失败，
   立即按 owner boundary进入 diagnostic-first stop；不得把 raw source改成 expected primary、把 Docling filename硬编码为
   expected primary、读取 raw meta/private path或修改 Fins contract来迁就 test。其它 fresh R11 exit/storage owner失败或
   fresh R12在 secret读取之后出现新 failure，同样不得沿用当前 root causes解释新证据。

Open questions：`0`。当前 primary owner、raw-source publication证明、exact-node allowlist、README零diff、remote closure与
security boundary均已收敛；implementation agent无需重新设计。

后续 implementation completion artifact除 §12 既有要求外，必须新增报告：

1. `CORRECTED_PLAN_BASE`、accepted exact-node implementation commit与两个 fresh dispatch-returned run ids/head SHA；
2. 唯一 `WIN4-RW-RF01` test-owner slice的 exact changed block、owner tests、review与回滚边界，以及 target node之外
   product/test/README/design/workflow/control零diff；
3. process exit、public company/source identity、Fins primary exact descriptor membership，以及 raw source exact basename唯一
   descriptor的public SHA-256等于本次fixture bytes SHA-256；明确二者独立且没有 hardcoded Docling expected primary；
4. company-name oracle、physical artifact integrity与既有 `cli-grammar-oracle.json`字段集合零变化；明确没有新增 helper、
   schema/public contract/oracle字段，没有读取 raw meta/private path，没有 Fins production/storage contract变化；
5. focused/public repository owner/aggregate/CLI regression、pyright、scoped/full Ruff baseline、diff/allowlist、README零diff与
   旧错误措辞/forbidden-source scans；
6. fresh R11/R12 identity、node counts、artifact integrity、两个独立 descriptor事实与 Controller-owned same-run value-free
   canary scan结论；
7. local platform skips、全部 residual risk与 diagnostic-first stop状态，不把 remote pending或当前 Docling primary选择误报为
   通用 primary contract或 closure。
