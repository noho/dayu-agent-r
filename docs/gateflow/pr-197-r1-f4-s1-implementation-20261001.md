RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown

CANARY=gpt-6-sol-5982b35f

# PR197 F4-S1 implementation 候选

## 1. 身份、authority 与状态

Label：`pr197-f4-s1-implement-sol-20261001-01`。当前仅完成 implementation 作者候选，**未 root accepted、未进入 code-review、未创建 accepted slice commit**。交付后停止；根独立核收与同版双路 Deepreview、必要 fix/re-review、accepted slice commit 均由根控制，本轮不派发。

本运行环境没有提供可独立读回的精确 canonical model ID，因此 MODEL 如实写 `unknown`；provider 是任务既定 `gpt-6-sol`，不能由 canary、label、token 或历史报告推断模型。Canary 由工具实际读取本轮指定文件，本文再次机械读取同一文件写入，未使用上一轮令牌。

唯一 workspace 是任务指定仓库，分支首尾 `codex/upload-material-oracle`。实读首尾 HEAD 均 `dc29c1fe5e173d9ef710cd7f44fd0889e0da46c9`，main 均 `fac32ecbff9bfe792b63ee9667c8697826b631f4`，暂存区为空。HEAD 只作为记录，未强制其它合法总控 checkpoint 不动。现有 PR197 的远端/PR accepted-plan 读回由输入 authority 提供；本轮没有联网复读 PR，也没有改 PR 状态、comment、merge、stage、commit、push、branch/worktree 或 main。

本轮已读 `AGENTS.md` 与 Gateflow skill，目标和 accepted 计划以 `docs/gateflow/pr-197-r1-f4-goal-20260930.md`、`docs/gateflow/pr-197-r1-f4-plan-20260930.md` 和最新 `docs/gateflow/pr-197-r1-f4-plan-narrow-adjudication-20261001.md` 为准。计划头部历史候选状态不覆盖最新最终 accepted 裁决。没有重跑计划裁决，没有恢复 trusted-only、普通 ValueError/FileNotFoundError → UNSAFE_PUBLICATION 或整 run O(D+S) 的撤回约束。

## 2. 动机、唯一增量与 owner

冻结源码直接证明旧 HK resolver 每候选先公开 list 再公开逐份 get，每次独立取得 guard。accepted/repair 排序/start/stream 重复调用这条扫描。问题成立在重复身份读取及独立观察窗口；本次没有把严重性扩大到整 run 数学 linear 或集合事务唯一性。

- storage owner：`SourceMetaReadEntry` / `SourceMetaReadView` 两个 frozen/slots 类型；仓储协议、Fs adapter 与 shared core 提供必填 kind 的 `read_source_meta_view`。同一原 publication guard 内完整有序 list → 原 unguarded get 成功前缀 → 第一个原 ValueError/OSError 对象 → finally release。list 失败或未声明异常即时原样传播，首个 get 失败后不读后项。复制并顶层 MappingProxyType，只读消费嵌套 JSON；不承诺深冻结，不含 manifest/path/revision/trust 字段，不新增 parser 或全局 DocumentMeta 迁移。
- identity owner：一次 build 保存全部 source match 与真实在场 allocated 财期 JSON 值，build 不 eager 拒绝缺 internal/duplicate。纯 query 保留原顺序：匹配前缀缺 internal → 同一 read_error → duplicate → 唯一匹配 → allocated 键存在三态及原 JSON 直接比较。缺席直接返回原分配；在场缺字段保留 None，不用默认 `(None,None)` 推断存在性。非字符串来源不 stringify；HK 原 provider 和两条原错误文本在 owner 处 Final 常量化。
- caller：真实路径在 `dayu/fins/pipelines`。W0 供 accepted 集合与 repair 排序共用；每个 start 在原取消检查后、原 try 外新读；stream 在原入口取消检查后新读，direct 签名没有新增 prepare/Phase A/index 参数。retry 保持原递归签名和 round0/1/2，每轮由 stream 新读。没有跨 publication cache，也没有把 W0/start 绑定传入 stream 授权写。
- integrity / company / error / events / rows owner：保持原边界。previous_meta、handle/blob、Phase A/B、post-repair inspection 和 commit 的全树扫描仍存在；元数据可读不代表来源可信。没有 sourceintegrity、infra、domain、adapter 或 error owner 写入。

