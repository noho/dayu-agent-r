# WU-CLI-INIT-01 S4 窄范围 Plan Amendment

## Gate metadata

- Work unit：`WU-CLI-INIT-01`
- Slice：`S4 — Managed whole-tree modes 与 repair`
- 类型：accepted plan 的窄范围 code-generation-ready amendment
- Base：`06ea49e071c292d84066ef4ac1c2566e95427c41`
- 生成时间：`2026-07-30T16:16:34+08:00`（来自本机系统时钟）
- plan fix 时间：`2026-07-30T16:31:33+08:00`（来自本机系统时钟）
- Reviewed target：
  `docs/reviews/wu-cli-init-01-plan-codex.md` 的 S4
- 输入 artifacts：
  - `docs/reviews/code-review-20260730-152220.md`
  - `docs/reviews/code-review-20260730-152426.md`
  - `docs/reviews/wu-cli-init-01-s2-code-review-adjudication-controller.md`
  - `docs/reviews/wu-cli-init-01-s2-fix-codex.md`
  - `docs/reviews/code-review-20260730-153912.md`
  - `docs/reviews/code-review-20260730-153933.md`
  - `docs/reviews/wu-cli-init-01-s2-implementation-codex.md`
- Amendment artifact：
  `docs/reviews/wu-cli-init-01-s4-plan-amendment-codex.md`
- accepted plan：
  **不修改** `docs/reviews/wu-cli-init-01-plan-codex.md`
- production / tests：本 gate **不修改**
- commit：本 gate **不创建**

## 1. 结论

结论为 **plan gap 成立，风险真实，S4 可用小而清晰的 owner-aligned 方案修复**。
不需要立即 STOP，但 S4 必须扩展 allowed files；只在原三个文件内实现会迫使代码把
读取补偿塞进 transaction/staging 下游，既无法关闭首个 model prompt 前的读取窗口，
也违反语义 owner 边界。

风险不是“init lock 内几乎不可触发”的纯理论问题：

1. `.dayu-init.lock` 只串行 Dayu init，不约束编辑器、同步程序或其它进程；
2. 当前 `dayu.cli.commands.init._workspace_execution_profile_is_regular_file(...)`
   先 no-follow stat；
3. 随后 `ConfigLoader._load_layered_config_file(...)` 再以
   `Path.exists()` 和 `Path.read_text()` 从可交换 workspace pathname 读取；
4. stat 后把 regular file 换成 symlink，可以越过 S2 的静态 shape 分类；
5. stat 后删除路径会让 loader 静默采用 package layer；原
   `workspace_profile_exists=True` 不会收到异常，因此无法 fail closed；
6. 读取期间对同一 inode 原地写入，可能产生漂移或混合 snapshot。

后续 locked snapshot 重检能阻止 mutation publication，但不能撤销已经发生的
workspace 外部读取，也不能撤销基于错误 minimum 已展示的 model/context prompt。
因此 locked snapshot 不能代替本次 read boundary 的 fd/no-follow snapshot。

严重程度定为 **中**：触发需要并发 mutation，但一旦发生会跨越 workspace 路径安全
边界或改变首个交互步骤采用的业务真值；S4 已明确拥有 path-safety，不能继续 defer。

## 2. Semantic owners

### 2.1 唯一 owner 划分

| 语义 | 唯一 owner | S4 amendment 中的责任 |
|---|---|---|
| 锁内 mode、workspace root identity、首个 model prompt 前的 profile source 选择 | `dayu.cli.commands.init` | PRESERVE 时打开并读取一个稳定、no-follow 的 workspace file descriptor；FIRST/OVERWRITE/RESET 明确选择 package-only |
| workspace 路径安全与读取时点 | `dayu.cli.commands.init` 的 init orchestration boundary | 以 locked `_WorkspaceRootIdentity` 锚定 root，逐层 fd-relative 打开 `config/` 与目标文件；不把可交换 workspace path 交给 loader |
| 当前配置文件名 manifest | `dayu.runtime.config_loader.config_file_names()` | `execution_profiles.json` 名称只从 typed manifest 取得；删除 CLI 重复字面量 |
| JSON decode、严格 JSON 数值规则、workspace/package overlay、schema 与 typed profile | `dayu.runtime.config_loader.ConfigLoader` | 新增只消费 immutable bytes snapshot 的 execution-profile typed load 入口，并复用同一 parser/overlay/typed projection |
| managed-root mutation drift、staging、validation、publication、rollback | `dayu.cli.init_workspace` | 保持现有 `_require_snapshot_unchanged(...)` 为 mutation boundary 真源；不让 read helper承担 publication CAS |

### 2.2 明确禁止的 owner 漂移

- 不在 `dayu.cli.init_workspace` 的 staging 或 validation 结果上反推 model prompt
  应使用的 minimum；该时点太晚。
