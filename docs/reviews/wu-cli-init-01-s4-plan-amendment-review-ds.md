# WU-CLI-INIT-01 S4 Plan Amendment — Adversarial Review (DS)

## Gate metadata

- Type: plan review
- Role: independent adversarial reviewer (DS 路)
- 日期: 2026-07-30T16:26:08+08:00
- Reviewed target: `docs/reviews/wu-cli-init-01-s4-plan-amendment-codex.md`
- Base commit: `06ea49e071c292d84066ef4ac1c2566e95427c41`
- Author: Codex (plan amendment)
- Reviewer: AgentDS (this review)
- Review artifact: `docs/reviews/wu-cli-init-01-s4-plan-amendment-review-ds.md`
- MiMo review: intentionally not consulted (DS-independent pass per /planreview instruction)

## Executive summary

本 plan amendment 以 owner-aligned、最小侵入的方式关闭了 S2 handoff 中明确 defer 到 S4 的完整 TOCTOU gap。risk motivation 真实、owner 划分正确、方案可 code-generation-ready。

四个低严重度 finding 均为规格化微调，不构成 stop condition。三个 open question 为 impl-level 澄清。

结论：**PASS**。

---

## 1. Assumptions tested

| Assumption | 来源 | 测试结论 |
|---|---|---|
| stat→read TOCTOU gap 真实存在 | 代码 `_workspace_execution_profile_is_regular_file` (L445-466) + `_load_layered_config_file` (L963-993) | **成立**。stat 用 `os.stat(follow_symlinks=False)`，后续 loader 用 `Path.exists()` → `Path.read_text()`，两者之间 pathname 可被外部进程替换。 |
| S4 原三文件不能关闭 gap | accepted plan S4 allowed files: `init_workspace.py` + 两个 test 文件 | **成立**。read 入口 `_load_target_min_context_window` 在 `dayu/cli/commands/init.py`，不在 transaction module。只在 staging/mutation 下游补偿会太晚（首个 model prompt 已基于错误 source 展示）。 |
| init lock 不排除外部 mutation | `file_lock` 协议 + S2 adjudication (S2-MIMO-002) | **成立**。file lock 只串行同 lock 进程；编辑器、sync 工具或其它进程可在 stat 与 read 之间修改 pathname。 |
| locked snapshot 不能替代 stable read | `_require_snapshot_unchanged` 发生在 `prepare_workspace_transaction` / `publish_workspace_transaction` (L584, L782-799) | **成立**。locked snapshot 在 model prompt 之后的多步骤才发生，它只能阻止 eventual publication，无法撤回已发生的 pathname read 或基于错误 minimum 的 model/context prompt。 |
| ConfigLoader 不应拥有 no-follow path open | loader API 只接收 `workspace_config_dir: Path`，无 locked root identity / mode | **成立**。loader 不知道 init trust boundary、locked mode 或 `_WorkspaceRootIdentity`，把 no-follow open 放在 loader 会迫使所有 callers 承担 init-only policy。 |
| 文件名不能只靠位置索引 | `_CONFIG_FILE_NAMES` 当前为普通 tuple (L30-36) | **成立**。现有 consumer 按位置索引或 `execution_profiles.json` 字面量硬编码（`init.py:74`），owner 不在 CLI。 |
| Darwin capability 证据不能替代 cross-platform | Section 8 Darwin evidence (L423-430) | **成立**。amendment 明确声明该证据只证明 Darwin path 可行；真实 Windows/Linux 验收需要 runner 给出事实。 |

## 2. Architecture boundary review

### 2.1 Layering

Amendment 严格维护了当前分层：

- `dayu.cli.commands.init` — 拥有 locked root identity、mode、fd-relative snapshot read
- `dayu.cli.init_workspace` — 拥有 mutation boundary snapshot、staging、publication
- `dayu.runtime.config_loader` — 拥有 typed filename manifest、JSON parser、typed projection、snapshot consumption API