典型两份 HK 实测 batch 读取 5 次（`1+2n`）；n=1、r=1/2 的 retry 分别观察 4/5 次。身份 query 的 public list/get 为零；已完成来源的原 previous_meta public get 为每份一次，测试独立记账，不冒称全部 get/blob/全树成本归零。每窗一次 list 与一次 guard、逐成功项一次 core get；总工作量依各实际窗口 D 变化。

## 3. 保全既定业务的直接证据

`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/preserved-owner.json` 与独立 stdout/exit 保留 AST 对照：原 public get/list、persisted meta parser、integrity classification/list、company 发布、summary/result、Phase B commit、retry、safe_get 和 filing failure projection 均逐 AST 相同。direct stream 参数完全相同，去掉唯一新读取赋值并将 resolver 第三参数还原仓储后，其余整个函数 AST 相同。此证据与真实测试互补，不以单纯代码相似替代行为验证。

| 规则 | 本轮真实 owner 证据 |
| --- | --- |
| 同窗观察与锁 | `test_meta_view_reader_guard_keeps_two_documents_all_a_then_all_b` 在 reader 首 get 后启动独立真实 writer，B commit 等待 guard，view 两份全 A，释放后下一 view 全 B；两种 `test_meta_view_reader_waits_at_real_writer_rename` 在真实 target→backup / staging→target barrier 使 reader 等待后两份全 B。实际 core acquire/release/list 各一次、get 各一次，非 mock-only 一致性证明。 |
| 原 list/get / 损坏前缀 | full view 顺序与公开 list/get 相同；FILING/MATERIAL 隔离；私有 revision 去除；空根、普通文件/隐藏项、descriptor、非隐藏链接、坏 root、malformed/missing/identity mismatch/meta symlink、unexpected RuntimeError 与 guard 释放均使用真实 Fs。原 get 错对象被 view/index/query 保留。 |
| 身份优先序 | `test_real_fs_prefix_query_preserves_missing_internal_and_original_get_error` 使用真实 published 文件与坏后项：X 在 A 缺身份优先，Y/late 抛首读错；唯一有效/有效重复后仍读错优先，ZZ 后项不读。纯 owner 测试补合法 duplicate、空/非字符串 internal、非字符串来源、空来源字符串、ticker/kind 开发误用及 allocated 缺席/同值/异值/缺字段/真实 None/非字符串 JSON 比较。 |
| raw-readable UNSAFE direct | `test_hk_direct_stream_preserves_raw_binding_then_original_rejection` 无 ticker preflight：raw UNSAFE 仍绑定 A-original/internal-original，然后原 Phase A typed 拒绝；坏 sibling 则原 ValueError/FileNotFoundError 同对象，不迁移 typed。download/converter/reset 均零调用，损坏注入后的旧 publication bytes 不因 owner 失败改变。 |
| start / stream 新鲜度 | 真正 HK 路由读取 W0/start/stream，批初 accepted/repair 排序共用 W0；前 filing publication 后下一窗口见到新树。start yield 后独立 writer 将绑定重发为 rebound，stream 取得新外/内部 ID。实际坏 meta 在 stream 内先产生普通 failed，下一 start 仍在原 try 外抛原错，不制造第二 start/failed；首/后 start 错保全已有事件，不改造 typed partial abort。 |
| retry / 取消 | 独立 writer 在转换边界真实改变 target revision，round0/1/2 每轮读取新内部身份，每轮 PDF/conversion 重取；成功只发布最后轮 Docling payload，耗尽保留一次 start/一次 ordinary failure。HK after-start 取消仅 W0/start 两读，direct 取消与非取消 checker 错保持原对象且零身份读。原 PDF/convert/commit 前取消、generator aclose、rollback/commit、skip/overwrite/reuse 回归同组运行。 |
| ordinary / typed / rows | HK runtime W0 与 stream 的 malformed/missing/UNSAFE 输入经过真实仓储、adapter、direct/job：ordinary stream failed 后恢复实际输入再继续下一候选，2 rows = 1 failed + 1 downloaded；原整体结果保持既有规则。typed 原 reason/hint 与 stream 一条 failed/abort 保持，原 CN/HK Phase B/commit/postrepair 已处理 rows 与持久摘要守恒回归同组运行。 |
| manifest / company 成功语义 | 原 complete-source、whole-tree commit validator、repair gate 与独立 company publication 函数没有改；同组真实 commit 负例、repair ordinary failed break、typed abort、company旧值与原 manifest 完成规则仍通过。没有将 manifest 未成功登记的文档报成功。 |