- 不让 `ConfigLoader` 接收 locked workspace path、root identity、init mode 或
  no-follow policy；这些不是配置解析语义。
- 不在 `dayu.cli.commands.init` 复制 `json.loads`、finite-number parser、
  overlay 或 execution-profile schema。
- 不把 snapshot bytes 写入临时文件后再交给 `ConfigLoader` 路径 API；该做法引入
  临时文件生命周期、权限、cleanup 与第二次 pathname read glue。
- 不使用 `/dev/fd`、`/proc/self/fd`、`Path.resolve()` 后再读或
  `stat -> Path.read_*` 作为替代；它们不是跨平台、逐层 no-follow 的 owner contract。
- 不用 `hasattr/getattr` 猜 loader 或平台行为，不增加 path fallback、package retry
  或 loose parsing。

## 3. S4 allowed files amendment

### 3.1 保留原 S4 allowed files

- `dayu/cli/init_workspace.py`
- `tests/cli/test_init_workspace.py`
- `tests/cli/test_init_smoke.py`

### 3.2 必须新增

- `dayu/cli/commands/init.py`
  - 真实读取入口、locked workspace identity 与 mode owner 在此；
  - 删除 S2 临时静态 stat helper 和重复文件名常量；
  - 实现 fd-relative/no-follow bytes snapshot。
- `tests/cli/test_init_command.py`
  - owner-level symlink/special 与 deterministic syscall-boundary race tests 在此；
  - 证明 loader 只收到 immutable bytes，不再收到 workspace path。
- `dayu/runtime/config_loader.py`
  - JSON parser、overlay、typed profile owner 必须提供 snapshot consumption contract；
  - `config_file_names()` 必须提供可按语义字段访问的唯一 filename manifest。
- `tests/runtime/test_config_loader.py`
  - 证明 path load 与 bytes-snapshot load 复用同一严格 parser/overlay/typed contract；
  - 锁定 typed filename manifest。

### 3.3 本 slice 不新增

- 不新增 `dayu.runtime` 通用 filesystem module。当前只有 init orchestrator 需要
  locked workspace root-aware read；提前抽成跨层 runtime abstraction属于过度设计。
- 不新增 README allowed file。S4 会命中既有 README 检查，但 accepted plan 已由 S6
  统一更新 `dayu/config/README.md` 与 `tests/README.md`；S4 implementation artifact
  只记录“已检查、行为文档由 S6 承接”，不得提前写 future behavior。
- 不修改 `dayu/config/*.json`、Service、Host、Engine 或 public CLI schema。

## 4. Exact contract

### 4.1 Typed filename manifest

在 `dayu.runtime.config_loader` 中把当前五个松散 filename 常量收敛为一个继承
`typing.NamedTuple` 的 immutable、strictly typed `ConfigFileNames` manifest；
字段固定为：

```text
models
execution_profiles
host_runtime
runtime_lanes
tool_discovery
```

`config_file_names() -> ConfigFileNames` 返回该唯一 manifest。`typing.NamedTuple`
保证它仍是 tuple 子类，保留既有 tuple iteration、位置迭代、`in` containment 与
`set(config_file_names())` 行为；不得改用普通 dataclass 或自定义 iterable。因而
`dayu.cli.init_workspace` 仍可按 manifest 顺序遍历，但需要 execution profile
语义名的调用方使用：

```text
config_file_names().execution_profiles
```

内部 `_MODELS_FILE` 等 parser context 也从同一个 manifest 字段派生；不得在 CLI
定义 `_EXECUTION_PROFILES_FILE_NAME`，不得使用位置索引、字符串匹配或重复
`"execution_profiles.json"`。

这不是兼容 wrapper：typed manifest 同时拥有顺序和语义字段，消除当前“tuple 只可按
偶然位置猜测”的缺口。

### 4.2 Init-owned fd/no-follow read

`dayu.cli.commands.init` 新增私有、模块级、严格 typed helper：

```text
_read_workspace_execution_profile_snapshot(
    *,
    workspace_identity: _WorkspaceRootIdentity,
) -> bytes | None
```

返回语义：

- `None`：在 pinned workspace root 下，`config/` 或目标文件于原子 open boundary
  真实不存在；
- `bytes`：只来自一个已打开、已 fstat 为 ordinary regular file、读取前后 state
  未漂移的 descriptor；
- 其它 shape、identity drift、读取 drift 或 capability 缺失：抛
  `CliInitOperationError`；
- 非 shape/capability 的系统 I/O 错误继续以 `OSError` 传播，由现有 CLI 顶层做
  value-free 类型诊断。

固定打开/读取顺序：

