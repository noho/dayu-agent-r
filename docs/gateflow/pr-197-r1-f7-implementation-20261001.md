# PR197-R1/F7 S1 实施候选

RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/实际模型未核验
CANARY=gpt-6-sol-005589b9

## 1. 身份、权威与 gate

- Label：`pr197-f7-implement-sol-20261001-01`。runtime 为当前 Codex 工具会话，`gpt-6-sol` 是任务指定的 provider 路由；当前上下文没有 canonical provider/model 回执，实际 model 不猜测。canary 来自本轮指定文件实际读取，不能用它证明模型。
- 唯一主树为本仓库、branch `codex/upload-material-oracle`。首尾 HEAD 均实读为 `2a8c5d3e3c14b26e2d1e28efb66448b567c21465`，也是 accepted plan commit。本轮不 stage/commit/push、操作 PR/merge/comment、创建 branch/worktree 或派发子 Agent。
- Binding goal：`docs/gateflow/pr-197-r1-f7-goal-20260930.md`；完整 accepted plan：`docs/gateflow/pr-197-r1-f7-plan-20260930.md`，SHA-256 `5820a4924bcd91c7a964b3bbc241fa739979ef3a8183bf11a7837787dc944e3d`。
- 已读 AGENTS、Gateflow skill、完整 goal/plan、首审两报告、根首审/最终窄复审裁决及相关源码/tests/两个 README 职责。PV01 以根最终 `docs/gateflow/pr-197-r1-f7-plan-rereview-adjudication-20261001.md` 为准，已修复，不重新裁决业务或重跑旧 679 baseline。
- 本轮仅 **approved implementation**。结果为 **implementation candidate，未 code-reviewed、未 accepted slice**。不宣告产品/PR 闭环，不自行进入 review/commit gate。
- 共同源码排程依本次用户 launch 授权执行；没有自行实施 F4 或写 storage。起始 29 输入与 29 originals 全 MATCH，新 owner test 缺席；收尾 21 只读 live SHA 与 29 originals 仍全 MATCH。公告的 F3 utils、F4/root 治理 docs 无关 dirty 不由本轮认领。

## 2. Owner、固定决定与 changed files

动机成立且严重性仍低：冻结版本 workflow/adapter 分散持有三值，rebuild 内联，`_build_result` 接受任意 str。既有 `cn_download_models` 已负责 CN/HK 共享无 IO 类型/字面量，是本协议唯一 owner。修复只落在该 owner 和直接 producer/consumer，不重新设计。

| Changed file | 实际变化 |
| --- | --- |
| `dayu/fins/pipelines/cn_download_models.py` | Literal 三值、三个 Final 常量、派生 normal tuple、五符号 `__all__` |
| `dayu/fins/pipelines/cn_download_workflow.py` | `_build_result` status 窄类型/完整中文 docstring、两实际 callsite owner 常量、删除私有重复值 |
| `dayu/fins/pipelines/cn_download_rebuild.py` | 显式同类型 terminal_status，直接消费 owner OK/CANCELLED |
| `dayu/fins/pipelines/cn_pipeline.py` | 普通 membership 消费 owner tuple、abort 比较 integrity 常量；删除 workflow 私有 import 和本地两值 |
| `tests/fins/test_cn_download_models.py`（新增） | 独立字面量/get_args/原生 str/normal 真子集/`__all__` 契约 |
| `tests/fins/test_cn_download_workflow.py` | 零候选/rebuild empty/matching/failed-row/cancel/typed abort 状态断言；CN/HK seeded 取消、read/checker identity、早期 ticker/form/date 非法输入 |
| `tests/fins/test_cn_download_runtime.py` | 两入口合法/互拒/unknown/case/strip/missing/null/int/blank 矩阵；合法 status 不绕过其它坏摘要字段 |
| `dayu/fins/README.md` | 现 Download adapter 节短段说明 owner 与入口子集 |
| `tests/README.md` | 现下载终态段增一短句说明三值和保全覆盖 |
| `docs/gateflow/pr-197-r1-f7-implementation-20261001.md`（新增） | 本实施候选及本轮实际证据 |

