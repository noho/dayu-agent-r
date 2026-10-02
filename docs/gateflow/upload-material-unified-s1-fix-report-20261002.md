RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-0de5ca51

# S1 集中 code-review fix 报告

任务 label：`upload-material-unified-s1-fix-sol-20261002-01`。唯一 workspace：`/Users/leo/workspace/dayu-agent-r`。本次仅集中修复 root accepted 的 US1-R01 / US1-R02；作者状态 **已修复，验证完成，待 root 冻结同版 MiMo / ds-flash re-review**。未赋 gate accepted，未推进 S2/S3。实际模型标识未由本轮运行时暴露，记 unknown；不以指定角色、路由、canary 推断模型。

## 输入、授权与保全

已读 AGENTS.md、gateflow SKILL 的 implementation/review/fix 规则、accepted 计划、S1 实施报告、root code-review adjudication 和 fix-owner addendum。当前授权优先于 skill 自动推进/commit 规则；本任务止于作者修复交付。

| 核查 | 首核与末核 |
| --- | --- |
| branch | `codex/upload-material-oracle` |
| HEAD | `6c49f818efd5a11b4dbd91d9a44f3bcfb2c01e58` |
| main | `fac32ecbff9bfe792b63ee9667c8697826b631f4` |
| accepted plan SHA256 | `c99c35adba919a8baf371b0142e0ab1abf256a951e89b2fc15e8a2d38988e8ea` |
| fix input manifest SHA256 | `726e15ac5fe70aaebfed56d2dce26876d14de6ffd69d8a249be018ecf25c57d3` |

唯一写白名单为 `workspace/tmp/upload-material-unified-repair-20261002/concentrated-s1-fix-01/allowed-files.json` 的 9 件，另仅新增本文和独占技术根 `workspace/tmp/upload-material-unified-s1-fix-sol-20261002-01/`（下文 E）。9,269 件首核逐 hash 零漂移；末核仅 9 件白名单变化，9,260 件 protected 零漂移。原作者 root 选定 252 件专项证据全部 hash 相同，旧 validation index 的 27 轮及其失败票据保留；原实施报告、两路 review artifacts、root 计划/控制/裁决、旧 Raw/fixture/依赖/config 未改。

`E/initial-binding-check.json`、`initial-owned-sha256.json`、`oldsource/`、`initial-worktree.diff` 保存修前证据；`final-input-sha256.json`、`final-owned-sha256.json`、`finalsource/`、`end-verification.json`、`old-author-evidence-check.json` 保存末核。原 S1 tracked 完整 diff 保留在 `initial-worktree.diff`，当前完整 diff 为 `final-worktree.diff`，本次增量为 `final-fix-only.diff`；原三个 untracked S1 源码/测试由冻结清单保护，未改。staged 为空；未 branch/worktree/clone/detach/commit/stage/push/PR/merge/approve/外发/派发子 Agent。

## findings 与唯一 owner

| finding | 作者最终状态 | 修复与证据 |
| --- | --- | --- |
| US1-R01（含 DS-F2 / MiMo-F1 重复项） | 已修复，待同版复审 | 按生产 owner 真实行为修 docstrings 与根 README；六个生产文件移除 docstring 后 AST 与修前完全一致。 |
| US1-R02（DS-F1） | 已修复，待同版复审 | 仅 `_render_posix_script` 为再生成注释每个 LF 物理行加 `# `，10 条新增 owner/真实 CLI 用例全部通过。 |
| US1-T01 | 既有已修，保留回归 | 未重裁；原 tool/raw 路径及组合首错测试参与本次最终 26 模块回归。 |
| DS-F3 / MiMo-F2、DS-OQ1/OQ2 | 保持 root 原裁决 | 不改 duplicate import / `__all__`、hint、auto pipeline_action；不扩 public API。 |