1. capability gate：要求 `os.open` 支持 `dir_fd`，并要求平台提供
   `O_NOFOLLOW`、`O_DIRECTORY`；缺失即在任何 workspace profile bytes 被读取前
   fail closed；
2. 以 `O_RDONLY | O_DIRECTORY | O_NOFOLLOW` 打开 locked canonical workspace
   root；
3. `os.fstat(root_fd)` 只与 `_WorkspaceRootIdentity` 的
   `{device, inode, mode}` 完全比较，且 mode 必须为 directory；
   `canonical_path` 只用于步骤 2 的 root open，不参与 fd identity 比较；
4. 仅用相对名 `config` 和 `dir_fd=root_fd` 打开 config directory，flags 同上；
   只有该次 fd-relative `os.open` 抛出的 `FileNotFoundError` 才映射为 `None`；
   symlink、reparse、非目录或其它 shape fail closed；root open/fstat、普通
   `os.fstat`/`os.read` 或其它非 fd-relative open 的 `FileNotFoundError` 不得映射
   为 absent；
5. 从 `config_file_names().execution_profiles` 取得唯一 basename；只用
   `dir_fd=config_fd` 与
   `O_RDONLY | O_NOFOLLOW | O_NONBLOCK` 打开目标，避免 FIFO open 阻塞；
6. 只有该次 final fd-relative `os.open` 抛出的 `FileNotFoundError` 才表示目标真正
   absent 并返回 `None`；symlink/dangling、directory、FIFO/socket/device 等
   special shape 不得归为 absent；
7. open 后第一次 `os.fstat(file_fd)` 必须为 regular file，记录稳定 state：
   `{st_dev, st_ino, st_mode, st_nlink, st_size, st_mtime_ns, st_ctime_ns}`；
   保留 `st_nlink` 与 `st_ctime_ns` 是有意的保守 fail-closed 选择：chmod/chown、
   link-count 或其它 inode metadata drift 即使未改变内容，也要求用户 rerun，不把
   metadata-only 并发当成可忽略事件；
8. `dayu.cli.commands.init` 自有模块级
   `_WORKSPACE_PROFILE_READ_CHUNK_BYTES: Final[int] = 1024 * 1024`；只用
   `os.read(file_fd, _WORKSPACE_PROFILE_READ_CHUNK_BYTES)` 循环读取，不从
   `dayu.cli.init_workspace` import 私有 `_FILE_READ_CHUNK_BYTES`，不得重新打开
   pathname；ordinary regular file 的 `os.read` 返回 bytes，empty/EOF 返回
   `b""` 并结束循环；若已由 `fstat` 证明为 regular file 后仍收到
   `BlockingIOError`，按 `OSError` fail closed 且不重试，不把 `EAGAIN` 改写成 EOF；
9. EOF 后第二次 `os.fstat(file_fd)` 必须与第一次稳定 state 完全相同，否则以
   “workspace execution profile changed while being read; rerun” fail closed；
10. 在所有成功、absent 与异常分支严格按 `file_fd -> config_fd -> root_fd` 逆序
    close，并继续尝试关闭其余已打开 fd：
    - 没有 primary error 时，保留并传播第一个 `os.close` 的 `OSError`；后续 close
      errors 只能作为该第一个 close error 的 notes/chain 记录，不能替换它；
    - 已有 open/fstat/read/identity/shape primary error 时，保留并重新抛出同一个
      primary exception；第一个 secondary close error 通过 exception chaining
      记录，其余 secondary close errors 用 `BaseException.add_note(...)` 记录类型与
      fd role，不能替换 primary；
    - close error diagnostics 只记录 exception type 与 `file/config/root` role，
      不含 path、配置 bytes 或 secret；
11. bytes 一旦返回，即不再读取 workspace profile pathname。文件名在 open 后被
    rename/replace 时，当前解析只消费 pinned descriptor 的 bytes；managed tree 的
    名称/identity/content drift 仍由后续 `_require_snapshot_unchanged(...)` 在
    mutation boundary 拒绝。

不得在 final open 前先 `stat` 决定 shape；shape 真值来自成功 open 后同一 descriptor
的 `fstat`。只有步骤 4/6 明确列出的 fd-relative `os.open` 所抛
`FileNotFoundError` 可在 root identity 已锁定后映射为 `None`。

`O_NONBLOCK` 必须保留用于避免攻击者以 FIFO 占位造成 open 阻塞。Controller 驳回
MiMo R001：当前 Darwin / Python 3.11 的两次实测证明 ordinary regular file 不出现
其声称的 EOF `EAGAIN`。empty/ordinary EOF 行为由第 6 节测试锁定；实现不得删除
`O_NONBLOCK`，也不得为假设性 `EAGAIN` 增加 retry loop。

### 4.3 ConfigLoader snapshot consumption

`ConfigLoader` 新增一个窄 public method：

