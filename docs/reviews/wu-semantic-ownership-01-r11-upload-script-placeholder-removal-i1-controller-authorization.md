# WU-SEMANTIC-OWNERSHIP-01 / R11-I1 atomic cutover Controller implementation authorization

## 1. 身份与唯一授权真源

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU、feature、issue，也不是重开旧 sub-WU。
- internal remediation sub-WU：R11 — OLD-aligned upload shell/cmd workflow 与 placeholder surface 删除。
- implementation slice：`R11-I1 atomic Fins producer + CLI consumer/renderer cutover`。
- accepted-plan amendment local commit：
  `a527ec030215e5bfcf9c4fad2f4a6fda243f5d65`，parent
  `f7b452f992b4797b32fea7c6f7212b5ec4345ec1`。
- accepted plan：
  `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`
  889 lines / 75,526 bytes / SHA-256
  `55d35256f0f89f39f722438dc19d9ae65269b16810f96f1cd0129c6eba06d427`。
- cumulative product baseline remains R10 completion
  `2b14b2fbc89654267e3d33daa2ae410ceff45e68`；本 slice 不重写 R01-R10 已接受语义。
- 本 artifact 与 `docs/host/issues-implementation-control.md` 是当前 live authorization/control truth；长生命周期 plan 与 reviewer verdict 不自行授权 write。

## 2. Entry preflight

- branch：`phaseflow/host-issues-control`。
- entry `HEAD`：`a527ec030215e5bfcf9c4fad2f4a6fda243f5d65`。
- working tree / staged tree：创建本 Controller artifact 与更新 control 前均为空。
- activated Ruff version：verbatim `ruff 0.15.11`。
- full Ruff baseline：`workspace/tmp/r11-ruff-baseline.json`，144 findings / SHA-256
  `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`；该 temp evidence 不得 stage/commit。
- new production target `dayu/cli/upload_script.py`：entry 时不存在；必须由本 slice 新建，不得用 compatibility re-export/wrapper。

任一 entry lock、branch、plan、Ruff version/baseline 或 closed allowlist 在 Agent 开始前不匹配，立即 stop 并报告 Controller；不得自行重新锁定或扩 scope。

## 3. Exact write allowlist

AgentCodex 本次只允许写以下九个路径：

1. `dayu/fins/upload_batch.py`
2. `tests/fins/test_upload_batch.py`
3. `dayu/cli/commands/fins.py`
4. `dayu/cli/arg_parsing.py`
5. `dayu/cli/upload_script.py`（new）
6. `tests/cli/test_upload_filings_from_command.py`
7. `tests/cli/test_fins_commands.py`
8. `tests/cli/test_arg_parsing.py`
9. `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-i1-implementation-codex.md`

其余所有路径只读。特别禁止修改/stage/delete/overwrite：

- `docs/host/issues-implementation-control.md`、本 authorization、accepted plan 与任何既有 review/controller artifact；
- `pyproject.toml`、`requirements.txt`、`.github/**`、全部 README、placeholder packages/tests（这些属于 R11-I2）；
- `dayu/service/**`、`dayu/host/**`、`dayu/engine/**`、`dayu/runtime/**`、`dayu/config/**`、`dayu/tool/**`、`dayu/ui/**` 与 design docs；
- Issue 142/151/175/177/178、R12、Topic 8/9 或统一 tool authorization framework 相关路径。

不得 stage、commit、push、建 PR、修改外部 issue 或进入 R11-I2。Controller 只在完整验证、review/fix/re-review/aggregate gates 闭合后另行授权 accepted commit。

## 4. Locked inputs

