# WU-SEMANTIC-OWNERSHIP-01 / R12 init workflow plan-fix — AgentCodex

## 0. Gate identity 与结论

- Active work unit 仍是既有 umbrella `WU-SEMANTIC-OWNERSHIP-01`；R12 是同一 WU 的内部 remediation sub-WU，本文不新建 WU。
- Current gate 是 Controller adjudicated `R12 plan-fix`；未进入 implementation、accepted-plan commit 或后续 gate。
- Immutable original plan：483 行 / 41,413 字节 / SHA-256 `6470ec0aafc8214e4fb3f0df88539e4ec97525b992e359bc4abbc75f06b2f5d0`。
- Writable scope 只有修改 `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md` 与新增本 artifact。本轮没有修改 control、已有 review/validation/entry、production、tests 或 README，没有 stage/commit。
- 结论：`R12-PF-01..R12-PF-12` 全部已修复，MiMo `OQ-001/OQ-002` 已吸收；被 Controller 拒绝的实现未进入 plan。
- Gate result：`FIXED / READY_FOR_CONTROLLER_PLAN-FIX_VALIDATION`。

## 1. 完整读取的 authority 与直接证据

| 输入 | 机械证据 | 本轮用法 |
|---|---|---|
| AgentDS complete review | 365 行 / SHA-256 `f83fc2d7058be2941637cd9c43f17ef863940fd055712ee848145b56c1699ff2` | 完整读取 Challenge/F-01..F-10 与 DS OQ |
| AgentMiMo complete review | 236 行 / SHA-256 `88714fc66d964ec54d587ae651210d4a79c62bd099de50830d9fcb0b169fdeec` | 完整读取 FINDING-001..005 与 MiMo OQ-001/OQ-002 |
| Controller adjudication | 142 行 / SHA-256 `73445f3d09c145e34f38dbf9311bd75e534f0f9318df702e127996453a33bc46` | 唯一 PF 接受/拒绝裁决来源 |
| Controller plan validation | 99 行 / SHA-256 `693e76a36cf1aeabc02e10288035cee45dc8cb57f3c08f0b9b857475f12ea520` | mandatory challenge 与 scope 基线 |
| Controller plan-entry validation | 118 行 / SHA-256 `678a1e424c325d8c170dee3d0375e2387149c3c3ff4c4e0440416dafa3a7a489` | authority order、owner 与 no-scope 基线 |

补充直接 CURRENT/OLD 证据：

- Ruff `0.15.11` full JSON 诊断集在 immutable code base 精确为 144 项，原始 stdout SHA-256 连续两次都是 `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`；R12 四个已有 candidate Python path 的 scoped Ruff 是零。
- `dayu.runtime.filelock.file_lock` 明确接受 `timeout_seconds: float | None = None` 和 `create_parent_dirs`；`None` 映射当前第三方无限等待语义。
- `prepare_entrypoint_runtime` 是 async，返回 `EntrypointRuntimeResult`；`prepare_host_admin` 返回 `ServiceHostAdminResult`；Fins builder 返回只注册 processor class metadata 的 `ProcessorRegistry`。这三个 preparation result 都没有 owned close contract。
- package manifest 和 scene 路径证明精确 scene id 是 `prompt`/`interactive`，两者都要求 `fins_default_subject`/`current_time` 字符串 slot。
- OLD init SHA-256 `f23c41835c22514dbead1f7121d64f7b6a010cb64e2527f9e1d80aa75a4f7e8e` 的 `_CUSTOM_OPENAI_TEMPERATURE_PROFILES` 精确给出 custom 八个 temperature；当前 `RunnerOptionHintConfig` 要求 `temperature/top_p/stream` 三字段。

## 2. PF-01..PF-12 before/after evidence

### R12-PF-01 — Ruff gate 可执行且不扩 scope

- Before：immutable original §8 S1/S2/S3 和 §9.2 要求 full Ruff 零错误，与已证实的 144 个历史诊断直接矛盾。
- After：fixed plan §2 lines 88–92 锁定 Ruff 版本、144 项、full JSON SHA 和 candidate-path-zero 事实；§8 每个 slice 有累积 changed-path 零诊断命令；§9.2 lines 423–466 要求 baseline/current JSON count+SHA+`cmp` 逐字节零差异。Full pyright 仍必须 exit 0/零诊断。
- Status：`FIXED`；不清理 144 项，不仅比较 count。

### R12-PF-02 — fresh workspace root 有显式 pre-lock owner