```text
load_execution_profiles_snapshot(
    *,
    workspace_file_snapshot: bytes | None,
) -> ExecutionProfilesConfig
```

契约：

- 参数必须显式传入；不设隐式默认值；
- `None` 精确表示调用方已建立 workspace file absent，加载 package-only；
- `bytes` 精确表示调用方已 pin 的 workspace overlay；loader 不接收也不构造
  workspace path；
- package root 仍从受信 package config path 读取；
- workspace bytes 使用与 path API 同一个 UTF-8、strict JSON finite-number、
  top-level object、overlay、schema、extends 与 typed profile parser；
- malformed UTF-8、malformed JSON、NaN/Infinity、shape/schema/default-id 错误继续
  抛现有 `ConfigLoadError` family；不得返回 fallback profile；
- 现有 `load_execution_profiles(workspace_config_dir=...)` 保留给普通 runtime
  callers，但 init PRESERVE 不再调用它。

实现时抽取一个唯一的“JSON text/bytes -> `JsonObject`”私有 parser helper和一个唯一的
“execution profile root -> `ExecutionProfilesConfig`”私有 typed projection helper；
path API 与 snapshot API 都复用它们。禁止复制 `json.loads` 参数、overlay 或 typed
字段校验。

### 4.4 `_load_target_min_context_window(...)`

将入参从裸 `workspace_root: Path` 收窄为 locked
`workspace_identity: _WorkspaceRootIdentity`，避免安全 helper重新从 path 猜 owner
identity。

固定行为：

- FIRST / OVERWRITE / confirmed RESET：
  `workspace_file_snapshot=None`，不触碰 workspace config path；
- PRESERVE：
  调用 `_read_workspace_execution_profile_snapshot(...)` 恰好一次；
- 随后调用同一个 `ConfigLoader(...).load_execution_profiles_snapshot(...)`
  恰好一次；
- workspace bytes 存在且 parser/typed validation 失败时，保持现有 value-free
  `--overwrite` 诊断；
- bytes absent 时 package 失败，保持 repair/reinstall 诊断；
- 不调用旧 `load_execution_profiles(workspace_config_dir=<workspace>)`，不以
  package-only 重试，不读取第二次 workspace path；
- typed default profile 与 `min_context_window_tokens` 的 owner/下传保持 S2 已接受
  contract，不改变交互 oracle。

删除：

- `_EXECUTION_PROFILES_FILE_NAME`
- `_workspace_execution_profile_is_regular_file(...)`
- `workspace_profile_exists` 的 stat-derived 判定

## 5. Race semantics

| Race | 本次 read owner 的结果 | 后续 snapshot owner 的结果 |
|---|---|---|
| locked snapshot 后、final open 前 regular -> symlink/special | `O_NOFOLLOW` 或 open 后 `fstat` fail closed；不读 target | 不需要依赖后续检查保证不 follow |
| final file open 后 pathname 被 rename/换成 symlink或另一 regular file | 从原 descriptor 读取 pinned inode；不读新 pathname | mutation boundary snapshot 比较拒绝 publication |
| config directory open 后 pathname 被换成 symlink/另一目录 | file open 相对 pinned `config_fd`；不穿越新 pathname | mutation boundary snapshot 比较拒绝 publication |
| read 期间同一 inode 原地写入 | pre/post descriptor state 不等，read fail closed；不进 parser | 不依赖后续检查 |
| read 完成后、parse 前 pathname swap | parser 只消费 immutable bytes | mutation boundary snapshot 比较拒绝 publication |
| 目标在 fd-relative open 时真实 absent | 返回 `None`，package-only | 若相对 locked snapshot 发生 drift，mutation boundary 拒绝 publication |
| root identity 在 root open 前漂移 | root fd identity 与 locked identity 不同，fail closed | 不进入后续交互 |

该契约不声称阻止其它进程 mutation，也不引入文件锁/CAS；它只保证本次读取不 follow
可交换 pathname、不会把多个 inode/版本拼成一个未检测 snapshot，并把 mutation
publication 的最终裁决继续留给 locked snapshot owner。

## 6. Exact tests

### 6.1 `tests/runtime/test_config_loader.py`

新增/更新 owner-level contract tests：

1. `config_file_names()` 返回 `typing.NamedTuple` typed manifest，五个语义字段与
   迭代顺序唯一；既有 tuple iteration、`in` containment 和 `set(...)` 消费保持，
   CLI 不再需要重复 filename literal。
2. `load_execution_profiles_snapshot(workspace_file_snapshot=None)` 与 package-only
   path load 返回相同 typed view。
3. 有效 workspace bytes 按现有 execution-profile map/non-map overlay 规则产生相同
   typed view。
4. malformed UTF-8、malformed JSON、NaN/Infinity、非 object、schema invalid、
   default id missing 全部抛对应 `ConfigLoadError`，不得回退 package。
