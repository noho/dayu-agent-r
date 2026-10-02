RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-aa25fd3d

# S2 owner 输入合同集中修复候选报告

## 工作单与当前结论

任务 label `upload-material-unified-s2-owner-contract-sol-20261003-01`；统一 upload_material 修复 WU 的 gate `fix S2`，仅收尾 `US2-R04-T01`。T01 已完成本轮实现与验证，状态是**已修候选，待总控安排同版双复审**。不宣告 S2 pass，不修改 root finding 的最终状态，不开新 slice。

本轮仅在唯一 workspace `/Users/leo/workspace/dayu-agent-r` 和唯一开发分支 `codex/upload-material-oracle` 执行。HEAD `f7e60c9d3e4c6e77a6c2abf18d09cd8020c19235`、main `fac32ecbff9bfe792b63ee9667c8697826b631f4` 不变。具体服务模型 identity 未在本轮工具/上下文中暴露；上下文仅说明 GPT-6 家族，故精确 MODEL 如实记为 unknown，不从 provider 或 CANARY 推定。CANARY 来自本轮指定 canary.txt 实读，并保存于 `workspace/tmp/upload-material-unified-s2-owner-contract-sol-20261003-01/canary.txt`。

## 动机、owner 与最窄修复

总控两份裁决全文和 AGENTS.md/CLAUDE.md 已读取。直接证据是冻结 core 的登记方法在读取 `expected_source_state.source_integrity` 前没有类型校验，旧测试通过 cast 非法 None 后断言 AttributeError。该异常依赖内部属性访问，不能作为公共输入错误合同。输入语义 owner 是 `_FsMaterialUploadStateMixin.register_material_upload_preconditions`，无需下游补偿或新业务语义。

生产逻辑只新增方法首部 `isinstance(expected_source_state, MaterialUploadPublishedState)` 校验：非该类型立即抛 TypeError，中文原因为“expected_source_state 必须是 MaterialUploadPublishedState 类型的完整材料状态”，在材料条件登记前拒绝，不读取非法值的内部属性。签名仍必填、非 nullable、无默认值。原 capability、重复登记、source/company 精确比较、锁序、commit、final guard 和 readonly validate 显式 None 代码均保留。

core、protocol、publicFs 仅该 register 方法的中文 docstring 同步参数、返回、TypeError 及既有 ValueError、公司/源冲突、身份损坏、读取和可信结果异常。protocol/publicFs 没有执行逻辑增量。

原 `test_explicit_none_validates_company_without_missing_source_claim` 迁移为同一测试的 None/非法字符串两种参数。只以 cast 故意突破静态类型。真实 Fs 仓储先发布 COMPLETE，再验证 readonly None 返回该完整状态、具体 stale MISSING 严格拒绝；非法登记必须抛定义的 TypeError，公共 commit 按原 ValueError 合同拒未登记，finally rollback 后 `_bytes` 比较 portfolio 全部文件路径及 SHA256，以完整业务字节摘要证明未改写。没有假字段、私有 condition/state 断言或 AttributeError 断言。既有公司全快照/alias 漂移、合法登记/commit 与重复登记用例保留并在同一集合执行。

## 实际 changed paths、diff 与 SHA

冻结允许四文件全部是本轮 changed paths；另只新增本报告及自有 tmp。逐文件 delta 见 `workspace/tmp/upload-material-unified-s2-owner-contract-sol-20261003-01/diffs/`，合并 delta 见 `workspace/tmp/upload-material-unified-s2-owner-contract-sol-20261003-01/candidate-delta.diff`；这些 diff 相对本轮 frozen before，未把继承 dirty 内容误计为本轮变更。

| 文件 | frozen SHA256 | candidate SHA256 |
|---|---|---|
| `dayu/fins/storage/_fs_material_upload_state_core.py` | `7819477a9f2653cb2f4b0c114c0461bae617325f9f7ab0e36124d5805f3fbb47` | `0a9d16ba641c4950cd2e628234316badde45e77bd461d54d168ef295035bef11` |
| `dayu/fins/storage/repository_protocols.py` | `93082b720613509c5b5371c62d6d7b4cd5a12ba5b6ff8bb68cde62377c10cd15` | `a65da7e8692898240ce117b16275168590cfb9e2e918389a7b13c6e28ad686b1` |
| `dayu/fins/storage/fs_material_upload_state_repository.py` | `c736cd83b0581c04e0cfcfb27e272bdc897d88ac9190f33e8b56a86026681e64` | `a5f9978ebc337ee1eb4f36d436e2d0a967667809e8f41476dc6c718cbeb8b591` |
| `tests/fins/test_material_upload_state_repository.py` | `96dcdef2670513c1d5e336865c90d87f8de9c0211415bc49b32ccf8509feefce` | `8adbf0742909db886a08bd82d43d2bf1ef1b0f2aecc7099ecd05ba8e0807792c` |

