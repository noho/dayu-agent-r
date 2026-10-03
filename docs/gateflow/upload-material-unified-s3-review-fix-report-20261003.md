RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol
CANARY=gpt-6-sol-31953a08

# S3 首轮 accepted findings 集中修复

本轮 label `upload-material-unified-s3-review-fix-sol-20261003-01`，仅执行既有 S3 fix，交付后由总控核收并同版双路 re-review；不代表 slice/gate pass。

首核 workspace/branch/HEAD/main 与正式 identity 一致；四份 frozen manifest SHA 与派发值一致，12128 输入及12122 protected 全部零漂移，票据为本轮 own tmp 的 `initial-integrity.json`。

## 修复记录

- US3-R01：Documents 生命周期 owner 先检查 valid，再访问真实 backend；无效输入不读取缺失属性、不宣称关闭。旧恒带 None 的 fixture 已替换为真实缺属性形状，并保留无效但已有 backend 的零卸载断言。
- US3-R02：与 R01 一并补 worker 五格合成控制流矩阵，真实结果类型注入 status/errors/export/成功/结果取得前异常；断言单次 XBRL dispatch、PDF 零调用、execution/serialization 分类、持有结果后释放一次。另有真实 Docling sniff/解析合成坏内容回归，断言 DocumentLoadError、valid=False、缺 backend、worker/父公开 execution 保留。合成矩阵不证明真实正例或内核隔离。
- US3-D01：只修根 README，管理员工作区外 taxonomy 源/清单/config 与请求生成快照、用户原件副本分开说明；未新增原件位置限制。

## Docs decision

已读根 README 读者约束；公开配置误述属于用户手册职责。tests README 只新增现有测试职责和证据边界说明，无文案镜像测试。未改变装配/分层/Fins 生产 owner，其它 README 不触发。

旧正例/安装/OS及关系边界仅按下文未变源确切 SHA 与原执行范围继承，不重跑。

## 最终状态与真实验证

| finding | fix 状态 | 证据与未完成项 |
| --- | --- | --- |
| US3-R01 | **部分修复** | 生产/同源回归已修复；真实 Docling 合成坏内容实证 XML_XBRL、DocumentLoadError、valid=False、缺 backend，worker/父投影保持 execution。必需的默认 CLI 内容 execution 实跑未到达解析：当前执行环境拒绝 sandbox_init，故不能关闭该验收缺口。 |
| US3-R02 | **已修复**，待总控核收/re-review | 五格矩阵和结果取得前异常均通过；status failure 与 success+errors 为 execution，export 为 serialization，持有有效 backend 的结果只释放一次，尚未取得结果不释放。矩阵为控制流证据，不冒 Arelle 正例。 |
| US3-D01 | **已修复**，待总控核收/re-review | 根 README 只改管理员源目录/config/清单、程序生成快照及用户原件副本的说明。 |

所有本轮路径均相对唯一 workspace。独占证据根记为 `workspace/tmp/upload-material-unified-s3-review-fix-sol-20261003-01/`（下表 command 目录均在该根）。每个 command 都有 `command.json`、`stdout`、`stderr`、`receipt.json`，receipt 保存实际 PID/wait/exit 与三者 SHA；`receipt-index.json` 再绑定 receipt SHA 和对应源清单 SHA。没有用末尾 echo/cat 的 0 替代验证命令退出。

| command 目录 | actual exit / actual wait | 实际结果 |
| --- | --- | --- |
| tests-final-v2 | 0 / true | 激活 `.venv` 后显式 standard-venv Python；82 passed，5 deselected，11.08s；包含既有取消/释放/IPC 合同。未配置外部 positive 资源，明确排除旧真实正例和四个需内核权限的旧负例，未把它们计为 pass。 |
| pyright-final-v2 | 0 / true | 激活 `.venv` 后 `python -m pyright`：0 errors、0 warnings、0 informations。 |
| own-tools-type | 0 / true | 本轮六份新临时采集/回读/复验/diff 脚本显式 pyright：0 errors、0 warnings。 |
| cli-r01-01 | **1 / true** | 默认 `python -m dayu.cli upload_material`；实际 stderr `sandbox initialization failed: Operation not permitted`；failure_code=`docling_converter_construction`，stored_files=0。**不是内容 execution 实测**。 |
| readback-01 | 0 / true | 只用 FsMaterialUploadStateRepository、FsSourceDocumentRepository、FsCompanyMetaRepository 公共 API：material missing、无 source_meta/publication identity、material_ids=[]、公司独立存在且名称正确。 |
| final-integrity-command | 0 / true | 四份 frozen manifest SHA、12122 protected、24 最终 scope 源、workspace/branch/HEAD/main 逐项匹配；相对输入只变白名单六项。 |
| incremental-diff-v2-command / patch-check | 0 / true | 六文件修前重建字节逐项等于 frozen input SHA，再产生 `repair-only.patch`；只读 `git apply --reverse --check` 通过。 |

`coverage-owner-v2.json`：唯一修改的生产文件 `dayu/documents/docling_runtime.py`，214/235 statements，**91.06382978723404%**；missing21，excluded21。未新增覆盖排除。最终 coverage/test 票据绑定 `source-final-v2.json`；首版 `source-final.json` 保留，唯一源差异是测试 DoclingDocument 导入路径类型纠正，生产 SHA 未变。CLI 票据绑定首版源清单，其所有生产文件与最终版逐项一致；并不因这一点把 construction 失败改称 execution。

本轮修复增量恰为六项：`dayu/documents/docling_runtime.py`、`tests/documents/test_docling_runtime.py`、`tests/fins/test_docling_process_converter.py`、`tests/fins/test_xbrl_controlled_upload_integration.py`、`README.md`、`tests/README.md`。源 SHA 完整保存在 `source-final-v2.json`（24 scope）及 `summary.json`（六项变更）。未改 interruptible_process、失败分类 owner、upstream、依赖/锁、跨平台实现、原件准入、control/ledger 或旧证据。

