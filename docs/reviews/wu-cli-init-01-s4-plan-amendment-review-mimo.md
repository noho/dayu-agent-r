# WU-CLI-INIT-01 S4 Plan Amendment — Adversarial Review (MiMo)

## Gate metadata

- Review target：`docs/reviews/wu-cli-init-01-s4-plan-amendment-codex.md`
- Reviewer：AgentMiMo（独立 adversarial reviewer）
- 日期：2026-07-30T16:23:20+08:00（来自本机系统时钟）
- Artifact path：`docs/reviews/wu-cli-init-01-s4-plan-amendment-review-mimo.md`
- 审查范围：S4 plan amendment 的风险真实性、owner 划分、allowed files 扩展理由、
  typed manifest/bytes snapshot API 最小性、fd/no-follow 逐层 discipline、capability
  gate 行为、stop condition 清晰度、测试 determinism、allowed files 充分性。

## Reviewed artifacts

- `docs/reviews/wu-cli-init-01-s4-plan-amendment-codex.md`（amendment 主体）
- `docs/reviews/wu-cli-init-01-plan-codex.md`（accepted plan S4 原文）
- `docs/reviews/wu-cli-init-01-s2-code-review-adjudication-controller.md`（S2 residual）
- `docs/reviews/wu-cli-init-01-s2-fix-codex.md`（S2 fix）
- `docs/reviews/wu-cli-init-01-s2-implementation-codex.md`（S2 实现）
- `dayu/cli/commands/init.py`（真实代码）
- `dayu/runtime/config_loader.py`（真实代码）
- `dayu/cli/init_workspace.py`（真实代码）

## Assumptions tested

| # | Assumption | 证据与结论 |
|---|---|---|
| 1 | init lock 排除外部 mutation | 被证伪。`.dayu-init.lock` 只串行同一 lock 的进程（`file_lock` 实现）；编辑器、同步程序或其它进程不受约束。amendment §1 证据成立。 |
| 2 | S2 静态 no-follow stat 足够 | 被证伪。`_workspace_execution_profile_is_regular_file(...)` 使用 `os.stat(path, follow_symlinks=False)`，但随后 `ConfigLoader._load_layered_config_file(...)` 以 `workspace_path.exists()` 和 `path.read_text()` 从同一路径读取，两者都 follow symlink。amendment §1 与 `config_loader.py:984` 行证据一致。 |
| 3 | locked snapshot 能替代 stable read | 被证伪。locked snapshot 只在 mutation boundary 比较；不能撤销已经发生的 workspace 外部读取。amendment §1 证据成立。 |
| 4 | 原 S4 allowed files 能关闭 gap | 被证伪。S2 的 `_EXECUTION_PROFILES_FILE_NAME` 和 `_workspace_execution_profile_is_regular_file(...)` 在 `init.py` 中，不在原 S4 白名单；`ConfigLoader` 也不在白名单。amendment §3.2 扩展理由成立。 |
| 5 | capability gate 在缺能力时能 fail closed | 成立，但有条件。amendment §4.2 步骤 1 要求 `os.open in os.supports_dir_fd` 等；在 Darwin 上已验证（`True`）。但 §8 的 stop condition 2 说 Windows 可能需要 native handle binding，当前无 Windows 验证证据。 |

## Findings

### S4-AMEND-R001-未修复-[中]-O_NONBLOCK 在 macOS 上对 regular file 产生 EAGAIN

- **位置**：amendment §4.2 步骤 5
- **问题类型**：契约缺失 / 平台行为未覆盖
- **当前写法**：`O_RDONLY | O_NOFOLLOW | O_NONBLOCK` 打开最终目标文件；步骤 7 用 `fstat` 确认为 regular file 后读取。
- **反例/失败场景**：macOS 上 `O_NONBLOCK` 对 regular file 的 `os.read()` 在无数据可读时返回 `EAGAIN`（`errno=EAGAIN`），而非阻塞等待。虽然 `fstat` 在步骤 7 确认了 regular file，但 `os.read` 在步骤 8 仍使用含 `O_NONBLOCK` 的 descriptor。对于 empty file 或 read chunk 边界情况，`EAGAIN` 会导致 `OSError` 传播，而非正常的 empty bytes/EOF 行为。
- **直接证据**：`man 2 open` on macOS：`O_NONBLOCK` on regular files causes reads to return `EAGAIN` when no data is available. Linux 上 `O_NONBLOCK` 对 regular file 无影响（regular files are always ready）。
- **为什么有问题**：amendment 只考虑了 FIFO 阻塞防护，未考虑 `O_NONBLOCK` 在 macOS 上对 regular file 的副作用。步骤 7 的 `fstat` 确认发生在 open 之后、read 之前，但 descriptor 上的 `O_NONBLOCK` 标志不会因 `fstat` 结果而改变。
- **影响**：macOS 上读取 empty `execution_profiles.json` 时 `os.read` 抛 `OSError(EAGAIN)`，被传播为系统 I/O 错误，而非正常的 `bytes=b""` 返回。
- **建议改法和验证点**：
  1. 修正：打开时不使用 `O_NONBLOCK`；步骤 7 的 `fstat` 确认 regular file 后，若目标不是 regular file（即 FIFO/socket），再以 `O_NONBLOCK` 重新打开或直接 fail closed（因为 amendment 步骤 6 已要求 FIFO/socket 等 special shape fail closed）。
  2. 或者：保留 `O_NONBLOCK`，在步骤 8 的 `os.read` 循环中捕获 `EAGAIN` 并重试，但这增加复杂度且与"fail closed"精神不符。
  3. 验证：测试 empty profile file 在 macOS 上正常返回 `bytes=b""`。
