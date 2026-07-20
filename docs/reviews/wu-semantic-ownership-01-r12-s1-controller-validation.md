# WU-SEMANTIC-OWNERSHIP-01 / R12 S1 Controller validation

## 1. Gate identity

- Umbrella work unit：`WU-SEMANTIC-OWNERSHIP-01`。
- Internal remediation sub-WU：R12，`dayu-cli init` workflow。
- Slice：S1 — typed catalog、manifest projection 与 OS environment owner。
- Accepted-plan HEAD：`8f7a1946fa46975c3b9e1aefdc2eb3c765b001f8`。
- Immutable plan：`docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`，
  608 lines，SHA-256
  `69ddfd888336cbb70d093743a96a56f18e694fa68436fb086be1c9b56dcb88c2`。
- AgentCodex completion artifact：
  `docs/reviews/wu-semantic-ownership-01-r12-s1-implementation-codex.md`，
  248 lines / 13,229 bytes / SHA-256
  `278ced438b77b8296bf3fc4a669dbc991e24703bbf168e89c20df32bceac2fed`。
- Controller verdict：
  `PASS_WITH_MANDATORY_REVIEW_CHALLENGE / READY_FOR_DUAL_COMPLETE_CODE_REVIEW`。

本 artifact 只授权 AgentMiMo / AgentDS 对当前 immutable S1 tree 做并发完整 code
review。它不接受 S1、不授权 fix、不授权 S2/S3、commit、aggregate、Windows success
claim、push 或 PR。

## 2. Scope、hash 与完整阅读

Controller 完整阅读了两个 production owner、两个 owner test 和 AgentCodex completion
artifact。当前 branch/HEAD 精确为：

- branch：`phaseflow/host-issues-control`；
- HEAD：`8f7a1946fa46975c3b9e1aefdc2eb3c765b001f8`；
- staged tree：空；
- Controller-owned `docs/host/issues-implementation-control.md` 继续保持有意 dirty；
- 除 control 外只有以下五个 S1 untracked paths。

| Path | Lines / bytes | SHA-256 |
|---|---:|---|
| `dayu/cli/init_catalog.py` | 854 / 33,977 | `937315f3a6c83004788027c891c3b18e3cf2c848db2333430661998768ffe754` |
| `dayu/cli/init_environment.py` | 570 / 21,758 | `754e441e0f7de9c0384375eb7e1924a459e68f406f8398216df2edc97fdde845` |
| `tests/cli/test_init_catalog.py` | 610 / 22,659 | `23f1c406e89c62159ea89e5fd4d795aecf9237ec2d42fae0ac06870e7b0473b4` |
| `tests/cli/test_init_environment.py` | 567 / 20,475 | `40f0d9b2a75545a19b18c3090fd578394ac83d3c404fc1e2b93a659e474b7111` |
| AgentCodex completion artifact | 248 / 13,229 | `278ced438b77b8296bf3fc4a669dbc991e24703bbf168e89c20df32bceac2fed` |

`git diff --check` 通过；`git diff --cached --name-only` 为空。没有修改 public init
入口、argparse、workspace transaction、package config、README、Service、Host、Engine、
Fins 或 workflow；没有进入 S2/S3。

## 3. Owner-boundary validation

### 3.1 Catalog / model / manifest

Controller 确认：

- 15 项 catalog、ordinary/thinking pair、required env ref 和 dynamic record builder 只由
  `init_catalog.py` 拥有；静态 pair 校验消费真实 `ConfigLoader.load_models()` 产生的
  resolved `ModelsConfig`，没有复制 extends resolver。
- Ollama 复制 staging 中的完整 template，只替换三个显式字段；custom record 使用当前
  schema 并产生计划锁定的八个 runner hints；写回后重新由真实 ConfigLoader 读取。
- known manifest role 是两个显式、互斥的 8-item 集合；13 production / 3 test-owned
  validation 集合同源并互斥。projection 只读取精确 16 个 known paths、只替换
  `model.default_model_id`，不枚举或改写 user manifest。
- `manual-smoke` catalog fixture 只存在于 test module；production 没有 synthetic tool /
  provider、完整 manifest parser、network/runtime assembly 或 S2 real discovery。

### 3.2 Environment persistence

Controller 确认：

- persistence entry 的 value `repr=False`，name 来自 catalog / optional-integration 固定
  allowlist；错误和 result 只投影 env names / safe target。
- 未确认 plan 在 writer 前拒绝；POSIX 只选一个 `.zshrc` / `.bashrc`，拒绝 profile
  symlink、dangling symlink 和非普通文件，使用同父目录 `mkstemp`、明确 mode、fsync 与
  `os.replace`，新文件 mode 为 `0600`，已有文件保留 mode。
- Windows 调用精确为 argument tuple、`shell=False`、`capture_output=True`、
  `text=False`、`check=False`；首个失败停止，只报告 written/unwritten names。
