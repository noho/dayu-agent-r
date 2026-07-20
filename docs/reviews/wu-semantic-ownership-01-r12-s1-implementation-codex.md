# WU-SEMANTIC-OWNERSHIP-01 / R12 S1 implementation completion

## 1. Gate identity

- Umbrella work unit：`WU-SEMANTIC-OWNERSHIP-01`。
- Internal remediation sub-WU：R12，`dayu-cli init` workflow。
- Slice：S1 — typed catalog、manifest projection 与 OS environment owner。
- Gate：implementation completion；不是新 WU，不是 code review，不授权 S2/S3。
- Accepted-plan HEAD：`8f7a1946fa46975c3b9e1aefdc2eb3c765b001f8`。
- Accepted immutable plan：608 lines，SHA-256
  `69ddfd888336cbb70d093743a96a56f18e694fa68436fb086be1c9b56dcb88c2`。
- Completion status：`S1_IMPLEMENTATION_COMPLETE / WAITING_CONTROLLER_S1_VALIDATION`。

## 2. First-principles judgment and owner boundary

动机成立。实现前直接证据表明四个 S1 owner/test 路径均不存在；当前 public init
仍不拥有 plan §4/§5 的 typed catalog 与 secret persistence contract。S1 的最小正确
边界是新增两个内部 owner，不改变 public command orchestration：

- `dayu.cli.init_catalog` 唯一拥有 15 项选择顺序、普通/思考 pair、required env ref、
  dynamic current-schema record 与 16 个 known manifest role projection。
- `ConfigLoader` / `ModelsConfig` 继续唯一拥有 models schema、extends resolver 与 typed
  validation；catalog 不复制 resolver 或 schema parser。
- `dayu.cli.init_environment` 唯一拥有 allowlisted persistence entry/plan/result、POSIX
  单 profile marker writer、Windows `setx` 与 whole-batch current-process injection。
- `prepare_scene` 继续唯一拥有完整 manifest parser；projection helper 只访问并替换
  `model.default_model_id` 的最小路径。
- test-owned `manual-smoke` catalog fixture 只存在于测试；production 只承诺三个 basename
  的 validation ownership boundary。

没有修改 orchestration、workspace transaction、public CLI grammar、package config、
Service/Host/Engine/Fins 或 README；没有引入 compatibility、fallback、shim、migration、
通用 provider registry 或第二套 schema owner。

## 3. Mechanical entry and immutable-source locks

### 3.1 Entry state

- Branch：`phaseflow/host-issues-control`，不是 protected trunk。
- `git rev-parse HEAD`：`8f7a1946fa46975c3b9e1aefdc2eb3c765b001f8`。
- Entry dirty state 只有 Controller-owned
  `docs/host/issues-implementation-control.md`；本 slice 未覆盖它。
- Staged diff：空。
- 四个 S1 source/test baseline paths：全部 `ABSENT`。
- HEAD transition 相对 plan 的旧 product baseline 只包含 docs/control evidence；没有
  product-source drift。

### 3.2 Read-only locks before/after implementation

以下 SHA-256 在实现前、实现后均精确不变：

| Path | SHA-256 |
|---|---|
| `dayu/runtime/config_loader.py` | `a5b5b05de27a85df106a6ebd0a0a54681d5e9ae1366312fdaa9a06816db7018e` |
| `dayu/config/models.json` | `d817a17135a01e1e7d89ada9e6b93b107d29fa9715105340c7ff44d505cf8b68` |
| OLD `dayu/cli/commands/init.py` | `f23c41835c22514dbead1f7121d64f7b6a010cb64e2527f9e1d80aa75a4f7e8e` |

16 个 package manifest 也逐项复核并保持 plan §2 的 SHA：`audit` `9102bd6a...`、
`confirm` `e8d3bd95...`、`conversation_compaction` `a4b35fc3...`、`decision`
`89f0202c...`、`fix` `a7c7ac76...`、`infer` `d70fbdad...`、`interactive`
`050800d1...`、`overview` `4cb7ce05...`、`prompt` `1ebd2910...`、`regenerate`
`bc73ceb4...`、`repair` `a2a332b4...`、三个 `smoke_host_public_*` 分别
`a89b13f9...` / `cf88ebe5...` / `9d291b63...`、`wechat` `4c9c3d5c...`、
`write` `af693585...`；完整机械输出已在当前 implementation turn 留存，未改写这些文件。

### 3.3 Ruff entry baseline

执行：

```bash
source .venv/bin/activate
python -m ruff --version
mkdir -p workspace/tmp
set +e
python -m ruff check dayu/ tests/ utils/ --output-format=json > workspace/tmp/r12-ruff-baseline.json
ruff_baseline_status=$?
set -e
# count/SHA assertions from accepted plan §9.2
```

结果：exit `0`（包括对 raw Ruff exit `1` 的预期断言）；Ruff `0.15.11`；raw count
`144`；SHA-256
`051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`。
辅助文件仅位于 `workspace/tmp/`，未 stage。

