RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-8898ad67

# upload_material 统一修复 WU：aggregate fix 报告

实际模型名未由本运行环境提供，记为 unknown；不以任务指定 provider 或 canary 推断模型。CANARY 逐字读取本轮指定文件。

## 身份、动机与授权边界

- label：`upload-material-unified-aggregate-fix-sol-20261003-01`；gate：aggregate deepreview 的集中 fix。
- 唯一 workspace：`/Users/leo/workspace/dayu-agent-r`；branch：`codex/upload-material-oracle`。
- HEAD：`ec54351e58e66cd5d00b009c862589b109064ade`；main：`fac32ecbff9bfe792b63ee9667c8697826b631f4`；初末身份一致。
- 唯一正式 accepted 清单为 UA-R01/R02/R03/UA-E01。已读 AGENTS.md、gateflow skill、findings register、DS/MiMo report 及两份 root audit，以 MiMo root audit 的最终裁决补足登记中的旧在途状态，不回写总控资料。
- 动机成立且范围为低风险收尾：材料真实准入抛共享异常，CLI 硬编码命令归属；runtime 常量只有定义无消费者；测试 root 引用历史 label；Raw EOF 影响 PR whitespace 检查。未重裁 user oracle、未新增 WU/slice、业务规则、parser、质量门槛或兼容逻辑。
- 本轮只写正式 10 项白名单与 own 目录；不派发子 Agent，不做 Git/GitHub 写入，不自行宣告 aggregate/WU/PR pass。

## Finding 最终状态与 owner

| Finding | 状态 | owner 与修复证据 |
| --- | --- | --- |
| UA-R01 | 已修复；待总控复审 | CLI 命令归属投影 owner：`dayu/cli/commands/fins.py` 使用 args.command_name 同时投影日志及 stderr。typed failure/message/exit1 与准入零业务写不变。真实 CLI 主入口 4 损坏 × auto/update/delete 共 12 例通过。 |
| UA-R02 | 已修复；待总控复审 | `dayu/fins/ingestion_runtime.py` 删除无消费者旧常量。共享 no-runner failure/status/双摘要 owner 不变，完整 runtime 测试包含 no-runner 终态回归。 |
| UA-R03 | 已修复；待总控复审 | 测试隔离 owner：缺身份用例改为 pytest tmp_path 独占根，保留两个 MISSING code，新增状态读取零调用与目录不存在断言，SEC/CN 共 4 例通过；不修改产品校验顺序。 |
| UA-E01 | 已修复；待总控复审 | 历史证据 owner：原 191 字节无损 base64 carrier、原 log 改 ASCII 引导、validation 与 manifest 两处链同步；解码 identity 与 before/frozen HEAD 全等。 |

## 精确变更路径与最终 SHA256

报告自身 SHA 位于 own summary.json，避免自引用摘要；其余九项如下。

| 路径 | SHA256 |
| --- | --- |
| `dayu/cli/commands/fins.py` | `0285f93d3ee26c5dcdd144a3f371dcf0d74ff5b1e591e348e9e7aec7e0fb6e64` |
| `dayu/fins/ingestion_runtime.py` | `1defbc52d20b8e21666af41c4730304bc449a75304c598aae811e8c05b887af8` |
| `tests/cli/test_fins_commands.py` | `b1772f5111699c3714feff4b062b0cc5a43c8541c1dfedd78a587781bee2d72d` |
| `tests/fins/test_fins_ingestion_runtime.py` | `4caacce453077494707924304897a051b0435f1677e9fc71a21bdf8063a88437` |
| `tests/fins/fixtures/sec_earnings_repair_v1/workpapers/final-pyright.log` | `31bfd34fccbe65a397b8875ac69cba184c920cd954578fd513a045006875f20e` |
| `tests/fins/fixtures/sec_earnings_repair_v1/workpapers/final-pyright.raw.json` | `7f89f136651ed7a5546a0c5811d331341e068abd7d369848dda45699fe8b73de` |
| `tests/fins/fixtures/sec_earnings_repair_v1/workpapers/validation.json` | `0fac23d924a4eed94d1bf2b3055681fe6f48e79602cc7bb1d90f5368b71b5034` |
| `tests/fins/fixtures/sec_earnings_repair_v1/change_manifest.json` | `5a3f8854d190b8d2c1f0d364e653ba31d5bea62915dd819e8a16c375eb248d3e` |
| `tests/README.md` | `78fa35da25e15f5b3433e85da9569983469110630cc11b51ce752d309d79c4b0` |

完整最终源清单：`workspace/tmp/upload-material-unified-aggregate-fix-sol-20261003-01/source-final-v2.json`，SHA `8b16119e01c413d869cf38a660ade0da5650ac4586a70530189abd002c1ca91d`。覆盖冻结 84 项 + Raw 四件 = 88 项；Raw 非生产证据。84 项内只有两生产/两测试变化，80 项字节不变（36 生产、40 测试、4 配置）。tests/README.md 不在该 84 项内，另由 input/白名单扫描记录。

## 本轮实际验证

