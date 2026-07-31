# WU-CLI-INIT-01 S4 Plan Amendment — Plan-fix Rereview (DS)

## Gate metadata

- Type: plan-fix rereview
- Role: independent adversarial rereviewer (DS 路)
- 日期: 2026-07-30T16:36:15+08:00
- Reviewed target: `docs/reviews/wu-cli-init-01-s4-plan-amendment-codex.md` (plan-fix 更新后)
- Base commit: `06ea49e071c292d84066ef4ac1c2566e95427c41`
- Plan-fix timestamp: `2026-07-30T16:31:33+08:00`
- Prior DS review: `docs/reviews/wu-cli-init-01-s4-plan-amendment-review-ds.md`
- Rereview artifact: `docs/reviews/wu-cli-init-01-s4-plan-amendment-rereview-ds.md`
- MiMo review: intentionally not consulted (per /planreview instruction)

## Rereview scope

核对以下几项是否已在 plan-fix 版 amendment 中完整关闭：

1. DS-001：`st_ctime_ns` / `st_nlink` conservative metadata drift
2. DS-002：`_FILE_READ_CHUNK_BYTES` / local chunk constant 归属
3. DS-003：close precedence / primary-error 优先级
4. DS-004：`ConfigFileNames` NamedTuple 向后兼容声明
5. OQ-001/OQ-002：absent/root identity 的 `FileNotFoundError` 映射边界与 fd identity 比较字段
6. Controller 裁决：MiMo R001（O_NONBLOCK reject）、MiMo R002（deterministic mechanism accept）
7. 是否引入新 owner/scope/不可实现要求

只核对 plan artifact 本身的一致性与完整性，不验证实现。

---

## 1. DS finding closure audit

### DS-001 — `st_ctime_ns` / `st_nlink` conservative metadata drift

| 维度 | 原始 plan (v1) | plan-fix 版 (v2) | 状态 |
|---|---|---|---|
| stable state 声明 | Step 7: `{st_dev, st_ino, st_mode, st_nlink, st_size, st_mtime_ns, st_ctime_ns}` 无解释 | Step 7 追加：**"保留 `st_nlink` 与 `st_ctime_ns` 是有意的保守 fail-closed 选择：chmod/chown、link-count 或其它 inode metadata drift 即使未改变内容，也要求用户 rerun，不把 metadata-only 并发当成可忽略事件"** | **已关闭** |
| residual risk 记录 | 无 | Section 12 item 5：**"`st_nlink` / `st_ctime_ns` 的 metadata-only drift 也触发 rerun...分类：`accepted conservative behavior`"** | **已关闭** |
| test coverage | 6.2.7 仅 "pre/post state 漂移" | 6.2.7 追加：**"另分别让 `st_nlink`/`st_ctime_ns` 漂移，锁定 metadata/link drift 也要求 rerun 的有意保守 contract"** | **已关闭** |

**裁决：完整关闭。** 采用了 DS-001 建议的选项 2（记录 tradeoff）。

---

### DS-002 — chunk constant 归属

| 维度 | 原始 plan (v1) | plan-fix 版 (v2) | 状态 |
|---|---|---|---|
| 常量名 | Step 8: `_FILE_READ_CHUNK_BYTES`（无名分） | Step 8: **"`dayu.cli.commands.init` 自有模块级 `_WORKSPACE_PROFILE_READ_CHUNK_BYTES: Final[int] = 1024 * 1024`"** | **已关闭** |
| 跨模块 import | 未声明 | Step 8: **"不从 `dayu.cli.init_workspace` import 私有 `_FILE_READ_CHUNK_BYTES`"** | **已关闭** |

**裁决：完整关闭。** 采用了 DS-002 建议的选项 1（自有常量）。

---

### DS-003 — close precedence

| 维度 | 原始 plan (v1) | plan-fix 版 (v2) | 状态 |
|---|---|---|---|
| close order | 未指定 | Step 10: **"严格按 `file_fd -> config_fd -> root_fd` 逆序 close，并继续尝试关闭其余已打开 fd"** | **已关闭** |
| no-primary error | 未指定 | Step 10: **"保留并传播第一个 `os.close` 的 `OSError`；后续 close errors 只能作为该第一个 close error 的 notes/chain 记录"** | **已关闭** |
| has-primary error | 未指定 | Step 10: **"保留并重新抛出同一个 primary exception；第一个 secondary close error 通过 exception chaining 记录，其余 secondary close errors 用 `BaseException.add_note(...)` 记录类型与 fd role，不能替换 primary"** | **已关闭** |
| diagnostic safety | 未指定 | Step 10: **"close error diagnostics 只记录 exception type 与 `file/config/root` role，不含 path、配置 bytes 或 secret"** | **已关闭** |
| test coverage | 6.2.10: 单行描述 | 6.2.12: 两个子场景，断言 descriptor leak 零、notes 内容受限 | **已关闭** |

