RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-fea5bb90

# PR197 F3-S1 输入路径链接环必要 fix 交付

## 当前状态与范围

label：`pr197-f3-s1-input-loop-fix-sol-20261001-03`。design_doc：N/A。provider 是本次授权任务路由；没有可核验的本轮实际 model metadata，故为 unknown，不由 canary 或旧轮次推断。以上 canary 来自本轮 `sub-agents.Fnnmua/canary.txt` 的真实工具读取，内容逐字保留。

本轮交付 **修复实现与验证证据**，F3-CR1-A1 的最终修复裁决等待 root 核收及同版 MiMo/Kimi re-review；不宣称 code review 或 slice 通过。完成本报告后停止，不派审、不推进后续 gate、无 commit/push/PR/merge 操作。

唯一 workspace 为 `/Users/leo/workspace/dayu-agent-r`，唯一分支 `codex/upload-material-oracle`。首检 HEAD `8328699a0f124c11c1e9db0e489e0337fe394f73`，末检 HEAD `8328699a0f124c11c1e9db0e489e0337fe394f73`；main `fac32ecbff9bfe792b63ee9667c8697826b631f4`。原件和新证据全部保持在各自路径，没有新分支或工作树。

已读 AGENTS、Gateflow skill、完整 739 行 accepted plan（SHA `2983efa4326cc799565fab27a350d79bf74b40d540beb0143b4dfa90f181a421`）、amendment 最终裁决、输入环裁决、双路 code review 裁决、Sol routing recovery receipt，以及 root 四 CLI 双流 `workspace/tmp/pr197-controller-collection-20261001/f3-out-root-loop-probe/commands.json`。原 -01/-02 的 routing timeout/turn.failed 与只读健康测量保持原历史状态，没有把旧失败回写通过，也没有进行新的 routing 重试。

新证据目录唯一为 `workspace/tmp/pr197-f3-s1-input-loop-fix-sol-20261001-03/`；唯一新增正式报告为本文。F6 plan 及总控 queue/handoff 四个非冻结文档的并发改动只记入 `current-identity.json`，不当作冻结身份失败，本轮未修改这些文件。F4 aggregate 已通过、最终 PR review 待做的上游状态保持。

## 直接根因、owner 与实际五文件变化

问题成立，严重性沿原低等级：Python 3.11 的输入路径 `Path.resolve()` 遇真链接环抛 RuntimeError；root 的四个 out 反例实际 exit1/英文 traceback，而四 main 的既有中文输入拒绝合同只接收 OSError/ValueError。它属于开发分析输入解析事实，不是财报分析算法失败。

唯一异常语义 owner 是 `utils/analysis_sample_inputs.py` 的解析边界。新增朴素严格类型接口 `resolve_analysis_input_path(path: Path, input_name: str) -> Path`：仅将此次 `path.resolve(strict=False)` 的 RuntimeError 转为包含中文输入名称和原路径的具名 ValueError，使用 `raise ... from exc` 保留原因链；其它 OSError 原样传播。helper 的中文 docstring 自足列出参数、返回值和异常。

| 文件 | 本轮必要变化 |
| --- | --- |
| `utils/analysis_sample_inputs.py` | 新增唯一 resolve helper；root、manifest、清单 PDF 及公共产物身份解析复用它，移除原公共身份函数的重复 RuntimeError 转换。PDF 外层继续补 1-based 记录上下文及 ValueError cause。 |
| `utils/build_semantic_digests.py` | 显式导入 helper，仅替换输入 try 内的 out.resolve。 |
| `utils/docling_schema_regression.py` | 同上，保留原 Path(args.out) 构造。 |
| `utils/verify_missing_tokens.py` | 同上，替换 data_root 的输入 resolve。 |
| `utils/ab_ocr_compare.py` | 同上，保留原 Path(args.out) 构造。 |

