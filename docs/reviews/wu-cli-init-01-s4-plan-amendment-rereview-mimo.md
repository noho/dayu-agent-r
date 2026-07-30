# WU-CLI-INIT-01 S4 Plan Amendment — Rereview (MiMo)

## Gate metadata

- Review target：`docs/reviews/wu-cli-init-01-s4-plan-amendment-codex.md`（plan-fix 后版本）
- Reviewer：AgentMiMo（独立 adversarial reviewer）
- 日期：2026-07-30T16:34:37+08:00（来自本机系统时钟）
- Artifact path：`docs/reviews/wu-cli-init-01-s4-plan-amendment-rereview-mimo.md`
- 审查范围：Controller adjudication 后更新内容与原 findings R001/R002 的 closure；
  NamedTuple、chunk constant、close precedence、metadata drift、absent/root identity。

## Rereview inputs

- 原 review：`docs/reviews/wu-cli-init-01-s4-plan-amendment-review-mimo.md`
- DS review：`docs/reviews/wu-cli-init-01-s4-plan-amendment-review-ds.md`
- 更新后 amendment：`docs/reviews/wu-cli-init-01-s4-plan-amendment-codex.md`（plan-fix 时间 2026-07-30T16:31:33）
- 真实代码：`dayu/cli/commands/init.py`、`dayu/runtime/config_loader.py`、`dayu/cli/init_workspace.py`
- 本机 Darwin syscall 实测

## 1. R001 re-evaluation：O_NONBLOCK on Darwin

### 原 finding

MiMo R001 声称 macOS 上 `O_NONBLOCK` 对 regular file 的 `os.read()` 在无数据可读时返回 `EAGAIN`，severity 中。

### Controller adjudication

Controller rejected R001。§8.1 记录了两次当前 Darwin/Python 3.11 实测命令与 exact result。§4.2/§6.2 冻结 empty/ordinary EOF 与 unexpected `BlockingIOError` fail-closed/no-retry contract。

### 本机独立验证

Reviewer 在当前 Darwin/Python 3.11 环境独立执行以下实测：

| Test | 操作 | 结果 |
|---|---|---|
| non-empty regular file | `os.open(f.name, O_RDONLY \| O_NONBLOCK)` → `os.read(fd, 4096)` | `b'profile-bytes'` ✓ |
| empty regular file | `os.open(f.name, O_RDONLY \| O_NONBLOCK)` → `os.read(fd, 4096)` | `b''` ✓ |
| read after EOF | non-empty file read all → second `os.read` | `b''` ✓ |
| fstat on O_NONBLOCK fd | `os.fstat(fd)` after open with O_NONBLOCK | `S_ISREG=True`, all fields populated ✓ |

**结论**：R001 的前提（Darwin 上 `O_NONBLOCK` 对 regular file 产生 `EAGAIN`）被本机直接证据否定。Darwin/Python 3.11 的 `os.read` 对 ordinary regular file（无论 empty 还是非 empty）在 `O_NONBLOCK` 下正常返回 bytes 或 `b""`，不产生 `BlockingIOError`。

amendment §4.2 步骤 8 的补充条款"若已由 fstat 证明为 regular file 后仍收到 `BlockingIOError`，按 `OSError` fail closed 且不重试"是合理的 defense-in-depth，不引入 retry loop，不改变正常行为。

**R001 status：已关闭。** Controller rejection 正确。

## 2. R002 re-evaluation：race test determinism

### 原 finding

MiMo R002 声称 §6.2 要求 10 个 deterministic race test 但不指定实现机制，severity 高。

### Controller adjudication

Controller accepted R002。§6.2 已更新，固定了 pytest monkeypatch + `threading.Event`/`threading.Barrier` 机制。

### 更新后 §6.2 核查

更新后 §6.2 包含以下 code-generation-ready 规格：

1. **机制**：pytest `monkeypatch` 包装 `dayu.cli.commands.init` 实际调用到的 `os.open`、`os.read`、`os.fstat` 和 `ConfigLoader.load_execution_profiles_snapshot(...)`。close fault test 另包装 `os.close`。
2. **delegation**：wrapper 必须先保存 original syscall/method，并在指定 boundary delegate original；不得伪造成功 fd、bytes、stat result 或 typed config。
3. **synchronization**：用 `threading.Event` 或 `threading.Barrier` 在 wrapper 与测试 mutation thread 之间建立 happens-before。
4. **bounded wait**：每个 test 都必须有 bounded join/wait failure assertion，防止测试挂死；timeout 只用于判定测试失败，不用于制造 race。
5. **prohibition**：禁止 `time.sleep`、概率重复、依赖 scheduler 运气或"循环 100 次未失败"作为证据。