动机由直接源码成立：runtime 的输出 document_id 文案误写成输入一致性断言；POSIX 再生成文本使用 `shlex.join(raw argv)` 却仅给首行注释前缀，合法 raw form 的 LF 使后续文本逃出注释。修在文档对应 owner 和脚本 renderer，无需更改材料合法性或业务 contract。

R01 具体修订：

- ingestion runtime：下载进度、上传 pipeline result、result summary、direct 文档标签和 progress helper 的 document_id 均描述实际业务 ID；输入 material request 仍保一致性断言。`_upload_request_document_id` 明确 material 返回已生成 identity ID，filing 返回 request.document_id，删除不存在的 ValueError 越界承诺。
- upload tools：`_validate_upload_file_path` 仅检查已存在普通文件，不把空内容写成参数拒绝。
- asset plan：constructor/validate/filing_original_storage_name 为不展开、不 resolve 的纯校验/计算；删除错误 OSError 解析承诺。
- Docling prepare：两 kind 的 empty / conversion failure 都是 typed content failure；准确区别 filing 路径规范化、文件状态/读取/仓储操作与 material pure plan 校验。
- storage：`get_primary_file`、其直接 unguarded owner、`get_primary_source` 补 material strict primary 缺字段 KeyError 文档。
- CLI `_single_batch_material_form` 明确保 raw 候选、逐项判空后才判多个；对应原文传播测试 doc 同步。根 README 明确 `--files` 符号链接循环 exit1，`--primary` 解析失败 usage exit2。

`E/final-r01-behavior-ast-check.json` 六项全部 true；文档修订未改真实行为或接口。diff 复核发现一次字符串替换误触相邻 `_single_optional_form` 的 docstring，已恢复首字节，最终该 helper 零增量。

R02 使用对已渲染再生成注释的 LF 替换，保 CR 原字符；普通单行脚本文本字节完全保持。命令 body 原 `shlex.join(command)` 与 raw argv 均未改；不在 batch strip 补偿、不加 parser/黑名单/换行业务拒绝、不改 Windows 既有字符约束。新增测试全部在原 `tests/cli/test_upload_filings_from_command.py`：

- 1 条普通 single-line 固定字节 oracle。
- 3 条真实 sh：LF/CRLF/CR 再生成多行含引号、touch/command substitution、首尾空行；sh-n0，注释无执行效果；独占技术 recorder 把 multiline fixed/appended argv 编为原始字节 hex 后 exact roundtrip。
- 6 条真实 CLI：form 首/尾 LF、CRLF、双边空行均生成 exit0，sh-n0；撤销注释前缀后 raw 原文仍在，命令 form 为身份 owner 唯一规范值 EARNINGS_PRESENTATION。这些新增 CLI 用例只生成脚本，不执行真实上传或 PDF 转换。

新增技术探针共 9 个唯一目录、18 个真实 child exit 均 0、93 个技术文件 hash，见 `E/new-technical-probe-index-02.json`；argv/脚本/recorder 输出/独立 stdout/stderr/exit 保存在 `E/broad-01-tmp/` 对应用例目录。既有套件的真实上传与取消回归照常执行。

## 实际验证、命令与失败恢复

每轮均先 `source .venv/bin/activate`。环境为本 workspace `.venv/bin/python` / Python 3.11.15 / macOS arm64，`dayu.__file__` 指向本 workspace，见 `E/validation-environment.json`。pytest 每轮独占 COVERAGE_FILE、basetemp、JUnit、coverage JSON、双流、actual child exit；`-p no:cacheprovider`，显式 `-o "addopts=-m 'not stress'"` 保原默认 stress 排除语义。未写 root `.coverage` / pytestcache，未安装依赖或压制 type errors。