新增 runtime 证据还揭示**已有**公开入口差异：W0 普通异常的 job generic catch 保存 `str(exc)`；direct 投影固定安全文案，typed job/partial wrapper 使用 typed 路由。本轮先查 `_run_download_job` / `_save_failed_from_exception` 真源，再改测试期望，不为统一文案改 owner，也不把该既有差异升级为本 slice 新拒绝规则或 F6 提前修复。

## 4. 实际文件与精确差异

本轮产品/测试/README 实际改变 14 文件：8 production、4 tests、2 README；另新增本报告。`tests/fins/test_hk_period_rebuild.py` 在 allowed 内但没有写入，原 SHA 保持，它的真实 CLI 财期纠正、旧身份守恒及新 Q1 分配用例随最终九模块运行。没有混入其它 WU dirty。

每个 changed file 对原件执行 `git diff --no-index <original-or-/dev/null> <candidate>`，完整 raw patch/双流/真实 exit 见 `workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/candidate-diffs/`；每份完整文件执行同命令加 `--check`，均 exit 1、零 stdout/stderr。raw exit 1 代表有差异，check exit 1 且双流为空在此命令形式也代表差异，没有 whitespace 诊断；不把 exit 1 标为失败或手造 exit 0。没有豁免 fence、上下文行或特定文本。

| 文件 | 冻结原 SHA256（新增为 absent） | 实际 candidate SHA256 |
| --- | --- | --- |
| `dayu/fins/storage/source_meta_read.py` | `absent` | `cf6d39f8dae6b330ba2a76df4a5e5544cc3dde2c39d4bff97ad329f30493446f` |
| `dayu/fins/storage/repository_protocols.py` | `8f82d3a4ddc4b1edb5a265e83862a9566e95196edf45c50404f4fbd1e28a35a1` | `20f2f9f4772f8dba51ffc4d5a519e1420f8e0f0c214d566ac0c881ab9182045b` |
| `dayu/fins/storage/__init__.py` | `f04281910d61fd423cacfac92206d916346d09db9e62ed3812827c64e60290bb` | `d6e0b6a4d9b1aa16516a501ab964d91f4231471c1c3bfaca385e0c13f75c89e1` |
| `dayu/fins/storage/_fs_source_document_core.py` | `65ba54ae7d58cc765bcda0ef4782461e053e45b409335d5a15774b9f035d4c74` | `022c94500ca129e1612ba08ac53ead9097025c295886a9b938e6cb81b21848e3` |
| `dayu/fins/storage/fs_source_document_repository.py` | `027784a3e201e1a26e63a2a863f7855c8e92eeb611dc20e244599c5745ca1275` | `85145188948b1da2a75731a38a86e82b9a6b9cace82eaacdea163bef3ee000eb` |
| `dayu/fins/pipelines/cn_download_identity.py` | `71bb00d438bb681ea0344fdb2679bf5178fb4a804423d02f1168be109de32510` | `21842fbc08cf4f68c2ede914cbbc9a423ff0a5801ee18be37940d4f98cb21a6c` |
| `dayu/fins/pipelines/cn_download_workflow.py` | `989b77b0c4866f0e7753858c822bae40abddd4ef6e6522caa1c631c46e2c7b49` | `5fe5ec5b904b1ef649e1d6c23da46c64ca37cf8564bfb21653392cf126591fec` |
| `dayu/fins/pipelines/cn_download_filing_workflow.py` | `85002256c3375d227add85733cd7b23d3367c1f54e9d40224958fe3a860ed470` | `708ed8ce8a360d452f6e00ff2514814900446f0f0647f6a2051f6f45a060163b` |
| `tests/fins/test_cn_download_identity.py` | `absent` | `46705ced662bf2d30ec0d7f06b6ac1355d95ce30221e107969138835411cedc5` |
| `tests/fins/test_fins_storage_atomicity.py` | `9af834a776ea22a79ec9534cf4ca77de0f13cc0c96b4d769c2b22703ae122430` | `08776754cfa5cf2945230b9cc7e0e721cde8fde347f2c38ae37db3b83498d2d8` |
| `tests/fins/test_cn_download_workflow.py` | `8a8fede5189141c766997c2eba25ffff980db68640d07cb955b7665a0bfdb387` | `652849f8698b880b52ddebaac24b0d5661469b8113e61032b11768de7e4dd8e2` |
| `tests/fins/test_cn_download_runtime.py` | `6a1608d0051ef8b000b146be973ed4c21cedf7e94af205cff7a96a4176776ae4` | `aed27e1ed10e75e18e3c3d3b688a8a6f8a6bc840d393b2059fc1d92e39ac32fa` |
| `dayu/fins/README.md` | `76fc499131beb7d76fc4b5a3c07823b2178101a6c5945b36c93310fb15688f79` | `18105cd4701fbb72b37866e0afdb9d500bd36606c75aca2d3ca20dab6464a197` |
| `tests/README.md` | `4a8309ea7a19cd880474a87e42466b18cdac758fb3aff2895dbc685f1b6c5494` | `780e2a143fcb54efd094d1bae9c9cd472846f2ee946fd8e9edb05bc8576f9604` |

