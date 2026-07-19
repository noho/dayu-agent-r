# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-S3 implementation（AgentCodex）

## 1. Gate identity

- Umbrella：`WU-SEMANTIC-OWNERSHIP-01`。
- Continuation：`AR-F07 WIN4`，同一 remediation continuation，不是新 WU。
- Slice：`WIN4-S3 — Timeout-safe outer harness and final docs`。
- Gate：implementation；本轮不进入 code review、accepted-slice commit 或 remote closure。
- Baseline HEAD：`5c8c11f88fb0d935ad5730aa7d892ad26a060633`。
- Branch：`phaseflow/host-issues-control`。
- S2 accepted-commit Controller validation：
  `PASS / EXACT_SCOPE_ACCEPTED_COMMIT / READY_FOR_WIN4_S3_IMPLEMENTATION`。

## 2. First-principles owner judgment

本 slice 动机成立。原 `_run_init()` 使用 `subprocess.run(input=..., timeout=...)`，会让 input 文本继续成为
`Popen.communicate()` / `_communicate()` frame material；pytest/JUnit 展开 raw timeout frame 时存在复制测试输入值的直接
路径。outer real CLI process 的捕获、timeout cleanup 与测试失败投影由 `tests/cli/test_init_smoke.py` 唯一拥有，production
CLI、S2 setx owner、workflow/JUnit plugin 都不是修复边界。

S2 已在 production owner 把无消费者的 native setx stdout/stderr 改为 DEVNULL，并锁定 direct timeout。本 slice 只治理
test outer process：它不以 test cleanup 替代 S2，不修改 production，也不增加 process-tree、job object、process group、
workflow redact、global subprocess helper 或 named-temp cleanup framework。

## 3. Changed paths and ownership

| Path | Owner change |
| --- | --- |
| `tests/cli/test_init_smoke.py` | test-local typed result、anonymous-handle Popen lifecycle、timeout safe renderer、deterministic canary 与 owner tests |
| `tests/README.md` | 真实 Windows gate 的 accepted capture/timeout evidence 区别 |
| `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s3-implementation-codex.md` | 本 implementation durable artifact |

没有修改 production、S1/S2、workflow、root README、plan/control/design 或 deferred Issue paths。

## 4. Implemented contract

### 4.1 Outer real CLI lifecycle

- `_InitProcessResult` 只拥有 `returncode/stdout/stderr`，不保留 argv、cwd、path 或 input。
- `_run_init()` 在一个 context lifetime 内创建三个 `tempfile.TemporaryFile(mode="w+b")` handles。
- stdin 先 strict UTF-8 encode、write、flush、rewind；随后清空 helper frame 中的 input text/bytes 变量，再启动
  `subprocess.Popen[bytes]`。
- Popen 保留既有 argv/cwd/env，固定 `shell=False`、`close_fds=True`、`text=False`；只使用
  `wait(timeout=180)`，不调用 `communicate()`。
- ordinary completion 后才 rewind/read stdout/stderr，并 strict UTF-8 decode。ordinary nonzero 仍返回 typed result，由
  `_assert_init_result()` 判定；不重分类成 timeout。

### 4.2 Timeout state owner

- deadline 后先做一次 nonblocking `poll()`，锁定 `returncode_at_timeout`。
- deadline 时已退出：不 kill、不二次 wait，投影 completed cleanup。
- deadline 时仍运行：只 kill direct outer process，再做一次 `wait(timeout=180)`。
- cleanup wait 再次 timeout：恰好再做一次 nonblocking `poll()`，投影 `running` 或 `exited`；此后没有二次
  wait/kill 或 process-tree 治理。
- failure path 不读取 stdout/stderr；三个 handles 覆盖 child execution 与 bounded cleanup，并由 context unwind 统一关闭。
- 唯一 renderer 只输出 `category`、`timeout_seconds`、`returncode_at_timeout`、`cleanup`、
  `cleanup_returncode`；仅 cleanup timeout 追加 `process_state_after_cleanup_timeout`。