- Before：immutable original §6.3 要求 workspace 已存在，但 FIRST 无人负责创建 lock parent。
- After：fixed plan §3 把 bootstrap 交给 `commands/init.py`；§6.3 lines 259–264 定义路径解析、existing symlink/non-directory 拒绝、RESET No 先于创建、`mkdir(parents=True, exist_ok=True)`、并发 identity 复核、permission/ENOSPC/type-race 失败和“init 不删 workspace root”。S2 lines 342–351 给出编排与测试。
- Status：`FIXED`。

### R12-PF-03 — prewarm invocation 精确且不发明 lifecycle

- Before：immutable original §7 只说 prompt/interactive，未写精确 scene id 和 async boundary；DS 还提出了无直接证据的 generic close 建议。
- After：fixed plan §7 lines 281–288 吸收 MiMo OQ-001/OQ-002：精确 `scene_id="prompt"`/`"interactive"`，一次 `asyncio.run` 进入私有 async helper 后顺序 await，typed request 的空字符串 slots 不伪装业务事实，当前三类 result 无 close/aclose/context-manager contract。S3 line 381 固定接入点。
- Status：`FIXED`；CURRENT 若日后出现真实 closable result 则停止交 Controller，不做反射 fallback。

### R12-PF-04 — publication success 与 cleanup warning 分界

- Before：immutable original §6.4 未说清 backup delete/post-delete fsync 失败是 rollback 还是 warning。
- After：fixed plan §6.4 lines 270–278 把 success boundary 定义为全部 required `os.replace` + parent durability `fsync`；边界前失败 rollback，边界后 no-follow delete/fsync 失败仅 typed warning，精确报告 retained path 或 deletion-durability-unconfirmed path，不 rollback、不改成功 exit。S2 故障测试在 lines 352–353。
- Status：`FIXED`。

### R12-PF-05 — static/dynamic catalog validation 分离

- Before：immutable original §4.1 的“两个 ID 都存在”可被应用到不存在于 package 的 `custom-openai`。
- After：fixed plan §4.1 lines 154–162 分成 13 个非 dynamic pair、package `ollama` template 和 dynamic `custom-openai` 三条互斥校验路径；S1 lines 309–311 分别断言 static mismatch fail-closed 与 custom absence non-error。
- Status：`FIXED`。

### R12-PF-06 — private staging 精确但不成为 public protocol

- Before：immutable original §6.3 只说“同父目录”，没有把 unique/private 和临时名非公开语义同时写清。
- After：fixed plan §6.3 lines 267–268 要求 workspace-root 内的不可预测 unique private staging/backup，与 managed target 同 filesystem 且验证 `st_dev`；名称/prefix 明确不是 public/README/LLM-facing contract。S2 line 351 测试不固定名称。
- Status：`FIXED`。

### R12-PF-07 — lock wait 显式无限且可中断

- Before：immutable original §6.3 提到 timeout/interrupt，但没有固定参数语义。
- After：fixed plan §6.3 line 263 精确调用 `file_lock(..., timeout_seconds=None, create_parent_dirs=False)`，显示等待但不显示 secret，等待 SIGINT 零 publish，已获 token 按现有 typed 语义释放；S2 lines 342/351 覆盖编排与竞争测试。
- Status：`FIXED`；没有 finite magic timeout。

### R12-PF-08 — PRESERVE 只复制 missing files

- Before：immutable original §6.2 写“缺失的文件/目录”，可误实现为 directory merge/empty-directory protocol。
- After：fixed plan §6.2 line 252 只允许 package prompt 普通 missing file，只为它创建 missing parents，不复制空目录且不做目录级 merge；S2 line 347 固定 owner-level 测试。
- Status：`FIXED`。

### R12-PF-09 — init lock 不声称 active Host exclusion

- Before：immutable original §6.3 把锁写成宽泛“进程间互斥”，而 CURRENT Host 不消费 `.dayu-init.lock`。
- After：fixed plan §6.2 line 255 在 RESET 确认前警告停止 active Dayu；§6.3 line 265 明确只是 init-to-init serialization；S2 line 349 断言无 Host lock/process discovery/kill；S3 README line 389 将这一用户边界写入文档；§10.1 把 external writer 竞争作为 residual。
- Status：`FIXED`。

### R12-PF-10 — custom runtime hints 逐值有直接来源

- Before：immutable original §4.2 给 custom 写了 Ollama 的 `(0.6/0.1/...)` temperatures，既不是 OLD custom record，也没有 current projection 说明。
- After：fixed plan §4.2 lines 166–182 逐 hint 引用 OLD custom temperatures `1.0/1.0/0.8/1.0/1.0/1.0/0.5/0.4`，再按当前 `RunnerOptionHintConfig` 与 package 一致语义投影 `top_p=1.0`、普通 stream true/compaction false；明确 catalog 是 current projection owner，不叫做通用 provider default。S1 line 311 逐值测试。
- Status：`FIXED`。