**各 race 的 exact wrapper boundary**：

| Race | Wrapper boundary | Mutation action |
|---|---|---|
| stat/open swap (test 4) | final `os.open` wrapper 在 delegate original 前暂停 | mutation thread 把 pathname 换成 symlink 后释放 |
| open/read file-name swap (test 5) | `os.open` wrapper 先 delegate 并拿 fd，再 signal；`os.read` wrapper 等待 mutation 完成 | mutation thread rename 原名并放入 symlink |
| directory swap (test 6) | config-directory `os.open` wrapper 先 delegate 并拿 config_fd，再 signal；final-file `os.open` wrapper 等待 | mutation thread 把 public config 名换成 symlink |
| read/in-place-write race (test 7) | `os.read` wrapper 先 delegate 取首 chunk，再 signal writer；final `os.fstat` wrapper 等待 writer 完成 | mutation thread 修改同一 inode |
| read/parse swap (test 8) | EOF `os.read` wrapper delegate 并 signal；`ConfigLoader.load_execution_profiles_snapshot` wrapper 等待 mutation 完成 | mutation thread 换掉 public path |

**结论**：§6.2 现在是 code-generation-ready。每个 race test 有明确的 wrapper 注入点、synchronization 机制和 delegation 要求。implementation agent 可以直接按规格编写测试，不需要自行设计测试架构。

**R002 status：已关闭。** Controller acceptance + plan-fix 正确。

## 3. 其它规格项核查

### 3.1 NamedTuple

**amendment §4.1**："继承 `typing.NamedTuple` 的 immutable、strictly typed `ConfigFileNames` manifest"。

**本机验证**：

```python
from typing import NamedTuple
class ConfigFileNames(NamedTuple):
    models: str
    execution_profiles: str
    host_runtime: str
    runtime_lanes: str
    tool_discovery: str
```

| Property | 结果 |
|---|---|
| `isinstance(names, tuple)` | `True` ✓ |
| `for n in names` | 5 个文件名按定义顺序 ✓ |
| `"models.json" in names` | `True` ✓ |
| `set(names)` | 5 个文件名集合 ✓ |
| `names[0]` | `"models.json"` ✓ |
| `names.execution_profiles` | `"execution_profiles.json"` ✓ |

**结论**：`typing.NamedTuple` 是既有 `tuple[str, ...]` 的自然 typed 升级，保持所有既有 tuple 语义（iteration、containment、set conversion、positional access），同时新增语义字段访问。不是兼容 wrapper。规格充分。

### 3.2 Chunk constant

**amendment §4.2 步骤 8**："`dayu.cli.commands.init` 自有模块级 `_WORKSPACE_PROFILE_READ_CHUNK_BYTES: Final[int] = 1024 * 1024`；只用 `os.read(file_fd, _WORKSPACE_PROFILE_READ_CHUNK_BYTES)` 循环读取，不从 `dayu.cli.init_workspace` import 私有 `_FILE_READ_CHUNK_BYTES`"。

**核查**：当前 `init_workspace.py` 第 52 行定义 `_FILE_READ_CHUNK_BYTES: Final[int] = 1024 * 1024`。amendment 明确要求 `init.py` 自有独立常量，不跨模块 import transaction 私有常量。DS-002 采纳。

**结论**：规格清晰，owner 边界正确。

### 3.3 Close precedence

**amendment §4.2 步骤 10**："在所有成功、absent 与异常分支严格按 `file_fd -> config_fd -> root_fd` 逆序 close，并继续尝试关闭其余已打开 fd"。

子条款：
- 没有 primary error 时，保留并传播第一个 `os.close` 的 `OSError`
- 已有 primary error 时，保留并重新抛出同一 primary exception；第一个 secondary close error 通过 exception chaining 记录，其余用 `BaseException.add_note(...)` 记录
- close error diagnostics 只记录 exception type 与 fd role，不含 path、配置 bytes 或 secret

**结论**：规格完整。逆序 close、primary error preservation、secondary error 记录方式均有明确 contract。DS-003 采纳。

### 3.4 Metadata drift

**amendment §4.2 步骤 7**："记录稳定 state：`{st_dev, st_ino, st_mode, st_nlink, st_size, st_mtime_ns, st_ctime_ns}`；保留 `st_nlink` 与 `st_ctime_ns` 是有意的保守 fail-closed 选择：chmod/chown、link-count 或其它 inode metadata drift 即使未改变内容，也要求用户 rerun"。