完整精确 diff 的文件名由路径 `/` 替换为 `__`，例如 `dayu__fins__pipelines__cn_download_identity.py.raw.stdout`；对应 `.raw.json/.stderr` 与 `.check.stdout/.stderr/.json` 均保留。原件目录与 freeze 未覆盖。原始 `git status` 中 F3 五 utils 候选、独立 F3/F5 review/controller/queue/handoff 的其它新增/变化只作为外部状态记录，不是本文 changed files，不暂存、不回滚、不纳入本 slice 差异。

## 5. 验证命令、真实退出及日志

所有以下命令均通过独立 runner 先 `source .venv/bin/activate`；每条命令的 stdout/stderr 与真实 exit JSON 独立写在 `workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/<name>.*`，没有组合末尾 0 遮盖前失败。历史失败原日志不覆盖。以下按证据名称列全部内部验证运行，最终 gate 证据为 `pytest-final-coverage`、`pyright-final`、`preserved-owner`、`final-evidence` 与当前报告全文卫生读回。

### `final-evidence`

```bash
source .venv/bin/activate
python workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/final-evidence.py
```

真实 exit：`0`。14 candidate 文件的 raw/check 精确 diff，25 readonly 与 38 originals SHA 保全、正确 branch/main、暂存空；全部实际断言通过。

日志：`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/final-evidence.stdout.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/final-evidence.stderr.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/final-evidence.exit.json`。

### `preserved-owner`

```bash
source .venv/bin/activate
python workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/check-preserved-owner.py
```

真实 exit：`0`。AST 不变规则与 25 readonly SHA 全部 true；完整 stdout 与 JSON 保留。

日志：`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/preserved-owner.stdout.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/preserved-owner.stderr.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/preserved-owner.exit.json`。

### `pyright-01`

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/ --outputjson
```

真实 exit：`0`。早期 production 版本：1.1.409，782 files，0 errors；不作为最终版证据。

日志：`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pyright-01.stdout.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pyright-01.stderr.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pyright-01.exit.json`。

### `pyright-02`

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/ --outputjson
```

真实 exit：`1`。783 files，2 errors：只读 Mapping 的非法 setitem 测试调用；随后移除非法调用，改断言真实 MappingProxyType。

日志：`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pyright-02.stdout.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pyright-02.stderr.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pyright-02.exit.json`。

### `pyright-03`

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/ --outputjson
```

真实 exit：`0`。783 files，0 errors；随后最终版再核验。

日志：`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pyright-03.stdout.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pyright-03.stderr.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pyright-03.exit.json`。

### `pyright-final`

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/ --outputjson
```

真实 exit：`0`。最终 1.1.409，783 files analyzed，0 errors/0 warnings/0 information，33.629s；非 filesAnalyzed=0 假 green，未新增 ignore/cast/Any/stub 或改 pyrightconfig。

日志：`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pyright-final.stdout.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pyright-final.stderr.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pyright-final.exit.json`。

### `pytest-coverage-01`

```bash
source .venv/bin/activate
COVERAGE_FILE=workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/coverage-01.data python -m pytest tests/fins/test_cn_download_identity.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/fins/test_fins_storage_atomicity.py tests/fins/test_hk_period_rebuild.py tests/fins/test_cn_report_selection.py tests/fins/test_hkexnews_downloader.py tests/fins/test_source_meta_contract.py tests/fins/test_fins_storage_provider.py -q --cov=dayu.fins.storage.source_meta_read --cov=dayu.fins.storage.repository_protocols --cov=dayu.fins.storage --cov=dayu.fins.pipelines.cn_download_identity --cov=dayu.fins.pipelines.cn_download_workflow --cov=dayu.fins.pipelines.cn_download_filing_workflow --cov-report=term-missing --cov-report=json:workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/coverage-01.json
```

真实 exit：`2`。收集失败 4 errors：命名 --cov package 采集触发 NumPy cannot load module more than once per process；未改依赖，改用目录 source 配置恢复，失败证据保留。

