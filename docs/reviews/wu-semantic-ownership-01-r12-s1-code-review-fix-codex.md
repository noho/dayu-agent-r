# WU-SEMANTIC-OWNERSHIP-01 / R12 S1 Code Review Fix — AgentCodex

## 1. Gate identity

- Umbrella work unit：`WU-SEMANTIC-OWNERSHIP-01`。
- Internal remediation sub-WU：R12，`dayu-cli init` workflow。
- Slice：S1 — typed catalog、manifest projection 与 OS environment owner。
- Gate：accepted code-review finding fix；不是新 WU，不是 re-review，不授权 S2/S3、
  stage、commit、control update、aggregate、push 或 PR。
- Accepted-plan HEAD / 当前 HEAD：
  `8f7a1946fa46975c3b9e1aefdc2eb3c765b001f8`。
- Branch：`phaseflow/host-issues-control`，不是 protected trunk。
- Finding：`R12-S1-CR-F01`，Controller 裁决为 `ACCEPTED / HIGH`。
- Completion status：
  `R12_S1_CR_F01_FIXED / WAITING_CONTROLLER_VALIDATION_AND_DUAL_REREVIEW`。

本轮只修改 `dayu/cli/init_environment.py`、
`tests/cli/test_init_environment.py`，并新增本 artifact。既有 control dirty state、S1
catalog、plan、裁决、两路 review、implementation/Controller artifacts、S2/S3 及其它路径
均未修改。本轮没有 stage/commit。

## 2. Authority 与完整读取

实现前完整读取并核验：

| Authority / input | Lines | SHA-256 |
|---|---:|---|
| `AGENTS.md` | 128 | 项目当前完整指令 |
| accepted plan | 608 | `69ddfd888336cbb70d093743a96a56f18e694fa68436fb086be1c9b56dcb88c2` |
| Controller adjudication | 97 | `b3a9aca59a9f03bd1cf143bc6f4e5f30e35560d09054d1240f72d5dd5f441c19` |
| AgentMiMo review | 294 | `4f27c186ac0ec9f439956f5eadf34458dd7f11455d5a8684f57e9d3dfcdc7492` |
| AgentDS review | 442 | `06094e2704e6f8a42385f77e7d0e0fa56474be40272bfe511948b81958900652` |
| S1 implementation artifact | 248 | `278ced438b77b8296bf3fc4a669dbc991e24703bbf168e89c20df32bceac2fed` |
| S1 Controller validation | 166 | `826b11a6caa288c19562b1663b3000448dbdd3ff519ab40971b27f199f9bec19` |

还完整走读了当前 `dayu/cli/init_environment.py` 与
`tests/cli/test_init_environment.py`。两路 review 对同一直接代码链给出一致 root cause；
Controller 的 HIGH 分级是本轮 authority，AgentDS 的 CRITICAL 候选未被采用。

## 3. 第一性原理判断与 semantic owner

动机成立。`EnvironmentPersistenceEntry` 明确只拒绝空值和 NUL/CR/LF；marker 字样不是
value rejection contract。POSIX managed-block parser 只拥有两类结构事实：

1. begin/end 是否是独立、完整 marker 行；
2. 唯一 block 是否配对、顺序正确且只包含合法 allowlisted export 行。

修复前 `_parse_managed_block()` 已用逐行精确等值产生 `begin_indexes` / `end_indexes`，却
再用全文 `content.count(marker)` 推翻该结构真源。`shlex.quote()` 产生的合法 export value
只要包含 marker 子串，就会在 `os.replace()` 已完成后的写后校验中被错误计为第二个
marker。根因和 owner 同源，必须在 `dayu.cli.init_environment` 的 parser boundary 修复；
不得把 marker 加入 secret 黑名单，也不得在调用者、workspace、测试 fake 或环境注入层
补偿。

本轮采用最小逐行判定，没有正则/parser framework：

- 完整独立 marker 行继续作为结构 marker；
- 只有以 `export ` 开始、具有非空赋值左侧且 marker 不在赋值左侧的行，才允许 marker
  出现在 `=` 右侧 value 文本；