| run | actual child exit | 结果 |
| --- | --- | --- |
| owner-01 | 0 | 551 passed / 2 skipped / 3 warnings，44.26s；6 个受影响 owner modules。 |
| pyright-01 | 0 | 全量 0 errors / 0 warnings / 0 informations。 |
| pyright-02 | 0 | 最终源码全量 0 errors / 0 warnings / 0 informations。 |
| broad-01 | 0 | 最终 2175 passed / 3 skipped / 3 warnings，163.13s；一次最终宽回归。 |
| artifact-index-02 | 0 | 后处理恢复：9 个唯一探针目录 / 18 actual exits0 / 93 hashes。 |
| helper-pyright-01 | 0 | 两个自有技术脚本显式 pyright，0 errors / 0 warnings / 0 informations。 |
| diffcheck-01 | 0 | 本次白名单 worktree diff check；不冒全 PR 历史 Raw EOF 检查通过。 |

真实 argv/cwd/env 允许摘要、当次源码 SHA、独立双流 hash 和 actual exit 在 `E/command-index.json`、`validation-index.json` 及每轮 `<run>.command.json/.stdout/.stderr/.exit/.receipt.json`。启动命令为 `python E/run_validation.py <run>`；表中的 full pyright 无文件筛选，技术脚本检查单列不替代 full。pyright-02 与 broad-01 捕获的 9 件源码 SHA 和末核完全一致。

broad-01 的 26 个模块逐项读取原 `workspace/tmp/upload-material-unified-s1-implement-sol-20261002-01/pytest-16.command.json` 的实际 argv，保持原模块和顺序，仅换独占输出位置并明确 addopts；新 renderer 用例所在模块原已包含。没有采用旧 validation-index 错误 command 描述，没有 append 旧 campaign coverage 冒当前证据。

本次 pytest/type 检查无非零；唯一非零为初次后处理索引工具（chunk `e8e046` actual exit1）：目录前缀未匹配 pytest 截短的 `test_posix_multiline_regenerat0/1/2`，又跟随 `current` symlink 重复计入一份 CLI，误收14张 exit 而期望18。coverage 和 JUnit 已正确落盘，该断言不影响通过的测试/生产源码。错误票据 `E/artifact-index-01.failure.json` 如实注明该 inline 工具原输出仅由运行轨迹保 combined 流，未伪造独立双流；`E/new-technical-probe-index.json` 为这次失败的 partial/invalid 索引，不能作为成功证据。恢复只修自有索引 locator 并排除 symlink，使用新 `artifact-index-02` 的真实命令/双流/exit 与新成功文件，未重跑宽 suite 或覆盖失败记录。

pytest 三个 warnings 是既有 edgartools deprecation；pyright 自带新版本提示为非错误，未升级依赖。既有真实内容失败 CLI 子进程的 expected exit1、SIGINT 的 expected exit130 是通过用例的预期业务结果，不冒本次 pytest 非零或未知失败。

## 最终逐生产文件覆盖率

全部来自本轮一次最终 `E/coverage-broad-01.json`，SHA256 `7c32827451e750f56dfc2cf734d1eb7c36071aafb5244ffad341169cd6553030`；结构化读取为 `E/final-production-coverage.json`。原 S1 18 件加 renderer 1 件全部 >=80%；不以全包总覆盖率替代逐文件。

| 生产文件 | covered / statements | coverage |
| --- | --- | --- |
| `dayu/fins/pipelines/docling_upload_service.py` | 548 / 605 | 90.58% |
| `dayu/fins/pipelines/sec_upload_workflow.py` | 162 / 171 | 94.74% |
| `dayu/fins/pipelines/sec_pipeline.py` | 417 / 476 | 87.61% |
| `dayu/fins/pipelines/cn_pipeline.py` | 438 / 463 | 94.60% |
| `dayu/fins/ingestion_runtime.py` | 2213 / 2423 | 91.33% |
| `dayu/fins/upload_asset_plan.py` | 240 / 268 | 89.55% |
| `dayu/fins/upload_usage_contract.py` | 131 / 141 | 92.91% |
| `dayu/fins/upload_failure.py` | 156 / 162 | 96.30% |
| `dayu/fins/upload_format_contract.py` | 160 / 172 | 93.02% |
| `dayu/fins/upload_batch.py` | 303 / 317 | 95.58% |
| `dayu/fins/domain/document_models.py` | 425 / 449 | 94.65% |
| `dayu/fins/storage/source_meta_contract.py` | 19 / 19 | 100.00% |
| `dayu/fins/storage/source_manifest_contract.py` | 6 / 6 | 100.00% |
| `dayu/fins/storage/_fs_source_document_core.py` | 457 / 531 | 86.06% |
| `dayu/fins/storage/_fs_source_integrity.py` | 518 / 589 | 87.95% |
| `dayu/cli/arg_parsing.py` | 335 / 346 | 96.82% |
| `dayu/cli/commands/fins.py` | 413 / 466 | 88.63% |
| `dayu/fins/tools/upload_tools.py` | 132 / 139 | 94.96% |
| `dayu/cli/upload_script.py` | 141 / 151 | 93.38% |