| Path | Entry lines / bytes | Entry SHA-256 | Role |
|---|---:|---|---|
| `dayu/fins/upload_batch.py` | 376 / 12,000 | `6767d30cfd788e584cef22e5109b1ae0b787ecaedc8581a4cfcf2c49d5ad6178` | Fins semantic owner |
| `tests/fins/test_upload_batch.py` | 187 / 5,914 | `7668bf268eab97f250684cee2ea3cacbca31e6e5a7a02c9605ab90b2b7ea6a69` | Fins owner tests |
| `dayu/cli/commands/fins.py` | 1057 / 37,116 | `0db8ff2dedf541c2b58bc11342a02cd0bf4098bc9fcc19d948efa5cf4afc95a6` | CLI command consumer |
| `dayu/cli/arg_parsing.py` | 932 / 31,124 | `a0e25ad6c58f3f266ef1afc4447c4a7e875d18c23ad346550ccf8cfd283c1c2c` | CLI grammar owner |
| `tests/cli/test_upload_filings_from_command.py` | 402 / 12,534 | `f9578f1b1e23bcfcfa3be0524bcd0f60cd2184ad76def7559c64c7c5bf79c49d` | public workflow tests |
| `tests/cli/test_fins_commands.py` | 1803 / 60,418 | `d139e10c7636da59e62296d935ed305e7ea0762a94fc59168b7b2a4d199c9668` | CLI command tests |
| `tests/cli/test_arg_parsing.py` | 1170 / 37,259 | `ff18bbf4ce97683844c44b26befd7d0722ecc12ed9510d30935da45f16cf2484` | grammar tests |
| `tests/fins/test_fmp_company_info_resolver.py` | 222 / 7,075 | `3530bcf11d604f651c7770cafaa4cd61fa493158894ad1aef239e8e0a2baa455` | read-only FMP-once sentinel |

External OLD evidence remains read-only and exact：

- `/Users/leo/workspace/dayu-agent/dayu/fins/cli_support.py`：2267 lines / SHA-256 `248cc859d4dd0fdf8ed7829cc27dad48349227dfbd43f076414770166c93da45`；
- `/Users/leo/workspace/dayu-agent/dayu/fins/upload_recognition.py`：555 lines / SHA-256 `5a45618b2545ad0ee024efb428de7e614c96b2c5bb0a222bf1586febc1dff816`。

OLD 只提供用户工作流与分类行为证据，不拥有当前架构/API/类型；不得复制其 dict/`Any`、CLI/IO 混层、`list2cmdline`、非原子写或兼容接口。

## 5. 原子实施状态机

本 slice 是一个 coordinated atomic contract cutover，内部按以下顺序连续实施：

1. WP-A：在 Fins owner 中形成 typed immutable batch plan、classification/fiscal/material/skip facts 与唯一 owner tests；
2. WP-B：CLI grammar/command 机械消费同一 typed plan，新增唯一 argv builder + shell/cmd renderer + safe publisher，并更新三组 CLI tests；
3. WP-A 与 WP-B 全部编辑完成后，才允许首次运行 cumulative tests/pyright/coverage/Ruff/scans/smokes；
4. consumer 暴露 owner gap 时，只回 Fins owner 做 targeted correction，CLI 不得 fallback/重算；修复后重跑全部 cumulative validation；
5. validation 完成后写 implementation artifact，停在 Controller checkpoint。

WP-A/WP-B 不是独立 slices，不得在二者之间 validation、checkpoint、handoff、review、stage、commit 或宣称合法 intermediate tree。若中途出现真实 blocker，保留 failed working evidence并 stop；不得为通过中间状态引入 old/new dual surface、compat alias/property/wrapper、loose parsing、`hasattr/getattr` 或测试 shim。

## 6. 必须实现的 owner contract

### 6.1 Fins owner

- filesystem scan/classification、supported suffix、recursive policy、fiscal inference、material routing、skip reason、annual=5、periodic=latest-year/max6 均由 `dayu.fins.upload_batch` 唯一产生 typed facts；
- Q4 严格使用 OLD 已锁定语义：只检查 child 完整 filename；quarterly marker 只认 contiguous literal `季报`；FY/annual/年度报告/年报优先；direct `20YYQ4` parent fallback 仍只看 child filename；
- 五个 oracle 必须由 Fins owner tests 精确冻结；
- explicit `--fiscal-year` / `--fiscal-period` 分字段覆盖 inference；缺 year/period filing 进入 typed skip；
- 不读取内容/mtime/sibling 猜 metadata；不反向 import CLI/Service/Host/Engine/UI；不承担 shell quoting/render/publish。