无跨层反向依赖。`ConfigLoader.load_execution_profiles_snapshot` 不接收 workspace path 或 init governance 信息。

### 2.2 Dependency direction

- `init.py` → `config_loader.py`（既存依赖：第 67 行 import `ConfigLoader`）
- `config_loader.py` → standard library only（新增 snapshot API 不引入新依赖）
- `init_workspace.py` → `config_loader.py`（既存依赖：第 28 行 import `config_file_names`）

无新增反向依赖，无循环依赖。

### 2.3 Public contract boundary

- `ConfigLoader.load_execution_profiles_snapshot(workspace_file_snapshot: bytes | None)` 是窄 contract：bytes 已 pin 或 None 已 absent；不承担区分权限。
- `config_file_names() -> ConfigFileNames` 是 NamedTuple → 保持 tuple 子类，现有迭代/位置访问 consumer 无 breaking change。

**Boundary 检查通过。**

### 2.4 Overengineering risk

Section 3.3 明确不新增 `dayu.runtime` 通用 filesystem module。`_read_workspace_execution_profile_snapshot` 是 `init.py` 的私有模块级 helper，不是跨层 runtime abstraction。typed `ConfigFileNames` 是对既有 `_CONFIG_FILE_NAMES` 的语义补全（当前已为 tuple，typed 版本不增加新概念）。

**Overengineering risk: 不成立。**

## 3. State machine and race semantics review

### 3.1 逐层 fd/O_NOFOLLOW/fstat/read 可实现性

Section 4.2 的 11-step read procedure 逐层验证：

| Step | 操作 | 评估 |
|---|---|---|
| 1 | capability gate: `dir_fd`, `O_NOFOLLOW`, `O_DIRECTORY` | 可执行。Darwin/Linux 具备；缺失 → fail closed within PRESERVE only。FIRST/OVERWRITE/RESET 不进入此路径。 |
| 2 | `O_RDONLY \| O_DIRECTORY \| O_NOFOLLOW` open root | 防止 root 为 symlink；`O_DIRECTORY` 防止普通文件。 |
| 3 | fstat root_fd vs `_WorkspaceRootIdentity` | identity 来自 `_bootstrap_workspace_root` 的 no-follow stat + resolve；fstat 与 identity 比较 {device, inode, mode} 可捕获 root drift。 |
| 4 | dir_fd=root_fd, `O_DIRECTORY \| O_NOFOLLOW` open `config` | 只锚定 root_fd；不依赖可交换 workspace path。真正 absent → `None`。 |
| 5 | dir_fd=config_fd, `O_RDONLY \| O_NOFOLLOW \| O_NONBLOCK` open basename from typed manifest | `O_NOFOLLOW` 防止 symlink；`O_NONBLOCK` 防止 FIFO 阻塞；basename 只来自 `config_file_names().execution_profiles`。 |
| 6 | 真正 absent → `None`；symlink/dangling/directory/FIFO/socket/device → fail | fstat 判定；非 regular file 不归为 absent。 |
| 7 | first fstat file_fd → regular file check + stable state | 记录 `{st_dev, st_ino, st_mode, st_nlink, st_size, st_mtime_ns, st_ctime_ns}`。 |
| 8 | `os.read(file_fd, _FILE_READ_CHUNK_BYTES)` 循环 | 只从 descriptor 读取；不重新 open pathname。 |
| 9 | second fstat vs first stable state | pre/post 漂移 → fail closed。 |
| 10 | close file/config/root descriptors | primary error 不被 close error 覆盖。 |
| 11 | bytes 返回后不再读 workspace pathname | 文件名 rename/replace 不影响已 pin bytes。 |

**方向正确；见 Finding DS-002 / DS-003 / DS-004 的微调建议。**

### 3.2 遗漏的 race vector 检查