5. path API 与 snapshot API 共用 parser/typed projection 的行为矩阵；测试不复制
   production parser。

### 6.2 `tests/cli/test_init_command.py`

更新现有 S2 tests，并新增 deterministic barriers；禁止使用 `sleep` 猜 race。

所有 race test 使用同一个可审查机制：

- 用 pytest `monkeypatch` 包装 `dayu.cli.commands.init` 实际调用到的
  `os.open`、`os.read`、`os.fstat` 和
  `ConfigLoader.load_execution_profiles_snapshot(...)`；close fault test 另包装
  `os.close`；
- wrapper 必须先保存 original syscall/method，并在指定 boundary **delegate**
  original；不得伪造成功 fd、bytes、stat result 或 typed config；
- 用 `threading.Event` 或 `threading.Barrier` 在 wrapper 与测试 mutation thread
  之间建立 happens-before：wrapper 到达 boundary 后发 signal，mutation 完成后再
  release wrapper；
- 每个 test 都必须有 bounded join/wait failure assertion，防止测试挂死；timeout
  只用于判定测试失败，不用于制造 race；
- 禁止 `time.sleep`、概率重复、依赖 scheduler 运气或“循环 100 次未失败”作为证据。

各 race 的具体注入点必须固定如下：

1. 四态 loader-source test：
   - FIRST/OVERWRITE/RESET 明确传 `None`；
   - PRESERVE present 传 exact bytes；
   - old path-based `load_execution_profiles(...)` 设置为 forbidden call；
   - snapshot method 和 `_select_model` 各只调用一次。
2. 现有 symlink、dangling、directory、FIFO matrix 改为攻击新的 final
   `open/fstat` boundary；仍断言 loader/model/secret/transaction/publication 未发生，
   外部 target 未读取/修改，诊断 value-free。
3. config directory symlink/reparse/special 与 final file symlink/special 分别覆盖，
   证明不是只保护最后一个 path component。
4. **stat/open swap**：包装 final fd-relative `os.open`，在 delegate original
   之前用 Event/Barrier 暂停；mutation thread 把 pathname 从旧静态可见的 regular
   换成指向外部 secret 的 symlink后释放 wrapper。新实现没有 pre-stat acceptance，
   original `os.open(..., O_NOFOLLOW, dir_fd=config_fd)` fail closed，external secret
   不进入 bytes/diagnostic。
5. **open/read file-name swap**：`os.open` wrapper 先 delegate original并拿到真实
   final fd，再 signal mutation；第一次 `os.read` wrapper 等待 mutation 完成后才
   delegate original。mutation thread 把原名 rename 并放入外部 symlink或另一
   regular file；snapshot bytes 必须来自原 fd，不得来自新 pathname。
6. **directory swap**：config-directory `os.open` wrapper 先 delegate original并
   拿到真实 `config_fd`，随后 signal mutation；final-file `os.open` wrapper 等待
   public `config` 名被换成 symlink/另一目录后，仍以 pinned `config_fd` delegate
   original。随后 transaction snapshot drift 阻止 mutation。
7. **read/in-place-write race**：用大于一个 read chunk 的 fixture，在首个 chunk 后
   由 `os.read` wrapper 先 delegate original取得真实首 chunk，再 signal writer；
   final `os.fstat` wrapper 等待 writer 完成后 delegate original。修改同一 inode后
   pre/post state 漂移必须 fail closed，ConfigLoader 未调用；另分别让
   `st_nlink`/`st_ctime_ns` 漂移，锁定 metadata/link drift 也要求 rerun 的有意保守
   contract。
8. **read/parse swap**：bytes read 完成后、调用 ConfigLoader 前换掉 public path；
   EOF `os.read` wrapper delegate original并 signal mutation；
   `ConfigLoader.load_execution_profiles_snapshot` wrapper 等待 mutation 完成后再
   delegate original method。loader 收到 exact immutable bytes，不读取新文件；随后真实
   `prepare_workspace_transaction` 以 locked snapshot drift 拒绝 publication。
9. capability gate：模拟缺少 fd-relative/no-follow 能力，PRESERVE 在任何
   loader/model/secret/transaction 前给出 value-free actionable failure；不得调用
   path fallback。FIRST/OVERWRITE/RESET 仍是 package-only。
10. ordinary/empty/EOF matrix：
    - non-empty ordinary file 在含 `O_NONBLOCK` 的真实 fd 上首个 `os.read` 返回
      exact bytes，下一次返回 `b""`；
    - empty ordinary file 第一次 `os.read` 返回 `b""`；
    - `os.read` wrapper 在真实 `fstat` 已确认 regular 后注入一次
      `BlockingIOError`，断言其作为 `OSError` fail closed、不重试、loader未调用；
      该 fault injection 不推翻本机真实 syscall evidence。