**裁决：完整关闭。** close discipline 现在 code-generation-ready。

---

### DS-004 — `ConfigFileNames` NamedTuple 声明

| 维度 | 原始 plan (v1) | plan-fix 版 (v2) | 状态 |
|---|---|---|---|
| 类型约束 | "immutable、strictly typed"（泛泛） | Section 4.1: **"继承 `typing.NamedTuple`...保证它仍是 tuple 子类，保留既有 tuple iteration、位置迭代、`in` containment 与 `set(config_file_names())` 行为；不得改用普通 dataclass 或自定义 iterable"** | **已关闭** |
| test coverage | 6.1.1: "typed manifest，五个语义字段与迭代顺序唯一" | 6.1.1: 追加 **"既有 tuple iteration、`in` containment 和 `set(...)` 消费保持"** | **已关闭** |

**裁决：完整关闭。** Implementation agent 不再有选择 `@dataclass` 的自由度。

---

## 2. Open question closure audit

### OQ-001 — `FileNotFoundError` → `None` mapping boundary

| 维度 | 原始 plan (v1) | plan-fix 版 (v2) | 状态 |
|---|---|---|---|
| config absent | Step 4: "真正 absent 返回 `None`"（无异常映射） | Step 4: **"只有该次 fd-relative `os.open` 抛出的 `FileNotFoundError` 才映射为 `None`；...root open/fstat、普通 `os.fstat`/`os.read` 或其它非 fd-relative open 的 `FileNotFoundError` 不得映射为 absent"** | **已关闭** |
| file absent | Step 6: 同样模糊 | Step 6: **"只有该次 final fd-relative `os.open` 抛出的 `FileNotFoundError` 才表示目标真正 absent 并返回 `None`"** | **已关闭** |
| non-fd-relative FNFE | 未区分 | Step 3/8: 明确非 fd-relative open/fstat/read 的 `FileNotFoundError` 传播 | **已关闭** |
| test coverage | 无 | 6.2.11: config/final fd-relative absent → None；root open/fstat/read FNFE → 传播不 fallback | **已关闭** |

**裁决：完整关闭。**

---

### OQ-002 — root fd identity 比较字段

| 维度 | 原始 plan (v1) | plan-fix 版 (v2) | 状态 |
|---|---|---|---|
| 比较字段 | Step 3: "必须与 `_WorkspaceRootIdentity` 的 `{device, inode, mode}` 完全相同"（暗示但不明确排除 canonical_path） | Step 3: **"`os.fstat(root_fd)` 只与 `_WorkspaceRootIdentity` 的 `{device, inode, mode}` 完全比较...`canonical_path` 只用于步骤 2 的 root open，不参与 fd identity 比较"** | **已关闭** |
| test coverage | 无 | 6.2.11: "root `fstat` 只比较 dev/inode/mode；canonical path 不参与 fd identity" | **已关闭** |

**裁决：完整关闭。**

---

### OQ-003 — macOS `O_DIRECTORY` on APFS

| 维度 | 评估 |
|---|---|
| O_DIRECTORY 行为 | POSIX 标准：`O_DIRECTORY` + non-directory → `ENOTDIR`。这是跨实现的标准行为，Darwin 遵循。不需要实证。 |
| O_NONBLOCK 实证 | Section 8.1 补充了当前 Darwin/Python 3.11 的实际命令与 exact result，证明 ordinary/empty regular file 在含 `O_NONBLOCK` 的真实 fd 上不产生 `EAGAIN`。 |

**裁决：充分解决。** `O_DIRECTORY` 行为由 POSIX 标准保证；`O_NONBLOCK` 行为由实证锁定。

---

## 3. Controller 裁决执行审计

### MiMo R001（移除 O_NONBLOCK）— rejected

