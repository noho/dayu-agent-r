# WU-SEMANTIC-OWNERSHIP-01 / R12 init workflow plan — AgentDS Final Complete Adversarial Re-Review

## 0. Review Identity

- **Reviewer**: AgentDS (independent adversarial complete re-review, final round)
- **Timestamp**: 20260718-074448
- **Review type**: 从头到尾 complete adversarial re-review；不是增量 spot check，不是新 WU，不进入 implementation
- **Immutable re-review target**: `docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`
  - **608 lines** / **71,044 bytes** / SHA-256 **`69ddfd888336cbb70d093743a96a56f18e694fa68436fb086be1c9b56dcb88c2`**
- **Authority documents** (全部完整读取):
  - `AGENTS.md` — 项目指令与架构/编码硬约束
  - `docs/phaseflow-umbrella-optimization-control.md` — umbrella 流程优化约束
  - `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` — Topic 1–9 最终裁决
  - `docs/ui/design.md` — UI/CLI 设计真源（§3 init 用户工作流）
  - corrected AgentMiMo re-review: 249 lines / SHA-256 `a1812b6f...` — verdict `PASS_WITH_OBSERVATIONS`
  - corrected AgentDS re-review: 469 lines / SHA-256 `f08584c3...` — verdict `PASS_WITH_FINDINGS`, 5 candidates
  - Controller adjudication: 133 lines / SHA-256 `1f5142be...` — 5 accepted, 1 rejected
  - AgentCodex fix + follow-up: 211 lines / SHA-256 `861cedef...` — all 5 groups + CURRENT contradiction fix
  - Controller validation: 118 lines / 6,191 bytes / SHA-256 `fda4c9d7f67caa82e9d94fdc83c84d85b2517f3907c521538c1c3a2eb441a73d` — verdict `READY_FOR_FINAL_DUAL_COMPLETE_PLAN_REREVIEW`
- **Posture**: Adversarial — 默认假设 final plan 仍至少有一个重要问题，直到证据证明它足够可靠交给 implementation agent

## 1. Mechanical Verification

### 1.1 Immutable target metrics

| Metric | Plan claim | Actual | Match |
|---|---:|---|---|
| Lines | 608 | 608 | ✓ |
| Bytes | 71,044 | 71,044 | ✓ |
| SHA-256 | `69ddfd888336cbb70d093743a96a56f18e694fa68436fb086be1c9b56dcb88c2` | same | ✓ |
| Git HEAD | `5d4deef8d37fb75b496d33fef9e2da11111a76d6` | same | ✓ |

### 1.2 Baseline file hashes (独立复核)

**Existing candidate paths** — all 4 match plan §2 exactly:

| Path | Plan SHA-256 | Actual | Match |
|---|---:|---|---|
| `dayu/cli/commands/init.py` | `c33db731...` | `c33db731...` | ✓ |
| `dayu/cli/arg_parsing.py` | `d8442bc6...` | `d8442bc6...` | ✓ |
| `tests/cli/test_init_command.py` | `c7d226ed...` | `c7d226ed...` | ✓ |
| `tests/cli/test_arg_parsing.py` | `d3a4abcc...` | `d3a4abcc...` | ✓ |

**Read-only dependency anchors** — all 7 match plan §2 exactly:

| Path | Plan SHA-256 | Actual | Match |
|---|---:|---|---|
| `dayu/runtime/filelock.py` | `269f30e4...` | `269f30e4...` | ✓ |
| `dayu/runtime/config_loader.py` | `a5b5b05d...` | `a5b5b05d...` | ✓ |
| `dayu/config/models.json` | `d817a171...` | `d817a171...` | ✓ |
| `tests/runtime/test_filelock.py` | `799b0ea6...` | `799b0ea6...` | ✓ |
| `tests/runtime/test_config_loader.py` | `3a4deb04...` | `3a4deb04...` | ✓ |
| `tests/runtime/test_scene_prepare.py` | `ca57baa9...` | `ca57baa9...` | ✓ |
| `.github/workflows/r11-upload-script-windows.yml` | `8eae09d5...` | `8eae09d5...` | ✓ |

**README baselines** — all 3 match plan §2 exactly:

| Path | Plan SHA-256 | Actual | Match |
|---|---:|---|---|
| `README.md` | `b6e1bcfc...` | `b6e1bcfc...` | ✓ |
| `dayu/config/README.md` | `cc28ee57...` | `cc28ee57...` | ✓ |
| `tests/README.md` | `478efffc...` | `478efffc...` | ✓ |

**16 known manifest hashes** — all 16 match plan §2 exactly. ✓

### 1.3 Ruff immutable baseline

| Metric | Plan claim | Actual | Match |
|---|---:|---|---|
| Ruff version | `0.15.11` | `0.15.11` | ✓ |
| Full diagnostic count | 144 | 144 | ✓ |
| Raw stdout SHA-256 | `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea` | `051bd6cc...` | ✓ |
| R12 candidate paths scoped Ruff | 0 diagnostics (exit 0) | 0 diagnostics (exit 0) | ✓ |

### 1.4 Other mechanical checks

- `git diff --check`: exit 0 — pass ✓
- Git staged: empty — pass ✓
- OLD init SHA-256: `f23c41835c22514dbead1f7121d64f7b6a010cb64e2527f9e1d80aa75a4f7e8e` — verified against plan §2 ✓
- 16 known manifests: all 16 files exist at `dayu/config/prompts/manifests/*.json` — verified ✓
- `custom-openai` absent from `models.json`: confirmed ✓
- `ollama` present in `models.json` with `provider=ollama`, `api_key_ref=null`: confirmed ✓