只改八份获准已有文件及两份获准新增文件；临时 runner、log/JSON、basetemp、coverage 与候选快照只在 `workspace/tmp/pr197-f7-implement-sol-20261001-01/`。freeze/originals/rawsnapshot/旧 report 均不覆盖。

普通入口仍只 `ok/cancelled`，abort 仍只 `integrity_failed`；原 `_required_cn_text.strip()`、未知/交叉值与其它坏字段拒绝保持。没有 enum/facade/reexport/fallback、生产 runtime 新拒绝或 schema 字段。每文档 status/原因码、cancel/early error/repair/HK rollback、rows/count/cause/direct/job 投影均按原逻辑保全，不顺带 F4/F5/F6。

新增/修改函数有完整中文参数/返回/异常说明和严格类型；未新增 Any/object/getattr/hasattr/type ignore/状态 cast/兼容 shim。既有 fake/fixture 签名不改；新 probe 只在真实仓储读/checker 输入边界抛预构造原异常，不改生产语义。

## 3. 本轮真实命令、结果、失败与恢复

先 `source .venv/bin/activate`。实读 Python `3.11.15`、`python -m pyright --version` 为 `1.1.409`，两个版本命令均 exit0；独立记录在本轮 `environment.json`。pyright 有 1.1.414 可用提示，没有升级依赖。

实际执行下列入口，每个 runner 用 subprocess 执行完整 child argv，将 stdout/stderr、真实 returncode、墙钟时间分别存独立 log/JSON，最后以 child 原 returncode 退出。不能用尾 cat 或别的末项覆盖失败。owner/adjacent/pyright/coverage 的 child 完整实际 argv（含解析后的 venv Python 路径）见本轮对应 JSON。

```bash
source .venv/bin/activate
python workspace/tmp/pr197-f7-implement-sol-20261001-01/run_validation.py owner
```

```bash
source .venv/bin/activate
python workspace/tmp/pr197-f7-implement-sol-20261001-01/run_validation.py adjacent
```

```bash
source .venv/bin/activate
python workspace/tmp/pr197-f7-implement-sol-20261001-01/run_validation.py pyright
```

```bash
source .venv/bin/activate
COVERAGE_FILE=workspace/tmp/pr197-f7-implement-sol-20261001-01/coverage.data python workspace/tmp/pr197-f7-implement-sol-20261001-01/run_validation.py coverage
```

owner child：`python -m pytest -p no:cacheprovider --basetemp=workspace/tmp/pr197-f7-implement-sol-20261001-01/pytest-owner tests/fins/test_cn_download_models.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py -q`。

adjacent child：`python -m pytest -p no:cacheprovider --basetemp=workspace/tmp/pr197-f7-implement-sol-20261001-01/pytest-adjacent tests/fins/test_cn_pipeline.py tests/fins/test_hk_period_rebuild.py tests/fins/test_cn_report_selection.py tests/fins/test_fins_ingestion_runtime.py -q`。

pyright child：`python -m pyright dayu/ tests/ utils/`，检查实际改动后的源码和测试，不以旧 baseline/隔离探针代替。

coverage child 一次运行上述七模块，basetemp 为本轮 `pytest-coverage`，四个独立参数为 `--cov=dayu.fins.pipelines.cn_download_models --cov=dayu.fins.pipelines.cn_download_workflow --cov=dayu.fins.pipelines.cn_download_rebuild --cov=dayu.fins.pipelines.cn_pipeline`，以及 `--cov-report=term-missing --cov-report=json:workspace/tmp/pr197-f7-implement-sol-20261001-01/coverage.json -q`。