先激活 `.venv`；测试使用既有 `workspace/tmp/upload-material-unified-s3-implement-sol-20261003-01/standard-venv/bin/python`，完整执行 `tests/cli/test_fins_commands.py` 与 `tests/fins/test_fins_ingestion_runtime.py` 的一次成功并集。使用既有 collect-v2.py 原字节副本，每项命令真实 child.wait、独立 stdout/stderr/command.json/receipt.json，不以 shell 末尾命令改写退出码。所有票据绑定本轮最终 source manifest。

- tests-union-02：actual_exit=0、671 passed、0 failed、0 skipped，3 个 edgartools 既有 deprecation warnings。JUnit 与 coverage 已实读 SHA/断言。
- CLI 12 个真实损坏材料反例先由真实 publication owner 建立材料，再损坏 meta/原件/Docling/manifest，走 cli_main.main 和实际 Service admission；固定材料前缀、安全文案、path-free/无 traceback、operator 归属、factory/direct/observation/job/batch 零调用、seeded 整树字节不变；不是 mock exception 镜像。
- 原 filing 真实损坏 6 例、I/O 1 例、构造 resolve 1 例全部通过，原行为断言未删除或弱化。缺身份 4 例和 no-runner 1 例均在本轮 JUnit 中实际通过。

| 修改生产文件 | 本轮行覆盖率 |
| --- | --- |
| `dayu/cli/commands/fins.py` | 82.44111% |
| `dayu/fins/ingestion_runtime.py` | 90.65868% |

- `.venv/bin/python -m pyright` 全量 actual_exit=0：0 errors、0 warnings、0 informations；原 stdout 的 pyright 版本更新提示保留，不升级依赖。
- `git diff --check main` actual_exit=0，检查 main 到当前工作树的完整已跟踪 PR 差异，包含当前 fix；没有用 main...HEAD 的旧提交检查冒充当前结果。新 carrier 的 no-index check 双流为空，actual_exit=1 为 no-index 文件新增差异语义，不冒称 Git 返回0；新载体与新报告另做逐行 whitespace 核验。
- 初扫 input 95 项全匹配、protected 9364 项全匹配；末扫 input 仅白名单内 8 项旧文件变化，protected 9364 项 0 drift；新增 carrier/report 在白名单内。冻结身份、四份授权文件 SHA 已与任务给定值核对。

## Raw 指针链与历史事实

- `final-pyright.before` 为原件 own 副本：191 bytes，SHA `70a0f3577f8953319fd286c94822becc2dd8c6ec2ba6d76e8bc67172b4e12691`；carrier decode == before == HEAD 原 log，原 EOF 空行保留，未 trim。
- `final-pyright.raw.json` 仅 encoding=base64、size=191、原 sha256、exact payload；无新增生产 decoder 或测试框架。
- `final-pyright.log` 是纯 ASCII 引导，明确 NOT historical stdout，旧报告经该引导可找到载体及解码 identity。
- change_manifest files[21] 指向载体实际 path/size/SHA，另记录引导实际 identity 与 decoded_original 原 identity。validation pyright/log 指向载体，明确 base64 解码语义与原 size/SHA；files[24] 同时更新 validation 的实际 size/SHA。
- manifest 总计仍为 26 entries；除 [21]/[24] 外其余 24 entries 逐字段等于冻结 HEAD；git_head、diff identity 与所有其它 manifest 字段不变。validation 所有原结果与其它字段保持。data_source_manifest 与财报 Raw 未变。
- 原字节/链核验结果：`workspace/tmp/upload-material-unified-aggregate-fix-sol-20261003-01/raw-evidence-verification.json`，SHA `b47fe11bc6c1461abb6a3703621b4a95a8a6c51d72b0f4e52b236b2cf5ceec7f`；fresh owner/Test/JUnit 核验：`workspace/tmp/upload-material-unified-aggregate-fix-sol-20261003-01/validation-readback.json`，SHA `598c47e53a469e8cff86d590b9b3b3849ffa4cc40dbd2b589beb8382ba1c4e0e`。

## 票据清单

每个目录均含独立 command.json/stdout/stderr/receipt.json；全部实际 wait=True。

| 目录（own 下） | actual_exit | receipt SHA256 |
| --- | --- | --- |
| `tests-union-01` | 2 | `0dcd047355b1a02dafa40cdefd4a916b33af5d2fa318d39c3bd522522bfe862b` |
| `numpy-import-probe-01` | 0 | `32e8491bef30b75cdc373e32541c6539950d7fda07d5ef0a1f7fccd2ee6dfaa0` |
| `tests-union-02` | 0 | `fd1ef93efec22826dacb8b2edc48aedfb16d399ad091ecd82e46bc2762fa5e07` |
| `pyright-01` | 0 | `7c77e0c912cba0520800fd020e9359a48abb3bff8d913069ba0ba77133dc9495` |
| `raw-readback-01` | 0 | `5466adbc0272dfe69954163fd78cdeba6ab5350813fade317d1b3c112485d04d` |
| `validation-readback-01` | 1 | `18e8b360d4c92e45ccdc8b2e126736daabb4088355a1e3fa85adc90f96396fc9` |
| `validation-readback-02` | 0 | `ba828ee159043ae4f422b775d676b8cab63297f1e3f43a9541a8b84a97bbb479` |
| `whole-pr-diffcheck-01` | 0 | `2feb34fc5269fbecf63c5ee455c4fa21babc5a73eedb894e30095d151e690d30` |
| `carrier-diffcheck-01` | 1 | `36181d86161afd65dd205eefc493efa4130aa036eecc8c070c8548157249e59c` |
| `end-scan-01` | 0 | `2d9523f0c2b02312346dfe977d1b7fd3939f402b19b19812974c4cbdce1b3003` |

