RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown

CANARY=gpt-6-sol-26780933

# PR197 F4-S1：F4-CR1-A1/A2 同 owner 修复候选

## 身份、输入与完成边界

- Label：`pr197-f4-s1-fix-sol-20261001-01`；唯一 workspace `/Users/leo/workspace/dayu-agent-r`；唯一分支 `codex/upload-material-oracle`。本轮为当前 S1 code-review fix，不新建 slice，不重裁现成业务。
- 实际模型无法通过本轮可用的权威 runtime metadata 核验，故 actual model 为 `unknown`；任务指定 provider/model 槽位为 `gpt-6-sol`，不将任务称谓或 canary 文本当实际模型证明。
- 上行 CANARY 来自本轮工具读取 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.xQKcsM/canary.txt` 的逐字内容；未采用历史 plan/report 的 token。
- 唯一身份输入 `workspace/tmp/pr197-f4-s1-fix-sol-20261001-01/freeze.json`，SHA256 `20dcf7055993f3ccb358fce9db2898cc1ec9008d0c8c020d3e64f9260ce657a5`。实际 `len(files)=51`、`len(allowed_write)=8`、`len(readonly)=43`，不沿用上一轮 review 的47或报告误记。
- 首检：51/51 current、51/51 originals 与 freeze 对应 SHA 相同；branch、HEAD `dc29c1fe5e173d9ef710cd7f44fd0889e0da46c9`、main `fac32ecbff9bfe792b63ee9667c8697826b631f4` 均符合本轮输入。
- 已读 `AGENTS.md`、Gateflow skill、F4 goal/accepted plan、最新 root code-review/deep-json 裁决，以及 Kimi `docs/reviews/code-review-20261001-060123.md`、MiMo `docs/reviews/code-review-20261001-060644.md` 全文。A1 中/A2 低均沿用 root accepted，不重新判业务。
- 实际修改恰为 freeze 的八个 allowed 文件；唯一新增非临时 artifact 为本文。协议/adapter 仅修正原“脱离原返回值”的文档措辞，签名、类型及委托方法体保持。没有修改其余 F4 实际文件、原报告、root 控制文档、F3/F5/F6/F7、五 utils、类型/依赖配置或任何 originals/freeze。
- 期间发现 root docs checkpoint `87dfbeae8625e34162812c06886610c37ba0f4e9`（`gateflow: record F4 review and remaining repair queue`）。已实查相对旧 HEAD 的19个提交路径全部为 docs，旧 HEAD 是其祖先；当前 frozen readonly 的字节仍全部匹配。只记录该允许的文档 checkpoint，不把 HEAD 变化视为源码漂移。本轮作者没有 stage/commit/push/PR/comment/merge/main/branch/worktree 操作。
- 本文为作者修复候选；不自行判 code-review gate pass。完成验证和 artifact 后停止。下一入口为 root 核收 → 同版 MiMo/Kimi re-review；root/user 保有裁决与 merge 权限。

## A1：必要性、owner 与生命周期

问题真实成立。root 与双路真实 Fs 反例已证明深600 business meta 经 blob/source/batch API 真正 commit，旧 list/get 与 integrity COMPLETE 成功，新 view 的递归 deepcopy 单独失败。本轮新增真实 owner 回归在修前再次得到 dict-600/list-600 两个 `RecursionError`；8/300 控制与其他 meta-view 测试通过。动机是消除批量读取新增的合法 JSON 拒绝，无需新 JSON 规则或新的产品选择。

唯一行为修复位于 storage owner `_FsSourceDocumentMixin.read_source_meta_view`：删除专用于本 view 的 `deepcopy` import，将 `MappingProxyType(deepcopy(meta))` 改为 `MappingProxyType(meta)`。

实际直接链：

1. `_get_source_meta_unguarded` 调用 `_get_persisted_source_meta_unguarded`。
2. persisted getter 每次调用 `_read_json_object` → `_read_json` → `json.loads(path.read_text(...))`，产生本次独立 JSON 对象树，没有缓存或另一公开读取的嵌套引用。
3. `_source_meta_without_revision` 产生仅去私有 revision 的业务字典，嵌套值来自本次 parse；persisted 字典仅是该 getter 链的局部变量，不是外部持有者。
4. view 直接将该业务字典交给顶层只读 proxy；后续公开 get/read 再次解析，后续 publication 只改变磁盘事实，均不会回改旧 view 的对象树。

因此独立公开观察在递归副本之前已由 owner 生命周期成立，直接包装是最小修法。没有必要无递归副本的反证，未新增通用 JSON 框架。嵌套消费者仍只读，不承诺深冻结或“人工捕获的私有中间对象”隔离。

同 guard、完整旧枚举排序、get 次序、成功前缀、首个原 `ValueError/OSError` 对象及 break、list/guard/unexpected 的即时传播和 finally 释放原样。core AST 对比仅 `read_source_meta_view` 改变；public get/list、unguarded getters、classify/snapshot 等其余函数 AST 不变，parser/integrity/identity/workflow 源码 SHA 保全。没有下游 catch、fallback、限深、丢文档、typed UNSAFE 化、新入库限制、递归预算调整或错误优先序迁移。

## A2：测试迁到公开 owner 合同

- 从真实 reader probe 只删除用于持有私有中间 return 的 `returned` 字段/append；不再人为修改该私有引用。
- 原 reader 首 get barrier、真实 writer 等待、两文档全 A/全 B、两种 rename barrier、guard/list/get 顺序计数、四类成功前缀原异常同对象、list/unexpected 即时失败与锁释放全部保留。
- 原 barrier 用例保留顶层 `MappingProxyType` 只读断言，补独立公开 get 嵌套变异后再次 get 保真、latest view 全 B 嵌套值不污染、旧 view 全 A 嵌套值跨真实 B 发布不变。
- 新增参数化 owner 回归 `test_meta_view_committed_deep_json_preserves_public_observation_independence`：dict/list 每层容器各覆盖8/300/600，六个真实隔离仓储案例，使用原 blob/source helper 真正提交，真实 classify COMPLETE、旧 list/get 成功、新 view 成功、去私有 revision、顶层只读、每层形态和末端 `str/None/bool/int/float` 内容保真。
- 修改独立公开 get 返回的末端业务值，断言原 view、fresh get、fresh view 都未污染；两个 view 与 get/read 的末端嵌套对象身份独立。对 view 只读使用，没有用嵌套变异来要求深冻结。
- 通过 reset/source/blob/batch 再真正提交 B，断言新 view 为 B、两个旧 view 保留 A；不篡改磁盘来伪造合法数据、不 mock COMPLETE。
- 构建/检查深 JSON 都用迭代，避免测试的递归比较先失败；600 是已证明回归样本而非产品上限。回归在旧实现红、修后绿，且检查公开观察合同，未只断言实现调用次数。

| Finding | 既定裁决 | 作者候选修复状态 | owner / destination |
| --- | --- | --- | --- |
| F4-CR1-A1 | 中 / accepted | 已修复（候选，待 root 与 re-review 验证） | storage view 读取生命周期 → 当前 F4-S1 re-review |
| F4-CR1-A2 | 低 / accepted | 已修复（候选，待 root 与 re-review 验证） | storage owner tests → 当前 F4-S1 re-review |

## 计划与 README 决定

accepted F4 plan 仅改 §4 原 deepcopy 技术句及其 fresh-parse 生命周期说明，并在 §9 增补对应公开独立观察测试断言。旧身份头部、历史 canary/runtime、候选/接受历史文字保留，不把这些作者报告字节当本轮 runtime metadata；原件不改。binding goal SHA 仍 `d1f374b9adb053761c66e9dd04e2a27ae6cdb4e299b715f70d9f91ee99d9d05e`；全部其他接口、矩阵、ID规则、选项、错误优先序及事件窗口不改。这是直接反例否定技术假设后的必要 correctness 修正，保全同一 goal/public contract，没有新业务选择。

已读 Fins README 的 `Agent更新约束`：只同步已实现公开观察的 fresh parse 独立生命周期、顶层只读及嵌套消费者只读，未加入过程状态/测试清单/未来能力。tests README 未设独立 Agent 约束，以其开头“现有测试分层、运行方式与维护约定”为读者职责，补已存在的深层 owner 回归描述，明确回归层数不是产品限值。根 README 无入口/用户工作流/参数/输出/排障变化，dayu 总览无分层/装配变化，均不更新。

## 当前 SHA、范围与覆盖率

以下全部来自本轮真实读取及 `coverage-verified.json`，不是历史数字。八个 F4 production 文件逐份 >=80%；大目录总 coverage 不作为本 WU 的逐文件验收。

| F4 production 文件 | current SHA256 | 本轮范围 | covered / statements | coverage |
| --- | --- | --- | --- | --- |
| `dayu/fins/storage/source_meta_read.py` | `78dacf369cefa1cebce2df3a59fd85fb046075ee1c47fa5da24593abd852f1a2` | 修改 | 14/14 | 100.00% |
| `dayu/fins/storage/repository_protocols.py` | `c2c70eaa15bf0f728cf42b0a933687fbee27981a57573f73d96dbeb841616f6f` | 修改 | 238/292 | 81.51% |
| `dayu/fins/storage/__init__.py` | `d6e0b6a4d9b1aa16516a501ab964d91f4231471c1c3bfaca385e0c13f75c89e1` | 只读保全 | 15/15 | 100.00% |
| `dayu/fins/storage/_fs_source_document_core.py` | `6cbd47bef352ec7325e98e222e0ded1e0308785b9900f5d1d69611634af31cdc` | 修改 | 417/492 | 84.76% |
| `dayu/fins/storage/fs_source_document_repository.py` | `23a8a1ac563346319acf70e9d32dddf4d92e73c4323b50b9faa2a475265c2a2f` | 修改 | 88/91 | 96.70% |
| `dayu/fins/pipelines/cn_download_identity.py` | `21842fbc08cf4f68c2ede914cbbc9a423ff0a5801ee18be37940d4f98cb21a6c` | 只读保全 | 63/63 | 100.00% |
| `dayu/fins/pipelines/cn_download_workflow.py` | `5fe5ec5b904b1ef649e1d6c23da46c64ca37cf8564bfb21653392cf126591fec` | 只读保全 | 247/269 | 91.82% |
| `dayu/fins/pipelines/cn_download_filing_workflow.py` | `708ed8ce8a360d452f6e00ff2514814900446f0f0647f6a2051f6f45a060163b` | 只读保全 | 194/209 | 92.82% |

| 其余本轮改动文件 | current SHA256 |
| --- | --- |
| `tests/fins/test_fins_storage_atomicity.py` | `d47ba4a315469d03def7ab32b8e785e863310b971846fd5834403f1b6f1afdd1` |
| `dayu/fins/README.md` | `0304ee909bc0a3f29143a8c319e439b898454cd80d6f74651dd941612b3ad386` |
| `tests/README.md` | `a1b4b71e7c6c0b97f99fa6f5d4e83769101d4a8a76206d897a44c0af9dc847e1` |
| `docs/gateflow/pr-197-r1-f4-plan-20260930.md` | `10ddb72763c7b9e0ca7bdc3e22015a18ecfac018e24b6230a6ea0d54b66c58c0` |

全部51源 current/frozen/original SHA 与43只读身份详表：`workspace/tmp/pr197-f4-s1-fix-sol-20261001-01/candidate-audit.json`。完整差异为同目录 `audit-final-diff-0` 至 `audit-final-diff-7.stdout.log`，顺序为 freeze.allowed_write；逐件全文 noindex whitespace 检查为 `audit-final-hygiene-0` 至 `7` 以及 `audit-final-hygiene-report` 三件套。作者完整读八份真实差异，public/get/list/parser/integrity、身份/workflow 与其余 readonly 没有变更；F3 plan SHA 仍 `2983efa4326cc799565fab27a350d79bf74b40d540beb0143b4dfa90f181a421`。

## 实际验证与双流/exit

本轮独立 runner 为 `workspace/tmp/pr197-f4-s1-fix-sol-20261001-01/run-validation.py`；原 implement runner 仅只读参考并复制到本轮目录，原文件未改。runner 每条命令都先 `source .venv/bin/activate`，将真实 stdout/stderr/exit 分别写为 `<name>.stdout.log`、`<name>.stderr.log`、`<name>.exit.json`。不覆写失败记录，未改 coverage omit/config/ignore/skip；所有脚本/log/data/JSON 均在本轮目录。无网络或私有 corpus，真实仓储仅为 pytest/tmp 合成输入。

| 命令 label | 实际结果 | 用途/证据地位 |
| --- | --- | --- |
| `focused-before-fix` | exit1；2 failed / 17 passed / 242 deselected，5.02s | 新回归修前红，dict-600/list-600 在 deepcopy 抛 RecursionError |
| `focused-after-fix` | exit0；19 passed / 242 deselected，1.29s | owner 修复后首次 focused |
| `pyright-version` | exit0；1.1.409 | 实际版本，不改依赖 |
| `pytest-final-coverage` | exit0；794 passed / 3 warnings，43.31s | 首轮矩阵；随后测试类型修正，故以 verified 重跑为最终证据 |
| `pyright-final` | exit1；4 errors / 0 warnings | 新测试两处非法 setitem 的静态类型失败，后已恢复 |
| `focused-final` | exit0；19 passed / 242 deselected，1.47s | 最终测试源码 focused |
| `audit-before-final` | exit1；仅 git identity 被过强旧HEAD相等检查误报 | root 合法 docs checkpoint，源码/readonly/originals/hygiene 均无问题；原记录保留 |
| `audit-recovered` | exit0；43 readonly / 51 originals 保全，core仅view变化 | 改审计为核验docs checkpoint祖先与路径、仍逐件检查冻源字节 |
| `pytest-verified-coverage` | exit0；794 passed / 3 warnings，43.12s | 最终同版九模块及独立coverage data/JSON |
| `pyright-verified` | exit0；0 errors / 0 warnings / 0 informations | 最终默认全量 `python -m pyright` |
| `audit-final` | exit0，43 readonly / 51 originals 保全；全文hygiene无诊断 | 包括本文的末检证据，未发生额外源漂移 |

最终九模块与 coverage 实际命令（完整命令也在 exit JSON）：

```bash
source .venv/bin/activate
COVERAGE_FILE=workspace/tmp/pr197-f4-s1-fix-sol-20261001-01/coverage-verified.data python -m pytest tests/fins/test_cn_download_identity.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/fins/test_fins_storage_atomicity.py tests/fins/test_hk_period_rebuild.py tests/fins/test_cn_report_selection.py tests/fins/test_hkexnews_downloader.py tests/fins/test_source_meta_contract.py tests/fins/test_fins_storage_provider.py -q --cov=dayu/fins/storage --cov=dayu/fins/pipelines --cov-report=term-missing --cov-report=json:workspace/tmp/pr197-f4-s1-fix-sol-20261001-01/coverage-verified.json
python -m pyright
```

沿目录 source 运行 coverage，不用旧 named-package collection；`coverage-owner-summary.json` 是从最终 JSON 逐文件抽取并实查 >=80 的数据。运行 Python 为3.11.15；edgar 三个既有 DeprecationWarning 仍在。pyright 启动器提示新版本1.1.414可用，该提示单独记录，不是类型诊断 warning；未升级，本轮实际1.1.409。

### 所有非零命令、失败与恢复

1. 修前 focused exit1：预期反例采集，两个真实600层案例失败于生产 deepcopy；不是假造 fixture 失败。修后及最终 focused 均19通过。
2. 首次全量 pyright exit1：测试试图通过 `operator.setitem` 对静态只读 Mapping 做运行期非法写入断言，产生4条类型诊断。删除这两次非法调用，保留原 `MappingProxyType` 顶层只读断言及全部公开独立性/跨发布断言；未引入 cast/Any/object/ignore/反射或类型绕过。默认全量重跑为0 error/0 warning。生产只读保证来自该只读容器，不能要求生产补可变接口以测试非法写入。
3. `audit-before-final` exit1：临时审计错误要求 HEAD 与旧freeze HEAD完全相同，碰到允许的 root docs checkpoint；直接查19路径全部docs、祖先关系成立、43 readonly与51originals仍匹配后修正审计范围，`audit-recovered`/`audit-final` exit0。没有回滚或干预 root 的提交。
4. 一次 `rg 'deepcopy|原返回值|复制元数据|脱离'` 在四个相关 source 文件与当前 plan 无匹配，exit1；这是残留搜索的空结果，不是产品失败，没有“恢复”修改。
5. 本轮生成的8份 `git diff --no-index <original> <current>` 均exit1，stdout为真实差异、stderr为空；全文 `git diff --no-index --check /dev/null <file>` 的exit1/双流为空表示存在相对于空文件的差异且无空白诊断，不当成lint失败。未发现真正尾空白。每条真实exit与双流在审计记录中保留。
6. 其余本轮已执行测试、版本/coverage提取、读取与身份检查无非零失败；没有 provider 重试、子 Agent、网络或外部应用写操作。未将历史实施或review的失败冒称本轮自跑。

## Residual risk / 未覆盖项

| 项目 | 分类 | owner / destination |
| --- | --- | --- |
| A1合法深JSON新增拒绝与A2私有引用测试固化 | fixed in current slice（作者候选已修，待复审） | storage owner / owner tests → root核收及同版MiMo/Kimi re-review；不据分类自判gatepass |
| F4-R01 resolve→commit跨writer target-only集合唯一性局限 | requiring new issue or explicit user decision | storage/identity → root后续候选；不扩为本轮集合事务验收 |
| F4-R02 各窗O(D)读取/索引与完整性全树扫描的总成本 | assigned to later work unit | storage性能 owner → root后续性能WU；未承诺整run线性 |
| start/stream在外部publication下可观察不同ID | assigned to later work unit | 事件owner → 既有观察边界/后续WU；当前矩阵保全，不提升原子事件承诺 |
| 嵌套view值由消费者只读、不是深冻结 | fixed in current slice（合同明确且公开独立已验证） | storage/消费者 → 当前公共契约与owner回归；未来共享缓存/解析器变更必须守住同一独立观察合同，不在本轮增加机制 |
| 未穷举所有OS故障组合、所有JSON形态/任意栈深；无网络/私有corpus验证 | assigned to later work unit | storage测试owner → 后续有直接证据的验证WU；当前已有真实屏障/顺序/错误/释放矩阵与dict/list深600回归 |
| MiMo提及非缺陷的assert类型收窄清理、未来caller传非HK集合后查HK风险 | assigned to later work unit | identity owner → 后续真实caller扩展时审查；当前caller与readonly文件未改 |
| F3/F5/F6/F7与原upload队列 | assigned to later work unit | 各既有WU owner/root → 原队列与各既有gate；本轮不触碰其source/tests/报告 |
| 实际runtime model不可核验 | fixed in current slice（按任务协议如实报告unknown） | root runtime证据owner → 本轮外层metadata核收；不以任务名称补值，不新增用户业务选择或据此自判门禁 |

作者交付状态：本轮fix、实际验证与唯一报告已完成；A1/A2候选已修复，正式修复状态/门禁仍由root与re-review核验。停止于本任务边界。
