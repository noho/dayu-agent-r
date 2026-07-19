# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4 remediation plan — AgentMiMo 完整 Re-Review

## Gate identity

- Work unit：既有 `WU-SEMANTIC-OWNERSHIP-01` umbrella。
- Continuation：`AR-F07` 第四轮真实 Windows evidence remediation。
- Gate：Controller validation 通过后的完整 re-review。
- Baseline HEAD：`54e2dcbf653fb8c37b0206bd7aabbbf329ef040e`。
- 本 artifact 不是 implementation、不是 control transition、不 stage/commit/push/dispatch。

## 固定输入完整性确认

| 输入 | Expected SHA-256 | Actual SHA-256 | 状态 |
| --- | --- | --- | --- |
| Final plan | `0bd1382288a06cafb77f8bbced45b4b7e08d48c9ab895dfdac1fdad0efddbbe9` | `0bd1382288a06cafb77f8bbced45b4b7e08d48c9ab895dfdac1fdad0efddbbe9` | ✓ 已完整读取，634 lines |
| Controller adjudication | `a61568b1c4212286a8f92c80c7794ce5c889be56e3e333f6a1bd0ad87d7c9ba4` | `a61568b1c4212286a8f92c80c7794ce5c889be56e3e333f6a1bd0ad87d7c9ba4` | ✓ 已完整读取 |
| Plan-fix Codex | `fabf821f453996d3d2d141d530a5ac7ef28211f51eee513c55de43bc8083579a` | `fabf821f453996d3d2d141d530a5ac7ef28211f51eee513c55de43bc8083579a` | ✓ 已完整读取 |
| Plan-fix Controller validation | N/A（用户未提供 expected） | `f9be890e3abccf117167d911f91ec0df54d816a37026c9eb40916c5b6005ed52` | ✓ 已完整读取 |
| 原 MiMo review | `e5af0d3d08ca910a1da18e74f0a1f5c17c0ad643f7fa01fc762fc2bb087afaaf`（Controller adjudication 记录） | — | ✓ 已完整读取 |
| 原 DS review | `cb4ef70a0b28c1e168710cf3afabbbb2b3b17b0916ca3c54bfb03561fdd83fce`（Controller adjudication 记录） | — | ✓ 已完整读取 |

### 代码事实验证

| 文件 | 读取状态 |
| --- | --- |
| `dayu/cli/init_environment.py` | ✓ 836 lines，已完整读取 |
| `tests/cli/test_init_smoke.py` | ✓ 963 lines，已完整读取 |
| `tests/cli/test_init_environment.py` | ✓ 1246 lines，已完整读取 |
| `tests/cli/test_upload_filings_from_command.py` | ✓ 1012 lines，已完整读取 |
| `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` | ✓ 已读取前 100 lines |
| `docs/host/design.md` | ✓ 已读取前 100 lines |

---

## 逐项 Re-Review：WIN4-PR-F01..F04 闭合验证

### WIN4-PR-F01 — S1 pre-execution oracle 必须解析真正业务命令

**原 finding**：plan 对 S1 oracle 的实现方法只有"结构化/精确 oracle"的措辞，没有明确禁止简单字符串计数。Windows `.cmd` 文件包含 regeneration comment 和实际业务命令行，简单 `count("--company-name")` 可能误匹配 regeneration comment。

**Controller adjudication 修复要求**：oracle 在执行 `.cmd` 前运行并 fail closed；按 CRLF physical line 识别并排除 `REM Regenerate:` 注释和固定 batch header，只解析唯一的 `upload_filing` 业务命令；使用现有 Windows batch/CRT oracle 或等价的逐 token 解析，证明 `--company-name` 恰好一个且下一 token 精确为 `Apple Inc.`；禁止 whole-file count、substring presence、POSIX loose parsing、从执行结果反推输入，以及 comment-only 证明。

**Plan 闭合验证**：

Plan §4 S1 step 2 现已锁定：
> 按 CRLF physical line 识别生成脚本，排除 `REM Regenerate:` 注释与 renderer 固定 batch header，只允许并提取唯一非 `REM` 的 `upload_filing` 业务命令；再使用现有 Windows batch/CRT argv oracle 或等价的 Windows 语义逐 token 解析，断言 `--company-name` token 恰好一个且其下一 token 精确等于 `Apple Inc.`。不得使用 whole-file `count`、substring presence、POSIX loose parser、从 execution result 反推输入，或只证明 regeneration comment 含该参数。