11. absent/error mapping：
    - config/final 两个 fd-relative `os.open` 的真实 `FileNotFoundError` 各自映射
      `None`；
    - root open、root/file `os.fstat`、`os.read` 的 `FileNotFoundError` 均传播，
      不得静默 package fallback；
    - root `fstat` 只比较 dev/inode/mode；canonical path 不参与 fd identity。
12. 所有新 helper 的 fd close 正常/异常矩阵覆盖 root/config/file 三层和严格逆序：
    - 无 primary error + 多个 `os.close` wrapper 注入失败时，继续尝试全部 close，
      最终传播第一个 close `OSError`；
    - primary read/open error + secondary close errors 时，重新抛同一 primary
      exception，第一个 close error在 chain、其余在 notes，均不替换 primary；
    - 断言无 descriptor leak，notes/diagnostic只含 exception type 与 fd role。

### 6.3 `tests/cli/test_init_workspace.py`

保留 accepted S4 原测试矩阵，并明确加入两条 ownership assertion：

1. read 成功后 public config 发生 name/identity/content drift 时，
   `_require_snapshot_unchanged(...)` 仍是 mutation 前最终拒绝 owner；
2. transaction/staging 不重新实现或调用 execution-profile fd reader，不从 earlier
   prompt minimum 反推当前 tree truth。

### 6.4 `tests/cli/test_init_smoke.py`

保留 accepted S4 process/rollback smoke；只增加稳定、无 timing guess 的集成断言：

- PRESERVE 正常 ordinary profile 走真实 fd snapshot -> ConfigLoader typed parse ->
  model selection -> transaction validation；
- swap 已由 command owner deterministic unit tests穷举，smoke 不新增基于
  `sleep` 的 flaky race；
- 缺 capability 的 subprocess 明确 fail closed 且 workspace digest 不变。

### 6.5 静态残留检查

```text
rg -n '_EXECUTION_PROFILES_FILE_NAME|_workspace_execution_profile_is_regular_file' \
  dayu/cli/commands/init.py tests/cli/test_init_command.py
```

预期无命中。`execution_profiles.json` 的业务测试 fixture 可保留字面量，但 production
filename owner 只能在 `dayu.runtime.config_loader` 的 typed manifest 中出现一次。

## 7. Validation

实现后按以下顺序验证：

```text
source .venv/bin/activate

pytest tests/runtime/test_config_loader.py \
  tests/cli/test_init_command.py \
  tests/cli/test_init_workspace.py \
  tests/cli/test_init_smoke.py -q

coverage erase
coverage run -m pytest tests/runtime/test_config_loader.py \
  tests/cli/test_init_command.py \
  tests/cli/test_init_workspace.py \
  tests/cli/test_init_smoke.py -q
coverage report \
  --include='dayu/runtime/config_loader.py,dayu/cli/commands/init.py,dayu/cli/init_workspace.py'

python -m pyright dayu/runtime/config_loader.py \
  dayu/cli/commands/init.py dayu/cli/init_workspace.py \
  tests/runtime/test_config_loader.py tests/cli/test_init_command.py \
  tests/cli/test_init_workspace.py tests/cli/test_init_smoke.py

python -m ruff check dayu/runtime/config_loader.py \
  dayu/cli/commands/init.py dayu/cli/init_workspace.py \
  tests/runtime/test_config_loader.py tests/cli/test_init_command.py \
  tests/cli/test_init_workspace.py tests/cli/test_init_smoke.py

git diff --check
```

验收条件：

- focused tests 全绿；
- 三个修改生产文件各自 coverage `>= 80%`；
- pyright `0 errors`，无新增/扩散；
- ruff 与 diff check 通过；
- 真实 Windows runner 若不具备本 contract 所需 fd-relative/no-follow capability，
  必须得到预期 fail-closed verdict；不得把静态 monkeypatch 当成平台支持证据；
- S4 原 whole-tree/repair/cleanup/rollback completion signal 继续全部满足。

本 plan amendment gate 只改文档，因此不运行 production/test suite；只执行 artifact
完整性、`git diff --check` 与工作区范围核对。

## 8. Stop conditions

以下任一条件成立，S4 implementation 必须 **STOP 并回到 plan review**：

1. required platform 无法用 Python 3.11 提供 root-identity-checked、
   fd-relative、逐层 no-follow open；不得降级为 absolute path read、pre-stat +
   path read、`resolve()`、临时文件或 `/dev/fd`。
2. 产品要求该平台的 PRESERVE 必须成功，而该平台只能通过新的 native handle/Win32
   binding 实现完整契约；该 native capability 是独立设计范围，不能在 S4 临时加入
   ctypes/glue。