- 其它普通文本、注释、非法 export 形状或赋值左侧出现 marker 仍拒绝；
- block 内所有 export 行仍经过既有 `_parse_export_name()` 与 allowlist 校验；
- 缺配对、逆序、多块、重复名称等既有结构判断不变。

没有新增兼容分支、fallback、downstream compensation、rollback 协议、public API、schema
或依赖。

## 4. Before / after hashes 与精确 scope

| Path | Before SHA-256 | After SHA-256 | Before → after lines / bytes |
|---|---|---|---:|
| `dayu/cli/init_environment.py` | `754e441e0f7de9c0384375eb7e1924a459e68f406f8398216df2edc97fdde845` | `71be5ba886df7a9d33c6c15da1fba172540124684b02c65c67e17852d736b77f` | `570 / 21,758` → `584 / 22,342` |
| `tests/cli/test_init_environment.py` | `40f0d9b2a75545a19b18c3090fd578394ac83d3c404fc1e2b93a659e474b7111` | `ae243050136d92e0c772caf3a51b3bdd999ff8efe3af096d73161f32473fd947` | `567 / 20,475` → `672 / 24,469` |
| 本 fix artifact | `ABSENT` | 关闭文件后由 Controller/handoff 机械计算 | 新增 |

本 artifact 不能把自身最终 SHA 写入自身而仍保持该 SHA；因此 self after hash 留给文件关闭
后的机械 handoff。两个 production/test owner 文件的 before/after hash 已完整记录。

只读 S1 locks 在本轮结束前机械复核保持不变：

| Read-only path | Before = after SHA-256 |
|---|---|
| `dayu/cli/init_catalog.py` | `937315f3a6c83004788027c891c3b18e3cf2c848db2333430661998768ffe754` |
| `tests/cli/test_init_catalog.py` | `23f1c406e89c62159ea89e5fd4d795aecf9237ec2d42fae0ac06870e7b0473b4` |
| accepted plan | `69ddfd888336cbb70d093743a96a56f18e694fa68436fb086be1c9b56dcb88c2` |
| Controller adjudication | `b3a9aca59a9f03bd1cf143bc6f4e5f30e35560d09054d1240f72d5dd5f441c19` |
| AgentMiMo review | `4f27c186ac0ec9f439956f5eadf34458dd7f11455d5a8684f57e9d3dfcdc7492` |
| AgentDS review | `06094e2704e6f8a42385f77e7d0e0fa56474be40272bfe511948b81958900652` |
| S1 implementation artifact | `278ced438b77b8296bf3fc4a669dbc991e24703bbf168e89c20df32bceac2fed` |
| S1 Controller validation | `826b11a6caa288c19562b1663b3000448dbdd3ff519ab40971b27f199f9bec19` |

## 5. Tests 与真实状态契约

新增一个 3 × 2 参数矩阵：

- value 分别包含 begin marker、end marker、两者；
- profile 分别为首次创建与已有单 block 替换。

六个 case 都使用运行期随机 sentinel，不把 secret value 写入 source/artifact；都断言：

- `persist_environment()` 返回 whole-batch success；
- 从真实 profile 路径重读的 `os.replace()` 后磁盘内容包含精确
  `shlex.quote(value)` export 行；
- 独立 begin/end marker 行各恰好一个，不用全文 substring count 反推结构；
- 当前进程只在写后校验成功后获得同一值；
- 首次创建 mode 为 `0600`；已有替换保留外围文本、移除旧值并保留 `0640`。

malformed 参数矩阵继续并新增断言以下输入在 mutation 前 fail closed、profile bytes 不变、
进程不注入：缺 end、缺 begin、逆序、两个完整 block、普通文本嵌入 marker、注释嵌入
marker、普通非法 block 行、缺 `=` 的 export、以及 value 含 marker 但 name 不在 allowlist
的 export。最后一项证明新 value 判定没有绕过既有 `_parse_export_name()` owner。

### 5.1 修复前直接复现

使用真实 entry / plan / writer，在临时 HOME 对 begin/end/both × create/replace 执行。命令
exit `0`（脚本捕获预期异常），六行原始结论均为：