Plan §5.1 增加了对应 negative case：
> pre-execution oracle 遇到"comment 含 company name、唯一业务命令不含"或多条/零条 `upload_filing` 业务命令时必须在执行前 fail closed；不得用 whole-file count 或 execution success 替代逐 token 证明。

**代码事实对照**：

当前 `test_upload_filings_from_command.py` L844-860 的 Windows test generation argv 确实不含 `--company-name`，而 POSIX test（L738-739）显式传 `--company-name "Apple Inc."`。plan §4 S1 step 1 要求"显式追加 `--company-name`, `Apple Inc.`"，方向正确。

**结论：CLOSED。** Plan 已精确锁定 oracle 实现策略，明确禁止所有已知误匹配路径。Finding 修复充分。

---

### WIN4-PR-F02 — S3 cleanup-timeout 后必须投影非阻塞进程状态

**原 finding**：cleanup bounded wait 再次 timeout 时没有说明 direct outer process 的当时状态。

**Controller adjudication 修复要求**：cleanup timeout 后只调用一次非阻塞 `poll()`；`None` 投影 `process_state_after_cleanup_timeout=running`，integer 投影 `process_state_after_cleanup_timeout=exited` 并进入 `cleanup_returncode`。此后不再次 wait/kill，不递归治理 process tree，也不把 post-cleanup poll 冒充 deadline 前自然退出。

**Plan 闭合验证**：

Plan §2.3 step 5 现已锁定：
> timeout 时先 `poll()` 记录 `returncode_at_timeout`；若仍运行则 kill direct outer process 并 bounded wait，记录 `cleanup_returncode` 与 cleanup state。若 bounded cleanup 再次 timeout，只额外调用一次非阻塞 `poll()`：`None` 投影为 `process_state_after_cleanup_timeout=running` 与 `cleanup_returncode=not_available`；integer 投影为 `process_state_after_cleanup_timeout=exited` 并把该 integer 记录为 `cleanup_returncode`。此后不得再次等待、再次 kill、递归治理 process tree，或把 poll 观察到的状态伪装成 deadline 前自然退出。

Plan §5.3 增加了对应 negative case：
> cleanup timeout 必须保持 `cleanup=timeout` 并继续失败；其后恰好一次非阻塞 `poll()` 必须区分 `process_state_after_cleanup_timeout=running|exited`，可用 integer 只进入 `cleanup_returncode`，不得再次 wait/kill。

**结论：CLOSED。** Plan 已精确锁定 cleanup timeout 后的进程状态投影，四种终止状态（deadline 前自然退出、deadline 时已退出、kill 成功、cleanup timeout）边界清晰。

---

### WIN4-PR-F03 — S3 必须锁定 anonymous-file primitive 与 lifetime

**原 finding**：plan 必须明确临时载体清理契约。

**Controller adjudication 修复要求**：锁定 `tempfile.TemporaryFile(mode="w+b")` context managers；不使用 `mkstemp`、`NamedTemporaryFile` 或 pytest `tmp_path`；三个 handle 在 child execution 与 bounded cleanup 期间保持有效，并在 `finally` / context unwind 关闭；不记录 path，不增加显式 unlink、retained-path warning 或新的 cleanup framework。

**Plan 闭合验证**：

Plan §0.1 disposition lock 已锁定：
> `mkstemp`、`NamedTemporaryFile`、pytest `tmp_path`、retained-path warning、显式 unlink 与新的 cleanup framework 均被拒绝。§2.3 锁定 anonymous handle lifetime，不建立 durable test-artifact path 语义。

Plan §2.3 step 1 已锁定：
> 在同一 context lifetime 内创建 stdin/stdout/stderr 三个 anonymous binary handle。启动 subprocess 前把 `input_text` 用 strict UTF-8 编码后写入 stdin handle、flush 并 rewind；随后立即把调用 frame 中的 text/bytes 变量清空。Popen 只接收 handle，不接收 secret-bearing `input=`。

Plan §2.3 step 8 已锁定：
> 三个 handle 在 helper 的 `finally` / context unwind 中统一关闭；不记录 path，不使用 `mkstemp`、`NamedTemporaryFile` 或 pytest `tmp_path` 承载 sentinel，不增加显式 unlink、retained-path warning 或新的 cleanup framework。安全 contract 是 anonymous handle lifetime 与 evidence 零泄漏，不是 durable path 清理。