| Race vector | 覆盖？ | 机制 |
|---|---|---|
| root 在 bootstrap 后、root_fd open 前被替换 | ✓ | Step 3: fstat(root_fd) vs identity 比较 |
| config directory 在 config_fd open 后、file open 前被替换 | ✓ | file open 锚定 config_fd，不穿越新 pathname |
| config pathname 本身是 symlink | ✓ | Step 4: `O_NOFOLLOW \| O_DIRECTORY` fail closed |
| file 在 file_fd open 后、read 前被 rename | ✓ | read 从 pinned fd；后续 mutation boundary 拒绝 publication |
| file 在 read 期间被原地写入 | ✓ | Step 9: pre/post fstat 漂移 fail closed |
| file 在 read 后、parse 前被 swap | ✓ | parser 只消费 immutable bytes |
| file parent directory 是 symlink (before root open) | ✓ | Step 2: root open with `O_NOFOLLOW` |

**无遗漏的 race vector。Amendment 的 Section 5 矩阵完整。**

### 3.3 mutation boundary 的分工

Amendment 正确保留了 `_require_snapshot_unchanged` (init_workspace.py:782) 为 mutation publication 前的最终 drift owner。read helper 的 pre/post fstat 保证本次 bytes 一致性；mutation boundary 的完整 snapshot 比较保证 publication 一致性。两个职责不重叠，顺序明确。

## 4. Exact contract review

### 4.1 Typed ConfigFileNames

- 五个字段固定：`models`, `execution_profiles`, `host_runtime`, `runtime_lanes`, `tool_discovery`
- NamedTuple 保持 tuple 子类 → 既有 `for file_name in config_file_names()` (init_workspace.py:857) 与 `in` containment check (test_config_loader.py:401, test_init_workspace.py:1178) 无 breaking
- `config_file_names().execution_profiles` 替代 `init.py:74` 的 `_EXECUTION_PROFILES_FILE_NAME`

**最小且非兼容 wrapper**：NamedTuple 是既有 tuple 的自然 typed 升级，不是 wrapper/adapter pattern。

### 4.2 Bytes snapshot API

`load_execution_profiles_snapshot(*, workspace_file_snapshot: bytes | None) -> ExecutionProfilesConfig`

- `None` ≡ workspace file absent → package-only
- `bytes` ≡ pinned workspace overlay → 复用同一 UTF-8 / strict JSON / finite-number / top-level object / overlay / schema / extends / typed profile parser
- 不接收 workspace path
- 既有 `load_execution_profiles(workspace_config_dir=...)` 保留给 runtime callers

**路径 vs bytes 的 parser 共享**：amendment 要求抽取 `JSON text/bytes -> JsonObject` 私有 helper 和 `execution profile root -> ExecutionProfilesConfig` 私有 typed projection helper。既有 `_read_required_json_object` (L995-1017) 做 `path.read_text() → json.loads(...)`；抽取后 path 和 bytes 两个入口都调用同一个 `_parse_json_text` + `_parse_execution_profile_root`（或等价命名）。机械可行。

### 4.3 `_load_target_min_context_window` 重构

入参从裸 `Path` 收窄为 `_WorkspaceRootIdentity`，避免 helper 内从 path 重新猜 identity。删除 `_EXECUTION_PROFILES_FILE_NAME`、`_workspace_execution_profile_is_regular_file` 和 `workspace_profile_exists`。这些都是 S2 fix 的临时设施，删除正确。

## 5. Allowed files review

### 5.1 保留 (原 S4)

- `dayu/cli/init_workspace.py` — mutation boundary、staging、publication
- `tests/cli/test_init_workspace.py` — owner-level mutation tests
- `tests/cli/test_init_smoke.py` — integration smoke

### 5.2 新增