| 检查项 | plan-fix 版 (v2) 证据 | 状态 |
|---|---|---|
| O_NONBLOCK 保留 | Step 5: `O_RDONLY \| O_NOFOLLOW \| O_NONBLOCK` 保留 | ✅ |
| 实证证据 | Section 8.1: 两条实际命令与 exact result（非空 `b'profile-bytes'`，空 `b''`） | ✅ |
| fail-closed 契约 | Step 8: "若已由 `fstat` 证明为 regular file 后仍收到 `BlockingIOError`，按 `OSError` fail closed 且不重试，不把 `EAGAIN` 改写成 EOF" | ✅ |
| test coverage | 6.2.10: 普通非空/空 regular file 真实 `os.read` 行为 + `BlockingIOError` fault injection → `OSError` fail closed、loader 未调用 | ✅ |
| Section 13 记录 | "Controller 驳回 MiMo R001...S4 保留 `O_NONBLOCK` 防 FIFO open 阻塞" | ✅ |

**裁决：正确执行。** `O_NONBLOCK` 的 FIFO 防御角色得到保留，regular-file 行为有实证支持，异常路径有 fail-closed 契约。

---

### MiMo R002（deterministic test mechanism）— accepted

| 检查项 | plan-fix 版 (v2) 证据 | 状态 |
|---|---|---|
| 通用机制声明 | Section 6.2 前导段：pytest `monkeypatch` 包装 + delegate original + `threading.Event`/`Barrier` + bounded wait + 禁止 `sleep` | ✅ |
| wrapper 约束 | "wrapper 必须先保存 original syscall/method，并在指定 boundary **delegate** original；不得伪造成功 fd、bytes、stat result 或 typed config" | ✅ |
| 每个 race 的 injection point | 6.2.4-6.2.8: 每个 test 明确列出 wrapper boundary、signal/release 时序、mutation 操作 | ✅ |
| bounded wait | "每个 test 都必须有 bounded join/wait failure assertion，防止测试挂死；timeout 只用于判定测试失败，不用于制造 race" | ✅ |
| Section 13 记录 | "Controller accepted MiMo R002：已在 §6.2 固定 pytest monkeypatch + `threading.Event`/`threading.Barrier` 机制" | ✅ |

**裁决：正确执行。** 所有 race tests 都有明确的 deterministic barrier 与 exact injection point。

---

## 4. 新引入内容的审计

### 4.1 新 section / 段落

| 新增内容 | 位置 | 性质 | 评估 |
|---|---|---|---|
| O_NONBLOCK 实证 | §8.1 | 事实证据 | 仅记录当前 Darwin 状态；不改变任何 contract。 |
| Plan-fix 摘要 | §13 | 审计轨迹 | 仅记录 fix 与裁决对应关系；不新增语义。 |
| `BlockingIOError` fail-closed | §4.2 step 8 | contract 补全 | 窄 glitch handling；不新增成功路径。 |
| `os.read` 返回语义 | §4.2 step 8 | contract 补全 | 明确 empty/EOF 终止条件；消除 ambiguity。 |
| test mechanism 前导段 | §6.2 | test 实施约束 | 不在 production 增加代码。 |
| residual risk 5 | §12 | risk tracking | 仅记录，不承诺修复或 defer。 |

**无新 scope、无新 owner、无新 allowed file、无新依赖。**

### 4.2 测试 case 数量变化

| 版本 | items | 变化 |
|---|---|---|
| v1 | 10（原 1-10） | — |
| v2 | 12（1-12） | 新增 item 10（ordinary/empty/EOF + BlockingIOError）、item 11（absent/error mapping）；原 item 10（fd close）扩展为 item 12 |

新增的 2 个 test items 均为已有 contract 的自然覆盖扩展：
- item 10: 覆盖 step 8 的 `O_NONBLOCK` 实证锁定 + `BlockingIOError` glitch
- item 11: 覆盖 step 3/4/6 的 `FileNotFoundError` 精确映射 + root identity 比较字段

**无测试范围膨胀。每一项都有 direct contract 对应。**

### 4.3 架构边界

逐项检查是否引入越界：

- `_WORKSPACE_PROFILE_READ_CHUNK_BYTES` ∈ `init.py`（init orchestrator own）：**不越界**
- `ConfigFileNames` ∈ `config_loader.py`（config loader own）：**不越界**
- `load_execution_profiles_snapshot` ∈ `ConfigLoader`（config loader own）：**不越界**
- `_read_workspace_execution_profile_snapshot` ∈ `init.py`（init orchestrator own）：**不越界**
- close discipline 全部在 `init.py` 的 private helper 内：**不越界**

**无新增跨层依赖或反向依赖。**