```text
error=EnvironmentPersistenceError profile_exists=True disk_contains_new_value=True env_injected=False
```

因此修复前事实是“profile 已替换、当前进程未注入、调用报失败”，不是零 mutation。

### 5.2 修复后同路径

同一真实路径再次执行，命令 exit `0`；六行分别覆盖 create/replace × begin/end/both，
原始结论均为：

```text
succeeded=True profile_exists=True disk_contains_new_value=True env_injected=True
```

这如实证明当前 `os.replace()` 后状态在修复路径成功；没有用 fake 隐藏磁盘状态。

## 6. Validation 原始结论

所有命令均在 `source .venv/bin/activate` 后运行。

### 6.1 Four-file focused tests

```bash
pytest tests/cli/test_init_catalog.py tests/cli/test_init_environment.py -q
```

- Exit `0`：`66 passed in 0.23s`。

### 6.2 Per-production-file coverage

```bash
pytest tests/cli/test_init_environment.py \
  --cov=dayu.cli.init_environment --cov-report=term-missing --cov-fail-under=80 -q
```

- Exit `0`：environment `233 statements / 13 miss / 94%`，精确 coverage
  `94.42%`；`35 passed`。

```bash
pytest tests/cli/test_init_catalog.py \
  --cov=dayu.cli.init_catalog --cov-report=term-missing --cov-fail-under=80 -q
```

- Exit `0`：catalog `276 statements / 27 miss / 90%`，精确 coverage
  `90.22%`；`31 passed`。与修复前 catalog `276 / 27 / 90.22%` 精确相同，未退化。

### 6.3 Full pyright

```bash
python -m pyright dayu/ tests/ utils/
```

- Exit `0`：`0 errors, 0 warnings, 0 informations`。
- Pyright 另输出 `1.1.409 -> 1.1.411` 可用更新通知；它不是类型诊断，也未改变锁定环境。

### 6.4 Scoped Ruff

```bash
python -m ruff check dayu/cli/init_catalog.py dayu/cli/init_environment.py \
  tests/cli/test_init_catalog.py tests/cli/test_init_environment.py
```

- Exit `0`：`All checks passed!`。

### 6.5 Full Ruff immutable fingerprint

```bash
python -m ruff check dayu/ tests/ utils/ --output-format=json \
  > workspace/tmp/r12-ruff-current.json
cmp workspace/tmp/r12-ruff-baseline.json workspace/tmp/r12-ruff-current.json
```

- Ruff raw exit `1`（锁定历史诊断的预期状态）。
- Count：`144`。
- SHA-256：
  `051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`。
- `cmp` exit `0`。path/row/column/code/message/fix metadata 均未漂移。

### 6.6 Diff / whitespace / staged

```bash
git diff --check
git diff --cached --name-only
git diff --no-index --check /dev/null dayu/cli/init_environment.py
git diff --no-index --check /dev/null tests/cli/test_init_environment.py
```

- `git diff --check`：exit `0`，无诊断。
- staged name list：空；本轮未 stage/commit。
- 两个 untracked file 的 no-index check 都 raw exit `1`（存在新增 diff 的预期状态），
  stdout/stderr 均为空，即无 whitespace 诊断。

## 7. Source / propagation / security scans

### 7.1 Weak typing 与禁止协议

```bash
rg -n '\bAny\b|:\s*object\b|->\s*object\b|hasattr\(|getattr\(' \
  dayu/cli/init_catalog.py dayu/cli/init_environment.py \
  tests/cli/test_init_catalog.py tests/cli/test_init_environment.py
```

- Raw exit `1`，零命中。

```bash
rg -n '\bcompat\b|\bfallback\b|\bshim\b|\brollback\b|hasattr\(|getattr\(|(^|[[:space:]])import re$|re\.compile' \
  dayu/cli/init_environment.py tests/cli/test_init_environment.py
```

- Raw exit `1`，零命中。没有 parser framework、compat/fallback/shim 或 rollback 新协议。

legacy owner-drift 扫描只有 catalog/test 的 `OpenAI-compatible` 英文子串与
`default_name` / `_init_model_role` 不存在的负断言；无 production legacy owner。