JUnit：`workspace/tmp/upload-material-unified-aggregate-fix-sol-20261003-01/junit-02.xml` SHA `33c94fde41f4927117d5ae025b5dab7cea35f3a39e0b9ba7b66aab6b05bd99ca`；coverage：`workspace/tmp/upload-material-unified-aggregate-fix-sol-20261003-01/coverage-02.json` SHA `4064bcf61dc435d5049f953539b2b7663d9d0272fdeb7e65d66006ded826dec5`。

## README decision 与失败恢复

- tests/README.md 只补当前测试职责内的材料前置 CLI 覆盖事实。根 README 的最终用户边界已读：修正命令归属不改变入口、参数、工作区布局或排障操作，无需改正文。Fins README 的开发者稳定合同边界已读：删除死常量无能力/合同改变，无需更新；没有白名单外产品修改。
- tests-union-01 actual_exit=2，收集时报 NumPy cannot load module more than once per process，未执行测试；失败双流、JUnit 原件与票据保留。numpy-import-probe-01 同解释器单独导入 actual_exit=0。恢复仅将 dotted module coverage 选择改为既有 --cov=dayu，源未变，tests-union-02 完整并集通过。直接证据只支持该命令配置变化后的恢复，不夸称已定位 NumPy 内部缺陷。
- validation-readback-01 actual_exit=1：本轮回读断言误将 tests/README.md 计入冻结 84 项。该 84 项实际为38生产+42测试+4配置，变化仅4项；在新 validation-readback-02 修正清单预期后通过，不改源与旧票据。
- 初次只读探索有输出截断及不存在辅助/conftest 路径的 rg/sed 诊断，后续定点读取现存实现恢复；不以复合命令外层0冒称全部探索子查询成功。产品测试/type/raw/diffcheck 的正式命令均单独采集。
- carrier-diffcheck-01 的 actual1/空双流是 no-index 新文件差异返回，保原 receipt；本轮 tracked whole-PR check actual0 与新文件 whitespace 核验分别报告。

## 继承证据与分类 residual

`workspace/tmp/upload-material-unified-aggregate-fix-sol-20261003-01/inherited-evidence.json`（SHA `eae44def618979fec52b2da537386faa16a6dec8c8352f2acdf0cec003f712e8`）核原 e47 manifest 精确等于本轮冻结 initial_source_hashes、原成功并集 receipt 双流、JUnit/coverage SHA 与真实 XBRL 五 case 均通过。仅精确同版未改 owner/test 证据继承；本轮变化两生产/两测试使用 fresh 671-case 与 full type 票据，旧 e47 不是当前 fix 的测试。未重跑旧全42文件、安装、外部五case或OS/内核探针；macOS既有范围不得外推跨平台。

- fixed in current slice：UA-R01/R02/R03/UA-E01 实现与本轮验证已完成，await root focused re-review。owner/destination：CLI/runtime/test/evidence owner 与总控；同一 aggregate gate。
- fixed in current slice：DS ZIP 测试尾与架构 README、MiMo 31 tests 与 6 docs 的原审覆盖缺口仍由同版复审补证，本 worker 不声明 covered。owner/destination：总控与两路 focused reviewer；本 gate 已授权取证队列。
- assigned to later work unit：Linux/Windows 部署、Python 解释器升级、私有 backend/依赖 minor 升级；本轮 macOS/Python3.11 边界。owner/destination：平台部署、Documents runtime/集成维护者。
- assigned to later work unit：完整 upload_material CLI CI/oracle/registry 与既有 22 项全局/下载/filing/processed 残余队列。owner/destination：总控后续独立阶段及各既定语义 owner。
- tracked by existing issue：typed XBRL 抽取质量，Docling #4437；无本地 parser/质量门槛。owner/destination：Docling 上游与 Documents 集成维护者。
- assigned to later work unit：writer 树拷贝/每次 otool 成本及 C 级 list.append 绕过仅在真实规模或对抗需求出现时评估；当前 owner 机制不改。owner/destination：Fins storage、Documents runtime、immutable storage contract。
- assigned to later work unit：完整 PR 旧代码与历史生成报告全文由后续正式 PR review；旧同版 OS/XBRL 票据仅精确继承，不宣称本轮重跑。owner/destination：总控与后续正式 PR reviewer。

四项实现与本轮验证完成，停止交付总控核源码/全轨迹及同版双复审；本报告不构成 WU/PR pass，不更新 root 控制资料或推进 gate。