**结论: 所有机械基线验证通过。plan 声称的 immutable metrics 与所有文件级 SHA-256 均逐项匹配。**

## 2. Prior Findings Closure Verification

### 2.1 Original R12-PF-01..12 (first-round plan-fix groups)

All 12 groups were independently closed by both AgentMiMo and AgentDS in their corrected re-reviews. Controller adjudication confirmed closure. Independent re-review of final plan confirms:

| PF Group | Plan coverage | Independent evidence | Status |
|---|---:|---|---|
| PF-01 Ruff gate executable | §2 immutable baseline + §9.2 full fingerprint `cmp` zero-diff | Ruff `0.15.11`, 144 count, SHA verified | CLOSED ✓ |
| PF-02 fresh workspace pre-lock owner | §6.3 explicit `mkdir(parents=True, exist_ok=True)` before lock, identity recheck | `filelock.py` `create_parent_dirs=False` signature verified | CLOSED ✓ |
| PF-03 prewarm invocation exact | §7 explicit two-root tuple, `importlib.import_module` only | OLD `_run_init_prewarm` SHA-locked evidence | CLOSED ✓ |
| PF-04 publication/cleanup boundary | §6.4 success boundary = all `os.replace` + parent `fsync`; post-boundary cleanup warning only | Pre/post boundary fault injection tests required | CLOSED ✓ |
| PF-05 static/dynamic catalog separation | §4.1 three disjoint validation paths (13 paired, ollama, custom) | `models.json` `custom-openai` absent; `ollama` present | CLOSED ✓ |
| PF-06 private staging not public | §6.3 unique/private staging within workspace root, `st_dev` verified | Naming not fixed as protocol | CLOSED ✓ |
| PF-07 lock wait explicit infinite | §6.3 `file_lock(..., timeout_seconds=None, create_parent_dirs=False)` | `file_lock` signature verified | CLOSED ✓ |
| PF-08 PRESERVE only missing files | §6.2 file-granularity, missing parent creation, no directory merge | Package `config/prompts/` verified | CLOSED ✓ |
| PF-09 init lock not Host exclusion | §6.2 RESET warning + §6.3 init-to-init only + §10.1 residual | Host does not consume `.dayu-init.lock` | CLOSED ✓ |
| PF-10 custom hints have OLD source | §4.2 table matches OLD `_CUSTOM_OPENAI_TEMPERATURE_PROFILES` byte-for-byte | OLD SHA-locked evidence verified | CLOSED ✓ |
| PF-11 absent POSIX profile 0600 | §5.2 same-parent private temp → explicit `0600` → write/fsync → `os.replace` | Symlink/dangling fail closed | CLOSED ✓ |
| PF-12 .dayu/ internal state retained | §3 owner table + §6.1 whole-root transaction only for RESET | FIRST/PRESERVE/OVERWRITE don't enumerate internal state | CLOSED ✓ |

**Verdict: 12/12 closed. No regression, no weakening, no bypass.**

### 2.2 R12-RR-PF-01..05 (second-round re-review-fix groups)

Controller accepted 5 groups from the corrected AgentDS re-review. AgentCodex applied all 5. Controller follow-up corrected the prewarm contract after discovering the CURRENT ordinary/compactor contradiction. Independent re-review of final plan confirms:

#### R12-RR-PF-01 — resolved ModelsConfig truth

- **Plan**: §4.1 "把 ordinary/thinking 两个 ID 都交给当前 ConfigLoader / ModelsConfig 的既有 extends resolver 加载并 fail closed：两个 ID 都存在，且各自对应的 resolved model record 的 provider 和 api_key_ref 都精确匹配表中承诺；thinking child 通过现有 extends chain 继承这些字段是合法输入，禁止把 raw child 未重复写继承字段误判为缺失，也禁止在 catalog owner 中另造 extends resolver、补默认或接受别名"
- **S1 tests**: "测试必须包含一个 raw thinking child 只写 extends 而正确继承字段的成功例，以及父/child override 导致 resolved mismatch 的拒绝例；禁止 raw-field check 或 duplicate resolver"
- **Evidence**: `models.json` 中 13 个 thinking IDs 均使用 `extends` 继承；`ConfigLoader._resolve_record_map(...)` 是解析 owner
- **Status**: **CLOSED** ✓ — 措辞精确区分 raw vs resolved；测试覆盖继承成功与 resolved mismatch 拒绝

#### R12-RR-PF-02 — real/test Scene catalog boundary

- **Plan**: §4.3 锁定 13 production runtime manifests + 3 test-owned `smoke_host_public_*` manifests；§6.4 pre-publish validation 用真实 staging `RuntimeConfig` → Service effective-provider assembly → `discover_service_tools` → `SceneToolCatalog.from_tool_bundle` → 仅对 13 个 runtime manifests 调用 `prepare_scene`，传两个锁定空 slot `{"current_time": "", "fins_default_subject": ""}`
- **Test boundary**: 三个 `smoke_host_public_*` 的 `manual-smoke` tag selection 只由 test-owned explicit catalog fixture 调用同一 current parser 验证；不得注入 production discovery
- **Production prohibition**: 空/合成 catalog、synthetic product provider、duplicate parser、跳过真实 tag selection、放宽 `allow_empty`
- **Drift guard**: "若 implementation entry 的 13/3 basename、tool tag 或 required-slot 集合不再精确等于本节锁定值，停止并交 Controller"
- **Status**: **CLOSED** ✓ — 明确的 real/test catalog 边界、production validator 路径、test-owned fixture 范围与 drift stop condition