## skip 与 README 职责

最终 3 个 skip 的原名和真实理由来自 `E/broad-01.junit.xml`，结构化见 `E/final-junit-index.json`：

- `tests.fins.test_docling_upload_service_integration.test_real_docling_upload_service_conversion_when_enabled`：设置 DAYU_RUN_DOCLING_UPLOAD_INTEGRATION=1 后运行真实 Docling upload 集成测试。
- `tests.cli.test_upload_filings_from_command.test_windows_cmd_script_round_trips_adversarial_argv_with_real_cmd`：requires real cmd.exe。
- `tests.cli.test_upload_filings_from_command.test_windows_generated_script_runs_real_cli_into_temp_storage`：requires real cmd.exe。

README 职责先读：根文档为最终用户手册，此次仅修两种路径错误的真实退出码；Fins README 为当前包能力/公共边界手册，已有身份/primary/内容契约保持，不需修改；tests README 为当前测试分层/维护运行说明，新增用例仍属于已登记 renderer/CLI owner 测试模块，没有新测试层级，无需机械同步。后二者均受冻结保护且零变化。无分层/装配变化，不触发 dayu README。

## 本次实际增量与残余边界

精确修改 9 件：

- `README.md`
- `dayu/cli/commands/fins.py`
- `dayu/cli/upload_script.py`
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/pipelines/docling_upload_service.py`
- `dayu/fins/storage/_fs_source_document_core.py`
- `dayu/fins/tools/upload_tools.py`
- `dayu/fins/upload_asset_plan.py`
- `tests/cli/test_upload_filings_from_command.py`

另仅新报告本文与 E。新增产品行为仅 POSIX 再生成注释每 LF 加前缀，未改上传请求、身份、存储或 Windows 公共接口。

- **fixed in current slice**：R01/R02 作者实现与验证已完成；root 同版双审仍待执行，不能把本报告完成冒 slice pass。未发现需扩 scope 的新产品 finding，未明 owner / 白名单外 caller / 身份漂移 blocker 均无。
- **covered by later approved slice**：S2 状态/公司/amended/并发和 S3 macOS 受控 XBRL/runtime/taxonomy/deps/采集器，保持 root 计划，未实施。
- **assigned to later work unit**：Linux/Windows 延期平台验证、完整 upload_material CLI campaign/registry，在 root 既有后续排程；两个 cmd.exe skip 如实未覆盖。
- **requiring existing evidence closeout**：历史 Raw EOF 空行可逆载体封装仍归全部 slices 后最终 PR 收口，本次不 trim、不造 lineage、不冒全 PR diffcheck。
- **实际未覆盖**：历史 PDF 集成开关未开启；覆盖表未命中行仍存在，>=80 不等于全路径验证。R01 文档-only 不新增 mirror tests；其原行为由现有 owner 回归与 AST 保持证明。

current gate 仍为 S1 code-review fix；下一入口为 root 冻结本版、MiMo / ds-flash 独立 re-review 并裁决。此作者完成后停止，普通 commit/push 归 root，正式 PR197 review 仅全部 slices + aggregate 之后。
