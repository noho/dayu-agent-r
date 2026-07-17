# WU-SEMANTIC-OWNERSHIP-01 / R11 upload script 与 placeholder surface remediation 独立实施计划

## 1. Gate、第一性原理结论与停点

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- 内部 remediation：`R11 — OLD-aligned upload shell/cmd workflow 与 placeholder surface 删除`。
- 当前 gate：R11 独立 plan-only accepted-finding fix gate；不是新 WU、issue 或 feature，不创建替代 WU，不进入 R12。
- baseline：branch `phaseflow/host-issues-control`，HEAD
  `2b14b2fbc89654267e3d33daa2ae410ceff45e68`，staged tree 为空。
- 并行所有权：`docs/host/issues-implementation-control.md` 是 Controller-owned 有意 dirty 文件；本计划及后续
  implementation/review Agent 均不得修改、覆盖、stage 或提交它。
- 当前授权只允许修复本 plan artifact 并新增对应 plan-fix evidence；本计划本身不授权代码、测试、README、design、CI、
  commit、push、PR 或 R12。
- 本 gate 完成后停在 `READY_FOR_CONTROLLER_PLAN_FIX_VALIDATION`。

动机成立且严重性评估准确。直接 owner-side 证据不是“README 不一致”，而是：

1. `dayu/fins/upload_batch.py` 当前仅做 token 分类并返回单一 `entries` 与 path-only skip，未拥有已裁决的 OLD 财期推断、
   material routing、同期优先级/去重与数量规则；业务事实尚无完整 owner。
2. `dayu/cli/commands/fins.py` 当前把 Fins entry 再投影成
   `{schema_version: 1, commands: [argv...]}`，`--output` 缺省时写 stdout，既不是平台可执行脚本，也把 CLI argv 变成
   无生产消费者的第二公共协议。
3. `pyproject.toml` 仍发布 `dayu-web`、`dayu-wechat`、`dayu-render`，对应 package/grammar 只承诺 unavailable
   placeholder，不具备所发布产品能力。
4. 当前 `upload_filing` / `upload_material` runtime 真源已支持默认 `action=auto`，CLI 却只允许
   `create|update|delete` 且默认 `create`；batch 也缺 `auto`。这是入口 grammar 对 owner contract 的错误投影。

正确边界是：Fins 唯一产生 recognized/material/skipped 领域事实；CLI 只解析输入、调用一次可选 resolver、把 typed
plan entry 投影成当前公共命令并由单一平台 renderer 安全发布脚本；packaging 只发布真实能力。不得在 renderer、README、
fixture 或 Service 下游补 OLD 规则，也不得让 Fins 拼 executable/flags/quoting。现有设计与 Topic 7 裁决无直接矛盾，
因此无需重新提问。

## 2. Authority、source locks 与已完成依赖

### 2.1 Authority order

1. `AGENTS.md` 的语义所有权、分层、类型、测试、README 与安全约束；
2. `docs/fins/design.md` §10 与 `docs/ui/design.md` §1—2；
3. Controller discussion Topic 7 final adjudication；
4. umbrella remediation plan §7、§18、§20—22；
5. `docs/phaseflow-umbrella-optimization-control.md` 与当前 Controller control truth；
6. 当前 CURRENT production code/tests/READMEs；
7. 两个指定 OLD 文件只作为用户工作流与分类规则证据。

已裁决产品问题不重开。OLD 不拥有当前架构、API、类型或兼容需求；不得复制其 dict/`Any`、CLI/IO 混层、
`subprocess.list2cmdline`、非原子写或其它历史实现。

### 2.2 Baseline source locks