## 工具失败、恢复与影响

- pyright-final 首跑 actual1：新测试从 `docling_core.types.doc` 导入 DoclingDocument，触发 reportPrivateImportUsage。修为其公开定义模块 `docling_core.types.doc.document` 后，生成新源清单并以新目录重跑最终 tests/full type，均0；原双流及源清单保留。
- incremental-diff-command actual1：本轮逆变换工具给原文件末尾多加换行，SHA 校验按预期停止，未输出错误 patch，也未修改 source。原脚本/票据保留；新 build_diff_v2 取消该多余换行，六项 frozen-before SHA 全匹配后才输出 patch，实际0。
- 一次 apply_patch 因预期 typing 导入行不匹配而原子拒绝，无修改；随后实际读取导入行并按真实内容实施。完整工具轨迹保留该失败，不计 pass。
- 只读定位曾查询两个不存在的仓储/历史票据路径，rg 报 file-not-found；组合工具外0不作为内部 rg 成功证。后续从真实 `fs_company_meta_repository.py`、`repository_protocols.py` 及 frozen evidence-index 定位并读取，公共仓储读回实际0。无需改旧资源或 provider 重派。
- CLI 内核拒绝未恢复，属于必要证据 gap；不是 automatic approval review rejection，也没有尝试绕过生产策略/扩大读权。pyright 的新版本提示只记录 warning 原 stderr，未升级任何环境。

## 继承范围与 residual owner/destination

`unchanged-source-inheritance.json` 逐项绑定本轮 scope 中 **18 项未变文件**与 frozen input 精确相同 SHA；所有原环境/原件/taxonomy/旧票据也在12122 protected 首末核验中保持原字节。标准安装/依赖版本、原正例、原内核边界/取消、runtime-XSD allowed、FTP unknown、ENTITY/XInclude/PI not-attempted、取消模型未观察等仅保留原执行和根裁决范围。

Documents 生命周期 helper 本轮有变，**旧整链正例不是本轮最终源正例**；旧成功 backend 关闭观察保持历史事实。本轮有效 backend 恰一次卸载由 owner 计数及真实结果类型的合成矩阵验证，不冒新 Arelle model.isClosed 实测。不重跑正例安装、完整 OS matrix、668 回归或完整 CLI campaign。

- 当前阻塞 gap：R01 默认 CLI 到达真实内容解析并呈报 execution 的最终源票据。owner/destination：总控外层最小原生策略审批/执行与同版 re-review；当前材料 missing/company 独立只证明这次 construction 失败的真实状态，不能替代缺失 execution 票据。
- Linux/Windows/非3.11：assigned to later platform work，owner 平台部署/依赖与 Documents runtime，沿用户延期；rejected finding 不实现。
- 抽取准确性：tracked by existing upstream Docling #4437；特殊 XML/FTP/取消模型为既有有界技术 uncovered limits，归已有根裁决与后续技术验证，不新增解析器、admission 或质量阈值。
- aggregate/正式 PR review、完整 CLI CI/registry：分别由总控后续 gates 与 WU closeout 后独立阶段负责；本轮不推进。22 residual 保持原 owner/destination，不纳本轮。

供总控处理的最小重跑命令（**本轮未执行**）：在允许原生 sandbox_init 的外层，以同一最终源和既有标准解释器，使用新票据/新 base，保留本轮失败 run 不变。

```bash
source .venv/bin/activate
export PYTHONDONTWRITEBYTECODE=1
export DAYU_XBRL_CONFIG=/private/tmp/dayu-xbrl-s3-admin-qmid1407/config.json
export TMPDIR="$PWD/workspace/tmp/upload-material-unified-s3-review-fix-sol-20261003-01/"
python workspace/tmp/upload-material-unified-s3-review-fix-sol-20261003-01/collect-v2.py \
  workspace/tmp/upload-material-unified-s3-review-fix-sol-20261003-01/cli-r01-root02 \
  workspace/tmp/upload-material-unified-s3-implement-sol-20261003-01/standard-venv/bin/python \
  -m dayu.cli upload_material \
  --base "$PWD/workspace/tmp/upload-material-unified-s3-review-fix-sol-20261003-01/store-r01-root02" \
  --ticker MLAC --action auto --forms MATERIAL_OTHER \
  --material-name 'S3 R01 routed content failure' \
  --company-name 'Mountain Lake Acquisition Corp.' \
  --files "$PWD/workspace/tmp/upload-material-unified-s3-review-fix-sol-20261003-01/routed-bad.xml"
```

该命令 content failure 预期 CLI1，必须实际看 failure_code；之后针对新 base 用同三类公共仓储 API 回读，不能以路径存在/私有 JSON 推业务状态。不重用本轮 public_readback.py 的固定01 base 冒新回读。

## 最终身份及结构化交付

workspace `/Users/leo/workspace/dayu-agent-r`；branch `codex/upload-material-oracle`；HEAD/base `a514dea14c0ce66722da034502f3af54a54c3238`；main `fac32ecbff9bfe792b63ee9667c8697826b631f4`。初末 identity、四 manifest SHA、protected 均零漂移。本轮没有 stage/commit/push/PR/merge/branch/worktree/clone/detached，也没有派发子 Agent。

结构化交付为 own tmp `summary.json`，含 findings、changed paths、source hashes、receipt references、validation、residual 和最终身份。整体状态 **blocked-required-CLI-evidence**；源修复与其它验证交付完毕，到此停止，由总控核完整 actual event/tool trace、报告字节与证据后裁决，不能据本报告自行关闭 S3。