日志：`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-coverage-01.stdout.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-coverage-01.stderr.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-coverage-01.exit.json`。

### `pytest-coverage-02`

```bash
source .venv/bin/activate
COVERAGE_FILE=workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/coverage-02.data python -m pytest tests/fins/test_cn_download_identity.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/fins/test_fins_storage_atomicity.py tests/fins/test_hk_period_rebuild.py tests/fins/test_cn_report_selection.py tests/fins/test_hkexnews_downloader.py tests/fins/test_source_meta_contract.py tests/fins/test_fins_storage_provider.py -q --cov=dayu/fins/storage --cov=dayu/fins/pipelines --cov-report=term-missing --cov-report=json:workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/coverage-02.json
```

真实 exit：`0`。763 passed，3 个既有 edgar DeprecationWarning；目录采集成功，后续新用例加入前版本。

日志：`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-coverage-02.stdout.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-coverage-02.stderr.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-coverage-02.exit.json`。

### `pytest-final-coverage`

```bash
source .venv/bin/activate
COVERAGE_FILE=workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/coverage-final.data python -m pytest tests/fins/test_cn_download_identity.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/fins/test_fins_storage_atomicity.py tests/fins/test_hk_period_rebuild.py tests/fins/test_cn_report_selection.py tests/fins/test_hkexnews_downloader.py tests/fins/test_source_meta_contract.py tests/fins/test_fins_storage_provider.py -q --cov=dayu/fins/storage --cov=dayu/fins/pipelines --cov-report=term-missing --cov-report=json:workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/coverage-final.json
```

真实 exit：`0`。最终 accepted 九模块 788 passed，3 个既有 edgar DeprecationWarning；42.04s；覆盖率 JSON 和唯一路径 data 实际生成。

日志：`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-final-coverage.stdout.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-final-coverage.stderr.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-final-coverage.exit.json`。

### `pytest-identity-final`

```bash
source .venv/bin/activate
python -m pytest tests/fins/test_cn_download_identity.py -q
```

真实 exit：`0`。33 passed；canonical 输入恢复后真实 prefix 和全部纯身份 owner 通过。

日志：`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-identity-final.stdout.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-identity-final.stderr.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-identity-final.exit.json`。

### `pytest-owner-01`

```bash
source .venv/bin/activate
python -m pytest tests/fins/test_cn_download_identity.py tests/fins/test_fins_storage_atomicity.py -k "identity or meta_view" -q
```

真实 exit：`2`。收集失败：新候选 fixture 漏 content_length/etag/last_modified；补原类型要求字段。

日志：`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-owner-01.stdout.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-owner-01.stderr.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-owner-01.exit.json`。

### `pytest-owner-02`

```bash
source .venv/bin/activate
python -m pytest tests/fins/test_cn_download_identity.py tests/fins/test_fins_storage_atomicity.py -k "identity or meta_view" -q
```

真实 exit：`0`。51 passed / 233 deselected；真实 barrier/prefix 与身份 owner 首轮。

日志：`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-owner-02.stdout.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-owner-02.stderr.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-owner-02.exit.json`。

### `pytest-runtime-01`

```bash
source .venv/bin/activate
python -m pytest tests/fins/test_cn_download_runtime.py -k identity_windows -q
```

真实 exit：`1`。10 passed / 2 failed：误把普通 job generic 文案当成 direct 文案；读原 error owner 后修正。

日志：`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-runtime-01.stdout.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-runtime-01.stderr.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-runtime-01.exit.json`。

### `pytest-runtime-02`

```bash
source .venv/bin/activate
python -m pytest tests/fins/test_cn_download_runtime.py tests/fins/test_cn_download_identity.py -k "identity_windows or real_fs_prefix or multiple_candidates" -q
```

真实 exit：`1`。12 passed / 4 failed：runtime 全通过，新增 Fs fixture 用 00700 非 canonical ticker；改测试输入为原 owner 要求的 0700，无 normalization fallback。

日志：`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-runtime-02.stdout.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-runtime-02.stderr.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-runtime-02.exit.json`。

### `pytest-workflow-01`

```bash
source .venv/bin/activate
python -m pytest tests/fins/test_cn_download_workflow.py -k "identity_windows or fresh_after_start" -q
```

真实 exit：`1`。1 passed / 4 failed：summary 含 elapsed/converted/reuse 的原扩展字段；测试误用不存在的 pipeline.workspace_root。改为核对目标计数并显式传入隔离 root，不改生产语义。

日志：`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-workflow-01.stdout.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-workflow-01.stderr.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-workflow-01.exit.json`。