Plan §5.3 增加了对应 negative case：
> 不产生、记录或清理 named temp path；不得用 `mkstemp`、`NamedTemporaryFile`、pytest `tmp_path`、unlink failure 或 retained-path warning 建立第二套 cleanup 语义。

**结论：CLOSED。** Plan 已精确锁定 anonymous handle primitive 和 lifetime contract，明确禁止所有 named-file 替代方案。

---

### WIN4-PR-F04 — 真实 R11/R12 closure 必须有可执行 canary scan gate

**原 finding**：Controller 不能读取 GitHub Secrets，也不能取得当前测试内部用 `secrets.token_urlsafe()` 随机生成且未安全发布的原值；把这些值写成 Controller scan needle 会形成不可执行伪 gate。

**Controller adjudication 修复要求**：R12 真实 Windows setx test 只从公开 `GITHUB_RUN_ID` 经过固定 domain-separated 纯函数派生 API-key-shaped canary，本地非 workflow 路径可继续使用随机值。Controller 从公开 R12 run id 独立重算同一 canary，对新 R12 workflow log 和全部 downloaded artifacts（含其 embedded R11 artifacts）做 exact-value 扫描，零命中才通过。独立 R11 workflow 没有消费该 canary，不能把对其扫描一个从未输入的值写成有效安全证明。

**Plan 闭合验证**：

Plan §2.3 canary contract 已锁定：
> R12 workflow 环境只读取公开 `GITHUB_RUN_ID`。先要求该值是正十进制整数，再用其 canonical decimal text `str(int(GITHUB_RUN_ID))` 作为纯函数输入；`GITHUB_ACTIONS=true` 时缺失或非法必须在启动被测 CLI 前 fail closed。
>
> 固定 domain separator 为 ASCII bytes `dayu-ar-f07-win4-r12-canary-v1\0`，计算 `sha256(domain_separator + canonical_run_id.encode("ascii")).hexdigest()`，最终 canary 为 `sk-dayu-test-<64 lowercase hex digest>`。该函数无 secret/key/salt、无时间或随机输入，Controller 可只凭公开 run id 独立重算；prefix 只让输入保持 API-key-shaped，不表示真实 credential。
>
> 本地非 GitHub Actions 路径继续使用 `secrets.token_urlsafe(32)`，不要求 Controller 扫描本地随机值。

Plan §5.4 closure canary 已锁定：
> `GITHUB_ACTIONS=true` 时，R12 真实 Windows setx test 只能从合法 `GITHUB_RUN_ID` 按 §2.3 冻结纯函数派生 canary；缺失、空值、非十进制或非正值必须在启动 CLI 前 fail closed，不得回退随机值。
>
> 相同 canonical run id 必须产生相同 canary，不同 run id 必须产生不同 canary；domain separator、prefix、digest 算法或 canonicalization 任一漂移都必须由 owner test 失败。
>
> workflow canary 保持 API-key-shaped 但明确非秘密；不得写入 stdout、stderr、safe failure、JUnit 辅助字段或专门 needle artifact。测试内部可以把它写入预期 registry owner 并做 round-trip，但 cleanup 后不得把值作为 evidence 发布。

Plan §6.6 Controller canary scan 已锁定：
> Controller 只从公开 R12 run id 按 §2.3 冻结纯函数独立重算 non-secret canary，递归扫描 R12 完整 workflow log 和全部 downloaded artifacts（含 embedded R11），零命中才通过。Controller 不得从 test output/artifact 取得 needle，也不得读取或扫描 GitHub Secrets/configured production values。若命中，只记录 R12 run id、artifact-relative locator、`match_category=test_canary` 与 gate status，不复制 canary 或 matched content；扫描命令、review artifact 和 control doc 同样不得回显 canary。

Plan §8 closure matrix 已锁定：
> R12 Controller canary scan：Controller 只从新 R12 公开 run id 按冻结纯函数独立重算 non-secret canary，递归扫描 R12 完整 workflow log 和全部 downloaded artifacts（含 embedded R11），零命中。standalone R11 不在 scan 范围；不读/扫 GitHub Secrets 或 configured production 值；command/review/control 只记录 R12 run、artifact-relative locator、`test_canary` category 与 status，不回显 canary/matched content。