### R12-PF-11 — absent POSIX profile 原子创建 0600

- Before：immutable original §5.2 只有“首次创建用 0600”的暗示，未定义不存在时的发布路径。
- After：fixed plan §5.2 lines 210–213 要求确认 persistence 后才触及 profile，same-parent exclusive private temp 强制 `0600`、write/fsync/原子 `os.replace`，不先创建空 public file，existing mode 保留，symlink/dangling 仍 fail closed；S1 line 312 有直接测试。
- Status：`FIXED`。

### R12-PF-12 — `.dayu` 内部状态仍由 Host/runtime 等 owner 所有

- Before：immutable original §6.1 只说 `.dayu` 是 whole root，没有显式写内部 creation/lifecycle owner。
- After：fixed plan §3 owner table 与 §6.1 line 235 把内部名称、创建、校验、生命周期留给现有 Host/runtime/CLI/artifact typed owners；init 只拥有已确认 RESET 的 whole-root transaction，FIRST/PRESERVE/OVERWRITE 不创建、迁移、枚举、修补或重解释。
- Status：`FIXED`。

## 3. Rejected non-implementation 与 no-fix observations

以下内容按 Controller adjudication 明确不实现：

1. 不清理 144 个历史 Ruff 诊断，不接受 MiMo “顺手修三个 CLI lint”方案；只做 changed-path zero + full exact fingerprint no-delta。
2. 不固定 staging/backup 名称或 prefix 为 public protocol；只承诺 unique/private/workspace-root/same-fs 不变量。
3. 不加 finite magic timeout；显式使用 `timeout_seconds=None` 和现有可中断等待语义。
4. 不加 Host lock、process discovery、kill 或统一进程治理；RESET 只警告用户先停 active Dayu。
5. 不为当前纯 typed/in-memory preparation result 发明 resource close/cache/FD framework；真实 contract 若漂移则停止交 Controller。
6. DS OQ-01 的“把 prewarm 前移 staging”不采用；prewarm 仍是 post-publish warning-only。DS OQ-02 不改变 custom endpoint；仍校验并原样写入完整 URL，不猜 `/chat/completions`。

MiMo OQ-001/OQ-002 不属于上述 no-fix：它们已作为 PF-03 的 code-generatability 精度被吸收。

## 4. Fixed-plan metrics 与 validation

- New fixed plan：558 行 / 56,459 字节 / SHA-256 `37b00dfa00d39fce4ac136e803002a6c0bd61faa86882819001f942dfe1df79b`。
- Plan delta：相对 immutable original 增加 75 行 / 15,046 字节；内容只修复 Controller 裁决的 12 组 plan finding 和相关测试/验证可生成性，没有授权 implementation。
- `git diff --no-index --check /dev/null docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`：exit `1` 仅表示新增 no-index diff，无 whitespace diagnostic。
- `git diff --no-index --check /dev/null docs/reviews/wu-semantic-ownership-01-r12-init-workflow-plan-fix-codex.md`：exit `1` 仅表示新增 no-index diff，无 whitespace diagnostic。
- `git diff --check`：exit `0`，无 diagnostic。
- `git diff --cached --name-only`：空，没有 staged path。
- Scope check：plan-fix entry 已有 Controller-owned control/review/validation 状态全部保留；本 gate 只改 fixed plan 内容并新增本 artifact。Production、tests、README、control 和已有 artifact 无本轮变化。
- Docs decision：本 gate 本身只处理 plan/review artifact，README trigger 属于未授权的 S3 implementation；本轮不更新 README。

## 5. Residual risk、completion status 与 checkpoint

- Windows `setx` 多值不是跨调用 transaction；plan 仍要求 config 不发布、只报已写 env names。
- 多 managed-root publication 是可 rollback 的有序 rename，不是跨 root 单 syscall atomicity。
- Post-boundary backup cleanup 可 warning 并保留精确恢复路径，不改变已成功 publication。
- Init lock 只串行 init；active external Dayu writer 仍需用户在 RESET 前停止。
- Ruff 144 个历史诊断归 repository owner；R12 只承诺 changed-path zero/full fingerprint no-delta。
- 上述残余风险都已有 owner/contract，无 unclassified residual，无 blocking question。
- Completion status：`R12 PLAN-FIX COMPLETE`。
- 下一且唯一允许 checkpoint：`Controller plan-fix validation`。Controller 确认 exact scope/content 后，应把同一 fixed-plan SHA `37b00dfa00d39fce4ac136e803002a6c0bd61faa86882819001f942dfe1df79b` 交 AgentMiMo 和 AgentDS 并发 complete re-review。本轮在此停止，不实现、不 stage/commit。