## 4. Actual changed paths and SHA-256

四个 implementation paths 的 before 均为 `ABSENT`：

| Path | Before | After SHA-256 | Lines / bytes |
|---|---|---|---:|
| `dayu/cli/init_catalog.py` | `ABSENT` | `937315f3a6c83004788027c891c3b18e3cf2c848db2333430661998768ffe754` | 854 / 33,977 |
| `dayu/cli/init_environment.py` | `ABSENT` | `754e441e0f7de9c0384375eb7e1924a459e68f406f8398216df2edc97fdde845` | 570 / 21,758 |
| `tests/cli/test_init_catalog.py` | `ABSENT` | `23f1c406e89c62159ea89e5fd4d795aecf9237ec2d42fae0ac06870e7b0473b4` | 610 / 22,659 |
| `tests/cli/test_init_environment.py` | `ABSENT` | `40f0d9b2a75545a19b18c3090fd578394ac83d3c404fc1e2b93a659e474b7111` | 567 / 20,475 |

本 completion artifact 也是 allowlist 内新增路径；before 为 `ABSENT`。其 final after SHA
只能在文件关闭后由 Controller/handoff 机械计算，不能无自引用矛盾地写入自身。

## 5. Implemented owner contracts

### 5.1 Catalog/model/manifest

- 不可变 15-choice tuple 精确按 accepted table 排序；typed selection 必须引用该 tuple
  中的真实 entry；`kind` 同时承诺 resolved provider，不从 model id 字符串反推。
- 前 13 个 pair 逐 ordinary/thinking id 消费真实 `ConfigLoader.load_models()` 的
  resolved `ModelsConfig`，精确比对 provider/API ref；raw thinking child 只写
  `extends` 可成功继承，child override mismatch fail closed。
- package `ollama` template 单独要求 `provider=ollama`、`api_key_ref=None`；交互默认
  endpoint/context 从已验证 typed template 投影。
- Ollama staging record 复制 raw 完整 template，只替换 model、endpoint、context；custom
  生成计划锁定的完整 `openai_compatible` record、Authorization/JSON headers、三项
  capability、timeout/retry/SSE 字段、null extension 与精确八 hints。
- 动态输入在 mutation 前拒绝空/外围空白/control model、非完整 HTTP(S) URL、非正整数
  和 Python bool；endpoint 原样写入，不猜后缀，不联网。
- 动态记录写回 staging 后再次由真实 `ConfigLoader` 重载并核对显式字段。
- ordinary/thinking role 集合与 13 production / 3 test-owned validation 集合同源、互斥，
  package manifest 集合缺失/多余均 fail closed。
- projection 先读取全部 16 个 known manifest，再只替换 `model.default_model_id`；额外
  user manifest 不枚举、不重写。全部 16 个投影由 current `prepare_scene` 读取；三个
  `manual-smoke` catalog 只在 test module 构造。

### 5.2 Environment persistence and redaction

- entry value 使用 `repr=False`；name 必须来自 catalog required refs 或五个固定 optional
  names；值为空或含 NUL/CR/LF 时以只含变量名的错误拒绝。
- typed plan 只接受标准 `Windows` / `Linux` / `Darwin`；POSIX 根据已检测 shell 精确选择
 一个 `.zshrc` 或 `.bashrc`，其它平台/shell fail closed。
- 未最终确认时 writer 完全不执行；直接构造的 POSIX typed plan 也只能指向 `.zshrc` /
  `.bashrc`；profile symlink、dangling symlink、非普通文件、
  0/1 之外 marker、嵌入/重复/坏 export 均拒绝。
- POSIX value 使用 `shlex.quote`；所有写入经同父目录 `mkstemp` 私有文件、显式 mode、
  flush/fsync、`os.replace`；新 profile 精确 `0600`，已有 mode 保留。
- 原子发布后从磁盘重读，仅校验 marker/name 顺序与 mode；writer 或 verification 失败时
  不注入当前进程，不允许后续 workspace publish。
- Windows 逐项精确使用
  `subprocess.run(("setx", name, value), shell=False, capture_output=True, text=False, check=False)`；
  不读取/记录 stdout/stderr。首个失败后停止，result 只含已写/未写 names，不声称回滚。
- POSIX/Windows 都只有 whole-batch success 后才把同一批值写入 `os.environ`；Windows
  partial/first failure 与 POSIX fault 均证明零 current-process injection。

## 6. Validation evidence

### 6.1 Focused owner tests

```bash
source .venv/bin/activate
pytest tests/cli/test_init_catalog.py tests/cli/test_init_environment.py -q
```

Exit `0`：`56 passed in 0.23s`。