四 main 的 `except (OSError, ValueError) -> parser.error` 不变；没有加入 RuntimeError 宽 catch，执行后 mkdir 与分析业务异常仍在原 owner 和原传播路径。真实环 owner 链为 root/manifest/out 的 ValueError → 原 RuntimeError；record 为具名记录 ValueError → 解析 ValueError → 原 RuntimeError。旧 C02 公共身份直接原因链断言同样通过。

未新增参数、配置框架、兼容入口、类型 ignore、lazy import、弱签名或生产层变更。ASCII 保全、现存 samefile、原算法/default/worker/cache/selected-only/统计 quirk/C01/C02 产物规则保持。

## 实际验证与完整计数

所有矩阵先激活 `.venv`，仅在本轮目录自建合成输入，显式隔离 --out；没有私人语料、真实 PDF/OCR、外网调用。真实 CLI 子进程仍以 `python -m utils.<模块>` 执行，未 mock main 或 parser。

| 验证 | 最终实际结果 | 可核证据（均相对本轮证据目录） |
| --- | --- | --- |
| 原 S1 完整 harness | exit0，504 assertions / 175 subprocess commands | `original-matrix.stdout/.stderr/.exit`、`commands.json`、`assertions.json` |
| 原 C01/C02 完整矩阵 | run2 exit0，405 assertions / 88 actual module CLI commands | `collision-matrix-run2.stdout/.stderr/.exit`、`collision-commands.json`、`collision-assertions.json`、`collision-preservation.json` |
| 新 root/manifest/record/out 真环与正例 | exit0，189 assertions / 24 actual CLI commands | `loop-matrix.stdout/.stderr/.exit`、`loop-commands.json`、`loop-assertions.json`、`loop-preservation.json` |
| 汇总与源码保全 audit | exit0，1098 assertions / 287 commands；旧完整矩阵仍为909/263 | `evidence-audit.stdout/.stderr/.exit`、`counts.json` |
| 项目默认全量 pyright | exit0，filesAnalyzed=783，0 errors/0 warnings | `default-full-pyright.json/.stderr/.exit` |
| 本轮显式临时类型检查 | exit0，filesAnalyzed=11，0 errors/0 warnings | `temporary-types-run1.json/.stderr/.exit`、本轮 `pyrightconfig.json`、`temporary-type-file-inventory.json` |
| 源码 whitespace/diff | git diff --check exit0；五文件 no-index --check 各 exit1、双流空，预期表示存在差异 | `source-diff-check.*`、`fix-source-diff-checks.json`、`fix-source-check-0..4.*` |

旧 harness/support 共四文件复制到本 label：两份 harness 仅把 subprocess PYTHONPATH 的证据目录引用加入本轮 `cli_guard`；全部原断言、输入 bytes、算法对照不变，`frozen_numeric.py` 和历史 `build_semantic_digests.py` 对照原件逐字复制。完整重算证明这一限域替换，不削弱原175+88命令或504+405断言。

`cli_guard/sitecustomize.py` 对所有矩阵真实 CLI 明确拦截转换，启动 marker 在每条命令 stderr 中实际存在，检查没有被 Python 静默 startup 失败绕过。新16个负例另拦截 Path 业务字节/文本读取、mkdir/write、ProcessPool/ThreadPool、SequenceMatcher；只准真实读取当前 manifest。任何夹具误进入业务阶段都会失败，不能尝试 Docling。

新负例逐个先构造**同目录两向相对 basename** 链接，核对链接文本，并对双方真实 resolve 验证 RuntimeError，随后才执行四模块 CLI。16条均实际中文输入拒绝 exit2、具名角色/记录/路径、stdout 空、无 Traceback、sentinel 未触发。每项前后 inode/device/mode/link/bytes SHA 与完整 base64 bytes 一致；合成输入和缓存产物留在 `loop-fixtures/` 可复核，没有新业务读写。其余8条是四入口的有效 relative 路径及合法 root/manifest/out symlink 正例，全部 exit0。