3. `ConfigLoader` 无法在不复制 JSON parser/typed projection 的情况下消费 bytes
   snapshot；不得把 parser 移到 CLI。
4. 实现需要把 locked identity、init mode、workspace path policy传入
   `ConfigLoader`；说明 owner boundary 设计失败。
5. 需要新增第二个 transaction mutation helper、改变 snapshot owner 或让 staging
   修复 earlier read semantics。
6. pre/post descriptor state 无法稳定表达或 deterministic race tests 只能依赖
   timing/sleep。
7. 任一 symlink/special/race case读取外部 target、静默 package fallback、继续
   model/secret prompt 或产生 transaction/publication。
8. filename 统一只能靠位置 magic、字符串扫描、重复 literal 或 compatibility
   wrapper 完成。

当前本机直接 capability evidence：

```text
platform.system() == "Darwin"
hasattr(os, "O_NOFOLLOW") == True
hasattr(os, "O_DIRECTORY") == True
os.open in os.supports_dir_fd == True
os.stat in os.supports_dir_fd == True
os.stat in os.supports_follow_symlinks == True
```

### 8.1 Darwin / Python 3.11 `O_NONBLOCK` 实测

以下两条命令在当前项目 `.venv` 实际执行，不是文档推断。

非空 ordinary regular file：

```text
source .venv/bin/activate
python -c 'import os, tempfile; f = tempfile.NamedTemporaryFile(); f.write(b"profile-bytes"); f.flush(); fd = os.open(f.name, os.O_RDONLY | os.O_NONBLOCK); print(repr(os.read(fd, 4096))); os.close(fd); f.close()'
```

结果：

```text
b'profile-bytes'
```

空 ordinary regular file：

```text
source .venv/bin/activate
python -c 'import os, tempfile; f = tempfile.NamedTemporaryFile(); fd = os.open(f.name, os.O_RDONLY | os.O_NONBLOCK); print(repr(os.read(fd, 4096))); os.close(fd); f.close()'
```

结果：

```text
b''
```

因此 MiMo R001 的 Darwin `EAGAIN` 前提被本机直接证据否定。S4 保留
`O_NONBLOCK` 防 FIFO open 阻塞，并以第 6.2 节 ordinary/empty/EOF tests 锁定真实
行为。若 production 在 regular-file `fstat` 后仍收到 `BlockingIOError`，按既有
`OSError` boundary fail closed 且不重试。

该证据只证明当前 Darwin implementation path 可行，不替代真实 Windows/Linux
验收；production 实现不得使用上述 `hasattr` 作为语义 fallback。

## 9. Assumptions tested

| Assumption | 证据与结论 |
|---|---|
| init lock 排除外部 mutation | 被证伪；file lock 只约束配合同一 lock 的进程 |
| S4 原 allowed files 能关闭 gap | 被证伪；首个读取入口和测试不在白名单 |
| 静态 no-follow stat 足够 | 被证伪；后续 loader重新按 pathname exists/read |
| locked snapshot 能替代 stable read | 被证伪；它只能阻止后续 mutation，不能撤销 read/prompt |
| 可以不改 ConfigLoader | 被证伪；否则只能复制 parser或制造临时 pathname glue |
| ConfigLoader 应拥有 no-follow path open | 被证伪；loader不知道 locked root identity/mode，不能建立 init trust boundary |
| fd snapshot 会夺走 mutation drift owner | 被证伪；read consistency 与 publication drift 是两个顺序明确、不可互相替代的 contract |
| filename 只能继续重复 literal | 被证伪；typed `config_file_names()` manifest 可同时提供稳定顺序与语义字段 |

## 10. Plan review findings

### S4-AMEND-001-已收敛-[高]-S4 白名单排除了真实 read owner

- **位置**：accepted plan S4 `allowed files` 与 S2 residual handoff
- **问题类型**：范围漂移 / 架构边界 / 不可直接实施
- **当前写法**：S2 把完整 stat→read TOCTOU 交给 S4，但 S4 只允许 transaction 与
  workspace tests。
- **反例/失败场景**：implementation agent 只能在 staging 下游补救，首个 model
  prompt 仍从可交换 path 读取。
- **直接证据**：
  `dayu/cli/commands/init.py::_load_target_min_context_window(...)` 与
  `dayu/runtime/config_loader.py::_load_layered_config_file(...)`。
- **影响**：读取外部 target、错误 package fallback、owner 漂移或被迫越权改文件。
- **建议改法和验证点**：按第 3 节扩展四个文件，并实施第 4—7 节 contract。
- **修复风险**：中
- **严重程度**：高（plan code-generation readiness）
- **状态**：本 amendment 已收敛。

### S4-AMEND-002-已收敛-[中]-若只在 ConfigLoader 加 O_NOFOLLOW 会把 trust boundary 放错层