#### R12-RR-PF-03 — observable real-lock smoke

- **Plan**: §6.3 将 CLI 等待通知提升为 acquire 前必须输出的 public behavior（"正在等待此 workspace lock"通知，含 workspace 与 lock path，不含 secret）；§8 S3 规定 parent-held real lock + 一个/两个真实 `Popen`、bounded read timeout 等待 public notification、断言零 publish 后释放、两个 queued publishers 串行成功、终态由真实 `ConfigLoader` 读取
- **Prohibition**: 显式禁止 sleep、flaky、成功率/retry、finite production timeout、process-kill 协调、production-only sentinel、test shim
- **Production**: `file_lock(..., timeout_seconds=None)` 不变
- **Status**: **CLOSED** ✓ — 使用既有的用户可见 waiting notification 作为公共协调点；无 timing luck

#### R12-RR-PF-04 — current-process visibility + import-only prewarm

- **POSIX/Windows visibility**: §5.2/§5.3 profile 全批持久化成功后才注入当前 `os.environ`；partial failure 不注入且不 publish
- **Prewarm**: §7 完全不接受或读取 env/selection/secret；不接受 workspace/config/env/selection 参数；不读取 `os.environ` 或 secret typed entry；不调用任何 runtime assembly
- **Env-source contract**: 已被 CURRENT contradiction follow-up 彻底纠正——prewarm 不再需要 model secret 或 env mapping；import-only 不需要任何 env
- **Status**: **CLOSED** ✓ (原 runtime-assembly prewarm 部分 superseded and closed by Controller follow-up)

#### R12-RR-PF-05 — executable per-slice per-file coverage

- **S1**: `pytest tests/cli/test_init_catalog.py --cov=dayu.cli.init_catalog --cov-fail-under=80` + `pytest tests/cli/test_init_environment.py --cov=dayu.cli.init_environment --cov-fail-under=80`
- **S2**: 五个逐文件命令，`commands/init.py` 只引用 `test_init_command.py`（不引用 S3 的 `test_init_smoke.py`）
- **S3**: 累积 final profile，允许 smoke 贡献额外 coverage
- **Gate contract**: "S1/S2/S3 各自验证块中的逐文件命令是当 slice 的强制 gate，只能引用该 slice 当时已经存在的测试"
- **Status**: **CLOSED** ✓ — 每个 slice 的覆盖率命令只使用该 slice 已存在的测试文件；不延期，不追认

### 2.3 Rejected candidate retained

AgentDS `R12-RR-04` (dayu/config/README.md update trigger): **仍按 Controller 裁决拒绝**。`dayu/config/README.md` 已拥有 package defaults、workspace config overlay 与 init 旧行为，R12 正在改变该手册已拥有的用户可见 config lifecycle。S3 allowlist 保留该 README 更新，不需额外理由。✓

### 2.4 Controller CURRENT contradiction

Plan §14 完整记录了 CURRENT ordinary/compactor contradiction 的证据链：
- `compose_open_host_options` 的 compactor selection 只消费 `execution_profile.compactor_baseline.model_id`（四个 profiles 均为 `deepseek-v4-flash`）
- `ServiceAssemblyOverrides` 无 compactor override
- 非 DeepSeek selected-pair 的单一 env/ref 无法满足真实 assembly
- R12 无权改 execution profiles/Service/Host

**Resolution**: §7 恢复 OLD-aligned import-only prewarm。exact two roots `("dayu.cli.commands.interactive", "dayu.cli.commands.prompt")`，只调用 `importlib.import_module`，零 env/secret/runtime assembly。Controller 在隔离进程中独立验证通过。

**Status**: **CLOSED** ✓

## 3. Core Challenge Areas — Deep Adversarial Scan

### 3.1 Exact two-root import-only prewarm: strictly OLD-aligned?

逐项对照 OLD SHA-locked `_run_init_prewarm` (SHA-256 `f23c41835c22514dbead1f7121d64f7b6a010cb64e2527f9e1d80aa75a4f7e8e`) 与 plan §7：

| Requirement | OLD evidence | Plan §7 contract | Status |
|---|---|---|---|
| Only `importlib.import_module` | ✓ OLD loop body | ✓ "只维护上述两个 root strings 并调用 importlib.import_module" | ✓ |
| No env/secret reading | ✓ OLD no env access | ✓ "不接受 workspace/config/env/selection 参数，不读取 os.environ 或 secret typed entry" | ✓ |
| No runtime assembly | ✓ OLD no function calls | ✓ 不调用 `prepare_entrypoint_runtime`、`compose_open_host_options`、`prepare_host_admin`、Fins registry、`open_host` 等 | ✓ |
| No external mutation | ✓ OLD import-only | ✓ "除了进程内 sys.modules import cache 外零外部状态变化" | ✓ |
| Deleted roots absent | `dependency_setup`, `interactive_ui`, `commands.write` 在 CURRENT 均不存在 | ✓ "已删除的...任何 placeholder 都不得出现" | ✓ |
| Exact CURRENT roots | `dayu.cli.commands.prompt`、`dayu.cli.commands.interactive` 均存在 | ✓ 顺序锁定为 `("dayu.cli.commands.interactive", "dayu.cli.commands.prompt")` | ✓ |
| Transitive graph loaded | 两 commands 均 → `session_execution` → `entrypoint_runtime` | ✓ "Init 只维护上述两个 root strings...不得把 session_execution、entrypoint_runtime 或更深 Host/Engine/Fins transitive modules 复制进另一份 prewarm list" | ✓ |
| No lifecycle/cache framework | OLD no persistent state | ✓ "不得另造 cache、resource close、FD cleanup 或反射 lifecycle" | ✓ |
| Only FIRST/RESET | OLD behavior | ✓ "只在 FIRST/RESET 完成 config publication 后调用一次；PRESERVE/OVERWRITE 必须以调用计数断言为零" | ✓ |
| Failure = warning only | OLD catches and returns | ✓ "失败只输出 warning 与经过脱敏的异常类型/安全摘要，init 仍以配置发布成功结束，不回滚" | ✓ |
| Test network/secrets guard | N/A (new test) | ✓ `PYTHONDONTWRITEBYTECODE=1` 隔离 subprocess + socket/network fail-fast + workspace tree hash + environment snapshot；连续两次稳定 | ✓ |