| 文件 | 理由 | 评估 |
|---|---|---|
| `dayu/cli/commands/init.py` | read 入口、locked identity、mode owner | **必要**：S2 fix 的 `_workspace_execution_profile_is_regular_file` 在此，read gap 只能在此关闭 |
| `tests/cli/test_init_command.py` | fd snapshot / race 的 owner-level 测试 | **必要**：证明 loader 只收到 bytes、非 path |
| `dayu/runtime/config_loader.py` | typed filename manifest + snapshot consumption API | **必要**：parser/typed-projection owner；typed manifest 消除 CLI 重复字面量 |
| `tests/runtime/test_config_loader.py` | manifest + snapshot API contract tests | **必要**：证明 path/snapshot API 复用同一 parser |

### 5.3 明确不新增

- `dayu.runtime` 通用 filesystem module → 当前只有 init PRESERVE 需要 locked workspace root-aware read
- README → 由 S6 统一同步
- `dayu/config/*.json` → 不修改

**Allowed files 合理。无遗漏，无冗余。**

## 6. Test determinism review

Amendment 明确禁止使用 `sleep`/timing（6.2 总述："禁止使用 `sleep` 猜 race"）。

| Test case | 确定性机制 | 评估 |
|---|---|---|
| 6.2.2 symlink/dangling/directory/FIFO matrix | 静态文件系统替换；无 timing | deterministic |
| 6.2.3 config directory symlink + final file symlink | 静态替换两个路径组件 | deterministic |
| 6.2.4 stat/open swap | 新实现无 pre-stat → 不需要 race window；测试证明 `O_NOFOLLOW` fail closed | deterministic |
| 6.2.5 open/read file-name swap | open 后 rename；bytes 来自原 fd | 需要 barrier: open → barrier.wait → rename → barrier.wait → read。用 `threading.Barrier(2)` 或 `threading.Event` 可确定。 |
| 6.2.6 directory swap | config_fd open 后替换 config；file open 锚定旧 config_fd | 同上 barrier pattern |
| 6.2.7 read/in-place-write | 大 fixture (>1 chunk)，首 chunk 后写同一 inode | 需要 barrier 或用 `os.pwrite` 直接写 fd。可确定。 |
| 6.2.8 read/parse swap | bytes read 后替换 pathname；loader 收到 exact bytes | 无需 barrier（bytes 已 immutable） |
| 6.2.9 capability gate | 模拟缺 capability → PRESERVE fail closed，FIRST/OVERWRITE/RESET 仍 package-only | monkeypatch deterministic |
| 6.2.10 fd close 正常/异常矩阵 | 模拟 close failure + primary error | mock/注入 deterministic |

**所有 race tests 都有明确的 deterministic 机制，不依赖 timing/sleep。**

## 7. Findings

---

### DS-001-未修复-[低]-pre-post fstat 比较中 `st_ctime_ns` 可导致并发元数据操作的误报

- **位置**: Section 4.2, step 7 与 step 9；stable state 包含 `st_ctime_ns`
- **问题类型**: 最佳实践偏离
- **当前写法**: 第二次 fstat 必须与第一次的 `{st_dev, st_ino, st_mode, st_nlink, st_size, st_mtime_ns, st_ctime_ns}` 完全相同
- **反例/失败场景**: 并发进程在 init 读取期间对同一 inode 执行 `chmod` 或 `chown`（不修改内容）；`st_ctime_ns` 变化但 `st_size`/`st_mtime_ns` 不变。当前 contract 将此视为 "workspace execution profile changed while being read; rerun"，对用户是误报 rerun。
- **为什么有问题**: `st_ctime_ns` 反映 inode metadata change（包括 chmod/chown/rename），不精确反映 content change。content drift 检测应使用 `st_size` + `st_mtime_ns`，二者覆盖 truncation/growth 和 content modification。包含 `st_ctime_ns` 提高了误报率而不增加 content-safety。
- **直接证据**: POSIX 语义：`st_ctime` 随任何 inode metadata change 更新（包括 `chmod`、`chown`、link count change），不要求 content write；`st_mtime` 随 content write 更新。Amendment 明确以 "read 期间同一 inode 原地写入" (Section 5 row 4) 为目标场景，该场景 `st_mtime_ns` 已足够检测。
- **影响**: 极低概率运行时误报（并发 metadata-only 操作罕见）；用户收到 "rerun" 提示重新执行 init 即可恢复。不导致静默数据损坏或安全 bypass。
- **建议改法和验证点**:
  1. 将 stable state 从 7 fields 缩小为 `{st_dev, st_ino, st_mode, st_size, st_mtime_ns}`，移除 `st_nlink` 和 `st_ctime_ns`；
  2. 或保留 7 fields 但在 amendment 中记录 "st_ctime_ns / st_nlink 变化也触发 fail closed；这是保守策略，接受极低概率的并发 metadata 操作导致的误报 rerun"；
  3. 验证：测试只触发 content drift（`st_mtime_ns` 变化）即可通过 pre/post 检测，不需要额外覆盖 `st_ctime_ns` 专属场景。