Plan §9.3 security gate 已锁定：
> 本 gate 的执行 owner 是 Controller：只从公开 R12 run id 按 §2.3 冻结纯函数独立重算 canary，扫描该 R12 run 的新 workflow 完整 log 与全部 downloaded artifacts（含 embedded R11）。只有递归 exact-value scan 零命中才可通过。
>
> Controller 不得读取、请求、导出或扫描 GitHub Secrets/configured production values；当前 R12 workflow 没有把这些值作为本 test input，因此它们不是本 canary gate 可验证的 needle。standalone R11 没有消费 R12 canary，继续按 artifact integrity 与无 secret-input contract 验收，不进入 scan。

**可执行性验证**：

1. **纯函数确定性**：`sha256(domain_separator + canonical_run_id.encode("ascii")).hexdigest()` 是纯函数，无外部依赖，Controller 可独立重算。✓
2. **fail-closed**：`GITHUB_ACTIONS=true` 时缺失/非法 run id 必须在 CLI 启动前 fail closed。✓
3. **API-key-shaped**：prefix `sk-dayu-test-` + 64 hex digest = 75 chars，符合 API-key 形状。✓
4. **Controller 不取 needle**：plan 明确"不得从 test output/artifact 取得 needle"。✓
5. **standalone R11 分离**：plan 多处明确"standalone R11 没有消费该 canary，不进入 scan"。✓
6. **GitHub Secrets 不作为 needle**：plan 多处明确"不读取或扫描 GitHub Secrets/configured production values"。✓

**结论：CLOSED。** R12 canary contract 已从不可执行伪 gate 修正为可验证双 owner contract。纯函数、fail-closed、Controller 独立重算、standalone R11 分离均已锁定。

---

## Rejected / already-satisfied candidates 回流检查

| Candidate | 原 disposition | Plan 是否回流 | 验证 |
| --- | --- | --- | --- |
| DS `Finding 1.2b` | 并入 F01 | 否，只精确化 fail-closed 约束 | ✓ |
| DS `Finding 2.2a` | already satisfied | 否，`TimeoutExpired` 仍不绑定/格式化/记录/转抛 | ✓ |
| DS `Finding 2.2b` | rejected | 否，不增加 timing instrumentation | ✓ |
| DS `Finding 3.1a` | rejected | 否，不枚举 PIPE/handle-table 替代方案 | ✓ |
| DS `Finding 3.3a` named-path | rejected | 否，只锁定 anonymous handle lifetime | ✓ |
| DS `Finding 4.1a` | rejected | 否，不新增 dependency framework | ✓ |
| DS `Finding 4.4a` | rejected | 否，README 继续与 S3 同 slice | ✓ |
| DS `Finding 5.1a` | rejected | 否，不冻结易漂移测试数量 | ✓ |
| DS `Finding 5.6a` | rejected | 否，unexpected recurrence 继续阻塞 closure | ✓ |
| MiMo `RISK-2` | rejected | 否，保持 S1→S2→S3 串行顺序 | ✓ |

**结论：零回流。** 所有 rejected/already-satisfied candidates 均未被重新引入 implementation。

---

## 临时文件 / cleanup poll / command oracle 边界验证

### TemporaryFile 边界

Plan §2.3 锁定 `tempfile.TemporaryFile(mode="w+b")`，不使用 `mkstemp`、`NamedTemporaryFile` 或 `tmp_path`。三个 handle 覆盖 child execution 与 bounded cleanup 完整生命周期，在 `finally` / context unwind 关闭。安全 contract 是 anonymous handle lifetime 与 evidence 零泄漏。

**代码事实对照**：当前 `_run_init()`（L162-199）使用 `subprocess.run(input=input_text, capture_output=True, text=True, encoding="utf-8", errors="strict")`。Plan 要求改为 `Popen[bytes]` + 三个 `TemporaryFile` handles + `wait(timeout=180)`。方向正确，不引入 named-file lifecycle。

### Cleanup poll 边界

Plan §2.3 step 5 锁定四种终止状态的完整投影，cleanup timeout 后只调用一次非阻塞 `poll()`，不再次 wait/kill。当前 `_run_init()` 无 timeout 处理——直接 `subprocess.run(timeout=180)` 透传 `TimeoutExpired`。Plan 要求显式处理并投影 safe failure message，方向正确。

### Command oracle 边界

Plan §4 S1 step 2 锁定 CRLF line-based parsing + token-based `--company-name` 验证，禁止 whole-file count、substring、POSIX loose parser。当前 Windows test（L886-904）无 pre-execution oracle——plan 要求新增，方向正确。

**结论：边界清晰。** TemporaryFile/cleanup poll/command oracle 三个边界均在 plan 中精确锁定，无模糊地带。