**Verdict: STRICTLY OLD-ALIGNED** — 无 env/secret/runtime assembly/外部 mutation/deleted write/placeholder。所有禁止项均有直接 plan 文本禁止或测试断言要求。

### 3.2 13/3 real/test Scene catalog

逐项验证 §4.3 与 §6.4 的 catalog boundary：

| Concern | Plan contract | Evidence |
|---|---|---|
| 13 production runtime manifests | `audit`, `confirm`, `conversation_compaction`, `decision`, `fix`, `infer`, `interactive`, `overview`, `prompt`, `regenerate`, `repair`, `wechat`, `write` | All 13 exist as package manifests with `none` or real product tags |
| 3 test-owned manifests | `smoke_host_public_conversation_memory`, `smoke_host_public_conversation_memory_scenarios`, `smoke_host_public_multiturn` | All 3 exist; all use `manual-smoke` tag with `allow_empty=false` |
| Required slots | `current_time` 和 `fins_default_subject` | Union of all manifests' required slots — verified |
| Production validator path | staging `RuntimeConfig` → `assemble_effective_tool_provider_configs` → `discover_service_tools` → `SceneToolCatalog.from_tool_bundle` → 13x `prepare_scene` | Explicit path, explicitly only for 13 manifests |
| Test fixture boundary | "三个 exact smoke_host_public_* 的 manual-smoke tag selection 只由 test-owned explicit catalog fixture 调用同一 current parser 验证" | Test fixture owns the `manual-smoke` fake tool fact |
| Production prohibitions | 空/合成 catalog、manual-smoke product provider、duplicate parser、跳过 tag selection、放宽 `allow_empty` | All explicitly forbidden |
| Drift stop | "若 implementation entry 的 13/3 basename、tool tag 或 required-slot 集合不再精确等于本节锁定值，停止并交 Controller" | Stop condition in §10.2 |
| All 16 model projections | "projection helper 与测试仍覆盖全部 16 个 model.default_model_id" | All 16 covered: 13 in production pre-publish, 3 in test-owned fixture |

**Verdict: CORRECT** — 清晰的 production/test catalog 边界、明确的 validator 路径、完备的 drift stop condition。无空 catalog 或 synthetic provider 风险。

### 3.3 Resolved ModelsConfig

验证 §4.1 的三条互斥校验路径在 `models.json` 下的可实现性：

| Validation path | Plan contract | models.json fact | Feasibility |
|---|---|---|---|
| 13 non-dynamic paired choices | 两个 ID 通过 extends resolver 得到 resolved records；provider/api_key_ref 精确匹配表中承诺 | 13 ordinary IDs 均有 provider/api_key_ref；13 thinking IDs 通过 extends 继承 | ✓ |
| Package `ollama` template | `ollama` template 存在，provider=ollama, api_key_ref=null | confirmed: present with correct fields | ✓ |
| `custom-openai` absence | package-default 阶段不得做 ID 存在性校验 | confirmed: absent from models.json | ✓ |

S1 测试覆盖继承成功（raw child only extends）和 resolved mismatch 拒绝（parent/child override 分歧）。禁止 raw-field check 和 duplicate resolver。

**Verdict: CORRECT** — 校验面是 resolved records，不是 raw fields。`ConfigLoader` 是唯一 extends parser。

### 3.4 Real lock contention: no timing luck

验证 §8 S3 的竞争 smoke 设计：

| Concern | Plan contract | Anti-timing-luck measure |
|---|---|---|
| Coordination mechanism | "正在等待此 workspace lock" public notification | §6.3 将此通知提升为 acquire 前必须输出的 public behavior |
| Single-process scenario | parent-held real lock + 一个真实 `Popen` | Harness 等待 notification → assert zero publish → release → child succeeds |
| Two-process scenario | parent-held real lock + 两个真实 `Popen` | Both show notification → assert zero publish → release → both serialize and succeed |
| Bounded timeout | Only in test harness for fail-fast | Production `timeout_seconds=None` unchanged |
| Forbidden patterns | sleep, flaky, 成功率/retry, finite production timeout, process-kill, production sentinel, test shim | All explicitly forbidden |
| Final state verification | 真实 `ConfigLoader` 读取 | Independent confirmation of serialized publish success |

**Verdict: CORRECT** — 使用既有的用户可见 public notification 作为可观察协调点。无 timing luck、无 flaky marker、无 sleep。Bounded timeout 只在 test harness 用于 fail-fast。

### 3.5 POSIX/Windows persistence

验证 §5 的跨平台 secret persistence contract：