| Validation | 本轮实际结果 | 本轮 log |
| --- | --- | --- |
| owner pytest | 188 passed / 0 failed / 0 skipped / 3 warnings / exit0 | `workspace/tmp/pr197-f7-implement-sol-20261001-01/owner-1790788929854470000.log` |
| adjacent pytest | 553 passed / 0 failed / 0 skipped / 3 warnings / exit0 | `workspace/tmp/pr197-f7-implement-sol-20261001-01/adjacent-1790788961088734000.log` |
| full pyright | 0 errors / 0 warnings / 0 informations / exit0 | `workspace/tmp/pr197-f7-implement-sol-20261001-01/pyright-1790788987000589000.log` |
| 七模块一次 coverage | 741 passed / 0 failed / 0 skipped / 3 warnings / exit0 | `workspace/tmp/pr197-f7-implement-sol-20261001-01/coverage-1790789086892641000.log` |

pytest 每次的三条 warning 都是第三方 edgar 弃用提示；pyright 的版本可用提示不是类型 warning。四次代码验证首轮均通过，没有产品验证失败/恢复。

取证/报告生成事件如实保留：部分组合读取输出截断，随后按 plan/源码/测试/diff 相关区段重读；第一次生成报告的临时 Python heredoc 因嵌套 triple quote 提前闭合而 SyntaxError，未执行脚本或写入报告，随后 shell 尝试运行尚不存在的 `build_artifact.py`，整条工具命令实际 exit2。第一子命令的独立退出未采集，不把末项 exit2 当作它的退出。改用直接 apply_patch 写本报告恢复，失败输出另存 `artifact-generation-failure.json`；没有隐藏失败、改变源代码或重跑已绿门禁。

owner 用例实际覆盖普通/零候选、取消、Phase B/post-repair/post-repair company typed abort、cause/rows/no-completion；rebuild empty/matching/failed-row/cancel 与 CN/HK local-only。两个入口交叉/未知/大小写/strip/缺失/null/int/blank，以及 ticker/filters/missing/rows/coverage/真实空仓储 locator 拒绝均实际运行。保留已有 stream/checkpoint identity、initial preflight、真实仓储 direct RESULT/job 持久摘要回归。新增 ticker/form/start/end 非法参数在普通/rebuild 均直接 ValueError；CN/HK rebuild read/checker 均锁原异常对象 identity。

所有字节/候选/转换均是既有合成边界假件，真实 Fs 仅运行本轮隔离 basetemp；无私人语料、外网、真实下载/OCR/Docling、依赖升级、配置豁免。

## 4. 四文件 coverage

来自本轮七模块一次采集的 JSON，逐文件断言 >=80；不以 overall 掩盖。coverage.data/JSON 都在本轮 prefix，根 `.coverage` 收尾不存在。

| 生产文件 | statements / missing | 实际 percent_covered | 未覆盖行 |
| --- | --- | --- | --- |
| `dayu/fins/pipelines/cn_download_models.py` | 108 / 3 | 97.22222222% | 188, 190, 194 |
| `dayu/fins/pipelines/cn_download_workflow.py` | 267 / 14 | 94.75655431% | 170–172, 174, 190, 452–453, 673, 702, 723, 730–731, 884, 901 |
| `dayu/fins/pipelines/cn_download_rebuild.py` | 181 / 26 | 85.63535912% | 95, 174, 239, 281–283, 306, 316–320, 348–352, 358–363, 449, 453, 455 |
| `dayu/fins/pipelines/cn_pipeline.py` | 464 / 25 | 94.61206897% | 172, 194, 222–223, 287, 314, 341, 546, 626, 829, 887–889, 894–895, 900–901, 908–909, 1187, 1637, 1641, 1767, 1825, 1851 |

## 5. 精确路径与 diff 审计

`python workspace/tmp/pr197-f7-implement-sol-20261001-01/audit_candidate.py` 实际 exit0。首尾 SHA、完整实际命令/子退出与双流记录在 `candidate-audit.json` 和各 `.stdout/.stderr`。四生产/两修改测试/新 owner 测试/两 README 的精确 diff 已实读。