---

## 过度设计检查

| 维度 | 评估 |
| --- | --- |
| 新增 abstraction | 无。三 slice 只修改 test 文件和一个 production function |
| 新增 framework | 无。不引入 cleanup framework、dependency framework、process-tree framework |
| 新增 secret infrastructure | 无。canary 是 non-secret、test-owned、run-specific |
| 新增 diagnostic infrastructure | 无。§10 明确"不应预先增加通用 diagnostic infrastructure" |
| 扩域 | 无。不实施 Issue 142/151/175/177/178、Web/WeChat/render |
| 兼容性代码 | 无。§11 明确"零 compatibility re-export/wrapper/alias" |

**结论：无过度设计。** Plan 严格遵守最小化修复原则，三 slice 各自只修改 owner boundary 内的必要代码。

---

## R12 GITHUB_RUN_ID canary 可执行性深度验证

### 纯函数规范

```
domain_separator = b"dayu-ar-f07-win4-r12-canary-v1\0"
canonical_run_id = str(int(GITHUB_RUN_ID)).encode("ascii")
digest = sha256(domain_separator + canonical_run_id).hexdigest()
canary = f"sk-dayu-test-{digest}"
```

### 可执行性断言

1. **输入唯一性**：只依赖公开 `GITHUB_RUN_ID`，无 secret/key/salt/time/random。✓
2. **确定性**：相同 run id → 相同 canary。✓
3. **domain separation**：固定 ASCII prefix + NUL byte 防止 collision。✓
4. **fail-closed**：`GITHUB_ACTIONS=true` 时缺失/非正整数 → CLI 启动前 fail。✓
5. **Controller 可独立重算**：Controller 只需 run id + 上述规范即可重算。✓
6. **非秘密**：canary 本身是 SHA-256 派生值，不含 secret material。✓
7. **API-key-shaped**：`sk-dayu-test-` + 64 hex = 75 chars，模拟 API key 形状。✓

### Owner test 覆盖需求

Plan §4 S3 step 3 要求：
> 增加纯函数 determinism、domain separation、API-key-shaped 输出、workflow fail-closed 与 local-random owner tests，并断言 canary 不进入 stdout/stderr/safe failure。

这些 test 必须在 S3 实现中覆盖：
- 相同 run id 产生相同 canary（determinism）
- 不同 run id 产生不同 canary（collision resistance）
- domain separator 任一字节变化 → canary 变化（domain separation）
- prefix 固定为 `sk-dayu-test-`（API-key-shaped）
- `GITHUB_ACTIONS=true` + 缺失/非法 run id → fail closed
- `GITHUB_ACTIONS` 未启用 → 可随机
- canary 不进入 stdout/stderr/safe failure text

**结论：可执行。** 纯函数规范明确、无歧义，Controller 可独立重算，owner test 覆盖需求完整。

---

## Standalone R11 不伪造证明验证

Plan 多处明确 standalone R11 与 R12 canary scan 的边界：

- §5.4："standalone R11 没有消费该 canary，不进入本 scan，也不得声称由本 scan 证明其 non-disclosure。"
- §8："standalone R11 不在 scan 范围；不读/扫 GitHub Secrets 或 configured production 值"
- §8："standalone R11 的 closure evidence 只来自其 capability/four-node/argv/real-upload 结果、artifact integrity 与无 secret-input contract；R12 canary scan 不为 standalone R11 提供或声称额外 non-disclosure 证明。"
- §9.3："standalone R11 没有消费 R12 canary，继续按 artifact integrity 与无 secret-input contract 验收，不进入 scan。"

**结论：边界清晰。** Standalone R11 的 closure 证据来源明确限定为 artifact integrity 与无 secret-input contract，不从 R12 canary scan 获得伪造证明。

---

## GitHub Secrets 不作为 needle 验证

Plan 多处明确 GitHub Secrets 不在 scan 范围：

- §2.3："不读取 GitHub Secrets 或 configured production values，也不把它们加入 scan 范围"
- §5.4："Controller 不得从 test output/artifact 取得 needle，也不得读取或扫描 GitHub Secrets/configured production values"
- §6.6："Controller 不得读取、请求、导出或扫描 GitHub Secrets/configured production values"
- §8："不读/扫 GitHub Secrets 或 configured production 值"
- §9.3："当前 R12 workflow 没有把这些值作为本 test input，因此它们不是本 canary gate 可验证的 needle"