### 7.2 Marker source 与 propagation

marker test scan 命中 `begin-and-end`、`absent/existing`、`reverse-order`、
`multiple-blocks`、普通文本/注释嵌入以及两个非法 export case，证明要求的正反矩阵存在。

```bash
rg -n 'os\.environ\[|result\.succeeded|_parse_managed_block|_parse_export_name|marker_is_in_export_value|subprocess\.run|shell=|capture_output=|text=|check=' \
  dayu/cli/init_environment.py
```

原始命中分类：

- `os.environ[...]` 唯一写入位于 `if result.succeeded` 之后；
- parser 只由 render 与 post-write verification 两处消费同一 owner；
- block export 始终传播到同一 `_parse_export_name()`；
- Windows 仍精确为 `subprocess.run` + `shell=False` + `capture_output=True` +
  `text=False` + `check=False`。

没有新增下游重算、fallback 或环境注入补偿。

### 7.3 Secret / output / network / runtime safety

```bash
rg -n 'entry\.value|\.stdout|\.stderr|print\(|logging' dayu/cli/init_environment.py
```

只命中三个既有且必要的 secret sink：whole-batch success 后写入 `os.environ`、作为
argument tuple 的 `setx` value、以及 `shlex.quote` 后写入已确认 profile；无
stdout/stderr 读取、print 或 logging。

```bash
rg -n 'authorization|authorisation|tool[_ -]?auth|shell=True|text=True|print\(|logging|requests\.|httpx\.|socket|open_host|asyncio\.run' \
  dayu/cli/init_catalog.py dayu/cli/init_environment.py
```

- Raw exit `1`，零命中。

network/runtime scan 只命中 `init_catalog.py` 的本地 `urllib.parse.urlsplit` 与
`init_environment.py` 的 argument-safe `subprocess.run`；无 HTTP client、socket、download、
Host/runtime assembly。Production synthetic scan 只命中 catalog 对三个 test-owned
`manual-smoke` basename 的既有 contract docstring，没有 product fixture/provider 构造。

环境变量名扫描只得到 catalog/optional allowlist 名称与测试断言。测试 secret 继续由
`secrets.token_urlsafe()` 在运行期生成；本 artifact、异常、repr 和 source 均不记录其值。

## 8. README decision

本 fix 只纠正 S1 内部 parser 对既有合法 value contract 的误判，并补同层 owner tests；
不改变 public init 命令、参数、输出、最终用户工作流或测试层级。Accepted plan 把根 README、
config README 与 tests README 固定在 S3，本轮精确 allowlist 也禁止 README。因此不修改
任何 README；没有机械同步或越过 S1 gate。

## 9. Finding status、residuals 与 handoff

- `R12-S1-CR-F01`：`已修复 / WAITING_CONTROLLER_VALIDATION_AND_DUAL_REREVIEW`。
- Value equality candidate：Controller 已 `REJECTED / NO FIX`，未修改 catalog。
- Windows captured-output observation：`NO FIX`，production 仍不读取/记录内容。
- Windows 多项 `setx` 不可回滚：accepted residual，owner/destination 仍为真实 Windows
  external runner / later approved S3 and umbrella aggregate；本轮没有扩域。
- S2 real Service discovery / workspace transaction 与 S3 public smoke / README / Windows
  workflow：covered by later approved slices，本轮未开始。
- POSIX 一般写后校验故障仍按 accepted §5.2 contract 保持“profile 可能已 replace、但不注入
  当前进程、不 publish workspace”的真实状态；本轮没有伪称零 mutation，也没有发明未授权
  rollback。F01 的合法 marker-value 路径现已完成校验并返回成功。
- Unclassified residual risk：`0`。
- Blocking question / design contradiction / local blocker：`0`。

Next entry point：`Controller validation of R12 S1 code-review fix`，随后由 Controller 派发
AgentMiMo / AgentDS 完整 S1 re-review。AgentCodex 在此停止；不进入 S2/S3，不 stage/commit，
不更新 control。

Artifact path：
`docs/reviews/wu-semantic-ownership-01-r12-s1-code-review-fix-codex.md`。