另在真实 owner 验证 cause 链与 resolve PermissionError 原实例传播；四真实 main 的执行阶段 RuntimeError 注入分别位于 schema/digest 的 mkdir、verify worker、A/B 分析读取，均以原实例传播，不变成输入 exit2。注入只用于明确边界证明，不冒称实际权限异常/业务故障实跑。对应具名断言在 `loop-assertions.json`。

完整旧矩阵仍涵盖 Path worker 路由、实际 ProcessPool 参数可序列化验证、同签名转换 stub cache miss、selected-only、缓存错误/退出 quirk、C01/C02 碰撞与字节/链接保全、已观察卷的物理 Unicode 别名及合法窄规则正例。合成文档/stub 验证不构成真实转换 CI。

每条命令独立 stdout/stderr/exit 在 `original-command-streams/`、`collision-command-streams/`、`loop-command-streams/`，完整命令与 cwd 仍在三个 commands JSON。所有内层退出均逐项等于原 expected_exit：原矩阵22个0/3个1/150个2，C01/C02矩阵19个0/69个2，新矩阵8个0/16个2。最终287命令中49个0、3个1、235个2；这些受预期断言约束的非零不伪装成每条CLI0，harness outer0 也未掩盖内层退出。

## 类型、算法同源与原件保全

临时配置使用本 label 下相对 include、exclude=[]，Python 3.11、原项目默认规则，未另开 strict。实际11项是六个验证脚本 `acceptance.py`、`collision_acceptance.py`、`frozen_numeric.py`、`loop_acceptance.py`、`evidence_audit.py`、`cli_guard/sitecustomize.py` 加五个 utils。清单和本次文件 SHA 在 `temporary-type-file-inventory.json`；历史 source snapshot 只被 AST 读取，不是可执行验证脚本，保持原 bytes。没有修改 repo config、依赖、删除检验文件或用 cast/ignore/suppress 掩错。两种 pyright 实际版本均1.1.409，独立 `pyright-version.*` / `python-pyright-version.*` exit0；原工具提示有新版，未升级。

首检39 current +39 originals 全匹配；末检39 originals +34 readonly 全匹配，允许五源码发生上述精确增量。freeze 与 originals 原路径保全。`initial-preservation.json`、`final-preservation.json` 是逐文件核对；`source-deltas.diff` 是相对修复前快照的实际增量。`algorithm-default-audit.json` 重建完整期望源码，仅允许 helper 插入和具名 resolve/import 替换，再逐字节及完整模块 AST 相等；因此其它算法、默认数值/路径、worker/缓存、C01/C02 ASCII/samefile 与产物布局均同源保全。新增 helper 本身不是旧算法。

| 最终源码 | SHA256 |
| --- | --- |
| `utils/analysis_sample_inputs.py` | `286a590bc8e136de6ccecf2ec5bc3b056a7e16900208df0e54b0ca1b83009621` |
| `utils/build_semantic_digests.py` | `9b5da92e8713cebdf5b2d3d3a47ee03d19792c6e5d22759784874b18d11a681e` |
| `utils/docling_schema_regression.py` | `77481e460c2cc17586b1997921c8b450e42c48055eea7277e49e4592e4b47878` |
| `utils/verify_missing_tokens.py` | `288d1b51dabaac2db41bc2f8f9f5f68afe9a3e8a0052e27df219adbeeeff8197` |
| `utils/ab_ocr_compare.py` | `22822fff0529ed6a6bc7c9e58e995aee252a453182b3874ef2ee0a893444703f` |

## 全部非零与恢复