覆盖的计划正反例包括：15 项顺序、13 resolved pair、extends-only child、missing/provider/ref
mismatch、Ollama template、custom absent/完整 record/八 hints、URL/model/context boundaries、
static no-rewrite、exact 16 projection、user byte preservation、current parser 13/3 catalog
boundary；POSIX shell/profile、未确认、marker 0/1/坏结构、quote、0600、existing mode、
symlink/dangling/non-regular、replace fault、post-write verify fault；Windows exact argv/flags、
success、first failure、partial return-code/OSError、names-only result 与 no-injection。

### 6.2 Per-production-file coverage

```bash
pytest tests/cli/test_init_catalog.py --cov=dayu.cli.init_catalog --cov-report=term-missing --cov-fail-under=80 -q
pytest tests/cli/test_init_environment.py --cov=dayu.cli.init_environment --cov-report=term-missing --cov-fail-under=80 -q
```

- 第一条 exit `0`：catalog `276 statements / 27 miss / 90%`，`31 passed`。
- 第二条 exit `0`：environment `226 statements / 13 miss / 94%`，`25 passed`。
- 两个 production 文件分别达到 `>=80%`；没有用 package aggregate 替代单文件门槛。

### 6.3 Full pyright

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
```

Exit `0`：`0 errors, 0 warnings, 0 informations`。

### 6.4 Changed-path Ruff and full immutable fingerprint

```bash
python -m ruff check dayu/cli/init_catalog.py dayu/cli/init_environment.py \
  tests/cli/test_init_catalog.py tests/cli/test_init_environment.py
```

Exit `0`：`All checks passed!`。

```bash
set +e
python -m ruff check dayu/ tests/ utils/ --output-format=json > workspace/tmp/r12-ruff-current.json
ruff_current_status=$?
set -e
# exact status/count/SHA assertions
cmp workspace/tmp/r12-ruff-baseline.json workspace/tmp/r12-ruff-current.json
```

Exit `0`（包括 raw exit `1` 预期断言）；count `144`；SHA-256
`051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`；
`cmp` exit `0`。

### 6.5 Diff, scope and source/secret scans

- `git diff --check`：exit `0`，无输出。
- `git diff --cached --name-only`：空；未 stage/commit。
- `git status --short`：保留 Controller-owned control dirty path，并只新增四个 S1
  implementation paths 与本 artifact。
- weak typing scan `\bAny\b|:\s*object\b|->\s*object\b|hasattr\(|getattr\(`：零命中。
- legacy owner-drift scan：production 零命中；测试仅有对 `default_name` 与
  `_init_model_role` 不存在的负断言。
- production `manual-smoke` scan 仅命中计划要求的三个 basename contract/docstring；
  production 无 `SceneToolCatalog` / fixture/provider 构造。
- network scan 仅命中本地 `urllib.parse.urlsplit` 与 argument-safe `subprocess.run`；无
  HTTP client、socket、download、Host/runtime assembly。
- output scan：production 无 `print`、无 stdout/stderr 投影；`os.environ[...]` 唯一命中
  位于 `result.succeeded` 后的 whole-batch injection。
- env-name scan 只命中 catalog/schema names 与 test assertions；测试 sentinel 每次由
  系统随机源在运行期生成，实际值不在 source、repr、异常、captured output 或本 artifact。

## 7. README decision

本 slice 只新增 `tests/cli` 内 owner contract tests，没有新增测试层级；production 是尚未接入
public init 的内部 contract，不改变用户命令、参数、输出或工作流。Accepted plan 将三份 README
更新固定在 S3，且本次 S1 allowlist 明确禁止 README。因此读取并检查 `tests/README.md` 职责后，
本 slice 不修改任何 README。

## 8. Stop conditions and actual residuals

- Accepted-plan stop condition：`NONE`。
- ConfigLoader/current schema、OLD custom hints、16 manifest sets、current parser seam、
  source locks、full pyright 与 Ruff fingerprint均未漂移。
- Actual S1 residual：Windows `setx` 多变量写入没有跨调用 rollback；owner 已按 accepted
  contract 停止后续调用、阻止 current-process injection 与 workspace publication，并只报告
  names。该残余由 R12 accepted plan 明确接受。
- Covered by later approved slice：production 13-manifest real Service discovery 属于 S2；真实
  Windows runner 与 public subprocess smoke 属于 S3/umbrella aggregate。S1 未伪造这些结论，
  也不授权本 agent 进入它们。
- Unclassified residual risk：`0`。
- Reviewer conclusion：`NOT RUN`；用户只授权 S1 implementation，禁止自行进入 review。

## 9. Controller handoff

Next entry point：`Controller S1 validation`。

Controller 应机械复核当前 diff/scope、四个实现路径的 after SHA、artifact final SHA、focused
tests、两个独立 coverage 门槛、full pyright、changed-path Ruff、full Ruff count/SHA/cmp、
staged empty 与 source/secret scans。AgentCodex 在此停止；不 review、不 stage、不 commit、
不修改 control，也不进入 S2/S3。