### 6.2 CLI owner

- 删除 public JSON argv `schema_version=1` contract，不保留兼容 parser/fallback；严格按 accepted plan §6.2：
  `FILING_ACTION_CHOICES=auto|create|update|delete`、`BATCH_UPLOAD_ACTION_CHOICES=auto|create|update`，三个 upload parser
  default 均为 `auto`；生成 entry 为 `auto` 时省略 `--action`，显式 create/update 才投影；
- `--infer` 只注册在 `upload_filings_from`，为 `store_true` / default `False`；未传时零 resolver/env 访问，传入时读取
  `FMP_API_KEY` 并只调用一次 public `resolve_company_info(canonical)`，provider failure 无 fallback；
- grammar 支持默认/显式输出路径与用户可读摘要；FMP resolver 每 invocation 最多一次并把同一 ticker/company/aliases fact 投影到所有 entries；
- 一个 typed argv builder 产生 target `dayu-cli upload_filing` / `upload_material` argv；shell/cmd renderer 只做平台 quoting，不能重算文件分类、财期、material 或 cap；
- POSIX 与 Windows command body 可执行；Windows 必须 `setlocal DisableDelayedExpansion`，不得 `list2cmdline` 或 `shell=True`；
- output/source containment、root-self 与内部 symlink rejection、external-ancestor symlink allowed、same-directory atomic temp+fsync+replace、POSIX executable mode、old-target preservation/temp cleanup/secret non-persistence 全部落在明确 owner；
- script body 不含 API key、provider URL、网络调用或 `--infer`；generation comment 可含无 secret 的再生成命令；
- 函数/类/模块与新 public types 遵守 AGENTS.md 中文 docstring、严格类型、无 `Any/object`/generic bag/无必要 nested helper。

## 7. Validation gates

AgentCodex 必须完整执行 accepted plan §5.3、§6.6、§8，不得缩减。至少包括：

- affected owner/CLI tests、完整相关 tests 与必要 real filesystem smoke；
- POSIX recorder smoke 与 POSIX real Service/Fins workflow smoke；Windows 本地 recorder/grammar tests（真实 Windows runner 属 R11-I2 release gate）；
- changed production Python files 每文件 line coverage `>=80.00%`；
- full pyright `0 errors`，不得新增/扩散/ignore；
- scoped Ruff zero；full Ruff 与 locked 144-finding JSON 做 exact set difference，current-only 必须为空；
- `git diff --check`、staged empty、closed allowlist exact；
- JSON argv/placeholder/deferred/reverse-import/danger/secret/containment/owner/propagation scans；
- README trigger check：I1 不修改 README，只在 artifact 记录 I2 必须同步 root/dayu/fins/tests README；
- read-only sentinel `tests/fins/test_fmp_company_info_resolver.py` hash保持不变。

若任何 changed file coverage 低于 80%、full pyright 非零、Ruff current-only 非空、real smoke 不成立、allowlist 外 diff、sentinel drift 或安全/owner invariant 不成立，必须在本 slice owner allowlist 内修复并完整重跑；无法在 scope 内修复则 stop，不得标 PASS。

## 8. Handoff

implementation artifact 必须记录：

- final exact diff path set 与每个 changed/new file hash；
- typed producer-consumer mapping 与五个 Q4 oracle；
- 所有 test/smoke/coverage/pyright/Ruff/scans/diffcheck 的 exact command/result；
- README trigger、security retained/changed、deferred no-touch、remaining risk；
- staged empty、无 commit/push/PR；
- 末尾 marker：`READY_FOR_CONTROLLER_R11_I1_ATOMIC_CHECKPOINT`。

Controller checkpoint 通过后才可授权 R11-I2；本授权到此停止。

AUTHORIZED_FOR_AGENTCODEX_R11_I1_ATOMIC_IMPLEMENTATION