- 本轮 collision run1 真实 exit1：它读取原完整 harness 产物 `assertions.json`，而我错误地在该依赖尚未生成时并发启动。22条已执行内层命令的实际结果和中间保全证据留在 `collision-run1-failed-originals/`；原 `collision-matrix.stdout/.stderr/.exit` 仍保存首轮 FileNotFoundError traceback/exit1，没有回写通过。失败原件逐文件 SHA 在 `failed-originals-sha256.json`。原完整矩阵504/175真实 exit0后，以未改断言的相同 copied harness 顺序重跑 run2，最终405/88真实 exit0。源码没有为该时序错误修改。
- 一次进度查询 tail 成功，但进程尚未结束时 cat run2 的终态 `.exit` 文件不存在，组合 command exit1；这是状态查询缺口。后续实际托管 session61405 终态 exit0及独立 `.exit=0` 已核收，记录于 `failure-recovery.json`，不当作矩阵失败或已完成证明。
- 五份 no-index whitespace 检查 exit1均为预期源码差异，stdout/stderr全空；普通 diff --check exit0。所有矩阵预期内层非零已按上述完整counts保留，其中旧3个exit1为schema缓存错误及verify/A-B内容KeyError行为保持。
- 其它已执行的本轮矩阵、默认/临时类型、版本、源码audit和证据audit没有非预期非零。新矩阵全部24CLI及其 guard 均完成，不存在 wrapper0 包裹未恢复内层失败。本轮没有 routing/认证重试；旧服务故障原件未触碰。

## README 职责

已读根 README 的 Agent更新约束：面向最终用户的安装、初始化、dayu-cli 财报/会话操作。本次仅修未安装的 utils 开发分析输入解析，不改变产品用户工作流或分层装配，判定不属于根 README 职责。不改 README、dayu/、tests/，因此其它包 README 无触发；utils 按 AGENTS 永久 pytest/coverage 豁免，本轮用完整临时验收满足必要验证，没有新增永久镜像测试。

## 残余、owner、destination 与停止

| 项目 | 分类及准确 owner / destination |
| --- | --- |
| F3-CR1-A1 输入环 | fixed in current slice 的作者实现/证据候选；owner为共享输入解析边界；destination为root核收→同版MiMo/Kimi re-review，最终状态由root裁决。 |
| 尚未创建的非ASCII或未证明同一父目录的文件系统别名 | requiring new issue or explicit user decision；owner为分析产物命名/文件系统身份规则；destination为独立Unicode/身份goal，由root/用户决定；本轮没有Unicode禁令、casefold或写盘身份探针。 |
| 预检后外部换链/输入与并发事务 | requiring new issue or explicit user decision；owner为各producer执行期输入/输出一致性；destination为root另定事务/并发goal，保持原运行期不换输入的假设。 |
| 执行后mkdir及目录写I/O（含既有dangling-out问题） | requiring new issue or explicit user decision；owner为各入口执行期目录/产物写入；destination为原open question及root独立裁决，不进入此次输入resolve合同。 |
| 同stem跨运行缓存来源与失败结果复用 | requiring new issue or explicit user decision；owner为schema/digest/verify各自缓存producer；destination为独立缓存来源/retry goal，原规则和help保持。 |
| selected-only diagnose/parity后果及schema failed_stems等统计quirk | 原计划披露/保持；owner为相应汇总及consumer；destination为原计划操作边界，若改consumer/统计则root另定goal。 |
| 历史公开locator、真实OCR/性能/语料未覆盖 | requiring new issue or explicit user decision；owner为用户/root的历史处置和真实验证授权；destination为既有计划风险表及独立授权，没有以合成stub结果替代。 |
| F4/F5/F6/F7及其它已裁修复 | assigned to later work unit；owner/root与各既有WU；destination为原修复队列，F4 aggregate已通过、最终PRreview仍待做，F6本轮计划fix与这五源码不重叠。 |
| 用户整体upload_material目标 | owner为root总控及相应真实CLI CI/oracle/scenarios合同；destination为全部已裁修复后真实CLI CI，再确定oracle/scenarios；本次临时验收不构成该终点，不以registry ready宣称upload_material通过。 |

下一入口仅为 root 核收本报告与同版五源码，再按其授权进行 MiMo/Kimi re-review。本 Agent 交付后停止。