| 独立检查 | 实际结果 |
| --- | --- |
| tracked `git diff --check` | exit0，双流各 0 bytes |
| `git diff --check -- <精确八 allowed paths>` | exit0，双流各 0 bytes |
| 新 test `git diff --no-index --check /dev/null <test>` | exit1，双流各 0 bytes；新增差异语义，无空白错误 |
| 生产 `rg -n '_INTEGRITY_FAILED_STATUS\|_CN_TERMINAL_OK\|_CN_TERMINAL_CANCELLED' dayu/` | exit1，双流各 0 bytes；无命中是预期成功信号 |
| owner/type/consumer callsite `rg` | exit0，实输出见 `owner-callsite-search.stdout` |
| 八已有获准修改文件的精确集合 | 与 freeze allowed_existing_writes 一致；新 test 起点 absent、收尾存在 |
| 21 只读 live / 29 originals SHA | 首尾全部 MATCH；所有 original 维持起始 SHA |

新 artifact/no-index 和最终 sidecar 身份审计在本轮 `end-audit.json`。artifact 自身 SHA 独立记录，避免自引用。候选快照使用本轮新 `candidate-snapshot/` 与 `candidate-manifest.json`，不覆盖任何 rawsnapshot/original。主树公告的无关 dirty 首尾另记，不认领、不恢复。

## 6. README 决定

已读 fins README Agent 更新约束/Download adapter 节和 tests README 开头职责/现下载终态段。fins 只补已实现 owner 和入口子集短段，tests 只补当前测试覆盖短句；无 gate 治理/未来设计/职责扩张。根 README 用户工作流/CLI/安装未变，`dayu/README.md` 分层/装配未变，无更新触发；其它 README 不触发。

## 7. 风险、owner、目的地及停止

| 风险 / 未覆盖项 | 分类 | Owner / 目的地 |
| --- | --- | --- |
| 三值分散、漏 rebuild、普通/abort 子集漂移 | fixed in current slice（候选已实施并验证，未获 code review 裁决） | F7 owner → root 同版双路 code review，不等于 accepted finding/slice |
| serialized/取消/typed abort/rows/cause/direct/job 保全 | fixed in current slice（合成真实 Fs 与既有回归通过） | F7 owner → root 候选验收，不增加取消/原因/manifest 成功语义 |
| 表列未覆盖行、全仓 pytest/真实 provider/外网转换可用性 | assigned to later work unit | PR197 root 既有完整 PR 验证/closeout；当前只承诺受影响/相邻模块和全量类型检查 |
| F3/F4/F5/F6/其它原 WU 已登记残余 | assigned to later work unit | PR197 root 按对应 goal/WU 串行排程共用源码；本轮未实施/重裁 |
| CN/HK 空库 rebuild 取消不对称 | requiring new issue or explicit user decision | 沿用 root 裁决；非本 goal，不改，当前 seeded 文档取消只锁原检查点 |
| 实际 provider/model canonical 回执未暴露 | assigned to later work unit（运行核收，非业务风险） | root 托管回执核收；不以 label/token 猜型号 |

未触发 branch/21只读SHA/29原件漂移、共同源码写冲突、owner/必需输入不可读或质量门禁需越界修复的停止条件，没有需要扩大授权的 blocking 诊断。

唯一 S1 已生成可审查候选，下一入口固定为 **root 对同版候选安排 MiMo/Kimi code review 并独立裁决**。本轮完成后停止，不自行派发/推进 gate，不宣布 accepted slice 或产品/PR 闭环。

## 8. 冻结输入首尾 SHA-256

下表由本轮 start/candidate audit 实际数据生成。readonly 21 行首尾相等；allowed write 八行的 original 均保持 start SHA。详细起点/终点记录只写独立 JSON，不改原件。