### `pytest-workflow-02`

```bash
source .venv/bin/activate
python -m pytest tests/fins/test_cn_download_workflow.py -k "identity_windows or fresh_after_start or retry_rounds" -q
```

真实 exit：`0`。8 passed / 98 deselected；修复后的窗口、start writer 和 retry 用例。

日志：`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-workflow-02.stdout.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-workflow-02.stderr.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-workflow-02.exit.json`。

### `pytest-workflow-03`

```bash
source .venv/bin/activate
python -m pytest tests/fins/test_cn_download_workflow.py -k "hk_direct_stream or hk_repair_sort or hk_start_read or hk_cancel_after or hk_direct_cancel" -q
```

真实 exit：`0`。9 passed / 106 deselected；direct 原拒绝、repair sort、start try 边界、HK取消。

日志：`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-workflow-03.stdout.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-workflow-03.stderr.log`、`workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/pytest-workflow-03.exit.json`。

### 逐 production 文件覆盖率

采用 coverage 7.13.5 / Python 3.11.15 的实际 statement coverage，data 唯一路径 `workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/coverage-final.data`，完整 JSON `workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/coverage-final.json`，逐 owner 摘要 `workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/coverage-owner-summary.json`。目录采集没有 source omit、report omit、ignore_errors 或取平均；只将本轮 8 个 production 文件逐份判定，其它收集到的文件不被冒称本轮全仓覆盖率门禁。未新增任何 pragma/no-cover。

| 文件 | covered / statements | 缺行 | 精确覆盖率 |
| --- | --- | --- | --- |
| `dayu/fins/storage/source_meta_read.py` | 14 / 14 | 0 | 100.000000% |
| `dayu/fins/storage/repository_protocols.py` | 238 / 292 | 54 | 81.506849% |
| `dayu/fins/storage/__init__.py` | 15 / 15 | 0 | 100.000000% |
| `dayu/fins/storage/_fs_source_document_core.py` | 418 / 493 | 75 | 84.787018% |
| `dayu/fins/storage/fs_source_document_repository.py` | 88 / 91 | 3 | 96.703297% |
| `dayu/fins/pipelines/cn_download_identity.py` | 63 / 63 | 0 | 100.000000% |
| `dayu/fins/pipelines/cn_download_workflow.py` | 247 / 269 | 22 | 91.821561% |
| `dayu/fins/pipelines/cn_download_filing_workflow.py` | 194 / 209 | 15 | 92.822967% |

协议文件按 coverage 实际可执行 statement 报告：238/292 = 81.506849%，不把 exports 或 Protocol 类型声明当平均值。完整 JSON 如实记录协议的 160 个工具默认排除行（68 个 `...` 协议占位与 92 个空行），其余七个本轮生产文件 excluded_lines=0。默认配置来源是现有 coverage 对纯 ellipsis 的默认规则，没有为本轮改配置或额外排除可执行业务行；协议 54 条实际未覆盖行仍计入分母。exports 是实际 15/15。以上八份均 >=80%，不能仅用整数四舍五入或全目录平均判断。

`coverage debug config` 的只读诊断确认 source/report omit 均空、ignore_errors=False；此前 `cat .coveragerc` exit1 只是该文件不存在，实际配置来自 pyproject 和工具默认；新增代码禁止模式的 rg exit1 是没有命中。read-only 搜索的这些非零不冒称测试失败或通过，也未触发依赖或配置修改。

## 6. 文档职责与首尾冻结

Fins README 已先读其 Agent更新约束，仅说明当前已落地 storage 批量观察、身份读取窗口及其不代表完整性；未加测试流水账或未来能力。tests README 无另列 Agent更新约束，按既有测试手册职责补真实 owner 测试与 focused 命令。根 README 无安装/入口/参数/输出工作流变化，dayu 总览无分层/装配变化，两者不写。

逐项 preflight 保存在 `workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/preflight-sha.json`：38 live 与 38 original 均等于 freeze，2 newpaths 当时确实 absent。中途 `workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/mid-readonly-sha.json` 和最后 `workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/final-evidence.json`：25 readonly 输入无漂移，38 originals 完整保持；allowed HK rebuild 测试另按原 SHA 保持。原 freeze/originals/旧日志都未覆盖。