- **位置**：ConfigLoader 与 init orchestration boundary
- **问题类型**：架构边界 / 过度耦合 / 非最优方案
- **当前写法**：S2 artifact笼统写“需要 ConfigLoader fd/no-follow read contract”。
- **反例/失败场景**：loader只有 workspace config dir，不拥有 locked root identity；
  只保护最终文件仍可能沿被替换的 parent symlink读取 workspace 外部内容。
- **直接证据**：当前 loader API 只接收 `workspace_config_dir`，init command 独占
  `_WorkspaceRootIdentity` 与 locked mode。
- **影响**：伪 no-follow、跨层泄漏 init governance、其它 loader callers 被迫承担
  init-only policy。
- **建议改法和验证点**：init打开/pin/read，loader只消费 bytes并拥有 parser。
- **修复风险**：低
- **严重程度**：中
- **状态**：本 amendment 已收敛。

## 11. Open questions

无 owner 未决项。

平台 capability 不是开放设计选择：能力存在则走 exact contract；能力不存在则按
第 8 节 fail closed/STOP。若后续明确要求在缺少 `dir_fd` 的 Windows Python 上支持
PRESERVE success，必须新开 native handle design，不能由 implementation agent自由
选择 workaround。

## 12. Residual risks

1. fd snapshot 不是跨进程 mutation lock；它保证读取对象稳定并检测同 inode读取期
   drift。read 后的 tree mutation仍由后续 locked snapshot拒绝，用户可能需要重新
   执行 init。分类：`accepted operational behavior`。
2. package config 仍走既有受信 package path API；本 amendment 不把 package install
   mutation纳入 workspace TOCTOU。分类：`out of scope`，不影响本 finding closure。
3. 真实 Windows `dir_fd`/reparse capability 必须由对应 runner给出事实；当前 Darwin
   证据不能代替。分类：`tracked by S4 stop condition + S5/S6 cross-platform validation`。
4. 配置文件大小仍沿用现有 unbounded config read contract；本 amendment 不顺带新增
   size schema。分类：`not introduced by amendment`。
5. `st_nlink` / `st_ctime_ns` 的 metadata-only drift 也触发 rerun，可能对并发
   chmod/chown/link 操作产生保守误报；这是防止读取期间 inode 事实变化被忽略的有意
   fail-closed tradeoff。分类：`accepted conservative behavior`。

## 13. Plan-fix 摘要

- review inputs：
  - `docs/reviews/wu-cli-init-01-s4-plan-amendment-review-mimo.md`
  - `docs/reviews/wu-cli-init-01-s4-plan-amendment-review-ds.md`
- Controller accepted MiMo R002：已在 §6.2 固定 pytest monkeypatch +
  `threading.Event`/`threading.Barrier` 机制、每个 race 的 exact wrapper boundary、
  original syscall/method delegation、bounded wait 与禁止 sleep/概率重复。
- Controller rejected MiMo R001：保留 `O_NONBLOCK`；§8.1 记录两次当前
  Darwin/Python 3.11 实测命令与 exact result；§4.2/§6.2 冻结 empty/ordinary EOF
  与 unexpected `BlockingIOError` fail-closed/no-retry contract。
- DS-001：采用 reviewer 给出的保守选项；明确 `st_nlink`/`st_ctime_ns` drift 也
  rerun，并记录误报 tradeoff。
- DS-002：明确 read helper 自有
  `_WORKSPACE_PROFILE_READ_CHUNK_BYTES`，不跨模块 import transaction 私有常量。
- DS-003：明确 file/config/root 逆序 close、无 primary 时 first-close-error、
  有 primary 时 primary-preserving chain/notes，并补两类 tests。
- DS-004：明确 `ConfigFileNames` 使用 `typing.NamedTuple`，保持 tuple iteration、
  containment 与 set conversion。
- DS OQ-001/OQ-002：明确只有 config/final fd-relative `os.open` 的
  `FileNotFoundError` 映射 absent；root fd 只比较 dev/inode/mode，canonical path
  不参与 identity。
- reviewer artifacts、accepted plan、production 与 tests 均未修改；本 plan-fix
  只更新当前 amendment artifact。

Plan-fix decision：`pass`。无新增 open question；原 §8 stop conditions 保持。

## 14. Final plan review conclusion

**pass**

该 amendment 关闭了 S2 handoff 与 S4 allowed files 的结构性 gap，owner 清晰，方案
最小且可直接生成代码：

- init owner pin/read；
- ConfigLoader owner parse/layer/type；
- `config_file_names()` owner filename；
- locked snapshot owner mutation drift。

不存在需要当前立即 STOP 的不清晰 owner或必然 glue。实现若命中第 8 节任一条件，
必须 STOP，不得以 fallback 或兼容分支继续。
