# WU-SEMANTIC-OWNERSHIP-01 / R12 S2 corrected-plan 第一路完整 final re-review (AgentMiMo)

## 1. Review 身份与范围

- **Review target**: `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`，708 行 / 105,368 字节 / SHA-256 `aa7b50a90c9623ea8dcafe8c4c651665b16b9ee3be76ec8357c4d47977fb2a4c`
- **Gate**: 既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` / R12 S2 corrected-plan 的第一路完整 final re-review，不是新 WU/sub-WU
- **Reviewer**: AgentMiMo
- **Review scope**: 整个 corrected plan，逐项独立验证 `R12-S2-PR-F01..F06` 6/6 closure 与 rejected/no-fix 保持
- **本 review 不授权 implementation、不修改 plan/code/test/control/其它 artifact，不 stage/commit**

## 2. Authority hashes

| Artifact | 行数 / 字节 | SHA-256 |
|---|---|---|
| Fixed plan (review target) | 708 / 105,368 | `aa7b50a90c9623ea8dcafe8c4c651665b16b9ee3be76ec8357c4d47977fb2a4c` |
| AgentCodex fix artifact | 73 / 8,938 | `ba141650a8c2bc94a3e82bce63bf2b840c4255ceda64a8f431839b14146d4664` |
| Controller validation | 73 / 6,817 | `a8e692565a0c87121141a79462f33de56cb2f7a306ac63e53bff517158d706bd` |
| Controller adjudication (accepted F01..F06) | 94 / 10,426 | `56633e23f77c5c70dd2d6052d6a3ddd2e4ec322effbe8f009590f817fb6e2bee` |
| AgentMiMo 前轮 review (corrected plan) | 276 / 23,704 | `b59e529f6371cee21279124cfe3b8d2e7f7d3c013eab8396652e641563e9bec4` |
| AgentDS 前轮 review (corrected plan) | 293 / 25,633 | `b8e4773047caade4020a1d55847a87bfad47918c2ea33da5ae41b210b3425c32` |
| S2 implementation stop handoff | 155 / 9,139 | `b123dff616a0c4ac22bb3d1f47b00fe5913a9747e9f3e413ff34462ddbd82fcd` |
| Controller stop adjudication | 89 / 5,770 | `f2bb4029d83716e5e2a18e16fe1ac8c7970db7396adf54e951d9378ae4e3785c` |
| AGENTS.md | 128 / 10,036 | — |

直接代码证据（完整读取并用于本 review）：

| 代码文件 | 关键行 | 证据要点 |
|---|---|---|
| `dayu/service/host_assembly.py` | L528, L1461-L1503 | `assemble_effective_tool_provider_configs` 当前签名无 override；`_effective_fins_workspace_root_config_value` 在显式绝对/相对 root 时忽略调用方 `workspace_root` |
| `dayu/service/host_assembly.py` | L477-L510 | `discover_service_tools` 真实执行 provider binding，有 filesystem side effect |
| `dayu/fins/storage/_fs_storage_infra.py` | L397-L451 | `_FsStorageInfra.__init__` 创建 `portfolio/`、`.dayu/repo_batches` 等 |
| `dayu/fins/ingestion_runtime.py` | L1511-L1526 | `FsFinsIngestionJobStore.__post_init__` 创建 `.dayu/fins_ingestion/jobs` |
| `dayu/service/entrypoint_runtime.py` | — | 普通 runtime 调用 `assemble_effective_tool_provider_configs` 不传 override |
| Python 3.11.15 `.venv` probe | — | `shutil.rmtree.avoids_symlink_attacks = True`（macOS Darwin 25.5.0） |

## 3. R12-S2-PR-F01..F06 closure 逐项验证

### F01 — HIGH — 显式 Fins workspace root 必须受 validation-only override 支配

**Plan 位置**: §3 语义所有权表、§6.4 第 3 项、§8 S2 断言、§9 scans

**Plan 写法**: `assemble_effective_tool_provider_configs` 新增朴素 keyword-only `fins_workspace_root_override: pathlib.Path | None = None`；ordinary runtime 显式传 `None`，R12 init validation 唯一 non-`None` consumer 同时传 `workspace_root=<canonical public workspace>` 和 `fins_workspace_root_override=<recorded canonical absolute private validation root>`。override 无条件支配合法未配置/显式绝对/显式相对 Fins root；不改 raw bytes/schema；非 Fins/Web 不受影响。

**独立验证**:

1. **当前代码反例确认**: `_effective_fins_workspace_root_config_value`（L1477-L1503）在 `configured_workspace_root` 为显式绝对路径时返回 `str(configured_path.resolve(strict=False))`，完全忽略调用方传入的 `workspace_root`。这正是 PRESERVE 场景下用户显式配置了 Fins `workspace_root` 时 side effect 逃出 private root 的根因。F01 HIGH 动机成立。

2. **Override 机制正确性**: plan 要求修改后的函数仍先校验 raw Fins `config.workspace_root` 的现行 type/non-empty grammar（非字符串、空字符串、relative 缺基准仍拒绝），然后在 raw path precedence/return 前让合法 override 无条件成为 in-memory effective Fins root。三类合法 raw root 的行为：
   - **未配置** (`configured_workspace_root is None`): 当前返回 `str(workspace_root.expanduser().resolve())`；加 override 后在该 return 前检查 override 并返回 override → 正确
   - **显式绝对** (`configured_path.is_absolute()`): 当前返回 `str(configured_path.resolve())`；加 override 后在该 return 前检查 override 并返回 override → 正确，这正是 F01 要解决的核心反例
   - **显式相对**: 当前通过 `resolve_workspace_path(workspace_root, stripped)` 解析；加 override 后在该 return 前检查 override 并返回 override → 正确
   - **非法值**（非字符串/空字符串/relative 缺基准）: raw grammar 校验仍先于 override 检查并拒绝 → invalid raw 不会被 override 掩盖

3. **Raw bytes 不变**: override 只改变函数返回值（写入 effective config），不修改 `provider_config.config` dict。staging/public config 文件的序列化 bytes 不变。§9 scan 要求 raw mapping/serialized staging bytes 不变。

4. **非 Fins/Web 隔离**: override 函数只被 Fins provider 路径调用；`_effective_web_storage_state_dir_config_value`（L1506+）不消费 override。Web `playwright_storage_state_dir` 仍只按普通 `workspace_root` 解析。

5. **Owner boundary**: 修改在 `host_assembly.py` 的 `_effective_fins_workspace_root_config_value` 内，该函数已是 Fins effective-config classification/precedence 的唯一 owner。CLI 不复制 provider classification、不猜 provider id、不 strip raw config。

6. **Scan 同步**: §9 `fins_workspace_root_override` scan 覆盖 `dayu/cli dayu/service tests/cli tests/service utils`；production non-`None` consumer 必须只有 R12 init validation；ordinary `entrypoint_runtime` 必须显式 `None`。CLI classification/raw-strip negative scan production 为空。

**判定**: **closed**。override 机制在三类合法 raw root 场景下均正确支配 Fins effective root，raw bytes 不变，非 Fins/Web 隔离，owner boundary 最小。

---

### F02 — MEDIUM — OS fault injection 与 "test shim" 边界必须自洽

**Plan 位置**: §8 S2 断言段

**Plan 写法**: 明确 `pytest.monkeypatch` / `unittest.mock` syscall fault injection 不属于 provider/catalog test shim；禁止 production callback/factory/default-callable seam；逐阶段枚举 fault matrix。

**独立验证**:

1. §8 fault matrix 表精确列出 10 个阶段/注入点：staging/validation 前、validation cleanup identity、validation recursive delete、validation delete 后 POSIX sync、secret persistence、public backup moves、config publish、POSIX publication sync、rollback、post-publication delete/post-publication POSIX sync。每行指定"必须注入的 operation"和"预期 owner truth"。

2. 每个 replace/fsync 边界覆盖普通 `OSError` 和 `KeyboardInterrupt`；ENOSPC 只注入能实际抛出它的 write/copy/replace/fsync boundary。

3. Plan 明确禁止 production 新增 callback/factory/profile/default-callable 参数或 test-only branch。`pytest.monkeypatch` / `unittest.mock` 在 owner module lookup boundary 替换 `os.open`、`os.stat/lstat`、`os.fsync`、`os.replace`、`os.unlink/os.rmdir`、`shutil.rmtree` 是标准 Python mocking，不属于禁止的 "synthetic provider / metadata-only discovery / test shim"。

4. 前轮 AgentDS DS-F01 的 open question（`unittest.mock.patch` 是否被 plan 视为 test shim）已由 §8 明确回答：允许 syscall 级 monkeypatch/mock，禁止 provider/catalog 级 shim。

**判定**: **closed**。fault matrix 精确、syscall mock 边界清晰、production seam 禁止明确。

---

### F03 — MEDIUM — cleanup 后 parent-fsync 失败的 retained truth 必须唯一

**Plan 位置**: §6.3.1、§6.4 第 4 项、§8 fault matrix

**Plan 写法**: validation tree 已删除而 POSIX parent sync 失败时，retained truth 唯一是仍存在的 staging/container；child/quarantine absent，diagnostic 含精确 stage/path 与 `deletion durability unconfirmed`。partial delete 只承诺 retained path + failure stage，不承诺完整取证树。

**独立验证**:

1. §6.3.1 明确："validation tree 已全部删除但其 POSIX parent directory sync 失败时，唯一 retained truth 是仍存在的 transaction-private staging/container；validation child 必须不存在。typed diagnostic 报告 retained staging path、`deletion durability unconfirmed` 与 `validation_parent_directory_sync` stage，不得声称已删除 validation tree 仍被保留。"

2. §6.4 第 4 项："cleanup/identity/reparse/delete fault 必须在 public config publication 前 abort；POSIX parent-sync fault 同样 abort。删除未完成时报告 retained staging 与实际 remaining/quarantine path；validation child 已删除而 POSIX parent sync 失败时只报告仍存在的 staging/container、child absent 与 `deletion durability unconfirmed`。不得降级成 publication 后 warning。"

3. §8 fault matrix "validation delete 后 POSIX sync" 行："pre-publication abort；staging/container 存在、validation child 与 quarantine 不存在；diagnostic=`validation_parent_directory_sync` + `deletion durability unconfirmed`；Windows 无此 unsupported fault point"。

4. 前轮 MiMo Finding 001 的"preserve 语义歧义"已由 §6.3.1 和 §8 的精确 wording 闭合：保留的是 staging 目录（validation root 的父目录），不是已删除的 validation tree。

5. §6.3.1 同时覆盖 partial delete："任一不一致都 fail closed，不尝试猜测或清理替代对象。"

**判定**: **closed**。retained truth 唯一、diagnostic 精确、partial delete 有独立 contract、pre/post-publication 边界不混用。

---

### F04 — MEDIUM — no-follow 删除必须形成可执行的跨平台 contract

**Plan 位置**: §6.3.1、§8、S3 Windows job

**Plan 写法**: POSIX 使用 `shutil.rmtree.avoids_symlink_attacks is True` 时的 fd-safe 路径；Windows 使用 owner-local quarantine + identity + reparse classification + Python 3.11 junction behavior。预置 nested junction 必须 pre-publication fail closed；scan-delete race 与其分离。

**独立验证**:

1. **POSIX fd-safe**: §6.3.1 "POSIX 只有在当前解释器直接报告 `shutil.rmtree.avoids_symlink_attacks is True` 时才使用其 Python 3.11 `lstat/open/fstat` fd-safe 路径；调用时不提供吞错/重试 callback。不得用 `os.walk(followlinks=False)` 冒充 fd-safe deletion。" 项目 `.venv` 实测 `avoids_symlink_attacks = True`，fd-safe 路径可用。

2. **Windows quarantine + reparse**: §6.3.1 "Windows 不把 `shutil.rmtree.avoids_symlink_attacks is False` 解释为 'Python 3.11 必然跟随 link' 或 '所有正常 init 必须失败'。Python 3.11 官方 contract 明确 Windows 自 3.8 起不会先删除 directory junction 的 target contents，且 `os.stat(..., follow_symlinks=False)` 会禁用 name-surrogate reparse traversal；owner-local Windows 路径必须在 quarantine 前后及递归删除前用 `st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT` / `st_reparse_tag` 拒绝 root、nested symlink、junction、mount-point 或其它 reparse entry。"

3. **预置 junction vs scan-delete race 不混同**: §8 S3 "job 必须在 scan 前预置 nested directory junction 指向外部 sentinel；按 §6.3.1，这一预置 reparse entry 必须令 transaction 在 publication 前 fail closed，typed diagnostic 必须如实报告当时实际 retained staging/quarantine path、absent path 与精确 failure stage，public config 不得发布，external sentinel 的 bytes 与 filesystem identity 必须不变。'只删除或拒绝 reparse entry 本身而不触碰 target' 只可作为另一个 scan-delete race/syscall-fault 级证明，不能作为预置 junction 场景的同等成功标准。"

4. **平台证据**: §6.3.1 锁定 Python 3.11.15 `shutil.rmtree` 文档的 fd-safe capability 与 Windows junction 说明、`os.stat(..., follow_symlinks=False)` / `st_file_attributes` / `st_reparse_tag` contract，以及项目 `.venv` 的 macOS probe。

5. **普通 Windows symlink skip 约束**: "普通 symlink 若 runner 无创建权限可以按精确 privilege error skip，但必须保留 skip reason，不能替代 junction/reparse 证明。" junction test 与正常 transaction 不得 skip。

**判定**: **closed**。POSIX fd-safe 有直接平台证据，Windows quarantine+reparse 有 Python 3.11 contract 支撑，junction fail-closed 与 scan-delete race 明确分离，skip 约束精确。

---

### F05 — MEDIUM — directory durability 的平台语义必须真实

**Plan 位置**: §6.3.2、§6.4、§8、S3

**Plan 写法**: 精确区分 file content、directory entry、secure deletion、per-root replace 与 rollback；POSIX 拥有文件/目录 sync boundary；Windows 保留普通文件 fsync、same-volume replace、live rollback、isolation 和 typed diagnostics，诚实不承诺等价 parent-directory crash durability。

**独立验证**:

1. **三个事实严格分开**: §6.3.2 "三个事实严格分开：`fsync` 普通文件只提交该文件已写内容；对包含 rename/create/delete 的 parent directory 做 sync 只提交 directory entry/namespace change；symlink/reparse-safe deletion 只防越界或跟随外部 target，不承诺擦除已删除数据块或阻止 forensic recovery。"

2. **POSIX sync boundary**: §6.3.2 详列 publication 前 file fsync → directory sync → validation cleanup 后 parent sync → public replace → workspace-root sync 的完整序列。任一 pre-publication sync failure 按 fault matrix abort/rollback。

3. **Windows 诚实收窄**: §6.3.2 "Windows 的 Python 3.11 `os.fsync` 只为普通文件提供 `_commit()`；Python 3.11 的 `dir_fd` operations 在 Windows 不可用，现有标准库没有与 POSIX parent-directory `fsync` 等价且被本项目直接验证的接口。R12 因此仍对每个 staging 普通文件 `fsync`，继续使用同 volume `os.replace` 作为单个 namespace transition 和 live-process rollback primitive，但明确不承诺 successful return 已把 public/cleanup directory entries crash-durable 到 stable storage，也不因缺少 directory fsync 把正常 Windows init 永久拒绝。"

4. **Windows real job 要求**: S3 "实际 Windows runner 完成 init state smoke"。§10.1 "S3 real Windows normal transaction是 release evidence，不把该收窄伪装成 POSIX 等价。"

5. **前轮 DS-F04 闭合**: parent fsync 只保证目录条目持久化（不保证已删除文件数据块独立持久化）的限定已隐含在 §6.3.2 的精确三事实分离中。

**判定**: **closed**。file/directory/deletion 三事实精确分离，POSIX/Windows 行为分别写清，Windows 收窄诚实且不削弱 isolation/rollback/diagnostics。

---

### F06 — LOW — source/propagation scans 必须随 owner 修正

**Plan 位置**: §8 S2 断言、§9 scans

**Plan 写法**: Service diff 精确限于 4 个 owner/caller/test/README 路径；增加 override consumer、CLI classification/raw-strip、single discovery chain scans；Fins/package/Host/Engine/Tool/runtime/design/deferred ISSUE paths 与 utils 保持 tracked/untracked 零 diff。

**独立验证**:

1. **Service exact allowlist**: §8 S2 验证块 `test "$(git diff --name-only -- dayu/service tests/service | sort)" = "$(printf '%s\n' dayu/service/README.md dayu/service/entrypoint_runtime.py dayu/service/host_assembly.py tests/service/test_host_assembly.py | sort)"`。精确 4 个路径。

2. **Zero-diff scope**: `git diff --exit-code -- dayu/fins dayu/host dayu/engine dayu/tools dayu/runtime dayu/config/models.json dayu/config/prompts/manifests docs/fins/design.md docs/host/design.md docs/engine/design.md docs/tool/design.md docs/ui/design.md pyproject.toml utils`。

3. **Override consumer scan**: §9 `rg -n "fins_workspace_root_override" dayu/cli dayu/service tests/cli tests/service utils`。production non-`None` consumer 只有 R12 init validation。

4. **CLI negative scan**: §9 `rg -n "_is_fins_workspace_bound_provider_config|financial-(read|download|preprocess|upload)-tools|dayu\.fins\.tools\..*provider|pop\([^)]*workspace_root|del [^\n]*workspace_root" dayu/cli/init_workspace.py dayu/cli/commands/init.py`。production 命中为空。

5. **Negative scan**: §9 `rg -n "metadata[-_ ]?only|synthetic|fake[_ -]?provider|test[_ -]?shim" dayu/cli/init_workspace.py dayu/cli/commands/init.py tests/cli/test_init_workspace.py tests/cli/test_init_command.py`。production 命中为空；测试命中只能是"禁止"断言。

6. **Seven production files coverage**: §9 S2 验证块对 `init_catalog.py`、`init_environment.py`、`init_workspace.py`、`commands/init.py`、`arg_parsing.py`、`host_assembly.py`、`entrypoint_runtime.py` 逐文件 `--cov-fail-under=80`。

7. **README trigger**: §8 S3 "根 README 只写最终用户 init 交互...；`dayu/config/README.md` 写当前配置 owner...；`tests/README.md` 写 owner/fault/real-smoke 覆盖。无分层/装配边界变化，不修改 `dayu/README.md`。"

**判定**: **closed**。allowlist 精确、zero-diff 范围完整、override/CLI negative/single-discovery scans 同步、coverage/README trigger 正确。

---

## 4. Closure summary

| Group | Severity | 本轮验证结论 | 状态 |
|---|---|---|---|
| `R12-S2-PR-F01` | HIGH | override 在三类合法 raw root 场景均正确支配 Fins effective root；raw bytes 不变；非 Fins/Web 隔离；owner boundary 最小 | closed |
| `R12-S2-PR-F02` | MEDIUM | fault matrix 10 阶段精确枚举；syscall mock 边界清晰；production seam 禁止明确 | closed |
| `R12-S2-PR-F03` | MEDIUM | retained truth 唯一（staging/container）；diagnostic 含精确 stage/path/`deletion durability unconfirmed`；partial delete 独立 contract | closed |
| `R12-S2-PR-F04` | MEDIUM | POSIX fd-safe 有平台证据；Windows quarantine+reparse 有 Python 3.11 contract；junction fail-closed 与 scan-delete race 分离 | closed |
| `R12-S2-PR-F05` | MEDIUM | file/directory/deletion 三事实分离；Windows 诚实收窄不削弱 isolation/rollback；real Windows job 要求明确 | closed |
| `R12-S2-PR-F06` | LOW | Service exact 4 路径 allowlist；override/CLI negative/single-discovery scans 同步；7 文件 coverage/README trigger 正确 | closed |

**6/6 全部 closed。**

## 5. Rejected/no-fix 保持验证

| Item | 前轮裁决 | 本轮验证 | 状态 |
|---|---|---|---|
| DS-F02 独立修复（partial delete 复制 forensic tree） | REJECT | §6.3.1/§8 只保留可定位 staging + 精确 failure stage/path，不复制/预快照完整取证树。plan 未引入 cleanup journal。 | 保持拒绝 |
| MiMo Finding 003（RESET 双 root snapshot 扩为 single-syscall atomic） | REJECT | §10.1 "两个 managed roots 不能跨 root single-syscall 原子替换。R12 用 same-volume per-root replace、逆序 rollback 和故障测试提供 live-process 可恢复事务"。不扩 Host/process lock/kill/watcher。 | 保持拒绝 |
| Issue 142/151/175/177/178 | 非目标 | §1.3 明确列出。plan 未引入 migration、Write/assets owner、Docling 隔离、截断变更或 storage state lifecycle 变更。 | 保持非目标 |
| Web/WeChat/render | 非目标 | §1.3 "不改变入口、服务装配或渲染行为"。`wechat` 只作为 known manifest 接受 thinking model projection。 | 保持非目标 |
| Topic 8/Topic 9 | 非目标 | §1.3 明确不修改 exception truncation 或统一 tool authorization。 | 保持非目标 |
| Ruff cleanup | 不实施 | §9.2 "禁止清理这 144 项"。R12 只对 changed paths 零诊断和 full fingerprint 零差异负责。 | 保持不实施 |
| Host lock/process kill | 不实施 | §10.1 "R12 不扩展到 Host lock/process discovery/kill"。RESET 前强警告用户。 | 保持不实施 |

## 6. 重点 adversarial 检查

### 6.1 显式绝对/相对 Fins raw root 被 override 支配，但 ordinary runtime / raw bytes / Web / 非 Fins 不变

**验证**: `_effective_fins_workspace_root_config_value`（L1461-L1503）当前在显式绝对 root 时返回 `str(configured_path.resolve())`，忽略调用方 `workspace_root`。这是 PRESERVE 场景下 side effect 逃出 private root 的直接代码证据。

Plan 要求修改后先检查 override。对三类合法 raw root：
- 未配置 → override 支配（当前已用 caller root，加 override 后用 override）
- 显式绝对 → override 支配（当前忽略 caller root，加 override 后用 override）—— **这是 F01 核心反例的修复**
- 显式相对 → override 支配（当前用 caller root 解析，加 override 后用 override）

Raw bytes 不变：override 只改变函数返回值，不修改 `provider_config.config` dict。
非 Fins/Web 不变：`_effective_web_storage_state_dir_config_value` 不消费 override。
Ordinary runtime 不变：`entrypoint_runtime.py` 显式传 `None`。

**结论**: PASS。override 机制在三类场景均正确，隔离边界完整。

### 6.2 Service owner 参数是否最小且无 compat/fallback/CLI provider 猜测

**验证**: `fins_workspace_root_override: pathlib.Path | None = None` 是 keyword-only、默认 `None`、类型精确。现有所有调用方不受影响（使用默认值）。R12 init validation 是唯一 non-`None` consumer。

Plan 明确禁止：
- CLI 复制 `_is_fins_workspace_bound_provider_config` 规则
- CLI 按 provider id/import path/source id 猜 Fins
- 修改 staging raw config
- 引入 schema 字段/兼容分支/fallback/metadata-only discovery/test-only production seam

§9 scan 覆盖 `fins_workspace_root_override` 全部出现位置，production non-`None` consumer 只有 init validation。

**结论**: PASS。参数最小，无 compat/fallback/CLI 猜测。

### 6.3 POSIX fd-safe / Windows quarantine+reparse 是否可实施；预置 junction fail-closed 与 scan-delete race 不得混同

**验证**:

**POSIX**: 项目 `.venv` Python 3.11.15 实测 `shutil.rmtree.avoids_symlink_attacks = True`。Plan 指定使用其 `lstat/open/fstat` fd-safe 路径，不提供吞错 callback，不用 `os.walk(followlinks=False)` 冒充。若 capability 为 `False` 则停止并交 Controller。可实施。

**Windows quarantine+reparse**: Plan 指定 owner-local 路径：
1. 删除前重取 no-follow identity（`st_file_attributes` / `st_reparse_tag`）
2. 同父 `os.replace` 移到 quarantine basename
3. 重取 quarantine identity
4. 只有 identity 匹配且原名称已缺失才递归删除
5. `st_file_attributes & FILE_ATTRIBUTE_REPARSE_POINT` / `st_reparse_tag` 拒绝 reparse entry

Python 3.11 contract：Windows 自 3.8 起不先删除 junction target contents；`os.stat(..., follow_symlinks=False)` 禁用 name-surrogate reparse traversal。可实施。

**预置 junction vs scan-delete race**:
- 预置 junction：§8 S3 要求 scan 前预置 nested junction → transaction 必须 pre-publication fail closed → diagnostic 报告 retained staging/quarantine path、absent path、精确 failure stage → public config 不发布 → external sentinel bytes/identity 不变。不可 skip。
- Scan-delete race：独立证明场景，"只删除或拒绝 reparse entry 本身"只属于此场景的通过标准，不与预置 junction 混同。

**结论**: PASS。两者均有平台证据支撑，可实施；junction fail-closed 与 scan-delete race 明确分离。

### 6.4 Windows durability 收窄是否 truthful

**验证**: Plan §6.3.2 明确：
- Windows `os.fsync` 只为普通文件提供 `_commit()`
- `dir_fd` operations 在 Windows 不可用
- 无本项目直接验证的 parent-directory `fsync` 等价物
- R12 仍对每个 staging 普通文件 `fsync`
- 继续使用同 volume `os.replace` 作为 namespace transition 和 rollback primitive
- **明确不承诺** successful return 已把 directory entries crash-durable 到 stable storage
- 不因缺少 directory fsync 把正常 Windows init 永久拒绝
- S3 real Windows job 必须完成正常 init transaction

这是诚实的收窄：承诺了 process-visible atomic transition、live rollback、isolation 和 typed diagnostics，但不声称未验证的 power-loss directory persistence。S3 real job 证明普通 Windows init 可行。

**结论**: PASS。收窄 truthful，不伪装 POSIX 等价。

### 6.5 Fault matrix / rollback / diagnostic

**验证**: §8 fault matrix 10 行覆盖完整生命周期：
1. staging/validation 前 → 无 public replace，安全 cleanup 或 retained staging
2. validation cleanup identity → pre-publication abort，不递归删除 identity 不匹配对象
3. validation recursive delete → pre-publication abort，报告 actual failing operation/path
4. validation delete 后 POSIX sync → pre-publication abort，staging 存在/child absent/`deletion durability unconfirmed`
5. secret persistence → 不 publish，只报告 env names
6. public backup moves → 逆序 backup→original
7. config publish → 移除/隔离已发布 config，逆序恢复 backups
8. POSIX publication sync → 逆序 rollback + 再次 sync
9. rollback → typed rollback failure，报告精确 stage/truth/backup path
10. post-publication delete → init 仍成功，typed warning
11. post-publication POSIX sync → init 仍成功，`deletion durability unconfirmed`

每个 replace/fsync 边界覆盖 `OSError` + `KeyboardInterrupt`。ENOSPC 只注入能实际抛出它的 boundary。pre/post-publication 边界不混用。

**结论**: PASS。fault matrix 完整、边界精确、diagnostic truthful。

### 6.6 Allowlist / coverage / README / scans

**验证**:

- **Service exact allowlist**: 4 路径（`host_assembly.py`、`entrypoint_runtime.py`、`test_host_assembly.py`、`README.md`）
- **Zero-diff scope**: Fins/package/Host/Engine/Tool/runtime/design/deferred ISSUE paths + `utils` + `pyproject.toml`
- **Seven production files coverage**: `init_catalog.py`、`init_environment.py`、`init_workspace.py`、`commands/init.py`、`arg_parsing.py`、`host_assembly.py`、`entrypoint_runtime.py`，各 `>=80%`
- **Scans**: 14 条 `rg` 命令覆盖 env names、assets/portfolio/.dayu/config、compat/fallback/shim/hasattr/getattr、authorization、Service assembly chain、fins_workspace_root_override、CLI classification/raw-strip、metadata-only/synthetic/fake/test-shim、prewarm forbidden calls、import roots、network clients、Issue/Topic/Web/WeChat/render
- **README**: 根 README 写 init 交互/四态/secret/排障；config README 写 owner/PRESERVE/OVERWRITE/RESET/manifest projection；tests README 写 owner/fault/real-smoke；不改 `dayu/README.md`

**结论**: PASS。allowlist 精确、coverage 门槛明确、scans 完整、README trigger 正确。

### 6.7 三 slices 与 deferred Issue/Topic/Web/WeChat/render 边界

**验证**:
- S1：typed catalog + manifest projection + OS environment owner（4 个新/改文件）
- S2：workspace transaction + 四态 orchestration + Service override（+6 个新/改文件）
- S3：prewarm + POSIX/Windows smoke + README + closeout（+3 个新/改文件）
- 恰好三个 cumulative slices，无第四 slice / 新 sub-WU
- Issue 142/151/175/177/178、Web/WeChat/render、Topic 8/9 全部 §1.3 非目标

**结论**: PASS。三 slice 边界清晰，deferred scope 保持。

## 7. Open questions

**0**。所有 plan 声称的代码路径、side effect、owner 边界、平台 contract 和验证要求均经直接代码/平台证据确认。前轮 open question（`unittest.mock.patch` 是否被 plan 视为 test shim）已由 §8 明确回答。

## 8. Residual risks

| 风险 | 严重程度 | Owner | 跟踪方式 |
|---|---|---|---|
| Windows `setx` 多变量写入不具跨调用事务性 | 低 | `init_environment.py` (S1) | config 不发布 + 只报告已写 env names |
| 两个 managed roots 不能跨 root single-syscall 原子替换 | 低 | §10.1 residual | per-root replace + reverse rollback + fault tests |
| import-only prewarm 依赖 Python import graph | 低 | S3 | test 证明零网络/零外部状态 |
| shell profile 可能含损坏/重复 marker | 低 | `init_environment.py` | fail closed，用户显式修复 |
| repository full Ruff 144 个历史诊断 | 无 | repository owner | R12 只负责 changed paths 零诊断 + fingerprint 零差异 |

以上 residual risks 均已在 §10.1 明确记录，不阻塞 implementation。

## 9. Architecture / best-practice / optimal / overengineering / overcoupling review

### Architecture boundary
**PASS**。`init_workspace.py`（CLI 层 transaction owner）、`init_catalog.py`（CLI 层 catalog/projector）、`init_environment.py`（CLI 层 secret persistence）、`commands/init.py`（CLI 层 orchestrator）。CLI 通过 `workspace_root` + `fins_workspace_root_override` 参数调用 Service effective-config owner；Service 最小修改限于该 owner + ordinary caller，Fins production 零 diff。`dayu/runtime/` 是只读依赖。无反向依赖、无跨层泄漏。

### Best-practice
**PASS**。严格类型签名、中文 docstring、模块级私有辅助函数、无 `Any`/`object`/`hasattr`/`getattr` 补偿、无兼容性 re-export/wrapper/facade。

### Optimal-solution
**PASS**。private validation root 是 credible alternatives 中最优：最小变更（Service effective-config owner 新增一个 keyword-only 参数、ordinary caller 显式传 `None`、direct owner test/README 同步），Fins production 零 diff，保留全部真实验证。替代方案（metadata-only discovery / portfolio 纳入 manifest / discovery 后删除 public side effect / 修改 Fins provider 构造语义）均被正确拒绝。

### Overengineering
**PASS**。三个新模块承载三类不同 owner；不引入通用 transaction engine、provider plugin registry、lifecycle framework、cleanup framework 或 callback protocol。

### Overcoupling
**PASS**。Service/Fins 只通过参数被消费，无双向依赖、无共享可变状态。三个 slices 按 "contract → filesystem → smoke" 自然隔离。

## 10. Conclusion

**`PASS`**

Fixed plan（708 行 / 105,368 字节 / SHA `aa7b50a90c9623ea8dcafe8c4c651665b16b9ee3be76ec8357c4d47977fb2a4c`）高质量闭合了全部 6 个 accepted findings `R12-S2-PR-F01..F06`。

- **F01**（HIGH）：`fins_workspace_root_override` 在三类合法 raw root（未配置/显式绝对/显式相对）场景均正确支配 Fins effective root；raw bytes 不变；非 Fins/Web 隔离；owner boundary 最小且正确。
- **F02**（MEDIUM）：fault matrix 10 阶段精确枚举；syscall mock 边界清晰（允许 `pytest.monkeypatch`/`unittest.mock`，禁止 provider/catalog shim）；production seam 禁止明确。
- **F03**（MEDIUM）：validation child 已删而 POSIX parent sync 失败时 retained truth 唯一（staging/container）；diagnostic 含精确 stage/path/`deletion durability unconfirmed`；partial delete 独立 contract。
- **F04**（MEDIUM）：POSIX fd-safe 有 Python 3.11 平台证据；Windows quarantine+reparse 有 Python 3.11 contract 支撑；junction fail-closed 与 scan-delete race 明确分离。
- **F05**（MEDIUM）：file/directory/deletion 三事实精确分离；Windows 诚实收窄不削弱 isolation/rollback/diagnostics；real Windows job 要求明确。
- **F06**（LOW）：Service exact 4 路径 allowlist；override/CLI negative/single-discovery scans 同步；7 文件 coverage/README trigger 正确。

Rejected/no-fix 保持正确。三 slice 边界清晰。deferred Issue/Topic/Web/WeChat/render 保持非目标。无 open questions。

Plan 可进入 implementation。

## 11. 输出文件

- Review artifact: `docs/reviews/wu-semantic-ownership-01-r12-s2-stop-condition-plan-final-rereview-mimo.md`
- 本文件为唯一新增
- 不修改 plan/code/test/control/其它 artifact
- 不 stage/commit
- 下一入口: Controller validation / implementation authorization