- 通过 `pytest.fail(safe_message, pytrace=False)` 失败，不传播 raw `TimeoutExpired` frame/exception material。

### 4.3 GitHub Actions closure canary

- `GITHUB_ACTIONS=true` 时只读取公开 `GITHUB_RUN_ID`；缺失、空、非 ASCII 十进制或非正值均在启动被测 CLI 前
  fail closed，且不回退随机值。
- run id 通过 `str(int(raw))` canonicalize；唯一 domain bytes literal 求值为 31 bytes，末字节为 single NUL；
  SHA-256 输入为 domain 与 canonical ASCII run id，输出保持 `sk-dayu-test-` 加 64 位小写 hex 的 shape。
- owner test 精确冻结完整 domain bytes、single-NUL 事实、run id `1` 的 accepted known vector、determinism、
  canonicalization、不同 run id、prefix/digest shape。
- 非 GitHub Actions 本地路径继续调用 `secrets.token_urlsafe(32)`。
- timeout negative test 每次使用新的随机 sentinel，并同时把 deterministic canary 放入 raw timeout command/output 探针；
  最终 safe failure 的 `str/repr/capture`、failure-path stdout/stderr read 均为零命中。真实 setx node继续断言选中值不进入
  stdout/stderr；没有新增 JUnit properties、辅助字段或 needle artifact。

### 4.4 README decision

`tests/README.md` 只记录 accepted 区别：产品 setx native output 没有消费者、不由产品捕获；outer real CLI 仍用
anonymous binary handles capture 并 strict UTF-8 decode；timeout artifact 只保留安全状态字段和环境变量名，不记录
stdin input value。用户可见 CLI grammar、交互、输出通道与排障入口不变，因此 root README 不更新。

## 5. Deterministic negative owner tests

新增 owner tests 覆盖：

- Popen argv/cwd/env 保持，三个 binary handles、stdin write/flush/rewind、typed result exact fields；
- success strict UTF-8 stdout/stderr 与 ordinary nonzero typed result；
- invalid stdin strict UTF-8 在 Popen 前失败，invalid output strict UTF-8 在读取两个 channel 后独立失败；
- deadline poll 为 exit `1`；deadline poll 为 not-exited 后 kill/cleanup completed；
- cleanup timeout 后 single poll 的 running/exited 两种投影；
- 所有状态的 exact wait/poll/kill count、无 second wait/kill、handles execution/cleanup lifetime 与退出后 closed；
- failure path stdout/stderr read count 为零；raw timeout `str/output` 确实含动态探针，但最终 safe failure
  `str/repr/capture` 不含随机 sentinel、canary、argv/cwd/path/input/stdout/stderr 或 exception 类型；
- canary domain bytes/长度/single NUL/known vector/determinism/canonicalization/shape；
- workflow missing/empty/non-decimal/non-positive fail closed 且 random fallback 零调用；合法 workflow deterministic path
  random fallback 零调用；local path每次请求 32 bytes 随机 token。

## 6. Validation

所有 Python 命令均在 `source .venv/bin/activate` 后运行；环境为 Python `3.11.15`、pytest `9.0.3`、pyright
`1.1.409`、Ruff `0.15.11`。

| Validation | Result |
| --- | --- |
| `pytest tests/cli/test_init_smoke.py -q`（最终） | `28 passed, 5 skipped, 3 warnings`；skip 全部为本地非 Windows 平台事实 |
| accepted focused 5-file matrix | `200 passed, 7 skipped, 3 warnings` |
| stale-meta + POSIX real-upload 必选 nodes | `2 passed, 3 warnings` |
| `pytest tests/cli/test_init_environment.py --cov=dayu.cli.init_environment --cov-branch --cov-report=term-missing -q` | `57 passed`；single-file branch coverage `93%` |
| broader Fins two-file regression | `95 passed, 3 warnings` |
| `pytest tests/cli -q`（最终） | `538 passed, 7 skipped, 3 warnings` |
| `python -m pyright dayu/ tests/ utils/`（最终） | `0 errors, 0 warnings, 0 informations` |
| accepted scoped Ruff command | `All checks passed` |
| full Ruff entry baseline | exit `1`，既有 `142` findings；exact normalized tuple SHA-256 `9df493aafef1701c3e2732ee61ea8dfb265d321a435ac12355733c70e245eda5` |
| full Ruff final | exit `1`，同为 `142` findings；exact normalized tuple SHA-256 完全相同，新增/扩散 `0` |
| `git diff --check` | PASS |
| staged tree | empty |