- **修复风险**: 低（缩小比较字段或记录 tradeoff 均不影响安全边界）
- **严重程度**: 低

---

### DS-002-未修复-[低]-`_FILE_READ_CHUNK_BYTES` 常量归属在两个模块之间未明确

- **位置**: Section 4.2, step 8；引用 `_FILE_READ_CHUNK_BYTES`
- **问题类型**: 不可直接实施（minor specification gap）
- **当前写法**: step 8 写 "只用 `os.read(file_fd, _FILE_READ_CHUNK_BYTES)` 循环读取"
- **反例/失败场景**: `_FILE_READ_CHUNK_BYTES` 在 `init_workspace.py:52` 已定义为 `1024 * 1024`。但 `_read_workspace_execution_profile_snapshot` 按 amendment 是 `init.py` 的私有 helper。实现 Agent 面临选择：
  a. 从 `init_workspace` import（增加跨模块依赖）；
  b. 在 `init.py` 重新定义同名常量（重复）；
  c. 作为参数传入（过度参数化）。
- **为什么有问题**: amendment 应明确常量归属，避免 implementation agent 做出与项目 "禁止魔法数字" 约束不一致的局部决策。
- **直接证据**: `init_workspace.py:52` 已定义 `_FILE_READ_CHUNK_BYTES`；`init.py` 当前不依赖此常量。Amendment 的 Section 2.2 明确禁止 "把显式参数放进 extra payload"，但 `_FILE_READ_CHUNK_BYTES` 不是 extra payload — 它是合理的 chunk size 常量。
- **影响**: implementation agent 需自行决定；任何合理选择均不影响正确性，但可能引入不必要的模块耦合或重复。
- **建议改法和验证点**:
  1. 在 amendment 中明确：`_read_workspace_execution_profile_snapshot` 自身定义 `_FILE_READ_CHUNK_BYTES: Final[int] = 1024 * 1024`（模块级私有常量，与 `init_workspace.py` 的值相同但独立拥有）；
  2. 或明确从 `init_workspace` import，并记录理由（`init_workspace` 是既有 chunk-size owner）；
  3. 验证：静态检查无重复魔法数字，chunk size 值一致。
- **修复风险**: 低（选择任一方案均可）
- **严重程度**: 低

---

### DS-003-未修复-[低]-close failure 的 primary-error 优先级语义未完整规格化