**本机验证**：`os.fstat(fd)` 在 Darwin 上返回完整的 `st_dev`、`st_ino`、`st_mode`、`st_nlink`、`st_size`、`st_mtime_ns`、`st_ctime_ns` 字段。

**amendment §6.2 测试 7**："另分别让 `st_nlink`/`st_ctime_ns` 漂移，锁定 metadata/link drift 也要求 rerun 的有意保守 contract"。

**结论**：metadata drift 的保守 tradeoff 已在 amendment §12 residual risks 第 5 项记录为 `accepted conservative behavior`。规格清晰。

### 3.5 Absent / root identity

**amendment §4.2 步骤 4**："只有该次 fd-relative `os.open` 抛出的 `FileNotFoundError` 才映射为 `None`"。

**amendment §4.2 步骤 6**："只有该次 final fd-relative `os.open` 抛出的 `FileNotFoundError` 才表示目标真正 absent 并返回 `None`"。

**amendment §4.2 步骤 3**："`os.fstat(root_fd)` 只与 `_WorkspaceRootIdentity` 的 `{device, inode, mode}` 完全比较，且 mode 必须为 directory；`canonical_path` 只用于步骤 2 的 root open，不参与 fd identity 比较"。

**amendment §6.2 测试 11**：
- config/final 两个 fd-relative `os.open` 的真实 `FileNotFoundError` 各自映射 `None`
- root open、root/file `os.fstat`、`os.read` 的 `FileNotFoundError` 均传播，不得静默 package fallback
- root `fstat` 只比较 dev/inode/mode；canonical path 不参与 fd identity

**结论**：absent 映射边界清晰——只有 config dir 和 final file 的 fd-relative `FileNotFoundError` 映射 `None`。root identity 只比较 dev/inode/mode，canonical path 不参与。DS OQ-001/OQ-002 采纳。

## 4. 新 material findings 检查

逐项检查 updated amendment 是否引入新的 material issue：

| 检查项 | 结论 |
|---|---|
| owner 边界是否因 plan-fix 改变 | 否。init/pin/read、loader/parse/layer/type、transaction/mutation-drift 不变。 |
| `O_NONBLOCK` 保留是否引入新风险 | 否。Darwin 实测证明 regular file 不产生 `EAGAIN`；§4.2 步骤 8 的 `BlockingIOError` defense-in-depth 不引入 retry loop。 |
| monkeypatch 机制是否引入过度耦合 | 否。monkeypatch 只在 test 中使用，不影响 production code。wrapper 必须 delegate original，不得伪造。 |
| NamedTuple 是否引入兼容性问题 | 否。`typing.NamedTuple` 是 `tuple` 子类，所有既有 tuple 语义保持。 |
| close error 处理是否过度复杂 | 否。逆序 close + primary-preserving chain/notes 是 POSIX fd 管理最佳实践，规格清晰。 |
| metadata drift 保守性是否过度 | 可接受。`st_nlink`/`st_ctime_ns` drift 触发 rerun 是有意 fail-closed tradeoff，已在 §12 记录。 |

**无新增 material finding。**

## 5. Residual risks

1. Windows `dir_fd`/reparse capability 必须由对应 runner 给出事实。
   - 分类：`tracked by S4 stop condition + S5/S6 cross-platform validation`

2. `st_nlink`/`st_ctime_ns` metadata-only drift 保守误报。
   - 分类：`accepted conservative behavior`

3. 配置文件大小仍沿用现有 unbounded config read contract。
   - 分类：`not introduced by amendment`

## 6. Final rereview conclusion

**PASS**

R001 和 R002 均已关闭：

- **R001**：Controller rejection 正确。本机 Darwin/Python 3.11 独立实测证明 `O_NONBLOCK` 对 ordinary regular file（empty 和 non-empty）不产生 `EAGAIN`。amendment §8.1 的实测证据有效，§4.2 步骤 8 的 `BlockingIOError` defense-in-depth 合理。
- **R002**：Controller acceptance + plan-fix 正确。§6.2 现在指定了 pytest monkeypatch + `threading.Event`/`threading.Barrier` 机制、每个 race 的 exact wrapper boundary、original syscall delegation、bounded wait 与禁止 sleep。code-generation-ready。

其它规格项（NamedTuple、chunk constant、close precedence、metadata drift、absent/root identity）均有明确 contract，无新增 material finding。

该 amendment 可安全交给 implementation agent。