| 输入 | 属性 | start SHA-256 | end SHA-256 |
| --- | --- | --- | --- |
| `AGENTS.md` | readonly | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` |
| `docs/gateflow/pr-197-r1-f7-goal-20260930.md` | readonly | `b13da46c2cd9a008fb250ed1567131f0c51a6977fa70f3e718f410ed43a1a0b7` | `b13da46c2cd9a008fb250ed1567131f0c51a6977fa70f3e718f410ed43a1a0b7` |
| `docs/gateflow/pr-197-r1-f7-plan-20260930.md` | readonly | `5820a4924bcd91c7a964b3bbc241fa739979ef3a8183bf11a7837787dc944e3d` | `5820a4924bcd91c7a964b3bbc241fa739979ef3a8183bf11a7837787dc944e3d` |
| `docs/gateflow/pr-197-r1-f7-plan-controller-evidence-20260930.md` | readonly | `d10180216adcd0111b5b53347183b2cbe58c9198f87af9467c516f0f3ad333d5` | `d10180216adcd0111b5b53347183b2cbe58c9198f87af9467c516f0f3ad333d5` |
| `docs/gateflow/pr-197-full-review-adjudication-20260929.md` | readonly | `b712698078bc4c59e0d2ec5bd379f8b6c4dce29eaa8745352ebef57d0bd18c50` | `b712698078bc4c59e0d2ec5bd379f8b6c4dce29eaa8745352ebef57d0bd18c50` |
| `docs/reviews/pr-197-review-20260930-003634.md` | readonly | `a2cc191ad507a2b44d7426d75f260fcbe8a69d05e1fd11d4106568e337d32d9d` | `a2cc191ad507a2b44d7426d75f260fcbe8a69d05e1fd11d4106568e337d32d9d` |
| `dayu/fins/pipelines/cn_download_models.py` | allowed write | `abc7ecaa90d7f7fee89ec51c78902c720a0ca36a4fad6a52ef3e91bf50cedea0` | `c0311852f5a61f0fac4b3805535e59eceabb835e7ff2d0895f74ff25b7f79a20` |
| `dayu/fins/pipelines/cn_download_workflow.py` | allowed write | `13bc11cc7bad4aa771becfe63a4eb99428108da3d7c5c9e565a78b3fa646f0a6` | `989b77b0c4866f0e7753858c822bae40abddd4ef6e6522caa1c631c46e2c7b49` |
| `dayu/fins/pipelines/cn_pipeline.py` | allowed write | `5b902d10aa3f0de09759e9e7b93660afe6905f005895848251f6180d8b6327d7` | `a26052b8a45d7f57d66786fbfac4de4f96ab0a4054f9873616265ea56121739c` |
| `dayu/fins/pipelines/cn_download_rebuild.py` | allowed write | `1380997473be8749359db72cb00950c219d5f9ac79a354700e99893d6423cfe8` | `e55c8ed4ae7035716046606241f3ff48a2e0b9984610f933826cd7b3d1683d1c` |
| `dayu/fins/pipelines/hk_download_rebuild.py` | readonly | `e57a3e57dc4c6d14a32cdaa73db91107236918e2d75c30b804c8dbd1c8c742f2` | `e57a3e57dc4c6d14a32cdaa73db91107236918e2d75c30b804c8dbd1c8c742f2` |
| `tests/fins/test_cn_download_workflow.py` | allowed write | `38301f790796e276a9b83f8540306ecc84527d71957a2262040731f0f8a29218` | `8a8fede5189141c766997c2eba25ffff980db68640d07cb955b7665a0bfdb387` |
| `tests/fins/test_cn_download_runtime.py` | allowed write | `69e8bbf6cb4ff90d9d10a75225436cf0b9c7a8395dcfef46372fb8374bb52004` | `6a1608d0051ef8b000b146be973ed4c21cedf7e94af205cff7a96a4176776ae4` |
| `tests/fins/test_cn_pipeline.py` | readonly | `3e66092374464afd9dbf5459c3abe2b4bf697551b9f7a3bc4882c7a304f70ba2` | `3e66092374464afd9dbf5459c3abe2b4bf697551b9f7a3bc4882c7a304f70ba2` |
| `tests/fins/test_hk_period_rebuild.py` | readonly | `6e52c12ec828a0201285ef39e63c98188a5a72ab6b1bc970ad4d78fc37c1eb19` | `6e52c12ec828a0201285ef39e63c98188a5a72ab6b1bc970ad4d78fc37c1eb19` |
| `tests/fins/test_cn_report_selection.py` | readonly | `edce06f4e28829f4cbcd4486d9048cd25379880d846c1ceac7079e54e04158c2` | `edce06f4e28829f4cbcd4486d9048cd25379880d846c1ceac7079e54e04158c2` |
| `tests/fins/test_fins_ingestion_runtime.py` | readonly | `29d53d03f578ae58b7cec03d7abd32cde259a262a59846cbd7a646da8a553491` | `29d53d03f578ae58b7cec03d7abd32cde259a262a59846cbd7a646da8a553491` |
| `dayu/fins/README.md` | allowed write | `329da795925f1966db8bc9625c94ca09f235c009df54cf4e694e15bdd7259d1f` | `76fc499131beb7d76fc4b5a3c07823b2178101a6c5945b36c93310fb15688f79` |
| `tests/README.md` | allowed write | `5d7e9d76eebcd0aa9ae8c8de6af70d3327d0854264ae5a09ec9ffa1dbcbe04ad` | `4a8309ea7a19cd880474a87e42466b18cdac758fb3aff2895dbc685f1b6c5494` |
| `pyrightconfig.json` | readonly | `661d7c531f7cacc7038f570675b43052ed800cd87915a1a218504dbfe6d4357c` | `661d7c531f7cacc7038f570675b43052ed800cd87915a1a218504dbfe6d4357c` |
| `pyproject.toml` | readonly | `28429056b51e29c672f029723d3bbef0db0d781b6bc72d0cb8c2d3e823c79474` | `28429056b51e29c672f029723d3bbef0db0d781b6bc72d0cb8c2d3e823c79474` |
| `docs/gateflow/pr-197-r1-f7-plan-fix-20260930.md` | readonly | `394fe91bb4a76f40080655223aaefc9f90d435df6fbb1eeb7818ce4a2714f2aa` | `394fe91bb4a76f40080655223aaefc9f90d435df6fbb1eeb7818ce4a2714f2aa` |
| `docs/reviews/plan-review-20260930-230120.md` | readonly | `25b8827ebb64d7fe76c4611167cc9e9410692caee76138f3483240e85c94cf6c` | `25b8827ebb64d7fe76c4611167cc9e9410692caee76138f3483240e85c94cf6c` |
| `docs/reviews/plan-review-20260930-230304.md` | readonly | `018c3f1acc1d6ade0395113687eda5c7b14738b07cf5d43e0612119d5c30161c` | `018c3f1acc1d6ade0395113687eda5c7b14738b07cf5d43e0612119d5c30161c` |
| `docs/gateflow/pr-197-r1-f7-plan-review-adjudication-20260930.md` | readonly | `5762634862d2ea022d63497469f62065488b41870fe499242488ed045549054c` | `5762634862d2ea022d63497469f62065488b41870fe499242488ed045549054c` |
| `docs/gateflow/pr-197-f3-f7-fix-receipt-20261001.md` | readonly | `a0da40ab10588f37274de0b618019b6ddc47b945ffbd57eab903d5a7a8d55737` | `a0da40ab10588f37274de0b618019b6ddc47b945ffbd57eab903d5a7a8d55737` |
| `docs/gateflow/pr-197-r1-f7-plan-rereview-adjudication-20261001.md` | readonly | `2c622aefcbc8532959c6efba043f4a562d7b7b9e81b50b70eae6cefe0fb97471` | `2c622aefcbc8532959c6efba043f4a562d7b7b9e81b50b70eae6cefe0fb97471` |
| `docs/reviews/plan-review-20261001-002227.md` | readonly | `aca1d25f6eb2ec37172fa96408d8cbdaf29e4657803240a6839037639b47175a` | `aca1d25f6eb2ec37172fa96408d8cbdaf29e4657803240a6839037639b47175a` |
| `docs/reviews/plan-review-20261001-002251.md` | readonly | `8260db51ea34b695c3b6db0f6bc1d837ac763cf6f60ac561e18aac7fd3264603` | `8260db51ea34b695c3b6db0f6bc1d837ac763cf6f60ac561e18aac7fd3264603` |

新增 `tests/fins/test_cn_download_models.py` 起点 absent，收尾 SHA-256 `6092b64b972d097c4298067a82b65e878d6ede2b1166d8ce6a4b444dfd292e54`。