- **修复风险**：低
- **严重程度**：中（平台特定行为，macOS 上可触发）

### S4-AMEND-R002-未修复-[高]-race test determinism 机制未指定

- **位置**：amendment §6.2 测试 4-8、§8 stop condition 6
- **问题类型**：不可直接实施 / 测试缺口
- **当前写法**：amendment §6.2 要求 10 个 deterministic race test（stat/open swap、open/read file-name swap、directory swap、read/in-place-write race、read/parse swap 等），并明确"禁止使用 sleep 猜 race"。§8 stop condition 6 说"pre/post descriptor state 无法稳定表达或 deterministic race tests 只能依赖 timing/sleep"时必须 STOP。
- **反例/失败场景**：implementation agent 按 §6.2 编写 race test 时，无法在不使用 sleep 的情况下在 `os.stat` 返回后、`os.open` 调用前插入 path swap。Python 没有内建的 syscall-level hook；实现需要 monkeypatch `os.open` 或 `os.stat`，或使用 threading Event，但 amendment 不指定机制。
- **直接证据**：amendment §6.2 测试 4 的描述"在旧静态 stat 可见 regular 后、final open 前把 pathname 换成指向外部 secret 的 symlink；新实现没有 pre-stat acceptance"——这要求精确控制两个 syscall 之间的执行窗口，但不指定如何实现。
- **为什么有问题**：plan 的核心价值是 code-generation-ready。§6.2 定义了 10 个 race test 场景，但不指定 deterministic barrier 机制，迫使 implementation agent 在实现时重新设计测试架构。如果 agent 无法找到 deterministic 方案，必须按 §8 STOP，但 plan 不评估这一可行性。
- **影响**：implementation agent 可能被迫使用 sleep（违反 §6.2 约束），或发现 §8 stop condition 6 成立后必须 STOP 回 plan review，浪费实现周期。
- **建议改法和验证点**：
  1. 在 amendment 中增加 §6.2 race test 机制说明。推荐方案：monkeypatch `os.open` 和 `os.stat` 为可注入的 wrapper，在 test fixture 中通过 threading Event 控制 syscall 执行窗口。例如：
     ```python
     # 在 test fixture 中
     stat_barrier = threading.Event()
     open_barrier = threading.Event()
     original_stat = os.stat
     original_open = os.open

     def controlled_stat(*args, **kwargs):
         result = original_stat(*args, **kwargs)
         stat_barrier.set()
         open_barrier.wait()  # 等待 test 主线程完成 path swap
         return result

     def controlled_open(*args, **kwargs):
         open_barrier.set()  # 通知 stat 可以继续
         return original_open(*args, **kwargs)
     ```
  2. 或者：明确承认 race test 依赖 monkeypatch，并评估 monkeypatch 是否满足"deterministic"要求。
  3. 验证：每个 race test 不含 `time.sleep`，且在 CI 上 100 次重复无 flake。
- **修复风险**：中（需要设计测试架构）
- **严重程度**：高（blocking stop condition 未被评估）

## Open questions

无。平台 capability 不是开放设计选择：能力存在则走 exact contract；能力不存在则按 §8 fail closed/STOP。

## Residual risks

1. fd snapshot 不是跨进程 mutation lock；它保证读取对象稳定并检测同 inode 读取期 drift。read 后的 tree mutation 仍由后续 locked snapshot 拒绝。
   - 分类：`accepted operational behavior`
   - 跟踪：amendment §12 已记录。

2. Windows `dir_fd`/reparse capability 必须由对应 runner 给出事实；当前 Darwin 证据不能代替。
   - 分类：`tracked by S4 stop condition + S5/S6 cross-platform validation`
   - 跟踪：amendment §8 stop condition 2。