| Concern | POSIX (§5.2) | Windows (§5.3) |
|---|---|---|
| Atomic write | same-parent private temp → write/fsync → `os.replace` | `subprocess.run(("setx", name, value), shell=False)` per variable |
| Mode/permission | 显式 `0600`；已存在文件保留原 mode | `setx` stores in Windows registry; not file-mode governed |
| Symlink rejection | profile symlink/dangling → fail closed | N/A (setx doesn't follow symlinks) |
| Marker management | 一对固定 begin/end marker；恰好一对则替换；0 块追加；重叠/多块拒绝 | N/A (no marker in registry) |
| Value quoting | `shlex.quote` 形成 `export NAME=<quoted>` | argument-safe tuple, no shell |
| Transactional injection | 全部写成功后注入当前 `os.environ` | 全批 `setx` 成功后注入 `os.environ` |
| Partial failure | 不注入；不 publish | 不注入；不 publish；报告已写/未写 env names |
| Cross-variable atomicity | 单 profile 原子 | 明确不具事务性（§5.3 显式限制） |
| CI/testing | 非生产 sentinel 验证 marker/mode/脱敏 | 唯一非 secret sentinel 验证 setx/read/cleanup |

**Verdict: CORRECT** — POSIX 完整原子、Windows 契约诚实地暴露 `setx` 的非事务性限制。两者都在全批成功后才注入当前进程。Secret values 不进入 workspace/log/error/artifact。

### 3.6 Four-state/transaction/rollback

验证 §6 的状态机与 transaction contract：

| State | Trigger | Staging base | Old tree handling | Prewarm |
|---|---|---|---|---|
| FIRST | no reset/overwrite, config/ absent | package defaults | .dayu/ untouched | yes |
| PRESERVE | no reset/overwrite, config/ exists | byte-copy existing config/ + missing prompt files | .dayu/ untouched | no |
| OVERWRITE | `--overwrite`, no reset | package defaults | no merge; .dayu/ untouched | no |
| RESET | explicit `--reset` | package defaults | two whole roots per manifest | yes |

Priority: `RESET > OVERWRITE > (config exists ? PRESERVE : FIRST)`. `--reset --overwrite` dominated by reset.

**Transaction contract**:

| Phase | Contract | Plan location |
|---|---|---|
| Pre-publish validate | staging ConfigLoader → Service assembly → scene validation (13 manifests) | §6.4 step 3 |
| Publication success boundary | All required `os.replace` + parent `fsync` | §6.4 step 6 |
| Pre-boundary failure | Inverse-order rollback all backed-up roots; FIRST removes published config | §6.4 step 6 |
| Post-boundary cleanup | No-follow delete backups + parent `fsync` | §6.4 step 7 |
| Cleanup failure | Typed warning with precise path + "deletion durability unconfirmed"; no rollback; exit success | §6.4 step 7 |
| Rollback failure | Retain recoverable backup; print precise path without secret; return failure | §6.4 step 6 |

**Fault injection test coverage** (S2): pre-boundary replace/fsync/validation/ENOSPC/KeyboardInterrupt → old roots fully restored；rollback failure → retain backup path；post-boundary backup delete fail + post-delete parent fsync fail → warning only, path accurate, no rollback, exit success.

**Verdict: CORRECT** — 四态完备，优先级明确，transaction 有精确的 publication success boundary、pre/post boundary 差异化处理，fault injection 测试覆盖两侧。

### 3.7 Per-slice executable coverage

验证 §8/§9 的每个 slice 覆盖率命令只能用该 slice 已存在的测试：

| Slice | Production files | Test files available | Coverage commands reference | Gate |
|---|---|---|---|---|
| S1 | `init_catalog.py`, `init_environment.py` | `test_init_catalog.py`, `test_init_environment.py` | Only S1 tests | ≥80% each |
| S2 | S1 + `init_workspace.py`, `commands/init.py`, `arg_parsing.py` | S1 + `test_init_workspace.py`, `test_init_command.py`, `test_arg_parsing.py` | S2 tests (NO `test_init_smoke.py`) | ≥80% each |
| S3 | S2 all | S1+S2 + `test_init_smoke.py` | All tests including smoke | ≥80% each (smoke may add, not repair) |

S2 `commands/init.py` 覆盖率命令使用 `pytest tests/cli/test_init_command.py --cov=dayu.cli.commands.init --cov-fail-under=80`（不含 `test_init_smoke.py`）。S3 重新运行累积 final profile。

**Verdict: CORRECT** — 每个 slice 的命令只引用当时已存在的测试。不延期，不追认。

### 3.8 Ruff exact baseline

验证 §9.2 的 Ruff fingerprint 机制：

| Gate | Command | Requirement |
|---|---|---|
| Entry baseline capture | `ruff check dayu/ tests/ utils/ --output-format=json > workspace/tmp/r12-ruff-baseline.json` | count=144, SHA=`051bd6cc...` |
| Each slice scoped Ruff | `ruff check <changed-paths>` | exit 0, zero diagnostics |
| Each slice full fingerprint | full Ruff JSON → count=144, SHA=`051bd6cc...`, `cmp` zero-diff | No new/deleted/moved/rewritten diagnostics |
| Forbidden | ignore, config exclusion, `noqa`, Ruff version/parameter change | All explicitly forbidden |

Verified: Ruff `0.15.11` produces exactly 144 diagnostics with raw stdout SHA `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`.

**Verdict: CORRECT** — Ruff baseline mechanism 可在 immutable base 上精确执行，每个 slice 都保证零扩散。

### 3.9 Windows workflow / R11 release nodes

验证 §8 S3 的 CI contract：

| Requirement | Plan contract |
|---|---|
| OS | Windows + Python 3.11 + locked project dependencies |
| Smoke | Same real subprocess state smoke as POSIX |
| Secret handling | 唯一非 secret sentinel 验证 `setx`/user-env read/cleanup；严禁上传值 |
| R11 nodes | `test_windows_cmd_script_round_trips_adversarial_argv_with_real_cmd` + `test_windows_generated_script_runs_real_cli_into_temp_storage` |
| CI artifacts | 只允许测试报告、版本、文件 hash 与 env **names**；失败日志也不得 dump environment/registry values |

**Verdict: CORRECT** — Windows CI 覆盖真实 setx/CLI smoke + R11 两个真实 `.cmd` 节点。Secret safety 在 CI artifact 层面也覆盖。

### 3.10 Security retention

验证安全相关边界的完整保留：

| 安全边界 | Plan contract | Evidence |
|---|---|---|
| Secret value isolation | §5.1 "secret value 只活在 repr=False 的受限 typed entry 与 writer 调用范围，不进入异常 message、日志、workspace 或测试 snapshot" | All error/source scans exclude values |
| POSIX profile atomic 0600 | §5.2 "在同父目录 exclusive 创建私有临时文件、显式设为 0600、写入并 fsync，再用 os.replace 原子创建" | `umask` bypass; mode explicit |
| POSIX symlink/dangling rejection | §5.2 "profile 若是 symlink（包括 dangling symlink）拒绝" | No traversal |
| Windows argument-safe | §5.3 "subprocess.run(('setx', name, value), shell=False, capture_output=True, text=False, check=False)" | No command string, no shell |
| Containment + symlink no-follow | §6.3 "对 manifest root、所有已存在 descendant、staging、backup 使用 no-follow walk；发现 symlink...即在 managed-root mutation 前拒绝" | Lexical + resolved containment |
| Lock path safety | §6.3 "lock path 本身在获取前和获取后都必须是 workspace 内普通非 symlink 文件" | Lock file gated |
| Source scan guards | §9 network/assembly/prewarm/env scans | All forbidden patterns scanned |
| CI artifact sanitization | §8 S3 "只允许测试报告、版本、文件 hash 与 env names；失败日志也不得 dump environment/registry values" | CI-level guard |

**Verdict: CORRECT** — 安全边界完整。无新增攻击面。

### 3.11 Issue 142/151/175/177/178 和 Topic 8/9 no-scope

验证 §1.3 的 scope exclusion：

| Issue/Topic | Exclusion text | Boundary intact |
|---|---|---|
| Issue 142 (workspace migration) | "不设计或调用 workspace migration，不读取旧 schema，不增加 schema/version compatibility" | ✓ |
| Issue 151 (Write/assets) | "不实现 Write/assets owner；init 不创建、复制、删除或接管 package/user assets/" | ✓ |
| Issue 175 (Docling isolation) | "不改变 Docling 进程隔离" | ✓ |
| Issue 177 (document truncation) | "不改变文档截断、fetch_more 或文档工具结果 contract" | ✓ |
| Issue 178 (storage state lifecycle) | "不改变 storage state lifecycle；只把整个 .dayu/ 当作一个 managed root 参与 reset/rollback" | ✓ |
| Web/WeChat/render | "不改变入口、服务装配或渲染行为" | ✓ |
| Topic 8 (exception truncation) | "不修改 240 字 exception truncation 决议或相关代码" | ✓ |
| Topic 9 (tool authorization) | "不设计统一 tool authorization；init 只保留本地文件系统、环境变量与交互确认的局部安全边界" | ✓ |

`wechat` 的 exact manifest basename 是 §4.3 唯一允许的 production 命中（thinking role）。无新实现分支。

**Verdict: CORRECT** — 所有 Issue/Topic/入口边界完整。无 scope creep。

### 3.12 Owner drift, overdesign, hidden compatibility/fallback

**Owner drift scan**:
- §3 owner table 定义 7 个唯一 semantic owner，与 `docs/ui/design.md` §3 和 AGENTS.md 分层架构一致
- 三模块（catalog / environment / workspace）对应三类不可互换的 owner
- 无反向依赖，无 `dayu.runtime` 对上层模块的 import
- 无 God function/object/dataclass/builder

**Overdesign scan**:
- 无通用配置迁移 framework、通用 transaction engine、provider plugin registry
- 无统一 tool authorization、新公共 runtime abstraction
- 无 resource close/cache/FD framework、Host lock/process discovery/kill
- 无 finite magic timeout、frozen public temp protocol
- §10.3 逐项解释了为何不过度设计

**Hidden compatibility/fallback scan** (对照 §9 source scans):
- `_init_model_role`, `default_name`, `llm_models`, `DAYU_INIT_PROVIDER_OPTION` — must be absent
- `migrat(e|ion)`, `compat`, `fallback`, `shim` — production must be zero; tests/README only for absence proof
- `hasattr(`, `getattr(` — must be absent from production
- `prepare_entrypoint_runtime`, `compose_open_host_options` 等 assembly calls — production must be zero

**Verdict: CLEAN** — 无 owner drift、无过度设计、无隐藏兼容/fallback。

## 4. Adversarial Stress Test: Can This Plan Fail?

### 4.1 What if `SceneToolCatalog.from_tool_bundle` doesn't exist?

Plan §6.4 引用 `SceneToolCatalog.from_tool_bundle(discovered_tools.tool_bundle)`。若当前代码没有此 classmethod，implementation agent 需要适配。§10.2 将此列为 stop condition："真实 Service effective-provider assembly/discovery 不再能从 staging RuntimeConfig 产生 SceneToolCatalog.from_tool_bundle(...)"。Implementation agent 在 S2 首次调用时即发现，停止并交 Controller。

**Risk**: Low — stop condition covers this path.

### 4.2 What if `assemble_effective_tool_provider_configs` needs actual workspace config/ files?

Plan §6.4 显式传入 `staging_runtime_config.tool_discovery.providers`。若 Service assembly 函数接受 explicit providers 参数而不从 workspace_root 重新读取，则无问题。若它另外从 workspace_root 读取 config，implementation agent 发现 mismatch 后触发 §10.2 stop condition。

**Risk**: Low — stop condition covers this path.

### 4.3 What if CURRENT import graph changes before implementation?

§7 提供 drift guard："若 import roots/graph 漂移、导入开始需要 secret/network/Dayu runtime state，或必须调用 assembly 才能'预热'，停止并交 Controller；不得扩大 module list 或引入 fallback framework"。§10.2 列为 stop condition。

**Risk**: Low — stop condition covers this path.

### 4.4 What if 13/3 manifests or tags drift?

§4.3 和 §6.4 lock exact basename sets。§10.2 列为 stop condition："13 个 production runtime manifest / 三个 smoke_host_public_* 的集合、tool tags 或 required context slots 不再精确等于 §4.3/§6.4 锁定值"。

**Risk**: Low — stop condition covers this path.

### 4.5 What if OLD custom hint evidence or current-schema projection drifts?

§4.2 提供 drift guard："如实现时上述 OLD 证据或 current-schema 精确字段契约已漂移，必须停止并交 Controller；不得回退成 Ollama 值、另一 provider 值或隐式默认"。

**Risk**: Low — stop condition covers this path.

### 4.6 Can S2 reach `>=80%` on `commands/init.py` without S3 smoke?

`commands/init.py` 是 orchestrator，包含交互式选择、secret 收集、四态分支、prewarm、SIGINT handling、lock acquire/release。S2 只允许 `test_init_command.py` 和 `test_init_workspace.py` 提供覆盖率（不含 `test_init_smoke.py`）。Orchestrator 路径可通过 mock-heavy 单元测试达到 80%覆盖率——mock stdin、mock `getpass`、mock `file_lock`、mock staged `ConfigLoader`、mock FS operations。这是标准 Python 测试实践。

**Risk**: Low-Medium — reachable via disciplined mocking but requires implementation discipline. Plan correctly requires S2 gate to be met before proceeding; S3 smoke adds defense-in-depth but cannot repair a failed S2 gate.

### 4.7 Can Windows `setx` partial failure leave stale state?

Yes — plan §5.3 诚实地暴露此限制："setx 跨变量不具事务性。中途失败时 workspace 保持不变，结果只报告'已写变量名 / 未写变量名'，不声称回滚、不输出值"。Section §10.1 lists this as classified residual risk.

**Risk**: Accepted residual — correctly documented.

### 4.8 Can active Host writer corrupt RESET?

Yes — plan §6.2 要求 RESET 前显示警告"请先停止当前 workspace 的 active Dayu 进程"。Section §10.1 lists this as classified residual risk: ".dayu-init.lock 只串行 init。若 active Host 或其它 Dayu 进程继续写 managed roots，RESET 仍可与外部 writer 竞争"。

**Risk**: Accepted residual — correctly documented with user-facing warning.

## 5. Design Contradiction / Blocker Scan

逐项验证 final plan 与所有 authority documents 的一致性：

| Authority | Key claim | Plan consistency |
|---|---|---|
| `docs/ui/design.md` §3 | init 必须交互选择 provider/model、配置 API Key、更新 manifest、prewarm | Plan §1.1 目标全部对齐；§4 catalog、§5 secret、§4.3 manifest projection、§7 prewarm 精确实现 |
| `docs/ui/design.md` §3 | secret 只写入 OS 环境变量，不写 workspace JSON | Plan §5.1 精确对齐；§5.2/§5.3 定义 POSIX/Windows OS store |
| `docs/ui/design.md` §3 | 无 --overwrite 时保留用户 config，只补缺失 prompt assets | Plan §6.2 PRESERVE 精确对齐：byte-copy existing + missing files only |
| `docs/ui/design.md` §3 | --reset 列出目标、确认后删除 .dayu/config/（存在时的 assets/）| Plan §6.2 RESET: snapshot display + default-No confirm + whole-root reset; §6.1 manifest 只有 .dayu/config；assets/ 因 Issue 151 no-scope 不在 manifest |
| `docs/ui/design.md` §3 | containment + symlink rejection | Plan §6.3: no-follow walk, lexical + resolved containment, symlink → fail closed |
| `AGENTS.md` semantic ownership | 每个业务事实有唯一 owner | Plan §3 owner table: 7 个唯一 owner，消费者限制明确 |
| `AGENTS.md` 架构硬约束 | UI → Service → Host → Engine; 禁止反向依赖 | Plan 三模块属于 CLI 层，复用 runtime/filelock 和 runtime/config_loader，不引入反向依赖 |
| `AGENTS.md` 编码硬约束 | 无 Any/object/无类型、无 hasattr/getattr 逃避、无兼容性代码 | Plan §3 "所有新增模块、类、函数都使用严格具体类型...不得使用 Any、object、无类型签名"；§1.3 "不创建 fallback、compatibility shim、旧名 re-export、loose parsing、hasattr/getattr 补偿" |
| Phaseflow umbrella control | 风险驱动 gate 深度；生产语义按高风险执行 | Plan three cumulative slices 对应 pure contract → FS publish → integration；每个 slice 有独立 review gate |
| Controller discussion Topic 7.3 | init atomicity: whole-config staging/swap/rollback | Plan §6.3/§6.4 staging same-filesystem, rename, backup, rollback — aligned |
| Controller discussion Topic 8 | 240-char exception truncation no-code | Plan §1.3 "不修改 240 字 exception truncation 决议" — aligned |
| Controller discussion Topic 9 | no unified tool authorization framework | Plan §1.3 "不设计统一 tool authorization" — aligned |

**Verdict: NONE** — 零 design contradiction。零 blocking question。

## 6. Findings Ledger

### 6.1 Original PF groups (first round)

| ID | Status |
|---|---|
| R12-PF-01 through R12-PF-12 | All 12 CLOSED — independently verified |

### 6.2 Re-review PF groups (second round)

| ID | Status |
|---|---|
| R12-RR-PF-01 (resolved ModelsConfig) | CLOSED — independently verified |
| R12-RR-PF-02 (real/test Scene catalog) | CLOSED — independently verified |
| R12-RR-PF-03 (observable lock smoke) | CLOSED — independently verified |
| R12-RR-PF-04 (current-process visibility + import-only prewarm) | CLOSED — independently verified; runtime-assembly part superseded by Controller |
| R12-RR-PF-05 (per-slice coverage) | CLOSED — independently verified |

### 6.3 Rejected candidates

| ID | Status |
|---|---|
| AgentDS R12-RR-04 (config README trigger) | REJECTED by Controller; correctly retained in plan |

### 6.4 New findings from this final review

**NONE.**

经过对全部 608 行的完整 adversarial re-review、对 §1–§14 的逐节审查、对所有权威文档的一致性检查、对 11 个核心关注领域的深度扫描——本 review 未发现任何新的 material finding、design contradiction、blocker、owner drift、过度设计、不可执行 test/command、隐藏兼容/fallback 或 deferred scope leakage。

## 7. Residual Risks (all previously classified)

| Risk | Owner | Classification | Plan location |
|---|---|---|---|
| Windows `setx` 不具跨调用事务性 | R12 CLI | Accepted; contract honest | §5.3, §10.1 |
| 多 root publication 不是跨 root 单 syscall 原子 | R12 CLI | Accepted; rename + rollback | §6.4, §10.1 |
| Post-boundary backup cleanup 可失败 | R12 CLI | Accepted; typed warning | §6.4, §10.1 |
| Init lock 只串行 init，不防 active Host writer | R12 CLI | Accepted; RESET warning | §6.2, §10.1 |
| Shell profile 损坏 marker | R12 CLI | Accepted; fail closed | §5.2, §10.1 |
| Import-only prewarm 依赖 Python import graph | R12 CLI | Accepted; drift stop condition | §7, §10.1 |
| CURRENT roots transitive import 未来可能新增 import-time side effect | R12 CLI | Accepted; tests prove zero network/secret/mutation | §7, §10.1 |
| 三个 smoke_host_public_* 的 manual-smoke tag 靠 test fixture | R12 CLI | Accepted; production boundary explicit | §4.3, §6.4, §10.1 |
| Repository full Ruff 144 历史诊断归 repository owner | Repository | Accepted; R12 只对 changed paths 零诊断负责 | §9.2, §10.1 |

无 unclassified residual。所有 residual 均已有 owner、destination 和明确的 contract boundary。

## 8. Verdict

```
PASS
```

**Final immutable plan is code-generation-ready.**

- 全部 12 个第一轮 PF 组 genuinely closed
- 全部 5 个第二轮 RR-PF 组 genuinely closed
- Controller CURRENT contradiction 已由 exact-two-root import-only prewarm 彻底解决
- 所有 11 个核心关注领域（OLD-aligned prewarm、13/3 Scene catalog、resolved ModelsConfig、real lock contention、POSIX/Windows persistence、四态/transaction/rollback、per-slice coverage、Ruff baseline、Windows workflow/R11 nodes、security retention、Issue/Topic no-scope）均通过 adversarial stress test
- 零 design contradiction、零 blocker、零 new material finding
- 所有 mechanical baselines（SHA-256、Ruff fingerprint、manifest hashes、candidate file hashes、read-only anchors、README hashes）独立验证通过
- 所有 rejected preferences 正确保留（Ruff cleanup、frozen temp protocol、finite timeout、Host lock/process kill、README trigger exclusivity）
- Owner boundary、分层架构、语义所有权、AGENTS.md 约束全部一致
- 三个 cumulative slices 划分合理；每个 slice 有明确的 allowed paths、tests、per-file coverage、pyright/Ruff/diff 验证和 review gate
- §10.2 stop conditions 完备覆盖所有已知 contract drift 风险

**Plan 可以安全进入 implementation gate。Controller 应确认准入并将 handoff 交给 implementation agent。**

---

## 9. Artifact Metadata

- **Review file**: `docs/reviews/wu-semantic-ownership-01-r12-init-workflow-plan-final-rereview-ds.md`
- **Reviewer**: AgentDS
- **Timestamp**: 20260718-074448
- **Immutable target unchanged**: ✓ (未修改 plan、control、其它 artifact、production、tests、README、design/workflow)
- **No stage/commit**: ✓
- **Mechanical exit checks**:
  - `git diff --check`: exit 0 ✓
  - staged: empty ✓
  - only this artifact written ✓
- **Next gate**: Controller checkpoint — 由 Controller 决定是否准入 implementation