| Source | Lines | SHA-256 |
|---|---:|---|
| `AGENTS.md` | 128 | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` |
| Controller control（working tree，只读） | 2242 | `1906ce2f885d6d414d2e198f1c0c86463a8e0755c0da1a7c451f9ef6c16af808` |
| umbrella optimization control | 302 | `6d924e919a4ba797e6213879aadca7bdd4f47a37418630e1ee43cb1995e461db` |
| Controller discussion | 731 | `cd26760d626415c52caa13a724144b4d98f2a2b2fc159772e6d807833c01533a` |
| Host / Engine / Tool / Fins / UI design | 3696 / 553 / 134 / 123 / 111 | `276d35e1...43e9` / `f2091260...f31` / `ddc6efc0...ea7c` / `97033cf1...7abdd` / `5a19c829...ed973` |
| umbrella remediation plan | 1269 | `30c27562ece3360c7d25e55a6f2b0b189999d35cca8004e83d42de3c8ccda838` |
| CURRENT `dayu/fins/upload_batch.py` | 376 | `6767d30cfd788e584cef22e5109b1ae0b787ecaedc8581a4cfcf2c49d5ad6178` |
| CURRENT `dayu/cli/commands/fins.py` | 1057 | `0db8ff2dedf541c2b58bc11342a02cd0bf4098bc9fcc19d948efa5cf4afc95a6` |
| CURRENT `dayu/cli/arg_parsing.py` | 932 | `a0e25ad6c58f3f266ef1afc4447c4a7e875d18c23ad346550ccf8cfd283c1c2c` |
| CURRENT FMP resolver | 394 | `c2abfbe03227d8b98ea639c374cb7aa9c41c98214b0b004cfb7de492be7c46fa` |
| CURRENT `pyproject.toml` | 152 | `e076606fd68ab911291be92cdba1bda9df05835baf8db7f81b1d33d517ce6a25` |
| root / `dayu/` / Fins / tests README | 348 / 111 / 793 / 293 | `2f5cebfd...a6e6a` / `1534bcfd...d9a74` / `a4805995...9767` / `15bb09f8...1fba9` |
| CURRENT `requirements.txt` | 12 | `7e8c14d6...79c93` |
| OLD `dayu/fins/cli_support.py` | 2267 | `248cc859d4dd0fdf8ed7829cc27dad48349227dfbd43f076414770166c93da45` |
| OLD `dayu/fins/upload_recognition.py` | 555 | `5a45618b2545ad0ee024efb428de7e614c96b2c5bb0a222bf1586febc1dff816` |

进入 implementation 前，Controller 必须以 accepted-plan commit 的 parent 重新锁定所有 production/test/README/CI
输入。Controller-owned control 文件可因 gate transition 合法变化；任一 production contract、owner、allowlist 或依赖
发生 material drift 则 stop 并重新裁决，不能机械套用本计划。

### 2.3 Completion truth locks

- umbrella accepted plan：`227317a0`。
- R06：accepted plan `0d802220fd1ca4ec67addc85915df27becc9b594`；accepted implementation
  `4f417e91`；completion `f1c56ea9`；final ledger `9 closed / 0 open / 0 blocker`。
- R09：accepted plan `9d36a115400fb59fd95475189810b43a09fda31b`；accepted implementation
  `8e0f2c5588c395cc8ee459a35f36db1de737b450`；completion
  `1c2585275f4134d8456a3fda2d84464e4e52c9d7`；actual accepted residual `0`。
- R10：accepted plan `3dc01b10862a17cb4a4e982a1b684bb4c1680358`；accepted implementation
  `140de7144f8bfb79e98cf399abd4712e79a1771b`；completion/baseline
  `2b14b2fbc89654267e3d33daa2ae410ceff45e68`；accepted/open/residual 均为 `0`。
- R11 只消费 R06 已完成 upload transaction/command contract 与 R09 direct-stream terminal contract；不修改其 owner，
  不让 script generator 调 live Service。R10 仅提供当前完成基线。R12 未授权。

### 2.4 Umbrella baseline 到本计划 exact execution truth 的映射

| Umbrella mandatory baseline | 本计划 disposition | 直接证据与 exact replacement/refinement |
|---|---|---|
| R11-S1 Fins typed classification owner | 保留 | CURRENT `upload_batch.py` 仍只有 generic `entries`/path-only skips；§5 固定 OLD 分类、同期优先级、caps 与三分 typed plan。 |
| R11-S2 CLI/script contract 与 POSIX/Windows real smoke | 基于直接代码证据细化 | CURRENT CLI 仍输出 JSON v1；§6 固定 current grammar、唯一 renderer/publisher、真实 `/bin/sh` recorder 与真实 CLI/temp-storage node；§7 固定唯一 Windows workflow、真实 `cmd.exe` 两个 release-blocking node。 |
| R11-S3 `pyproject.toml`、placeholder packages/tests、根/Fins/tests README | 基于直接代码证据细化 | `requirements.txt:3,7,9,12` 仍消费 `[web]` 并宣称 Streamlit/dayu-web；`dayu/README.md:72` 仍把三 placeholder 写成稳定边界；`pyproject.toml:74-78,130-137` 还有 web extra/comment 与 `dayu.render` package-data。它们是删除 public/package surface 的直接传播点，故加入 closed allowlist；这不是新产品范围。 |
| constraints/lock 中 Streamlit/watchdog pin | 保留、no-touch | constraints 只限制“若 dependency graph 选择该依赖时的版本”，不会自行安装，也不发布 script/package。删除 `pyproject` web extra 与 `requirements.txt` 的 `[web]` 消费后，wheel `METADATA`/临时安装必须证明无 `Provides-Extra: web`、无 Streamlit requirement；不机械清理历史 pin。若 build/install 证明仍被 graph 消费则 stop，而非扩域改 lock。 |
| R11 placeholder/source 零残留 scan | 基于直接代码证据细化 | `tests/tools/web/test_web_tools_provider.py` 与 `test_diagnose_web_access.py` 的 `"dayu.web"` 是禁止恢复旧 UI import 的负向 boundary sentinel，必须保留；§8 只扫 public scripts/package files/importable archive/README unavailable claims，并对两个 sentinel 做正向精确断言，不做全仓裸 `dayu.web` 零命中。 |
| upload JSON 零残留 scan | 基于直接代码证据细化 | 仓库其它 ingestion/storage `schema_version` 合法；§8 仅扫 `_UPLOAD_BATCH_SCHEMA*`、`_render_upload_batch_plan`、相邻 `schema_version/commands/argv` 与 JSON-argv 文案。 |
| changed production coverage `>=80%` | 保留并纠偏为 line coverage | AGENTS/umbrella §7 要求每个实际 changed production Python file 的普通 line coverage；§8 不使用 `--branch`，逐文件读取 coverage JSON `summary.percent_covered >= 80.00`。 |
| generic build frontend smoke | 以可执行 wheel 验证替换 | 锁定 `.venv` 缺少额外 build frontend，且 R11 不授权增加 build 依赖；当前 `python -m pip wheel` 可用。§7/§8 使用 `pip wheel --no-deps --no-build-isolation`，直接检查 wheel metadata/archive并做隔离安装 smoke；不虚构未验证的 source archive owner。 |
| sub-WU slices/review/accepted commit | 保留 umbrella Gateflow | accepted-plan commit 后顺序实施三个 slices，每 slice 只做 Controller checkpoint；S3 后对完整 cumulative diff 做固定双 review/fix/re-review并只创建一个 accepted sub-WU commit，详见 §9，不发明 slice commit 或旁路 review。 |

## 3. Goal、success signals 与 forbidden scope

### 3.1 Goal

完成一个 OLD-aligned、current-architecture 的 `upload_filings_from`：Fins 从授权目录产生 typed
recognized/material/skipped plan；CLI 在生成阶段可选地只解析一次 FMP company info，把 plan 投影为当前平台可直接执行
的 `.sh`/`.cmd`，安全原子发布并输出可读摘要；同时撤下 Web/WeChat/render placeholder public surface。

### 3.2 Success signals

1. Fins 是扫描、OLD 规则分类、财期、material metadata、同期优先级/去重、数量限制、skip reason 的唯一 owner；
   CLI renderer 对文件名和 raw fields 零业务推断。
2. 产物不是 JSON：POSIX `.sh` 与 Windows `.cmd` 均真实可执行，default/explicit output、同源 regenerate comment、
   调用者追加参数与当前 `python -m dayu.cli upload_filing|upload_material` grammar 全部成立。
3. `upload_filing`、`upload_material`、`upload_filings_from` 的 action 都含 `auto` 且默认 `auto`；batch 只允许
   `auto|create|update`，绝不生成 delete。
4. ticker CSV 首项经现有 normalization 成为 canonical；其余显式 aliases 规范、稳定去重；`--infer` 最多调用一次
   当前 FMP resolver，显式值 precedence 与 metadata 传播有 owner tests。
5. 脚本发布保留 containment、symlink rejection、same-directory atomic replace、mode/newline；不可信 argv 不越界，
   API key/provider URL/异常 cause 中的 secret 不进入脚本、summary 或 artifact。
6. 真实 `/bin/sh` recorder、真实 POSIX `python -m dayu.cli -> Service/Fins -> temp storage` smoke 通过。
7. 真实 `windows-latest` / `cmd.exe` recorder 与 CLI grammar smoke 通过；任何 skip/未运行/失败是 release blocker。
8. wheel 不再发布 placeholder entrypoints/packages；README、help、tests 不冻结不存在能力或 JSON protocol。
9. 每个 changed production Python file 的 line coverage `>=80%`，affected/full-related tests、full pyright、Ruff、
   diffcheck、source/propagation/security/deferred scans 全通过。

### 3.3 Deferred / no-touch

- 不实现或修改 Issue 142、151、175、177、178；不创建新 issue，也不替既有 Web #84、WeChat #147 或 render tracker
  实现能力。
- 不进入 R12 `init`；不修改 init grammar、workspace mutation、provider/model/API-key setup 或 prewarm。
- 不实现真实 Web、WeChat、render package；只删除 placeholder。
- Topic 8 的 Engine 240-char projection 不变；Topic 9 不实现统一 authorization。仅保留本轮直接 I/O 与 argv 安全。
- 不改 `dayu/service/**`、`dayu/host/**`、`dayu/engine/**`、`dayu/runtime/**`、storage schema、FMP resolver、
  ticker normalizer、design docs、constraints/locks 或 Controller control。
- 不增加 JSON fallback、compat re-export/wrapper/alias、loose parsing、test-only production seam、第二 renderer、
  shell-specific业务分支、generic authorization 或 extra payload。

## 4. Semantic owner map 与 cumulative closed allowlist

| Semantic fact | 唯一 owner | 允许消费者 |
|---|---|---|
| upload suffix allowlist | 既有 current Fins upload suffix contract | batch scanner 直接复用，不复制 OLD suffix set |
| 文件发现、effective recursion、source containment/symlink verdict | `dayu.fins.upload_batch` | CLI 只收到 typed facts/failure |
| 财期推断、material routing/name、priority、dedup、caps、skip reason | `dayu.fins.upload_batch` 单一 helpers | CLI 机械投影 |
| canonical ticker 与显式 alias CSV grammar | CLI input boundary + 既有 ticker normalization | typed batch request、direct upload request |
| FMP response parse/normalize | 既有 `FmpCompanyInfoResolver` | CLI 生成阶段只调用一次；Fins 不读 env/网络 |
| explicit 与 inferred company/aliases merge | CLI input boundary | batch plan 接收已定型 typed metadata |
| direct upload public flags/defaults | `dayu/cli/arg_parsing.py` | command builder 必须精确使用该 grammar |
| plan entry -> argv 投影 | `dayu/cli/commands/fins.py` 的单一 builder | renderer 只消费 `tuple[str, ...]` |
| POSIX/Windows quoting、regenerate comment、passthrough | `dayu/cli/upload_script.py` 平台 renderer | command builder/tests 不自行 replace/escape |
| output target、containment、symlink、atomic publish、mode | `dayu/cli/upload_script.py` publisher | CLI command 只传 workspace/output intent |
| 可读 summary | CLI command | stdout，不产生机器 schema |
| console scripts、wheel 内容 | `pyproject.toml` + build artifact | README/tests 只描述真实 surface |
| Windows runner/triggers/artifact publication | `.github/workflows/r11-upload-script-windows.yml` | release gate 读取真实 run evidence |

R11 cumulative implementation closed allowlist：

**Production / packaging / CI**

- `dayu/fins/upload_batch.py`
- `dayu/cli/commands/fins.py`
- `dayu/cli/arg_parsing.py`
- `dayu/cli/upload_script.py`（新增）
- `pyproject.toml`
- `requirements.txt`
- `.github/workflows/r11-upload-script-windows.yml`（新增；已确认无现存 workflow/runner 后的唯一最小 workflow）
- 删除 `dayu/web/__init__.py`、`dayu/web/__main__.py`
- 删除 `dayu/wechat/__init__.py`、`dayu/wechat/main.py`
- 删除 `dayu/render/__init__.py`、`dayu/render/render.py`

**Tests**

- `tests/fins/test_upload_batch.py`
- `tests/cli/test_upload_filings_from_command.py`
- `tests/cli/test_fins_commands.py`
- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_public_package_entrypoints.py`

**README**

- `README.md`
- `dayu/README.md`
- `dayu/fins/README.md`
- `tests/README.md`

Gate 自身按 umbrella 固定流程另行授权的 plan/review/validation/implementation/completion artifacts 与 Controller control
transition 不计入 product allowlist。除此以外任何 tracked diff 都立即 stop。`tests/fins/test_fmp_company_info_resolver.py`
是只读验证输入，不在修改 allowlist。`test_public_package_entrypoints.py` 还拥有非 placeholder 的 Docling dependency/lock
测试，必须只删除/改写 placeholder 部分，不能机械删除整个文件。

## 5. Slice 1 — Fins OLD batch classification owner

### 5.1 Exact allowlist、flow 与 contract

本 slice 只允许修改：

- `dayu/fins/upload_batch.py`
- `tests/fins/test_upload_batch.py`

Flow：

```text
UploadBatchPlanRequest
  -> validate canonical input/source root
  -> stable supported-file discovery
  -> per-file OLD fiscal/material recognition
  -> material-first disjoint routing
  -> filing same-period priority/dedup
  -> filing/material caps
  -> UploadBatchPlan(recognized, material, skipped)
```

`BatchUploadAction = Literal["auto", "create", "update"]`，默认 `auto`。计划采用职责分离的 frozen typed models：

- `UploadBatchPlanRequest`：canonical ticker、aliases、source dir、action、recursive、explicit fiscal year/period、amended、
  filing/report dates、company name、overwrite、可选单一 material form override；不含 executable、argv、output 或 shell。
- `UploadBatchFilingEntry`：单一 file、ticker/aliases/action、最终 fiscal year/period、amended、dates、company、overwrite。
- `UploadBatchMaterialEntry`：单一 file、ticker/aliases/action、form type、material name、可选 fiscal year/period、amended、
  dates、company、overwrite；不臆造 `document_id` / `internal_document_id`。
- `UploadBatchSkippedEntry`：path、typed reason code 与业务可读 reason；reason 由 Fins 产生，CLI 不从路径重算。
- `UploadBatchPlan`：`recognized_entries`、`material_entries`、`skipped_entries` 三个 tuple；不得保留 generic
  `command_name`、JSON schema version、argv 或 raw dict bag。

所有新增/修改函数、类、模块按 AGENTS 写完整中文 docstring、严格类型；模块级 helper 拥有单一规则，不用 `Any`、
`object`、`hasattr/getattr`、nested class/function 或兼容 alias。

### 5.2 Exact classification rules

1. source root 必须存在、为真实目录，且 source root 这个 lexical path 自身不是 symlink；root 非法是 typed usage
   failure。lexical source root 与 resolved source root 分别形成扫描 boundary：候选 lexical path 必须在 lexical root
   内，candidate resolved path 必须在 resolved root 内；从 root 到 candidate 的每个内部组件（含 candidate）只要是
   symlink 就拒绝。不得向上扫描或拒绝 source root 外部祖先，因此 `/tmp -> /private/tmp` 这类 external ancestor symlink
   可用。候选用 current `FINS_UPLOAD_FILE_SUFFIXES`，不是复制 OLD 后缀表。
2. 默认只扫描直属文件；用户 `--recursive` 或顶层存在 OLD structured directory
   `20YY` / `20YYQ1..Q4` / `20YYH1` 时 effective recursive。候选按 relative POSIX path 的 Unicode code-point
   顺序稳定排列。
3. 候选 symlink、resolved escape 或非普通文件不得读取；进入 `skipped` 并给出明确安全原因。unsupported suffix 不进入
   recognized/material；测试固定其可读 skip/ignore contract，不能在 CLI 二次判定。
4. fiscal year 使用首个 `20YY`；period 依 OLD patterns 支持 `Q1..Q4`、`1Q..4Q`、中文一至四季度、`H1` /
   half-year/半年/中报/中期报告、`FY`/annual/年度报告/年报。Q4 含“季报”保留 Q4，否则为 FY。先看文件名；
   文件名不足时只允许从直接 structured parent `20YYQn`/`20YYH1` 补齐，纯年份 parent 不能猜 period。
5. 当前 `upload_filings_from` 已有 explicit `--fiscal-year` / `--fiscal-period` 是用户事实：对应字段有值时逐字段覆盖
   推断值，无值时才用 OLD inference。filing 最终缺 year 或 period 则 skipped；material 可保留可选 fiscal fields。
   不从 mtime、排序、文件内容或 sibling 猜 metadata。
6. material routing 按 OLD 表首个命中：`FINANCIAL_STATEMENTS`（财务报表）、`EARNINGS_CALL`（电话/业绩会议纪要、
   Earnings/Conference Call、Transcript）、`EARNINGS_PRESENTATION`（演示、Slide、Presentation、Investor Day、Deck）。
   已命中 material 的文件不再进入 filing。显式 `--material-forms` 最多一个 normalized form，只覆盖已经 material-routed
   entry 的 form type；它不能把所有文件强制变 material，多个值是 usage error。
7. material name 按 OLD 规则从 stem 派生：保留/补 structured year-period prefix，移除紧随前缀的 `HKEX` 标识；
   不把路径、内部 ID 或 CLI flag 混进名称。
8. 未走 material 的 filing 先按 `(fiscal_year, fiscal_period)` 分组。优先级从好到差固定为：长覆盖正式报告 `0`、
   季度正式报告 `1`、通用“报告” `2`、公告/通告 `3`、其它 `4`、演示/新闻/简报/摘要 `5`；同优先级以此前
   stable relative path 决胜。被去重项进入 typed skipped，不静默丢失。
9. 先同期去重，再做数量规则：FY 按年度降序最多 5；periodic 只保留已识别到的最新 fiscal year，并按
   `Q1,H1,Q2,Q3,Q4` 顺序最多 6；被裁剪项均带 owner reason。
10. material 分 form 排序稳定：`EARNINGS_PRESENTATION` 按文件名可识别年份降序最多 6；`EARNINGS_CALL` cap 精确等于
    过滤后的 recognized filing 数量；`FINANCIAL_STATEMENTS` 无 cap。filtered recognized filing count 为 `0` 时 call
    cap 也必须是 `0`，所有 `EARNINGS_CALL` candidates 都进入带 cap reason 的 typed skipped，不得擅自保留 minimum-one。
    没有识别年份时用 stable path 作最后排序键，不能从 mtime 猜年份。
11. explicit amended、dates、company、ticker aliases 原样传播到每个真实拥有这些 current upload 字段的 entry；
    `overwrite` 只作为 direct upload storage overwrite fact 原样传播。没有值就保持 `None/False/()`，禁止默认字符串、
    extra payload，或把 `overwrite` 解释为脚本 target replacement policy。
12. recognized/material 均为空时抛现有语义对应的 typed empty error，同时保留 skipped evidence；不得生成空脚本、
    JSON fallback 或把 unsupported 文件伪装成 material。

### 5.3 Tests、real smoke 与 stop conditions

Focused tests：

```bash
source .venv/bin/activate
pytest tests/fins/test_upload_batch.py -q
```

owner tests 必须覆盖：supported/unsupported、non-recursive/explicit recursive/structured auto-recursive、文件名与父目录
推断、Q4 分流、material routing precedence/name、explicit fiscal precedence、annual=5、periodic=latest-year/max6、
presentation=6、call=count(filtered reports)、zero recognized filings 时全部 call candidates typed skipped、financial
statements no cap、同期优先级/tie、stable ordering、每类 skip reason、external-ancestor symlink allowed、source root-self
symlink rejected、root 内 component/candidate symlink rejected、escape rejected、auto/create/update、
metadata/aliases/overwrite、empty plan。

真实 filesystem smoke（不 mock scanner、不经 CLI）：在 `workspace/tmp/r11-s1-smoke` 建真实层级与普通文件，调用公开
batch-plan API，核对 typed 三分结果、同周期 winner、caps、父目录 fallback 与 resolved containment；输出只写
`workspace/tmp`，不修改 tracked fixture。该 smoke 证明真实文件发现/owner plan，不冒充脚本或上传 smoke。

```bash
source .venv/bin/activate
python -m pytest tests/fins/test_upload_batch.py::test_real_filesystem_builds_typed_old_aligned_plan -q
```

S1 checkpoint 必须由 Controller 按以下 S2 consumer mapping checklist 逐字段冻结 producer contract；任何字段、枚举或
optional 规则不能留给 S2 adapter、renderer 或 fixture 推断：

| S1 typed fact | S2 current command / flag mapping | enum / optional lock |
|---|---|---|
| `UploadBatchFilingEntry` / `UploadBatchMaterialEntry` | 分别固定为 `upload_filing` / `upload_material` | entry type 是唯一 command discriminator；renderer 不再判型 |
| canonical ticker + aliases tuple | 单一 `--ticker` CSV，canonical 在首位，其后按 tuple 顺序 | aliases 为空时只传 canonical；不得另造 alias flag |
| `action` | `auto` 省略 `--action`；`create/update` 传对应值 | 只允许 `auto|create|update`；S2 不接受或产生 `delete` |
| 单一 `file` | `--files <path>` | 每 entry 精确一个 path；不得合并、重扫或重排 |
| `fiscal_year` / `fiscal_period` | 非 `None` 时分别传 `--fiscal-year` / `--fiscal-period` | `fiscal_period` 由 S1 归一为 `FY|H1|Q1|Q2|Q3|Q4`；filing checkpoint 必须二者都有值；material 可独立为 `None`，无值不传 |
| `amended` | `True` 时传 `--amended` | `False` 时不传，不生成字符串默认值 |
| `filing_date` / `report_date` / `company_name` | 非 `None` 时分别传 `--filing-date` / `--report-date` / `--company-name` | 无值不传；不得由 S2 再推断 |
| `overwrite` | `True` 时传 direct command 的 `--overwrite` | `False` 时不传；只表示 storage overwrite，不影响 publisher |
| material `form_type` / `material_name` | 分别传单值 `--forms` / `--material-name` | `form_type` 由 S1 归一为 `FINANCIAL_STATEMENTS|EARNINGS_CALL|EARNINGS_PRESENTATION`；二者只属于 material |
| filing/material 不拥有的 fields | 不产生对应 flag | filing 不带 material fields；batch material 不臆造 `--document-id` / `--internal-document-id` |
| skipped `path` / reason code / readable reason | 只进入 human summary，不生成 argv | 三项均由 S1 owner 产生；S2 不重算 display fact 或 reason |

若 checklist 暴露 typed fact 缺失、enum 与 current grammar 不一致，或 optional ownership 仍需消费者猜测，S1 checkpoint
不得通过。若同类 gap 在 S2 开始后才由首个真实 consumer 暴露，则按 §9.1 的唯一回返路径处理，禁止 S2 补偿。

Slice stop：任何 OLD rule 不能映射为当前 typed upload fact、current suffix owner 与实际 runtime 冲突、需要 Service/
storage/CLI classifier 才能完成、source containment 无法在 Fins boundary 保证，或 slice diff 越出两路径时立即 stop。
S1 通过 Controller exact allowlist/contract/test/smoke checkpoint 后才进入 S2；不做 slice acceptance 或中间
implementation commit。

## 6. Slice 2 — Current CLI grammar、FMP 与 shell/cmd renderer

### 6.1 Exact allowlist 与 input/output contract

本 slice 只允许修改/新增：

- `dayu/cli/commands/fins.py`
- `dayu/cli/arg_parsing.py`
- `dayu/cli/upload_script.py`（新增）
- `tests/cli/test_upload_filings_from_command.py`
- `tests/cli/test_fins_commands.py`
- `tests/cli/test_arg_parsing.py`

Flow：

```text
ParsedCliArgs
  -> normalize ticker CSV + optional one FMP resolve
  -> UploadBatchPlanRequest
  -> Fins typed UploadBatchPlan
  -> one current-grammar argv builder
  -> platform renderer
  -> contained atomic publisher
  -> human summary
```

`upload_filings_from` 不创建 direct Service；生成的脚本执行时才逐条进入现有 direct CLI -> Service -> Fins。

### 6.2 Current grammar locks 与 metadata projection

1. `upload_filing` current request fields 精确为：ticker/action/files/fiscal-year/fiscal-period/amended/filing-date/report-date/
   company-name/ticker aliases/overwrite。`upload_material` 在此基础上还拥有单一 form type、material-name、可选
   document-id/internal-document-id；batch entry 没有后两项，生成脚本不得臆造。
2. `FILING_ACTION_CHOICES` 改为 `auto|create|update|delete`；`BATCH_UPLOAD_ACTION_CHOICES` 为
   `auto|create|update`；所有三个 upload parser default 都是 `auto`。生成 entry 为 `auto` 时省略 `--action`，显式
   create/update 才写入；batch 不生成 delete。
3. ticker CSV 首项必须调用现有 strict `normalize_ticker` 得到 canonical。后续 alias token trim、拒绝空项，使用同一
   normalizer 产生比较 key 与 current runtime 可消费的 canonical alias；按输入顺序去重并排除 canonical。无效 alias
   是 CLI usage error，不把公司名当 ticker alias，不保留 loose fallback。
4. `--infer` 只注册在 `upload_filings_from`，精确 grammar 为 `action="store_true"`、`default=False`；help 必须自解释为
   “使用 FMP 公司信息补全公司名称与 ticker aliases（需要 `FMP_API_KEY`）”。未传时零 resolver/env 访问；传入时 CLI
   从 `FMP_API_KEY` 显式读取，缺失立即失败；创建当前 `FmpCompanyInfoResolver` 并只调用一次其现有 public method
   `resolve_company_info(canonical)`。这里“一次解析”是一次 resolver public method 调用，不臆测其内部 HTTP hop 数，
   也不修改 resolver HTTP owner。
5. merge precedence：canonical 始终来自用户首项；显式 aliases 在前、resolver aliases 在后，均经同一 key 稳定去重；
   显式 `--company-name` 非空时优先，否则使用 resolver company name。resolver canonical 与请求 canonical 不一致是
   typed generation failure，不静默改 ticker。provider failure 无 fallback；用户消息不得输出 API key、含 key URL、
   raw response 或 exception cause repr。
6. source command 当前 explicit fiscal/amended/dates/company/material/overwrite 字段精确进入 S1 request。为完成 current
   metadata 传播，`upload_filings_from` grammar 必须显式加入 `--overwrite`，精确为 `action="store_true"`、
   `default=False`；help 必须自解释为“允许每条生成的上传命令覆盖已有存储文档；不控制脚本文件替换”。它只传播到
   S1 request/entry 并投影为每条 direct upload 的 storage overwrite fact，不控制 publisher existing-target replacement，
   也不新增 `--force-output`。保留既有 fiscal/year、amended、dates、company 与 `--material-forms`，不新增 runtime 不拥有
   的字段。
7. 单一 argv builder 以 `("python", "-m", "dayu.cli", command, ...)` 开头，`command` 只能是 `upload_filing` 或
   `upload_material`；因此脚本每个 executable body line 都是相应 `python -m dayu.cli` 调用，不存在第三种 body command。
   每条带 `--base`、canonical+aliases CSV、`--files` 与该 entry 实际拥有的 optional fields。filing 不带 material fields；
   material 带 `--forms`、`--material-name`，不带未产生的 IDs。flag 顺序只在该 builder 定义；renderer 不判断 command kind。
8. regeneration argv 由同一 parsed facts/builder source 生成，注释可复制，包含 source/output/infer 等生成参数，但不含
   API key 或 inferred secret。脚本 body bake 合并后的 aliases/company，执行时不再次调用 FMP。

### 6.3 Output path、safe publish 与 human summary

- 无 `--output`：写入 resolved `--base` workspace root，POSIX
  `upload_filings_<CANONICAL>.sh`，Windows `upload_filings_<CANONICAL>.cmd`。
- `--output` 指向既有目录：目录内使用同一默认文件名；否则原样采用 exact explicit file path。平台内容、编码与换行由
  实际 OS 决定；不得重命名、补后缀或臆造无真源的显式输出后缀限制。
- lexical output target 必须位于 lexical workspace root，resolved output parent/target 必须位于 resolved workspace root。
  workspace root 这个 lexical path 自身是 symlink 时拒绝；从 root 到 output target 的内部路径组件（含已有 target）任一
  是 symlink 时拒绝。不得检查或拒绝 workspace root 外部祖先，所以 `/tmp -> /private/tmp` 这类 external ancestor
  symlink 必须允许。publisher 在目标同目录创建 owner-private temp，写完整内容、flush/fsync、POSIX chmod `0o755`，再
  `os.replace`；valid contained non-symlink existing regular target 也按此 output contract 独立原子替换，与 direct upload
  `--overwrite` 的 true/false 无关。失败或 `KeyboardInterrupt` 清理 temp，旧 target 保持 byte-for-byte，不留下 partial；
  existing directory/非普通 target 是 write failure。Windows 不宣称 POSIX mode，也不新增 `--force-output`。
- POSIX UTF-8/LF；Windows UTF-8/CRLF。脚本不得包含 env secret、resolver raw error、临时 storage path或 JSON protocol。
- stdout 仅输出脚本绝对位置、recognized/material/skipped counts 与逐项业务可读 skip reason；不输出第二机器 schema。
  成功 exit 0；usage/provider/write failure 复用 CLI 既有错误出口，不把 traceback/secret写进脚本。

### 6.4 POSIX renderer contract

- exact header：`#!/usr/bin/env sh`、`set -eu`。
- 每个固定 argv 只由 renderer 使用 `shlex.quote`/`shlex.join` 编码；每条 body command 末尾安全追加 `"$@"`，从而把
  caller 追加参数逐元素传给每条 upload command。
- regeneration comment 使用 `# ` 且由同一 argv 输入生成；不可因注释中的 metacharacter 改变脚本。
- unit oracle 与真实 `/bin/sh` recorder 必须恢复每个 fixed argv 和 appended argv 的 exact Unicode string/边界。

### 6.5 Windows outcome、invariants 与 evidence-driven algorithm gate

稳定 outcome 不是“生成字符串看起来已转义”，而是：

```text
typed argv
 -> batch file literal/percent expansion
 -> cmd.exe metacharacter and quote parsing
 -> target Python argv parsing
 == original argv, element-for-element and character-for-character
```

必须同时成立：

- 空字符串、空格、Unicode、单引号、双引号、连续/尾随反斜杠不丢字符、不合并/拆分 argv；
- literal `%` 不触发 `%VAR%` 或 batch parameter expansion；`!` 在 delayed expansion 关闭时保持 literal；
- `& | ^ ( ) < >` 不启动第二命令、pipe、group 或 redirect；无 marker 文件/额外进程；
- caller appended args 恢复 exact boundary；如果 raw `%*` 失败，必须由同一 Windows renderer 改用已验证的 owner 算法；
- fixed argv、regenerate comment 与 passthrough 只能共用一个 Windows quote/escape owner，builder/test fixture/caller 不做
  `replace`；不得使用 `subprocess.list2cmdline` 作为 batch owner、安全证明或 fallback。

script 固定以 `@echo off`、`chcp 65001 >nul`、`setlocal DisableDelayedExpansion` 开始，直到结束不得 re-enable delayed
expansion；CRLF。具体 quote/escape 算法不在无 Windows evidence 的 plan 中臆定。S2 实现顺序必须是：先把上述 adversarial
matrix 写成 renderer unit + real-recorder oracle；再在唯一 renderer 内实现一个候选算法；任何反例即修改同一算法并重跑，
直到真实 `cmd.exe` 通过后才锁定。禁止 compat/fallback/双算法/platform test shim。Windows 本地不可用时 S2 可以完成
非 Windows review，但必须明确标记 release gate pending，不能声称 quoting closed。

### 6.6 Tests 与两类真实 smoke

Focused tests：

```bash
source .venv/bin/activate
pytest tests/cli/test_upload_filings_from_command.py \
  tests/cli/test_fins_commands.py \
  tests/cli/test_arg_parsing.py \
  tests/fins/test_fmp_company_info_resolver.py -q
```

必须覆盖：三个 action grammar/default、auto omission/explicit action、ticker CSV invalid/dedup、`--infer` 与 `--overwrite`
help 的 exact contract、两者 parser default false / explicit true、infer zero/once/missing key/canonical mismatch/provider failure/
explicit merge、overwrite 只传播到每条 direct upload、overwrite true/false 均不改变 publisher replacement、所有 exact
metadata flags、default suffix/output exact file/output dir、summary、regenerate comment、write/replace/interrupt、
external-ancestor symlink allowed、workspace root-self symlink rejected、root 内 output component/target symlink rejected、
lexical/resolved escape rejected、mode/newlines、JSON/schema zero residual、POSIX/Windows 对抗矩阵与 appended args。

POSIX recorder smoke：测试创建临时 Python recorder，只记录 `sys.argv` 为 JSONL；renderer 以真实 Python executable +
recorder path 作为 typed command argv，生成脚本后用 `/bin/sh script.sh <adversarial appended args>` 执行。逐 entry exact
比较 recorder JSONL；测试 injection marker 不存在。recorder 只证明 argv，不进入 Service/Fins。

POSIX real upload smoke 的唯一内容源锁定为 tracked read-only fixture
`tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/aapl-20240928.htm`。测试只读取该 fixture，把其内容分别复制到
`workspace/tmp/r11-posix-real/source/2024FY_AAPL_Annual_Report.htm`（filing）与
`workspace/tmp/r11-posix-real/source/2024FY_AAPL_Earnings_Call_Transcript.htm`（material）；这两个名称必须按 §5 OLD
规则直接识别，不得为 smoke 增加分类特例。不得修改 tracked fixture、不得从网络下载或更新 fixture，所有副本、脚本与
storage 只在 `workspace/tmp/r11-posix-real`。随后使用真实
`python -m dayu.cli --base <temp-storage> upload_filings_from ... --action create` 生成 `.sh`，再用 `/bin/sh` 执行。必须
exit 0，并从临时 storage 证明每条命令真实经过 parser -> Service -> Fins direct runtime、产生对应 source document/
terminal success；不得 monkeypatch Service、runtime、validator 或 storage。外部 provider 不参与。

```bash
source .venv/bin/activate
python -m pytest tests/cli/test_upload_filings_from_command.py::test_posix_script_round_trips_adversarial_argv_with_real_sh -q
python -m pytest tests/cli/test_upload_filings_from_command.py::test_posix_generated_script_runs_real_cli_into_temp_storage -q
```

Slice stop：需要修改 Service/runtime/FMP resolver/ticker normalizer；真实 grammar 不能机械表达 typed entry；quote owner
泄漏到 builder/fixture；publisher 不能守 containment/symlink/atomicity；secret 出现在脚本/summary；或任何 JSON fallback
出现时立即 stop。S2 通过 Controller exact allowlist/contract/test/smoke checkpoint 后才能进入 S3；不做 slice acceptance
或中间 implementation commit。

## 7. Slice 3 — Placeholder/package/README closure 与 Windows release evidence

### 7.1 Exact allowlist 与 changes

本 slice 只允许修改/新增/删除：

- `pyproject.toml`
- `requirements.txt`
- `.github/workflows/r11-upload-script-windows.yml`（新增）
- 删除 §4 列出的六个 Web/WeChat/render package 文件
- `tests/cli/test_public_package_entrypoints.py`
- `README.md`
- `dayu/README.md`
- `dayu/fins/README.md`
- `tests/README.md`

要求：

1. 从 `[project.scripts]` 删除 `dayu-web`、`dayu-wechat`、`dayu-render`；删除只为 placeholder 存在的 `web` optional
   dependency/comment 与 `dayu.render` package-data mapping。保留真实 `dayu-cli` 与其它已实现入口。
2. 从 `requirements.txt` 删除 `[web]` extra 消费与 Streamlit/dayu-web stale placeholder 承诺；保留真实 test/dev/browser
   依赖入口，不顺带修改 constraints/lock 中未被 dependency graph 选择的 inert pins。
3. 删除三个仅 placeholder package 的全部 tracked 文件、future grammar、unavailable diagnostics；不留空 package、re-export、
   wrapper 或 README “暂不可用” surface，不实现 tracker 能力。
4. `test_public_package_entrypoints.py` 删除 placeholder 成功/失败/help contract，保留 Docling dependency/constraints 等真实
   packaging tests，并增加 wheel entrypoint/metadata/archive negative assertions。
5. 根 README 按其最终用户约束说明脚本生成/检查/执行、POSIX/Windows default 后缀、default/explicit output、ticker CSV、
   `--infer` 环境要求、auto、summary、追加参数与排障；删除 JSON argv 和 placeholder claims。
6. `dayu/README.md` 只删除把 Web/WeChat/render placeholder 写成当前稳定 package boundary 的 stale 承诺，并说明目前只列
   真实 package；不得改分层、装配或引入 future capability。
7. Fins README 只说明 typed scan/classification owner、OLD规则/caps/skip contract 与 CLI consumer boundary，不写 workflow/
   review 过程。tests README 只同步当前 tests、真实 smoke、Windows release gate 与 commands。

### 7.2 Existing Windows runner conclusion and minimal workflow

直接调查结论已锁：当前 HEAD 无 `.github` tree/workflow；GitHub repository `noho/dayu-agent-r` default branch `main`，
Actions workflow list/run list 均为空，`main:.github/workflows` 不存在。因此没有可复用 Windows runner owner、触发方式或
artifact 读取位置。R11 必须新增且只新增：

`.github/workflows/r11-upload-script-windows.yml`

最小 workflow contract：

- name：`R11 upload script Windows gate`；`permissions: contents: read`；job runner `windows-latest`；Python `3.11`；
  `timeout-minutes: 30`。
- triggers：`workflow_dispatch`；`pull_request.paths` 精确列出 §4 closed product allowlist：三个 changed production files、
  新 renderer、六个待删 placeholder package files、五个 test files、`pyproject.toml`、`requirements.txt`、四个 README 与本
  workflow。不得使用更宽 glob，不得添加 schedule、release、deployment、secret/provider 或 unrelated matrix。
- install：checkout、setup-python 3.11，并精确执行
  `python -m pip install -e ".[test,dev]" -c constraints/lock-windows-x64-py311.txt`；不安装被删除的 Web extra。
- test command 精确为：

  ```powershell
  New-Item -ItemType Directory -Force workspace/tmp/r11-windows | Out-Null
  python -m pytest tests/cli/test_upload_filings_from_command.py::test_windows_cmd_script_round_trips_adversarial_argv_with_real_cmd tests/cli/test_upload_filings_from_command.py::test_windows_generated_script_runs_real_cli_into_temp_storage tests/cli/test_arg_parsing.py::test_upload_actions_default_to_auto_and_batch_rejects_delete --junitxml=workspace/tmp/r11-windows/pytest-junit.xml -q
  ```

  前两个 node 分别是实际 `cmd.exe` recorder 与实际 `python -m dayu.cli`/temp-storage smoke；不得以 renderer unit test代替。
- invocation 必须是实际 `cmd.exe /d /c <generated.cmd> ...`；`/d` 排除 AutoRun。workflow 同时捕获 OS/Python version 与
  `cmd.exe /?` 输出作为 runner-local evidence，不把外部网页引用设为 blocker。
- env `DAYU_R11_WINDOWS_ARTIFACT_DIR=${{ github.workspace }}\workspace\tmp\r11-windows` 只指定测试证据发布目录，不改变
  production quoting。测试把 `generated-upload.cmd`、`recorder-oracle.jsonl`、`cli-grammar-oracle.json`、stdout/stderr、
  `cmd-help.txt`、`environment.txt`、`pytest-junit.xml` 写入该目录；不包含 API key/secret。
- `actions/upload-artifact@v4` 使用 `if: always()`，artifact name
  `r11-windows-upload-script-${{ github.run_id }}`，path `workspace/tmp/r11-windows/**`，retention 14 days，
  `if-no-files-found: error`。读取位置固定为 GitHub Actions 对应 run 的 Artifacts 区，解压后上述相对路径。

Windows recorder smoke 与 POSIX 同型，但真实执行 `.cmd`；对 fixed/adversarial/appended argv exact JSONL 比对并断言 injection
marker 不存在。Windows CLI grammar smoke 必须用 production builder/renderer 生成 `.cmd`，复制 current fixture 到含空格、
Unicode、`% ! & ^ ( )` 等合法 Windows 文件名/目录组合，以真实 `python -m dayu.cli upload_filing|upload_material` 至少
完成 argparse 与 direct入口；若依赖允许则以临时 storage exit 0 闭环。为消除“service failure 前是否 parse”的歧义，
本计划验收 oracle 固定为 exit 0 + terminal success + temp storage source artifact；环境不允许闭环即 gate fail，不降级成
unit/residual。Windows 禁止文件名字符（如 `|<>:"`）只在 recorder 的普通 argv 中覆盖，不能伪造为 filesystem path。

workflow 文件可随 R11 implementation commit 入库，但本地 branch 未发布前无法得到 GitHub-hosted run。按 umbrella
§7.3/§22，accepted implementation 可以将此 gate 标为 `PENDING_RELEASE_BLOCKER`，但不得标 Windows closed；最迟在
aggregate/draft PR check 触发并通过。任何未执行、skipped、cancelled、失败、artifact 缺失或 oracle 不相等都阻止 umbrella
aggregate acceptance、PR ready/final closeout，不得转 residual risk。

### 7.3 Packaging real smoke 与 stop

```bash
source .venv/bin/activate
pytest tests/cli/test_public_package_entrypoints.py \
  tests/cli/test_arg_parsing.py \
  tests/cli/test_upload_filings_from_command.py -q
rm -rf workspace/tmp/r11-dist workspace/tmp/r11-wheel-extract workspace/tmp/r11-wheel-venv
python -m pip wheel --no-deps --no-build-isolation --wheel-dir workspace/tmp/r11-dist .
python -c "from pathlib import Path; import zipfile; wheels=tuple(Path('workspace/tmp/r11-dist').glob('dayu_agent-*.whl')); assert len(wheels) == 1, f'expected exactly one wheel, got: {wheels}'; zipfile.ZipFile(wheels[0]).extractall('workspace/tmp/r11-wheel-extract')"
python -m venv workspace/tmp/r11-wheel-venv
python -c "from pathlib import Path; import subprocess; wheels=tuple(Path('workspace/tmp/r11-dist').glob('dayu_agent-*.whl')); assert len(wheels) == 1, f'expected exactly one wheel, got: {wheels}'; subprocess.run(('workspace/tmp/r11-wheel-venv/bin/python', '-m', 'pip', 'install', '--no-deps', str(wheels[0])), check=True)"
workspace/tmp/r11-wheel-venv/bin/python -m dayu.cli --help
workspace/tmp/r11-wheel-venv/bin/python -m dayu.cli upload_filings_from --help
workspace/tmp/r11-wheel-venv/bin/python -c "import importlib.util; assert all(importlib.util.find_spec(name) is None for name in ('dayu.web', 'dayu.wechat', 'dayu.render'))"
python -c "from pathlib import Path; root=Path('workspace/tmp/r11-wheel-extract'); files=tuple(root.glob('*.dist-info/METADATA')); assert len(files) == 1, f'expected one METADATA, got: {files}'; hits=tuple(line for line in files[0].read_text(encoding='utf-8').splitlines() if line == 'Provides-Extra: web' or line.lower().startswith('requires-dist: streamlit')); assert not hits, f'forbidden METADATA lines: {hits}'; print('wheel METADATA placeholder contracts: 0')"
python -c "from pathlib import Path; root=Path('workspace/tmp/r11-wheel-extract'); files=tuple(root.glob('*.dist-info/entry_points.txt')); assert len(files) == 1, f'expected one entry_points.txt, got: {files}'; hits=tuple(line for line in files[0].read_text(encoding='utf-8').splitlines() if any(name in line for name in ('dayu-web', 'dayu-wechat', 'dayu-render'))); assert not hits, f'forbidden entry points: {hits}'; print('wheel placeholder entry points: 0')"
python -c "from pathlib import Path; root=Path('workspace/tmp/r11-wheel-extract'); prefixes=('dayu/web', 'dayu/wechat', 'dayu/render'); hits=tuple(sorted(path.relative_to(root).as_posix() for path in root.rglob('*') if any(path.relative_to(root).as_posix() == prefix or path.relative_to(root).as_posix().startswith(prefix + '/') for prefix in prefixes))); assert not hits, f'forbidden extracted placeholder paths: {hits}'; print('wheel extracted placeholder paths: 0')"
python -c "from pathlib import Path; import csv; root=Path('workspace/tmp/r11-wheel-extract'); files=tuple(root.glob('*.dist-info/RECORD')); assert len(files) == 1, f'expected one RECORD, got: {files}'; rows=tuple(csv.reader(files[0].read_text(encoding='utf-8').splitlines())); prefixes=('dayu/web', 'dayu/wechat', 'dayu/render'); hits=tuple(sorted(row[0] for row in rows if row and any(row[0] == prefix or row[0].startswith(prefix + '/') for prefix in prefixes))); assert not hits, f'forbidden RECORD placeholder paths: {hits}'; print('wheel RECORD placeholder paths: 0')"
```

wheel `METADATA` 必须无 `Provides-Extra: web` 与 Streamlit requirement，`entry_points.txt` 只含真实 scripts，archive 中必须零
`dayu/web`、`dayu/wechat`、`dayu/render`；隔离安装后两个真实 help command 成功且无 placeholder/JSON claims。所有
build/extract/install 只在 `workspace/tmp`。四个 Python negative oracle 均必须 exit 0，且 stdout 依次精确包含
`wheel METADATA placeholder contracts: 0`、`wheel placeholder entry points: 0`、
`wheel extracted placeholder paths: 0`、`wheel RECORD placeholder paths: 0`；任一命中、缺少或出现多个 wheel/dist-info
文件都以 assertion 非零退出并打印 exact hits。wheel 与 dist-info 选择由 Python exact-one assertion 完成，不依赖 shell
wildcard 展开。importability assertion 也必须 exit 0。archive/RECORD oracle 已治理构建产物内任意 placeholder path；不单独
治理 working tree untracked `__pycache__`，也不把合法 `top_level.txt=dayu` 当残留。

Slice stop：删除项仍被 production import/entrypoint 引用、optional dependency 兼有真实非-placeholder owner、wheel 仍含
package/extra/requirement、需要实现 tracker 能力、Windows workflow 需 secrets或无法运行真实 cmd、或 README 职责越界时
立即 stop。S3 通过 Controller exact allowlist/contract/test/smoke checkpoint 后进入一次 cumulative review，不做 slice
acceptance 或中间 implementation commit。

## 8. Cumulative validation、coverage、scans 与 security gates

### 8.1 Mandatory local validation

```bash
source .venv/bin/activate
python -m ruff --version
pytest tests/fins/test_upload_batch.py \
  tests/cli/test_upload_filings_from_command.py \
  tests/cli/test_fins_commands.py \
  tests/cli/test_arg_parsing.py \
  tests/cli/test_public_package_entrypoints.py \
  tests/fins/test_fmp_company_info_resolver.py -q
pytest tests/cli tests/fins tests/service -q
pytest tests -q
python -m pyright dayu/ tests/ utils/
python -m ruff check dayu/fins/upload_batch.py dayu/cli/commands/fins.py dayu/cli/arg_parsing.py \
  dayu/cli/upload_script.py tests/fins/test_upload_batch.py \
  tests/cli/test_upload_filings_from_command.py tests/cli/test_fins_commands.py \
  tests/cli/test_arg_parsing.py tests/cli/test_public_package_entrypoints.py
python -m ruff check dayu tests utils --output-format json > workspace/tmp/r11-ruff-current.json
git diff --check 2b14b2fbc89654267e3d33daa2ae410ceff45e68
```

测试数量、skip 与 baseline delta 记录到 implementation/aggregate evidence；既有 unrelated skip 不得冒充 R11 smoke。Controller
在 accepted-plan parent 锁 `workspace/tmp/r11-ruff-baseline.json` 时，必须在同一已激活 `.venv` 用完全相同命令
`python -m ruff --version` 记录 verbatim version oracle。implementation 与 aggregate 开始时也运行这一命令，并在执行任何
Ruff delta 比较前逐字匹配该 oracle；版本漂移立即 stop，由 Controller 在同一 implementation 输入树上同时重新锁 version
oracle 与 full baseline，不能把 Ruff 版本/规则漂移算作 current finding。Ruff scoped command 必须零错误；full command 的
退出码与 JSON 原样记录，并与锁定的 baseline 按 relative filename/code/row/column/message 精确做 set difference，
current-only 必须为空。不得用 noqa、配置 exclusion 或只更新 baseline 掩盖 current finding。

### 8.2 Per-file line coverage

```bash
coverage erase
coverage run -m pytest tests/fins/test_upload_batch.py \
  tests/cli/test_upload_filings_from_command.py tests/cli/test_fins_commands.py \
  tests/cli/test_arg_parsing.py tests/cli/test_public_package_entrypoints.py
coverage json -o workspace/tmp/r11-coverage.json
```

从 JSON 对实际 changed production Python files 逐文件读取普通 line `summary.percent_covered`，每个
`>=80.00`：`dayu/fins/upload_batch.py`、`dayu/cli/commands/fins.py`、`dayu/cli/arg_parsing.py`、新增
`dayu/cli/upload_script.py`。未实际变更的文件不虚报；删除的 `dayu/render/**` 免覆盖率但不免 archive scan。低于阈值即
失败，禁止扩大 omit、pragma、fake/mock-only line 或用总覆盖率代替单文件结果。

### 8.3 Exact source/propagation/security/deferred scans

Implementation/aggregate 必须记录以下命令的 exact output，并结合人工 owner review；零匹配项使用 `rg` exit 1 作为成功
证据，不用 `|| true` 吞错：

```bash
rg -n '_UPLOAD_BATCH_SCHEMA(_VERSION)?|_render_upload_batch_plan|schema_version.{0,160}commands|commands.{0,160}(argv|upload_filing|upload_material)|JSON[- ]argv' \
  dayu/cli/commands/fins.py dayu/cli/arg_parsing.py dayu/fins/upload_batch.py \
  tests/cli tests/fins/test_upload_batch.py README.md dayu/fins/README.md tests/README.md
rg -n 'dayu-web|dayu-wechat|dayu-render|dayu\.(web|wechat|render)|尚未.*(Web UI|微信|渲染)|Streamlit Web UI|\[web\]' \
  pyproject.toml requirements.txt README.md dayu/README.md dayu/fins/README.md tests/README.md tests/cli
git ls-files dayu/web dayu/wechat dayu/render
rg -n '"dayu\.web"' tests/tools/web/test_web_tools_provider.py tests/tools/web/test_diagnose_web_access.py
rg -n 'list2cmdline|shell[[:space:]]*=[[:space:]]*True|setlocal EnableDelayedExpansion' dayu/cli
rg -n 'setlocal DisableDelayedExpansion' dayu/cli/upload_script.py tests/cli/test_upload_filings_from_command.py
rg -n 'FMP_API_KEY|R11_SENTINEL_FMP_SECRET_7f31c0|financialmodelingprep\.com' workspace/tmp/r11-posix-real/*.sh
rg -n 'FMP_API_KEY|R11_SENTINEL_FMP_SECRET_7f31c0|financialmodelingprep\.com' workspace/tmp/r11-windows/*.cmd
git diff --name-status 2b14b2fbc89654267e3d33daa2ae410ceff45e68 -- \
  dayu tests pyproject.toml requirements.txt README.md .github
git diff --name-only 2b14b2fbc89654267e3d33daa2ae410ceff45e68 -- \
  README.md dayu/README.md dayu/fins/README.md tests/README.md
rg -n 'upload_filings_from|upload_filings_<TICKER>|--infer|action.*auto' \
  README.md dayu/fins/README.md tests/README.md
git diff --name-only 2b14b2fbc89654267e3d33daa2ae410ceff45e68 -- \
  dayu/service dayu/host dayu/engine dayu/runtime dayu/config dayu/tool dayu/ui constraints \
  docs/host/design.md docs/engine/design.md docs/tool/design.md docs/fins/design.md docs/ui/design.md
git diff --stat 2b14b2fbc89654267e3d33daa2ae410ceff45e68
git diff --check 2b14b2fbc89654267e3d33daa2ae410ceff45e68
git diff --cached --name-only
```

前两个 `rg` 与 `git ls-files`、production danger scan、两个 artifact secret/network scan、deferred diff 均须零输出；
`DisableDelayedExpansion` 是正向命中。两个合法 `"dayu.web"` 负向 import-boundary sentinel 必须精确各命中一次且对应 test
files 无 diff，不能把它们纳入 placeholder 零命中。schema scan 不扫其它合法 storage/ingestion schema；API-key scan 只扫真实
生成 artifact 中的 env 名、固定 test secret 值与 provider URL，不把生产输入边界合法读取 `FMP_API_KEY` 误判为泄漏。Windows
artifact scan 在 release run artifact 下载后执行；缺 artifact 是 blocker，不等于零命中。

product `git diff --name-status` 必须逐项等于 §4 closed allowlist 的实际变更子集；deferred diff 必须为空。`git diff
--cached --name-only` 在 Controller 授权 stage 前必须为空。任何 allowlist 外路径、unexpected deletion/rename 或 Controller dirty
file 被覆盖均立即 stop。README diff 必须精确列出四个 allowlisted README；其正向 scan 必须覆盖最终用户 command/output/infer/
auto contract，由人工逐 README 对照各自 `Agent更新约束`，不得只靠关键词命中。

另做四项人工/自动 oracle：

1. 反向依赖：Fins production 零 `dayu.cli/service/host/engine/ui` import；renderer 零 filename/fiscal/material/cap regex；
   Service/runtime diff 为零。
2. propagation：每个 typed field 到当前 target flag 再到既有 Service request exact mapping；无 optional fact 不传；
   ticker/company/aliases 每 entry 同源；无 document ID 猜测。
3. security：source/output lexical+resolved containment、external-ancestor symlink allowed、root-self 与 root 内 candidate/output
   component symlink rejected、same-dir atomic replace、POSIX executable mode、Windows delayed expansion off、argv injection
   marker、old-target preservation、temp cleanup、secret scan全过；
   tests 还要分离脚本 comment/body，证明 executable body 无 `--infer`、API-key env/provider URL或网络调用，而 regeneration
   comment 可保留无 secret 的 `--infer` 生成命令。
4. deferred：Issue 142/151/175/177/178、R12、真实 Web/WeChat/render、Topic 8/9、统一 auth 的 production diff 为零；
   只允许 README 删除 placeholder 与本计划明确 no-touch 说明。

本轮 security closeout 只报告保留/加强的 path containment、symlink、atomic write、argv injection 与 secret non-persistence；
不得把它描述为统一 authorization、workspace trust 或 shell sandbox。

## 9. Review state machine、accepted commit 与 completion gates

### 9.1 Slice state machine

严格顺序最多三个 slices：`R11-S1 -> R11-S2 -> R11-S3`。每个 slice 只经历：

```text
implementation
 -> Controller exact allowlist/contract/test/smoke validation
 -> next slice（仅 checkpoint pass 时）
```

任一 source drift、stop condition、checkpoint failure 或 blocker 均禁止下一 slice。唯一允许的 owner 回返是：S2 首个真实
consumer 若发现 §5.3 checklist 未捕获的 S1 typed fact 缺失、enum mismatch 或 optional ownership gap，S2 立即 stop 并提交
direct contract evidence；只有 Controller 可以只授权 `dayu/fins/upload_batch.py` 与 `tests/fins/test_upload_batch.py` 内的 S1
owner targeted fix。修复后必须从 S1 checkpoint 重新开始，并重跑 S1+S2 全部 cumulative contract/tests/scans/smoke 后才可
继续。严禁在 S2 builder/renderer/adapter/test fixture 加 fallback、重算或兼容 seam，严禁为回返创建新 sub-WU、slice 或
中间 commit，也不得扩大 S1/S2 allowlist。三个 slice 之间不做 slice acceptance、code-review gate 或 commit；每个 checkpoint
重跑所有已完成 slice 的 cumulative tests/scans，防止后 slice 破坏前 slice owner contract。

### 9.2 Aggregate gate

S3 checkpoint pass 后执行一次 cumulative aggregate：

- 从 R10 completion baseline 到最终 tree 的 sorted path manifest、blob SHA、product/test/README/CI binary diff；
- 三 slice owner/contracts、所有 accepted/rejected findings 与 stop conditions ledger；
- S1 filesystem、S2 POSIX recorder、POSIX real upload、S3 wheel smokes原始证据；
- focused/full related/full tests、per-file line coverage、full pyright、scoped/full-baseline Ruff、diffcheck 与全部 scans；
- README trigger matrix与安全/deferred matrix；
- Windows gate 状态与 artifact locator。若尚未运行，只能写 `PENDING_RELEASE_BLOCKER`，不能写 pass/residual。

随后对完整 cumulative diff 并发执行两份 complete code review；Controller adjudicate 全部 finding，accepted findings 仅在其
owner 与 cumulative allowlist 内 narrow fix，完整 revalidation 后再并发执行两份 complete cumulative re-review。只有
`0 accepted open finding` 且 Controller 接受 aggregate 后，Controller 才可授权一次 exact-scope local accepted
implementation commit；Agent 不得自行 stage/commit。

### 9.3 Accepted implementation commit gate

commit 前必须：

- working diff 仅为 cumulative allowlist + 已授权 gate artifacts + Controller control transition；
- Controller-owned 既有 dirty 文件没有被 Agent 覆盖，stage manifest exact，`git diff --cached --check` 通过；
- 没有 `workspace/tmp`、dist、coverage、recorder、script、secret artifact 被 stage；
- commit parent 是 accepted R11 plan/control transition 所锁 SHA，commit message/scope由 Controller指定；
- commit 后记录完整 SHA/tree/parent/path count/product diff，working/staged状态与 Windows gate真实状态。

该 commit 只接受 R11 implementation，不关闭 umbrella、不授权 R12、不授权 push/PR。若 Windows 尚未通过，它仍是明确
release blocker；不得把 accepted local commit 描述为 cross-platform closure。

### 9.4 Completion and release gates

R11 completion handoff 必须链接 accepted plan、accepted implementation、全部 finding ledger、验证/coverage/README/security/
deferred evidence。Controller completion validation通过后才可另做 exact-scope completion commit。按 umbrella 允许的唯一
Windows延迟规则，R11本地 completion 可以记录 `PENDING_RELEASE_BLOCKER`，但 umbrella aggregate acceptance、draft PR
ready/final closeout 必须等待真实 GitHub run：

- event/commit SHA 与包含 workflow/implementation 的目标 tree 对应；
- Windows job success、无 skip；artifact 名/path/retention 与 §7.2一致；
- recorder exact argv、no injection、CLI terminal success/temp storage artifact全部可读；
- quoting candidate 与被反证 case/final invariant 记录在 implementation evidence；没有 `list2cmdline`、fallback或 shim。

Windows gate 失败时回到 R11 owner fix/review，不新建 WU，不转 residual。通过后 Controller 才能把 gate 从
`PENDING_RELEASE_BLOCKER` 改为 `CLOSED`。最终 R11 ledger 必须分别列 accepted findings、实际 accepted residual 与
Windows release blocker；真正 release closeout 时三者均为 0。

## 10. Plan acceptance checklist

- [ ] baseline/source locks 由 Controller 复核；唯一既有 dirty control doc未被触碰。
- [ ] Fins typed plan 与 CLI/renderer/package owner 边界无重叠。
- [ ] 三个 dependency-ordered slices 的 allowlist、contract、tests、real smoke、stop conditions均被接受。
- [ ] current direct grammar、action auto、ticker CSV、single FMP resolve、metadata projection逐字段审阅。
- [ ] S1 checkpoint 已按 S2 consumer field/enum/optional-to-current-flag checklist 冻结；owner gap 唯一回返路径可审计。
- [ ] POSIX recorder + real Service/Fins storage smoke可执行。
- [ ] repo/GitHub 无 workflow事实与最小 Windows workflow filename/triggers/artifact locator被接受。
- [ ] Windows outcome/invariants/oracle固定；具体 algorithm 保留给真实 runner反证，不存在 `list2cmdline`/fallback/shim。
- [ ] placeholder deletion、wheel metadata/extracted names/RECORD、README触发、line coverage、full tests/pyright/Ruff 同版本
      baseline/scans完整。
- [ ] security保留项与 deferred/no-touch边界完整；R12与 tracker能力未进入。
- [ ] accepted implementation、aggregate、completion与 Windows release blocker gate可审计。

READY_FOR_CONTROLLER_PLAN_FIX_VALIDATION