去 docstring 后 AST 的 SHA 如下，完整 dump 和检查票据见 `workspace/tmp/upload-material-unified-s2-owner-contract-sol-20261003-01/ast/`、`changed-files-index.json`、`delta-audit-01/`。

| 生产文件 | frozen non-doc AST SHA256 | candidate non-doc AST SHA256 |
|---|---|---|
| `dayu/fins/storage/_fs_material_upload_state_core.py` | `21df29b8535a881be5895bc1bda051c9f768f57640489b0aa70cef4a53ad8081` | `7bc3ffae4118b041df9811b8ff769c8255d79d320771b8ce99570c0528c3e225` |
| `dayu/fins/storage/repository_protocols.py` | `be70afc21d59f31e98df9c0d831cde3c6543855be3b32168de57742fc4770fd9` | `be70afc21d59f31e98df9c0d831cde3c6543855be3b32168de57742fc4770fd9` |
| `dayu/fins/storage/fs_material_upload_state_repository.py` | `1daddc07787d302ab711155da697bce3f3e924f3fbdf927bd85b3e314a65e8b7` | `1daddc07787d302ab711155da697bce3f3e924f3fbdf927bd85b3e314a65e8b7` |

protocol/publicFs 去 docstring AST 完全相等。core 仅首条 guard 不同；机械移除精确 guard 后完整 non-doc AST 与 frozen 相等，SHA 为 `21df29b8535a881be5895bc1bda051c9f768f57640489b0aa70cef4a53ad8081`。这验证原正常 condition 路径没有执行逻辑变化。`diffcheck-01` actual wait exit 0，末核另检查全部新增行无尾空白，涵盖 git diff 不显示的原 untracked core/test。

## 验证与实际退出

所有正式验证先 `source .venv/bin/activate`，cwd 为唯一 workspace。自有 subprocess 使用 Popen.wait，未设置 timeout、未 kill、未重派。每次保留真实 argv/cwd、stdout/stderr、owned PID、actual wait exit、开始/结束时间和源码首末摘要。无管道处理 exit。

| 票据 | actual wait exit | 结果 |
|---|---:|---|
| `targeted-tests-01` | 2 | 两模块收集错误；JUnit tests=2/errors=2，无测试成功声明，无 coverage JSON |
| `targeted-tests-02` | 0 | 同一 pytest 进程运行两指定模块，81 passed；JUnit tests=81/failures=0/errors=0/skipped=0 |
| `full-pyright-01` | 0 | 初次定向失败后按序执行，0 errors/0 warnings/0 informations |
| `full-pyright-02` | 0 | 定向集合恢复成功后再按要求执行完整 pyright，同为 0/0/0 |
| `delta-audit-01` | 0 | 三生产 AST/四文件 diff/前三轮 CLI 原 SHA 与实际退出核验 |
| `diffcheck-01` | 0 | allowed paths 的 git diff --check |

最终定向 argv 为 `python -m pytest -o addopts= -p no:cacheprovider tests/fins/test_material_upload_state_repository.py tests/fins/test_material_upload_publication.py`，使用 `targeted-tests-02/pytest-tmp` 独占 basetemp、独占 JUnit/COVERAGE_FILE，`--cov=dayu/fins/storage`、本轮 `coverage.ini` 仅报告 core、`--cov-fail-under=80`；完整精确 argv 在 command.json。core 75/78 statements，96.153846%，未覆盖行 68/182/193 属原逻辑。protocol/publicFs 本轮只有文档，覆盖证据沿原源码/非文档 AST 继承，不新增宽矩阵。最终 coverage.json、JUnit、原 .coverage 均保留；两次正式集合和 pyright 的 source-delta 均为空。

## 非零探索、失败与恢复

首次 `--cov=dayu.fins.storage._fs_material_upload_state_core` 深层模块定位触发 NumPy “cannot load module more than once per process”，pytest 收集失败，actual 2。直接 `coverage-dotted-probe-01` 独立复现同一异常，actual 1；普通 `coverage-import-probe-01` 模块定位 actual 0。coverage/inorout.py 的 find_spec 定位会导入父包并吞掉定位异常，深层 dotted source 在覆盖率初始化阶段提前加载依赖。改为目录 source、用 report include 选择 core 后 `coverage-directory-recovery-01` actual 0；最终同一定向集合 actual 0。恢复只修改自有验证配置/脚本，不改产品或虚拟环境依赖，不降低断言/覆盖门槛。