---

## 5. 未覆盖项检查

以下检查从原始 DS review 的 attack surface 角度确认无遗漏：

| 攻击面 | plan-fix 版覆盖状态 |
|---|---|
| 空 workspace（root absent、config absent、file absent） | Step 4/6 absent → None + Test 6.2.11 ✅ |
| workspace root 在 bootstrap 后漂移 | Step 3 fstat vs identity + Test 6.2.11 ✅ |
| config 目录为 symlink | Step 4 O_NOFOLLOW + Test 6.2.3 ✅ |
| execution_profiles.json 为 symlink | Step 6 O_NOFOLLOW + Test 6.2.2 ✅ |
| execution_profiles.json 为 FIFO | Step 5 O_NONBLOCK（open 不阻塞）+ Step 6 fstat S_ISREG fail + Test 6.2.2 ✅ |
| file 在 open 后、read 前被 rename | Step 8 从 pinned fd 读取 + Test 6.2.5 ✅ |
| file 在 read 期间被原地写入 | Step 9 pre/post fstat + Test 6.2.7 ✅ |
| file 在 read 期间被 chmod/chown（metadata-only） | Step 7 st_ctime_ns 有意的保守检测 + Test 6.2.7 ✅ |
| read 后、parse 前 pathname swap | Step 11 immutable bytes + Test 6.2.8 ✅ |
| 正常 empty file | Step 8 os.read returns b"" + Test 6.2.10 ✅ |
| 缺 capability 平台 | Step 1 capability gate + Test 6.2.9 ✅ |
| fd close 失败 | Step 10 逆序 + primary-preserving + Test 6.2.12 ✅ |
| read 成功但后续 transaction snapshot drift | Section 5 row 2/6 + Test 6.3 ✅ |

**无遗漏的 race vector 或 failure mode。**

---

## 6. Findings

**本轮 rereview 未发现新的 material finding。**

四个 DS findings 全部已关闭。三个 OQ 全部已解决。两个 Controller 裁决全部正确执行。

plan-fix 版 amendment 仅补全规格、添加实证证据、固定 test mechanism，未引入新 owner、新 scope、新 allowed files、新依赖或新不可实现要求。

---

## 7. Residual checks

### 7.1 测试可实现性

test mechanism（monkeypatch + Event/Barrier + delegate original）的关键实现前提已验证：

- Python 3.11 的 `os.open` 支持 `dir_fd` keyword argument：✅（`os.supports_dir_fd` True，Darwin）
- `threading.Event` / `threading.Barrier` 在 pytest 下可用：✅（标准库）
- pytest `monkeypatch` 可包装 built-in 模块属性：✅（`monkeypatch.setattr(module.os, 'open', wrapper)`）
- wrapper 通过 `dir_fd is not None` 区分 absolute vs fd-relative `os.open`：✅（step 2 不传 dir_fd，steps 4/6 传 dir_fd）
- wrapper 通过 path basename 区分 config open vs file open：✅（`"config"` vs `config_file_names().execution_profiles`）

### 7.2 Plan-fix 未修改项目清单

| 是否修改 | 范围 |
|---|---|
| 否 | accepted plan (`wu-cli-init-01-plan-codex.md`) |
| 否 | production code |
| 否 | tests |
| 否 | README / docs（本 amendment 之外） |
| 否 | git staging area |
| 是（仅此 artifact） | `wu-cli-init-01-s4-plan-amendment-codex.md` |

---

## 8. Final rereview conclusion

**PASS**

plan-fix 版 amendment 完整关闭了前轮 DS review 的全部四个 findings 与三个 open questions；Controller 的两个裁决（MiMo R001 reject + MiMo R002 accept）均已正确执行并具备直接 artifact 证据。

amendment 仍保持 code-generation-ready 状态：

- 7 个 allowed files（3 保留 + 4 新增），无遗漏无冗余
- 11-step fd/no-follow read procedure 规格完整到 single-syscall 级别
- 12 项 test matrix 覆盖所有 race vectors、failure modes 与 deterministic barrier
- close discipline 精确到逆序 + primary-preserving chain/notes
- typed filename manifest 约束到 `typing.NamedTuple` 级别
- 无新 owner、新 scope、新依赖或不可实现要求

当前轮未发现 blocking material finding。若 implementation 命中 Section 8 任一 stop condition，仍必须 STOP。

---

Rereviewer: AgentDS

Date: 2026-07-30T16:36:15+08:00