3. `O_NONBLOCK` 在 macOS 上对 regular file 的行为差异（见 R001）。
   - 分类：`needs amendment fix`
   - 跟踪：本 review R001。

4. race test determinism 机制（见 R002）。
   - 分类：`needs amendment clarification`
   - 跟踪：本 review R002。

## Architecture boundary review

amendment 的 owner 划分正确：

- `init.py` 拥有 locked workspace identity、mode、fd-relative/no-follow read boundary。
- `config_loader.py` 拥有 JSON parser、overlay、typed profile。
- `init_workspace.py` 拥有 mutation drift、staging、publication、rollback。
- 不在 `ConfigLoader` 接收 locked identity/init mode/no-follow policy（正确，loader 不拥有 init trust boundary）。
- 不在 `init.py` 复制 `json.loads`/overlay/typed profile（正确，loader 拥有 parser）。

## Best-practice review

- fd-relative open 是 POSIX 安全最佳实践，优于 `Path.exists()` + `Path.read_text()` 的 pathname-based read。
- `O_NOFOLLOW` 防止 symlink follow，`O_DIRECTORY` 防止非目录 open，`fstat` 后比对 identity 防止 fd swap——这是 defense-in-depth。
- pre/post descriptor state 比对检测 read 期间同 inode drift——比单一 `fstat` 更可靠。
- bytes snapshot 消除 ConfigLoader 对 workspace path 的依赖——是 clear ownership boundary。

## Optimal-solution review

amendment 是 credible alternatives 中最实际的路径：

- 替代方案 1：只在 `ConfigLoader` 加 `O_NOFOLLOW`。被 amendment §10 S4-AMEND-002 证伪：loader 不拥有 locked root identity。
- 替代方案 2：把 fd read 放在 `init_workspace.py`。被 amendment §2.1 证伪：transaction owner 不拥有首个 model prompt 前的 read boundary。
- 替代方案 3：使用临时文件。被 amendment §2.2 证伪：引入临时文件生命周期、权限、cleanup 与第二次 pathname read glue。
- 替代方案 4：使用 `/dev/fd` 或 `Path.resolve()`。被 amendment §2.2 证伪：不是跨平台、逐层 no-follow 的 owner contract。

amendment 选择的方案（init owner pin/read + loader owner parse/layer/type + config_file_names owner filename）是最小且可演进的。

## Overengineering review

- `ConfigFileNames` typed manifest 不是过度设计。当前 5 个松散常量 (`_MODELS_FILE`, `_EXECUTION_PROFILES_FILE`, ...) 只能按位置猜测；typed manifest 同时提供稳定顺序和语义字段，消除 CLI 重复常量，且不增加新抽象层。
- bytes snapshot API 不是过度设计。它是消除 ConfigLoader 对 workspace path 依赖的最小必要 contract。
- `_read_workspace_execution_profile_snapshot(...)` 不是过度设计。它是 init owner 建立 read boundary 的唯一入口。

## Overcoupling review

amendment 不引入过度耦合：

- `init.py` 只传 `bytes | None` 给 `ConfigLoader`，不传 identity/mode/path policy。
- `ConfigLoader` 只消费 bytes，不感知 init governance。
- `init_workspace.py` 不被修改，mutation drift owner 保持不变。
- 新增 4 个文件（2 production + 2 test）是 boundary 扩展，不是跨层穿透。

## Final plan review conclusion

**pass-with-risks**

该 amendment 关闭了 S2 handoff 与 S4 allowed files 的结构性 gap，owner 划分正确，方案最小且可直接生成代码：

- init owner pin/read（`init.py`）；
- ConfigLoader owner parse/layer/type（`config_loader.py`）；
- `config_file_names()` owner filename（`config_loader.py`）；
- locked snapshot owner mutation drift（`init_workspace.py`，不修改）。

两个 material findings 需要处理：

1. **R002（高）**：race test determinism 机制未指定。§8 stop condition 6 要求"deterministic race tests"，但 §6.2 不指定如何在 Python 中实现 syscall-level race 控制。建议 amendment 增加 §6.2 机制说明（推荐 monkeypatch 方案），或明确评估可行性后调整 stop condition。
2. **R001（中）**：`O_NONBLOCK` 在 macOS 上对 regular file 产生 `EAGAIN`。建议 amendment 修正 §4.2 步骤 5 的 open flags，在 `fstat` 确认 regular file 后不保留 `O_NONBLOCK`。

若这两个 finding 被修复，amendment 可安全交给 implementation agent。不存在需要立即 STOP 的不清晰 owner 或必然 glue。实现若命中 §8 任一条件，必须 STOP，不得以 fallback 或兼容分支继续。