三类 warning 均来自既有 edgartools deprecated imports；本 slice 未新增 warning owner。

### 6.1 Validation correction record

加强 raw-timeout 探针自校验时，首次测试错误地要求 `repr(TimeoutExpired)` 必须包含 command/output。Python 3.11 的
`TimeoutExpired.__str__` 与 `.output` 含探针，但 `repr` 固定不展开 args，导致该测试前置条件 `4 failed`。修正仅发生在
test fake assertion：改为证明 raw `str/output` 含探针，同时继续证明最终 safe failure `str/repr/capture` 零命中。修正后
target、完整 CLI、full pyright 与 Ruff 均通过/保持 baseline；production contract 与 implementation 零变化。

## 7. Source, security and scope scans

- `capture_output=True` 在 `dayu/cli/init_environment.py`：零命中。
- `shell=True` / `errors=...replace` 在 S2 owner与S3 smoke：零命中。
- `communicate(` 在 `tests/cli/test_init_smoke.py`：零命中。
- `mkstemp`、`NamedTemporaryFile`、`CREATE_NEW_PROCESS_GROUP`、`JobObject`、`Start-Process`、`PowerShell` 在 S3
  smoke：零命中。
- deferred Issue / `web_tools_storage_states` 扫描：零命中。
- broad `reg.exe` 扫描只命中 `test_init_smoke.py` 既有 registry cleanup/query owner；S3 diff新增 `0`，没有引入新的
  registry authority或 fallback。`winreg` 与其它 process-isolation alternatives 零命中。
- 唯一 timeout renderer调用 `pytest.fail(..., pytrace=False)`；domain bytes literal精确一个。
- production、S1/S2、workflow、root README、plan/design/deferred paths 的 diff 为零。
- 用户既有 `docs/host/issues-implementation-control.md` dirty diff 与未跟踪 S2 accepted-commit validation artifact 未触碰。

## 8. Hashes

| Material | SHA-256 |
| --- | --- |
| `tests/cli/test_init_smoke.py` | `6748c609664f1e51854d743fd6dd5497069a384aadf7a91604c41a4476ceec30` |
| `tests/README.md` | `0fa4165bea105738d48788e782e51ad48eadb7aca9ea6a44ddf07e2d795f6aa2` |
| binary payload diff from baseline HEAD（上述两个文件） | `8bba3cd26606dd62552f3ee34a647da749027c62eef737407d6d4c16606886c4` |

Payload numstat：`tests/cli/test_init_smoke.py +956/-41`，`tests/README.md +7/-3`。

## 9. Residual risks and stop status

- 本地 Darwin 无法执行真实 Windows setx/transaction/junction/symlink nodes；状态为
  `PENDING_RELEASE_BLOCKER`，owner/destination 是 S3 accepted commit 后的 Controller-owned R12 dispatch、metadata lineage
  validation 与同-run log/all-artifact canary scan。当前本地结果不声称关闭 WIN4/AR-F07。
- standalone R11 不消费本 canary，不进入 R12 canary scan；没有读取或扫描 GitHub Secrets/configured production values。
- full Ruff `142` 条与 edgartools `3` 类 warning 是既有 baseline，未分类为本 slice finding。
- 没有 unclassified local implementation residual；没有创建新 issue，也没有进入 deferred Issue scope。

Completion：`WIN4-S3_IMPLEMENTATION_COMPLETE / READY_FOR_CONTROLLER_VALIDATION`。本轮严格停在 implementation gate；
未 stage、commit、push、dispatch workflow 或进入 code review。

Artifact path：
`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s3-implementation-codex.md`。