- 两个平台都只在 whole-batch persistence success 后注入当前 `os.environ`；失败或
  partial failure 不注入。Windows 跨 `setx` 不可回滚继续是 accepted plan residual，
  不是 S1 新 finding。

## 4. Independent validation

Controller 在当前 tree 独立运行：

```bash
source .venv/bin/activate
pytest tests/cli/test_init_catalog.py tests/cli/test_init_environment.py -q
```

结果：exit `0`，`56 passed`。

```bash
pytest tests/cli/test_init_catalog.py \
  --cov=dayu.cli.init_catalog --cov-report=term-missing --cov-fail-under=80 -q
pytest tests/cli/test_init_environment.py \
  --cov=dayu.cli.init_environment --cov-report=term-missing --cov-fail-under=80 -q
```

结果：

- catalog：`276 statements / 27 miss / 90%`，实际 coverage `90.22%`；
- environment：`226 statements / 13 miss / 94%`，实际 coverage `94.25%`；
- 两个 production 文件分别满足当前 S1 `>=80%` gate。

```bash
python -m pyright dayu/ tests/ utils/
python -m ruff check dayu/cli/init_catalog.py dayu/cli/init_environment.py \
  tests/cli/test_init_catalog.py tests/cli/test_init_environment.py
```

结果：full pyright `0 errors, 0 warnings, 0 informations`；changed-path Ruff
`All checks passed!`。

Controller 另行重新生成 full Ruff raw JSON：raw exit `1`、count `144`、SHA-256
`051bd6cc84fcd32adbd792c81c9e524438dd0532a92c7504ea2edf8234ec1cea`，与
`workspace/tmp/r12-ruff-baseline.json` 的 `cmp` exit `0`。Weak typing、legacy
owner drift、production synthetic catalog、network/runtime assembly、`shell=True` /
`text=True` / `print` 扫描均为零命中。

README decision 正确：S1 是尚未接入 public init 的 internal contract slice；accepted
plan 明确把根 README、config README 与 tests README 放在 S3，本 slice 不修改 README。

## 5. Mandatory adversarial review evidence

Controller 发现一个必须由两路 reviewer 独立裁决的直接反例。当前
`_parse_managed_block()` 使用全文 `content.count(marker)` 检测“embedded marker”。因此一个
满足 S1 entry contract（非空且不含 NUL/CR/LF）的合法 secret，只要 quoted value 中包含
marker 字样，就会在 profile 已完成 `os.replace` 后被错误拒绝：

```text
value = "prefix # >>> dayu-cli init >>> suffix"
result = EnvironmentPersistenceError(
    "POSIX profile contains an embedded Dayu init marker"
)
profile_exists = True
```

Controller 以临时 HOME、真实 `EnvironmentPersistenceEntry`、真实
`plan_environment_persistence()` 和真实 `persist_environment()` 复现该结果。异常不泄漏
secret，且没有 current-process injection；但合法值被拒绝、profile 已经发布、workspace
随后不能 publish。该行为看起来直接超出 plan §5.1 的 value rejection 集合
（empty / NUL / CR / LF）以及 §5.2 的 marker **结构** owner（缺失、恰好一对、重叠、
不配对、多块），并把 marker substring 错当成 marker line。

两路 reviewer 必须：

1. 独立运行该反例，并判断它是否为 accepted S1 correctness finding；
2. 审查 begin 与 end marker substring、single/double-quoted value、existing unrelated profile
   text，确保修复若被接受只解析 marker line，不放宽真正的 malformed marker 结构；
3. 审查 post-write failure truth：即使不注入 env、不 publish workspace，也不能把已替换
   profile 叙述成“零 mutation”；
4. 对 `InitModelSelection` 的 catalog membership 使用 dataclass value equality 做一次对抗
   检查。一个语义完全相同的 copy 是否应被接受可以按 value-object contract 裁决；不得为此
   引入 registry/framework/identity shim。

## 6. Residuals and next entry

- Accepted/open review finding：尚未裁决；等待两路完整 code review。
- Mandatory Controller evidence：marker-substring false rejection，`1` 个。
- 已分类 residual：Windows `setx` 跨变量不可回滚，由 accepted R12 plan / S3 real Windows
  gate 承担；不是当前 fix waiver。
- Deferred owners：S2 real Service discovery / workspace transaction；S3 public smoke /
  README / Windows workflow；Issue 142/151/175/177/178 均未偷带。
- Unified tool authorization framework：未实现。
- Local blocker：`0`；当前证据足以进入 code review，而不是跳过 review 直接 fix。

Next entry point：AgentMiMo / AgentDS 对当前 immutable S1 tree 并发执行完整
`/deepreview`。Controller 收齐两路 findings 后统一裁决；任何 accepted finding 必须交回
AgentCodex 修复并完成双路 re-review，未 PASS 不进入 S2。