**结论：边界清晰。** GitHub Secrets 明确排除在 canary scan needle 之外，plan 正确识别了"当前 workflow 没有把这些值作为 test input"的事实。

---

## 原 MiMo review RISK-1 闭合验证

**原 RISK-1**：S1 oracle 实现指导不够具体，可能用简单字符串计数而非结构化解析区分 regeneration comment 和业务 command。

**Controller adjudication 修复**：已接受并精确化为 WIN4-PR-F01。

**Final plan 闭合**：Plan §4 S1 step 2 和 §5.1 已锁定 CRLF line-based parsing + token-based 验证，明确禁止 whole-file count、substring、POSIX loose parser。RISK-1 已被 WIN4-PR-F01 完全覆盖并精确化。

**结论：CLOSED。**

---

## 原 MiMo review RISK-2 闭合验证

**原 RISK-2**：S1 与 S2 无生产依赖但 Plan 暗示串行执行。

**Controller adjudication**：rejected，保持用户指定 S1→S2→S3 串行顺序。

**Final plan**：Plan §0.1 disposition lock 明确"保持用户指定的 S1→S2→S3 串行顺序，不改为并行实施"。

**结论：PRESERVED。** 串行顺序是用户裁决，plan 正确保持。

---

## 原 DS review findings 闭合验证

| Finding | 严重度 | Controller disposition | Final plan 状态 |
| --- | --- | --- | --- |
| 1.2a (oracle 精度) | MEDIUM | → WIN4-PR-F01 | CLOSED |
| 1.2b (oracle placement) | LOW | 并入 F01 | CLOSED |
| 2.2a (TimeoutExpired.cmd) | CRITICAL | already satisfied | PRESERVED |
| 2.2b (30s magic number) | LOW | rejected | PRESERVED |
| 3.1a (方案 B 排除) | LOW | rejected | PRESERVED |
| 3.2a (cleanup timeout gate) | MEDIUM | → WIN4-PR-F02 | CLOSED |
| 3.3a (temp file unlink) | MEDIUM | → WIN4-PR-F03 | CLOSED |
| 4.1a (S2→S3 硬依赖) | LOW | rejected | PRESERVED |
| 4.4a (README 回滚) | LOW | rejected | PRESERVED |
| 5.1a (_SetxRecorder 签名) | MEDIUM | rejected | PRESERVED |
| 5.5a (secret scan 执行者) | MEDIUM | → WIN4-PR-F04 | CLOSED |
| 5.6a (R11 upload gate 状态) | MEDIUM | rejected | PRESERVED |

**结论：全部闭合或 preserved。** 无遗漏 finding。

---

## Material findings

**零 material findings。**

本次 re-review 验证了以下全部维度：

1. WIN4-PR-F01..F04 四项 accepted findings 均已在 final plan 中精确闭合。
2. R12 public GITHUB_RUN_ID canary 的派生规范明确、纯函数可重算、fail-closed 设计完整、Controller scan 可执行。
3. Standalone R11 不从 R12 canary scan 获得伪造 non-disclosure 证明。
4. GitHub Secrets 明确排除在 canary scan needle 之外。
5. TemporaryFile/cleanup poll/command oracle 三个边界在 plan 中精确锁定。
6. 所有 rejected/already-satisfied candidates 均未回流。
7. 无过度设计：plan 严格遵守最小化修复原则。

---

## 结论

**PASS。**

Final plan（SHA-256 `0bd1382288a06cafb77f8bbced45b4b7e08d48c9ab895dfdac1fdad0efddbbe9`）已通过完整 re-review。四项 WIN4-PR-F01..F04 均精确闭合；R12 canary contract 从不可执行伪 gate 修正为可验证双 owner contract；standalone R11 边界清晰；GitHub Secrets 不作为 needle；临时文件/cleanup poll/command oracle 边界精确锁定；零 rejected candidates 回流；无过度设计。

Plan 已满足 `READY_FOR_IMPLEMENTATION` 条件。

---

## Artifact integrity

- 本 artifact 不含随机 sentinel、registry value、configured secret、raw source content 或用户绝对路径。
- 本 artifact 不修改 plan/control/production/tests/README/workflow，不 stage/commit/push/dispatch。
- 本 artifact 路径：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-remediation-plan-rereview-mimo.md`。
- 本 artifact SHA-256：`e00bd10b7edebabaee56e51a7fa9dbfc5f8e0eab271aa01858f41d02a9714a54`。
