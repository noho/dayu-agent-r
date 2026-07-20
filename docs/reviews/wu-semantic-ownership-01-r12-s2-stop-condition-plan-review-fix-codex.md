# WU-SEMANTIC-OWNERSHIP-01 / R12 S2 corrected-plan review-fix

## 1. Gate 身份与结论

- Gate：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` / R12 S2 corrected-plan review-fix；不是新 WU/sub-WU。
- Agent：AgentCodex。
- 权限：plan-only；implementation、S3、aggregate、control update、stage、commit、push、PR 均未授权。
- 结论：`PLAN FIX SELF-CHECK PASS / R12-S2-PR-F01..F06 CLOSED 6/6 / READY FOR CONTROLLER VALIDATION`。
- 唯一修改：`docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`；唯一新增：本 artifact。未修改 control、其它 review、product、test、README 或 workflow。

## 2. Authority 与 plan identity

完整读取并用于裁决：

| Authority | SHA-256 / identity |
|---|---|
| before corrected plan | 634 行 / 81,713 字节 / `1f4df5f942a49a5c95bd60f75d0ef3e8a3cbfacede2c2d8f7ecf3c42a1436715` |
| AgentMiMo final review | 276 行 / 23,704 字节 / `b59e529f6371cee21279124cfe3b8d2e7f7d3c013eab8396652e641563e9bec4` |
| AgentDS final review | 293 行 / 25,633 字节 / `b8e4773047caade4020a1d55847a87bfad47918c2ea33da5ae41b210b3425c32` |
| Controller adjudication | 94 行 / accepted `R12-S2-PR-F01..F06`、rejected/no-fix 2、blocking contradiction 0 |
| initial after fixed plan / Controller follow-up before plan | 708 行 / 104,647 字节 / `913f0fa6fc23b5150719cc9477a55f4f00a21d0b94ad982e24b1575bbce83db2` |
| after Controller follow-up plan | 708 行 / 105,368 字节 / `aa7b50a90c9623ea8dcafe8c4c651665b16b9ee3be76ec8357c4d47977fb2a4c` |

另完整读取 `AGENTS.md`、umbrella optimization control、overdesign Controller discussion、上一轮 stop-condition correction/validation/implementation stop artifacts及相关 direct owner code/tests。当前 worktree 的 S1 四个 untracked product/test 文件与 Controller-owned dirty paths均保留，未被本 gate 编辑。

## 3. 第一性原理与直接证据

动机成立，无 design-truth contradiction：

1. `dayu/service/host_assembly.py::_effective_fins_workspace_root_config_value(...)` 当前在 raw Fins config含显式绝对/相对 `workspace_root` 时优先该值；调用方 private root只在 raw字段缺失时补默认。`tests/service/test_host_assembly.py`又直接锁定 ordinary runtime保留显式 root。因此 PRESERVE raw config可把真实 discovery side effect导向 transaction-private container外，不能降级为 residual。
2. 正确 owner是同文件既有 effective-config classification/precedence boundary。CLI strip raw field或按 provider id/import path/source id猜 Fins都会复制 owner并改变 PRESERVE bytes；schema字段、fallback、compat、metadata-only或test seam同样不成立。
3. 项目 `.venv` 直接 probe为 Python 3.11.15 / macOS，`shutil.rmtree.avoids_symlink_attacks is True`，实现走 `lstat/open/fstat` fd-safe path。Python 3.11官方 `shutil.rmtree` contract同时说明 Windows自3.8起不先删除directory junction target contents；`os.stat(..., follow_symlinks=False)`在Windows禁用name-surrogate reparse traversal，并提供`st_file_attributes` / `st_reparse_tag`。因此不能把 `avoids_symlink_attacks=False` 等同于“Windows rmtree必然不安全”或永久拒绝普通Windows init。
4. Python 3.11官方 `os` contract说明 Windows `os.fsync`映射为文件 `_commit()`，而 `dir_fd` operations只在Unix工作。当前没有本项目直接验证的Python parent-directory sync等价物；最小正确方案是收窄Windows crash-durability承诺，而不是引入通用Win32 filesystem framework或削弱isolation/replace/rollback/diagnostics。

平台证据：

- <https://docs.python.org/3.11/library/shutil.html#shutil.rmtree>
- <https://docs.python.org/3.11/library/os.html#os.stat>
- <https://docs.python.org/3.11/library/os.html#os.fsync>
- <https://docs.python.org/3.11/library/os.html#os.supports_dir_fd>

## 4. Accepted findings closure（6/6）

| Finding | Plan closure | 状态 |
|---|---|---|
| `R12-S2-PR-F01` | §3、§6.4、§8、§9：Service新增plain `fins_workspace_root_override: Path | None` effective-config输入；ordinary runtime显式`None`，R12唯一non-`None` consumer同时传public ordinary root/private Fins override。合法raw未配置/绝对/相对root均由override支配但raw bytes/schema不变；非Fins/Web不受影响。S2 exact allowlist增加唯一Service owner/caller/direct test/README。 | closed |
| `R12-S2-PR-F02` | §8：明确`pytest.monkeypatch` / `unittest.mock` syscall fault injection不属于provider/catalog test shim；禁止production callback/factory/default-callable seam；逐行枚举validation cleanup、publish、rollback、post-publish fault matrix。 | closed |
| `R12-S2-PR-F03` | §6.3.1、§6.4、§8：validation child已删而POSIX parent sync失败时，retained truth唯一是仍存在的staging/container；child/quarantine absent，diagnostic含精确stage/path与`deletion durability unconfirmed`。Partial delete不承诺完整取证树。 | closed |
| `R12-S2-PR-F04` | §6.3.1、§8、S3：POSIX复用fd-safe capability；Windows使用owner-local quarantine + identity + reparse classification + Python 3.11 junction behavior，normal Windows init不依赖`avoids_symlink_attacks=True`。真实预置junction job必须pre-publication fail closed并保留truthful staging/quarantine diagnostic，public config不发布且external sentinel不变；只移除entry仅限独立scan-delete race/fault证明。job不可skip，不造通用FS framework。 | closed |
| `R12-S2-PR-F05` | §6.3.2、§6.4、§8、S3：分开file content、directory entry、secure deletion与per-root replace/rollback；POSIX定义file/directory sync boundary；Windows保留file fsync、same-volume replace、live rollback、isolation/typed diagnostic，明确不承诺等价directory crash durability，并要求真实normal transaction。 | closed |
| `R12-S2-PR-F06` | §8/§9：Service diff精确限于4个owner/caller/test/README路径；增加override consumer、CLI classification/raw-strip、single discovery chain scans；Fins/package/Host/Engine/Tool/runtime/design/deferred ISSUE paths与utils保持tracked/untracked零diff；七个production文件coverage与README trigger同步。 | closed |

Controller validation follow-up 只关闭两处规格卫生，不改变方案、slice或授权边界：

- §10.2 stop condition现与§6.4唯一真实调用一致：staging `RuntimeConfig` 以ordinary `workspace_root=<canonical public workspace>`装配，private `fins_workspace_root_override`无条件支配合法Fins effective root，catalog仍由真实Service discovery产生；历史§15 provenance未改。
- S3 Windows job现把scan前已存在的nested junction锁定为pre-publication fail-closed场景，并把“只移除entry本身”严格限定到另一个scan-delete race/syscall-fault级证明。`R12-S2-PR-F01..F06`仍为`closed 6/6`，design contradiction与blocking questions仍均为`NONE`。

## 5. Rejected/no-fix 与 scope audit

- DS-F02独立方案仍拒绝：partial deletion不复制、不预快照完整forensic tree，不新增cleanup journal；只保留可定位staging与精确failure stage/path。
- MiMo Finding 003仍拒绝：RESET两根snapshot/replace不是single-syscall atomic；保留per-root replace + reverse rollback，不扩Host/process lock、kill、watcher。
- S1→S2→S3仍恰好三个cumulative slices；未新增slice/sub-WU。
- Issue 142/151/175/177/178、Web/WeChat/render、Topic 8/9与统一tool authorization均保持非目标；Fins/package/Host/Engine/Tool/deferred路径零diff contract未削弱。
- Plan未引入CLI-side Fins provider classification、raw config stripping、schema/fallback/compat、synthetic/metadata-only provider、production callback seam或通用filesystem framework。

## 6. Validation、README 与 stop status

- Plan-only gate未运行implementation pytest/coverage/pyright/full Ruff；这些不能证明文本修订，且implementation未授权。
- Direct evidence probe：新增Service Python allowlist `dayu/service/host_assembly.py`、`dayu/service/entrypoint_runtime.py`、`tests/service/test_host_assembly.py` scoped Ruff为零。
- README decision：本gate未修改README；fixed plan把`dayu/service/README.md`列为S2 owner contract触发路径，根/config/tests README仍按S3既有trigger处理。
- Mechanical checks：plan与本artifact各自 `git diff --no-index --check /dev/null <path>` 均exit `1`且stdout为空（仅表示预期整文件diff，无whitespace diagnostic）；workspace `git diff --check` exit `0`；`git diff --cached --name-only`为空。终态status相对entry只新增本artifact并保留plan修改；Controller control、S1四个untracked product/test及既有review artifacts均未被本gate改写。
- accepted closure：`6/6`；rejected paths absent：`PASS`；design contradiction：`NONE`；blocking questions：`NONE`。
- 下一 checkpoint：`Controller validation`；implementation remains unauthorized。