- **位置**: Section 4.2, step 10
- **问题类型**: 不可直接实施（minor specification gap）
- **当前写法**: "close failure 不得被静默吞掉或覆盖更早 primary failure，沿项目既有 primary-error discipline 处理"
- **反例/失败场景**: 当前代码库中 try/finally 的 close 处理没有统一的 "primary-error discipline"。例如 `publish_workspace_transaction` (L580-605) 使用 `try/except` 链，但那是针对 workspace transaction 阶段，不是针对多 fd 顺序 close。实现 Agent 需要自行设计：是否用 `__exit__` / context manager / 显式 `try/finally`？close error 是否以 `__cause__` chaining？是否 suppress 到 stderr？
- **为什么有问题**: "沿项目既有 primary-error discipline" 指向不存在的明确定义。实施 Agent 需要 clarification 或自主决定，可能导致与后续 review 的契约争议。
- **直接证据**: `init_workspace.py` 中无多 fd close 的统一模式。搜索结果：该文件不使用 `st_ctime_ns` 或 `st_mtime_ns`，也没有显式 fd close error handling 范例。项目 CLAUDE.md 的 "语义所有权与修复边界" 要求 "代码必须改在 owner boundary"，close error 的处理策略必须是 read helper owner 的明确设计。
- **影响**: implementation agent 自行设计的 close discipline 可能在 review 中被质疑；不影响运行时安全（最坏情况是 close error 被意外 suppress 但不改变已返回 bytes 的正确性）。
- **建议改法和验证点**:
  1. 在 amendment 的 step 10 或新子节中写清楚：
     - 三个 fd 关闭顺序：file_fd → config_fd → root_fd（逆序不对也无安全影响但应记录）
     - 若 primary read/open 成功但 close 失败：primary result (bytes/None) 不丢失；close error 以 exception（`OSError`）传播或记录到 stderr。若 close error 传播，`run_init_command` 的顶层 `except OSError` (L243-248) 自然处理
     - 若 primary read/open 已经失败（Exception in flight），close 的 secondary error 不得替换 primary exception；建议使用 `try/finally` + `exc_info()` 或 context manager 实现
  2. 测试 (6.2.10) 应覆盖：primary read error + close error → primary error preserved；primary success + close error → close error 正确传播或记录。
- **修复风险**: 低（补充规格，不改变核心设计）
- **严重程度**: 低

---

### DS-004-未修复-[低]-`config_file_names()` 返回类型从 `tuple[str, ...]` 变更为 `ConfigFileNames` 的向后兼容性应显式论证

- **位置**: Section 4.1；Section 2.1 (owner table row 3)
- **问题类型**: 契约缺失（minor）
- **当前写法**: "`config_file_names() -> ConfigFileNames` 返回该唯一 manifest"；未提及既有 tuple consumer 的兼容性。
- **反例/失败场景**: 若 `ConfigFileNames` 实现为非 tuple 的类型（如 frozen dataclass），既有 `for file_name in config_file_names()` (init_workspace.py:857) 和 `"runtime_lanes.json" in config_file_names()` (test_config_loader.py:401) 会 break。amendment 未说明为何选择 NamedTuple 而非普通 class。
- **为什么有问题**: 项目 CLAUDE.md 要求 "不做过度设计，以最小化满足需求为标准" 和 "设计公共契约优先使用直接传参数的朴素接口"。NamedTuple 是朴素选择，应声明以消除 ambiguity。
- **直接证据**: init_workspace.py:857 用 `for file_name in config_file_names()` 迭代；test_config_loader.py:401 用 `in` containment check；test_init_workspace.py:1178 用 `set(config_file_names())`。这三者都在 NamedTuple subclass tuple 的情况下保持工作。但 amendment 未说明这一点。
- **影响**: implementation agent 若选择不保持 tuple 子类的实现（如 `@dataclass`），会导致既有 consumer break。
- **建议改法和验证点**:
  1. 在 Section 4.1 中增加：`ConfigFileNames` 继承 `typing.NamedTuple`（因此是 tuple 子类），既有位置迭代/in containment 消费者无需修改。
  2. 或明确要求 `ConfigFileNames` 必须保持 tuple-like 语义。
  3. 测试 6.1 item 1 加入：既有迭代 consumer 仍可正常工作，字段名仅提供额外语义访问。
- **修复风险**: 低（声明即可）
- **严重程度**: 低

---

## 8. Open questions

### OQ-001 — `O_DIRECTORY` + absent → `FileNotFoundError` → `None` 的映射边界