| related readonly 文件 | 首尾相同 SHA256 |
| --- | --- |
| `AGENTS.md` | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` |
| `docs/gateflow/pr-197-r1-f4-goal-20260930.md` | `d1f374b9adb053761c66e9dd04e2a27ae6cdb4e299b715f70d9f91ee99d9d05e` |
| `docs/gateflow/pr-197-r1-f4-plan-20260930.md` | `f17c95f4ce3ea3f9f89470d6b075e966e909f377b2d5acfc4831c90a89a3783f` |
| `docs/gateflow/pr-197-r1-f4-plan-narrow-adjudication-20261001.md` | `fbf0aa6dc234a41196fa35095ee3629063ff9204be459045d59b75ed8e6e0200` |
| `dayu/fins/storage/_fs_source_integrity.py` | `eb670d9b3963e57a83163ecf955c4596652b713a812bf23794426494f9743852` |
| `dayu/fins/storage/source_integrity.py` | `c0b90041a895e85da8af967a727c43034145af6cdead145b3a09c1b33c4aa6f7` |
| `dayu/fins/storage/_fs_identity.py` | `ba0163593d41ea8403b22f00c163c08f9223f0e8cafe9fa553b6105467997d1c` |
| `dayu/fins/storage/_fs_storage_infra.py` | `f4d1e9ecd94dab2cb2e82ea7f65c85e09eefee34cfcc13ffde9db1adf2f4001f` |
| `dayu/fins/storage/source_meta_contract.py` | `070a7536cd89a6409d1b1f2c5f52fd850bb6da0bee2db8b2977770fe8ed3f3df` |
| `dayu/fins/domain/document_models.py` | `45a90c287dbf51c5ace46f6c41c51d08c2317cf68af35644600c838651fc9e5d` |
| `dayu/fins/pipelines/cn_download_models.py` | `c0311852f5a61f0fac4b3805535e59eceabb835e7ff2d0895f74ff25b7f79a20` |
| `dayu/fins/pipelines/cn_form_utils.py` | `698854e2e3664d60a53a524df8d3ceb499fa206bc487eef6e736ff29e964e3d7` |
| `dayu/fins/pipelines/hk_download_rebuild.py` | `e57a3e57dc4c6d14a32cdaa73db91107236918e2d75c30b804c8dbd1c8c742f2` |
| `dayu/fins/ingestion_runtime.py` | `4b95c284a9eeae10aabed10358560a706dfd7482c98f3e921d01cdfbd2c57672` |
| `tests/fins/test_cn_report_selection.py` | `edce06f4e28829f4cbcd4486d9048cd25379880d846c1ceac7079e54e04158c2` |
| `tests/fins/test_hkexnews_downloader.py` | `63ec4c08e72d4ccb59f4af87739ac233bf898d9cb509a0b6752cb328920af334` |
| `tests/fins/test_source_meta_contract.py` | `bb3de62156456a723a0b32a6684ed53f8a5801c352272107933d4c42131e8461` |
| `tests/fins/test_fins_storage_provider.py` | `a1f92d98277012429f37e8825acb1bab5b63dd60aba6e31730e69e9157859f26` |
| `pyrightconfig.json` | `661d7c531f7cacc7038f570675b43052ed800cd87915a1a218504dbfe6d4357c` |
| `pyproject.toml` | `28429056b51e29c672f029723d3bbef0db0d781b6bc72d0cb8c2d3e823c79474` |
| `utils/analysis_sample_inputs.py` | `021e777e263a87d8389741819f933d61bcca0e2f9762d49b116ed9f36580e296` |
| `utils/build_semantic_digests.py` | `4eab095a838d21fd63dbf7402b7dc872ccc43cf0aa761bccc7f5835c0aa98fd0` |
| `utils/docling_schema_regression.py` | `c6a16716acdcbaf879d2ea2b1276c3eb73f42c8557968e5732cd99e63e95d208` |
| `utils/verify_missing_tokens.py` | `2cf113b92fa7723c24e064eb8f8c8f8ed36743865bc7b7b17b92361f65e3a339` |
| `utils/ab_ocr_compare.py` | `b28ad6f4d6119609290d3cd7f1683fe8de74255a78ddb487ea5695269e98d175` |

## 7. 本 slice 内新增修复登记与未覆盖边界

| 项 | 作者状态与恢复证据 | Owner / destination |
| --- | --- | --- |
| F4-S1-I01 测试候选漏必填字段 | 已修复；owner-01 的真实 exit2 保留，owner-02/identity-final/final suite通过 | 本 slice test fixture → 当前候选 |
| F4-S1-I02 覆盖采集命名 package 失败 | 已恢复；coverage-01 exit2 保留，目录 source 最终788通过，没有改依赖/生产 import | 本 slice validation → 当前日志包 |
| F4-S1-I03 summary/root 测试误设 | 已修复；workflow-01 exit1 保留，workflow-02/final通过；无生产补偿 | 本 slice test owner → 当前候选 |
| F4-S1-I04 非法只读 Mapping 写测试 | 已修复；pyright-02 的两错误保留，实际 MappingProxyType + 脱离元数据/嵌套 copy 断言；最终full0 | 本 slice test type contract → 当前候选 |
| F4-S1-I05 普通 job/direct 文案误设 | 已修复；runtime-01 exit1 保留，读原 generic owner后修测试，未向 typed 投影迁移 | 本 slice runtime test → 当前候选；既有入口差异保留 |
| F4-S1-I06 Fs fixture ticker 非 canonical | 已修复；runtime-02 exit1 保留，测试改0700，identity-final/final通过；无下游 normalize | 本 slice真实 Fs fixture → 当前候选 |

上述都是本轮内部实现/验证恢复项，没有借 residual 分类延期 accepted F4 finding。本报告未声称通过独立 code review 或根 gate 裁决。当前没有必要迁移 allowed 之外的真实 Protocol 实现，full pyright 实测0，不曾 cast/fallback/fake empty view 绕过。

| 风险分类 | 风险 / 未覆盖 | Owner / destination |
| --- | --- | --- |
| fixed in current slice | F4 同 guard metadata observation、成功前缀/原异常、纯索引、W0复用与各事件/stream/retry fresh；作者代码/真实 tests/逐file coverage/fulltype完成，仍待根核收 | storage / identity / pipeline → F4-S1 当前候选及根独立核收 |
| covered by later approved slice | 本 WU 只有 S1，没有已批准后续 slice；不虚构后续 slice 放行任何缺口 | 总控 → 不适用，本 slice accepted 范围没有延期 |
| assigned to later work unit | F4-R02 各窗口 O(D) meta/index 与完整性全树成本；start/stream 可以因外部 publication 观察不同 ID，未承诺原子事件；F5 年度可信输入/unknown/rebuild、F6 typed sibling reason 不在本轮 | storage 性能 / 事件 owner / F5 / F6 → 各独立 WU 与主修复队列 |
| tracked by existing issue | PR197 原 upload-material issue198 队列与其它独立修复资产；五 utils 原 SHA保持。F7 已 accepted 的封闭词表不修改 | 根 / 相应 WU → issue198、PR197 主队列；用户 merge |
| requiring new issue or explicit user decision | F4-R01 resolve→commit 跨 writer 的 target-only 重验局限；本批量观察不提供集合事务唯一性，不因新测试引入全 run 长锁或 trusted inventory | storage / identity 与根 → 后续单独 goal/用户裁决；未建新 issue，不关闭该风险，不是当前 accepted S1 门禁缺口 |

真实合成 Fs/PDF/provider/Docling fixture 覆盖本计划 owner 契约，没有真实网络下载、私有语料、OCR、依赖升级或其它市场生产数据测量；不是整 run 性能 benchmark。没有 exhaustive 所有操作系统故障组合的宣称。三个 edgar 弃用 warning 来自现有依赖，不在当前授权写界。真实 A/B barrier 是当前进程线程与独立 core writer 测试；原跨进程 publication rename 回归也在最终同组中通过。

## 8. 交付停止点与报告全文卫生

当前源码、tests、README 和唯一 implementation 报告交付为候选。下一未完成入口由根控制：独立核收 → 同版双路 Deepreview → 必要 fix/re-review → accepted slice commit。本轮不继续其它 gate，不修改其它 WU，不自放行。

完整报告首次全文件卫生检查已实际执行 `git diff --no-index --check /dev/null docs/gateflow/pr-197-r1-f4-s1-implementation-20261001.md`：真实 exit `1`，stdout/stderr 均0字节，表示新增文件差异且没有 whitespace 诊断（`report-check-01.*`）。本文补入该实际结果后，最终全文再次用完全相同命令读回，结果与本体 SHA 由 `report-check-final.*` 和 `delivery-receipt.json` 记录，不豁免此段或任何 fence/context。

最终交付读回 `workspace/tmp/pr197-f4-s1-implement-sol-20261001-01/delivery-receipt.json` 记录本报告实际 SHA、最终全文 noindex check 命令/exit/双流及25 readonly/38 originals再核验；报告不内嵌自引用 hash。该 receipt 的本体 SHA 必须与实际报告一致，且全文件检查包含本文全部 fence/context，才是本版卫生证据。