一次探索误猜 coverage/pytest_plugin.py 路径；原组合读取的 rg 输出暴露 missing-path，但后续 cat 使外层 exit 0，不能据此外层 0 宣称探索成功。本轮随后用 owned wait 单独留存 `exploratory-path-error-01` actual 2，同一缺失路径证据保留；`exploratory-path-recovery-01` 改读实际存在的 inorout.py/pytest_cov/engine.py，actual 0。初次验证总 wrapper actual 1 对应 pytest 2；恢复 wrapper actual 0。全部失败票据未覆盖，必需验证无未恢复项。环境 edgar 三条弃用 warning、pyright 新版本提示原样保留，未升级依赖。

## 合法路径 production CLI 继承

只读取上一修复的三轮真实 production 双 CLI 票据：`cli-multifile-sequential`、`cli-multifile-simultaneous`、`cli-existing-company`。每轮原 14 源码 before/after SHA 同版，且全部匹配本轮修改前树；实际 terminal exit 均 a=0/b=0。顺序轮与已有公司轮 statuses 为 ok/skipped、business_diff={}；同时轮为 skipped/ok、business_diff=null，缺中间 snapshot，不能声称同时轮零业务差异。

原 code SHA 与 command/stdout/stderr/result/actual-terminal 的原路径和 SHA 全部记录于 `workspace/tmp/upload-material-unified-s2-owner-contract-sol-20261003-01/inherited-cli-audit.json`，旧票据本身由 protected 末核证明未改。core/protocol/publicFs 的旧 byte SHA 保留，当前合法逻辑等价性由上面的 AST 核验支持；不把旧 CLI 说成本新版执行。本轮没有机械重跑双 CLI 或宏矩阵：真实 CLI 传入 typed state，本项只改变非法静态输入边界。

## README 职责裁决

已读 dayu/fins/README.md 的 Agent 更新约束和现有材料状态合同，以及 tests/README.md 的运行/维护边界和材料 required 条件说明。本项仅内部非法类型错误定义、register 方法中文异常文档及同文件 owner 断言，不改变对外业务能力、分层关系、测试层级/运行方式/维护规则。现有“readonly None 仅免源条件，writer 登记要求完整状态”仍正确，因此不机械更新 Fins/tests README。根 README 和其它 README 不触发；全部既有 dirty README 保留。

## 首末身份与边界核验

冻结根为 `workspace/tmp/upload-material-unified-repair-20261002/s2-owner-contract-closeout-01/`。identity.json 对 input/protected/allowed 两份裁决的 manifest SHA 已首核实匹配；9568 input 和 9564 protected 首核均零漂移。末核再逐文件重算：input 仅四个 allowed files 变化，protected 零漂移，identity/manifests/两份裁决均未改。工作区 tracked/unignored 源码树相对初始树仅四个 allowed files 与新增本报告；自有 tmp 是唯一新增票据目录。HEAD/main/branch 不变，提交树保持相同；现有 dirty/canonical evidence/rootcontrol/旧报告未覆盖。

首末真实结果与 report SHA 在 `workspace/tmp/upload-material-unified-s2-owner-contract-sol-20261003-01/initial-audit.json`、`workspace/tmp/upload-material-unified-s2-owner-contract-sol-20261003-01/final-audit.json`、`final-audit-01/`；source/tree 前后全摘要、git status 与四文件 SHA 已保存。交付 machine index 为 `workspace/tmp/upload-material-unified-s2-owner-contract-sol-20261003-01/machine-index.json`，完整票据 SHA 索引为 `workspace/tmp/upload-material-unified-s2-owner-contract-sol-20261003-01/fileshash.json`。fileshash 排除自身避免自引用，其余目录叶文件和 machine index 均纳入；报告 SHA 单独记录，不制造自哈希。

## residual 与交还

T01 已修候选仍需总控最窄 delta 同版双复审及独立裁决；本轮不派发 reviewer，不修改 root 状态，不自行切 gate。主 fix 的已核审查及合法 CLI 按原源码 SHA 继承。S3/XBRL 与 UP-RR-T01 归后续批准 slice；Windows/可选 PDF 等平台延期归后续相应 owner；完整 upload_material CLI campaign/CI 与 registry 归统一 WU 完成后；Raw 可逆封装归 aggregate 收口。本轮不做上述工作、不重裁 UM、不新增字段/code/状态/兼容/fallback/宽比较，不做全仓 type hardening。

实现、验证、报告和末核交付后停止。未 commit/push/PR/merge，未建 branch/worktree/clone/detached，未动 main，未 reset/clean/stash，未派发子 Agent，未使用进程枚举/kill/超时重派，未读取 private 财报。