Section 4.2 step 4/6 描述：config directory 或 target file 真正 absent → 返回 `None`。实现映射为 `os.open(..., O_DIRECTORY)` 对不存在路径抛 `FileNotFoundError` → 捕获并返回 `None`。step 4 只描述 "真正 absent 返回 `None`"，未显式写出 `FileNotFoundError` catch。建议 implementation agent 在 step 4 和 step 6 分别写清楚异常映射规则。

### OQ-002 — `_WorkspaceRootIdentity` identity 比较中 `canonical_path` 的角色

Step 3 比较 `fstat(root_fd)` 与 `_WorkspaceRootIdentity` 的 `{device, inode, mode}`。但 `_WorkspaceRootIdentity` (init.py:96-109) 还包含 `canonical_path`。Amendment 未声明是否只比较 `{device, inode, mode}` 三个字段（语义正确，因为 path 可能因 symlink 链差异而不同但指向同一 inode），还是比较完整 identity（包括 canonical_path）。建议在 step 3 中明确只比较 `{device, inode, mode}`。

### OQ-003 — macOS `O_DIRECTORY` 在 APFS 上的行为

Darwin 的 `hasattr(os, "O_DIRECTORY")` 为 True，`os.O_DIRECTORY` 在 APFS 上通过 Darwin `O_DIRECTORY` 实现。但 Python 3.11 的 `os.open` 文档在 POSIX 上要求 `O_DIRECTORY` + non-directory → `ENOTDIR`。amendment step 2 依赖此行为防止 root 被替换为非目录。建议 smoke test 验证 Darwin 上的 exact behavior（已知 `os.open(path, os.O_DIRECTORY)` 对 regular file 抛 `OSError(errno.ENOTDIR)`）。

## 9. Residual risks

1. **跨进程 mutation lock 不存在**：fd snapshot 保证读取对象稳定，不能阻止其它进程 mutation。read 完成后的 config mutation 由 locked snapshot 拒绝 publication，用户需重试 init。分类：`accepted operational behavior`（与 amendment Section 12 item 1 一致）。

2. **package config 路径安全**：仍走既存 `_read_required_json_object` 的 path API。分类：`out of scope`（与 amendment 一致）。

3. **真实 Windows capability 未确认**：Darwin evidence 不能替代。分类：`tracked by S4 stop condition #2 + S5/S6 cross-platform validation`（与 amendment 一致）。

4. **配置大小未限制**：amend 不新增 size schema。分类：`not introduced by amendment`（与 amendment 一致）。

5. **Finding DS-001 的 `st_ctime_ns` 误报风险**：见上方。分类：`accepted as conservative design` 或 `fix in impl`（视 controller 裁决）。

## 10. Final plan review conclusion

**PASS**

本 review 确认：

- TOCTOU gap 真实存在（代码直接证据：`init.py:457-466` 的 no-follow stat + `config_loader.py:984` 的 `Path.exists()` / `Path.read_text()`）
- 不能只在原 S4 三个文件修复（read 入口在 `init.py`，transaction 只能阻止 publication 不能撤回 read）
- typed `ConfigFileNames` / bytes snapshot API 是最小、非兼容 wrapper（NamedTuple 为 tuple 子类；snapshot API 与 path API 共享同一 parser/typed-projection）
- 逐层 fd/O_NOFOLLOW/fstat/read 可实现（11-step procedure 覆盖 root/config/file 三层 + parent/rename/in-place write 场景）
- FIRST/OVERWRITE/RESET 在缺 capability 时仍是 package-only（不调用 fd reader）
- Windows/Linux stop condition 清楚（Section 8 共 8 个精确条件）
- 测试 deterministic（使用 barriers 和文件系统操作，非 sleep）
- allowed files 合理且必要（7 files：3 保留 + 4 新增）

四个 DS findings 均为规格化微调（severity 低），不构成 stop condition。三个 open questions 为 implementation-level 澄清，不改变 architecture。

若 implementation 命中 Section 8 任一 stop condition，必须 STOP，不得以 fallback 或兼容分支继续。

---

Reviewer: AgentDS

Date: 2026-07-30T16:26:08+08:00
