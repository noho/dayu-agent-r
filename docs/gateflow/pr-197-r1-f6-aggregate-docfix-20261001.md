RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-d4354bcd

# PR197 F6-AG-A1 公共契约文档修复交付

状态：**fixed candidate，交 root；不是 aggregate gate pass**。日期：2026-10-01。
runtime/provider 按本轮指定外部 runner 身份记录；当前上下文未提供可独立核验的实际模型遥测，MODEL 如实标为 unknown，不将 canary 或请求的 provider 冒称实际模型。canary 由工具读取本轮 /private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.byKC77/canary.txt，18字节、无尾部换行；逐字原流为01-input-03.stdout。

唯一workspace：/Users/leo/workspace/dayu-agent-r；唯一branch：codex/upload-material-oracle；label：pr197-f6-aggregate-docfix-sol-20261001-01。
唯一源写入为dayu/fins/direct_events.py:195；本报告写前不存在，以exclusive create写入。临时证据仅在workspace/tmp/pr197-f6-aggregate-docfix-sol-20261001-01/，未新增持久Python脚本。下文短证据文件名均相对此目录。

## 根因、owner与scope

先读AGENTS.md，再全文读root combined裁决。combined明确两路reviewer均已托管终态，aggregate decision为fail / required fix，F6-AG-A1为accepted /未修复/低；MiMo未提出同项不否定root已接受的必要修复。

动机成立：公共owner的FinsDownloadFailureReason已公开SOURCE_REVISION_CONFLICT与SOURCE_REPAIR_REQUIRED，runtime在ingestion_runtime.py:6984–7000对两个真实storage sibling failure写入同字段。Attributes文档仍称“预检”，错误缩窄公共取值域。描述的owner就是FinsPublicFailure类文档，修复直接落在该owner。直接证据见02-owner.stdout、03-runtime-owner.stdout及root combined原件。

仅扩大本行至下载来源完整性失败，不改字段、enum、校验、序列化、runtime映射、业务文本或private wrapper预检文字。首轮A1/A2 code gate pass与accepted slice未重开。未修改其它源/tests/README/config/旧报告/冻结件/originals/其他label目录；没有派发Agent，没有stage/commit/push/网络/PR/merge/branch/worktree操作，没有真实Docling/OCR/private input调用。

## 实际diff与执行保全

~~~diff
-        reason_code: 下载来源预检的封闭公共原因；无细分原因时为空。
+        reason_code: 下载来源完整性失败的封闭公共原因；无细分原因时为空。
~~~

精确一文件、一行（195行），文件仍为1303行。raw原件为冻结originals/dayu/fins/direct_events.py，另以exclusive create保存direct_events.raw-before，两者保留原SHA。

| 输入/产物 | SHA256 |
| --- | --- |
| direct_events修复前/raw原件 | 66a887630b9927bf5424440b93581381b3372bd93b0777a735cd9f043273fcdb |
| direct_events修复后 | 6db072215b02a1d048fe895e8aa493bffc044d754ed5ef37497be2c62abe232a |
| 仅剔指定类docstring后AST（含位置） | 674f5205c63f0c3ee0fabaa74205a28ba776b1067456b7a434b98fbf3b95e5a4 |
| evidence-manifest.json | bc285c583874b9653ed7c1b7534724f48fd5e43cafac1930072e0da6306027d6 |
| 本轮canary原流 | 7717c8f0d866b13e2885261ac8488c1c4a904b110be5ca4d438c37e04ecaef03 |

两份AST只删除顶层唯一FinsPublicFailure的body[0]类docstring（187–196行），不删任何其它节点或位置属性；ast.dump(include_attributes=True)完全相同。写前与末轮均验证。除这段类docstring说明文本外，可执行结构、其它字符串和行位置不变。见05-docfix-ast.argv.json、ast-preservation.json、direct_events.one-line.diff、07-noindex-diff.stdout及08-identity-end.argv.json。

首核：372current+372originals逐件匹配freeze。末核：allowed文件仅上述新SHA，其余371current与全部372originals均匹配冻结SHA。三README未变；其余20slice文件还逐件核对accepted slice4f0b5b046e194d361fb0ccc798bfd26a8be4db7e的git blob，全部同SHA。见08-accepted-00至08-accepted-19的精确argv/双流/exit与identity-end.json。accepted slice对HEAD的ancestor检查innerexit0。

首末main：fac32ecbff9bfe792b63ee9667c8697826b631f4；branch不变。首末实际HEAD：4896b8d4f81b91c66c656305da34e2d8c06132ea；检查未将HEAD必须等初始值作为源码身份条件。文档checkpoint前移应以实际readonly/current/original SHA判断，历史提交触及某路径不代表当前字节漂移。

首核Git status空；末核除本文件，出现三个允许可变、非冻结root controller/handoff文档工作区变化：docs/gateflow/pr-197-review-repair-adjudication-20260930.md、docs/gateflow/upload-material-issue-198-repair-sequence-20260928.md、docs/upload_material_repair_handoff_prompt_3.md。仅读status路径，未读新内容或改这些文件；不误归为本writer变化或readonly源码漂移。证据01-input-06.stdout、08-source-status.stdout。

## 真实验证及所有非零/恢复

必要命令精确argv/cwd/env、stdout、stderr、innerexit分开保存，前缀全新、exclusive create。两pytest使用各自独占cache/basetemp，PYTHONDONTWRITEBYTECODE=1，先source .venv/bin/activate，再exec python执行。

| 检查 | 实际结果 | 证据前缀 |
| --- | --- | --- |
| python -m pytest -q tests/fins/test_fins_direct_stream.py（完整文件） | 19passed/innerexit0/stderr空 | 06-tests-direct |
| python -m pytest -q tests/fins/test_fins_ingestion_runtime.py::test_download_integrity_failure_closed_source_projection（实际21节点族） | 21passed/innerexit0/stderr空 | 06-tests-runtime21 |
| full python -m pyright --stats | Found783/checked783/parsed-bound2282；0errors/0warnings/0informations/innerexit0/stderr空 | 06-full-pyright |
| git diff --check -- dayu/fins/direct_events.py | innerexit0、双流空 | 08-whitespace-worktree |
| 末轮SHA及指定docstring之外AST/位置 | innerexit0、完全一致 | 08-identity-end |

两pytest stdout各有3条既有edgar DeprecationWarning；pyright stdout有版本升级提示和long operation记录，实际诊断计数为0。未将outer0或stderr空冒称全部执行轨迹innerexit均0。

所有非零与恢复均保留：
- 03-coverage-read innerexit1：本轮inline检查误假设历史eight-file-coverage.json的files为字典，实际为列表，产生AttributeError。输入存在未修改；04-coverage-read-recovered显式验证列表并完整读取，innerexit0，原双流/argv/exit未覆盖。该历史摘要部分文件含排除项，本轮复用独立无排除JSON。
- 07-noindex-diff innerexit1：git diff --no-index正常表示预期差异，stderr空，不等于whitespace失败。
- 07-noindex-whitespace innerexit1：git diff --no-index --check双流空，封装错误期望0，导致该outer退出1；后续未启动检查未冒称完成。新前缀08-noindex-whitespace-recovered按实际差异exit1处理，再显式断言双流空，原记录保留；该恢复命令仍为innerexit1，另有worktree whitespace检查真实exit0。
- 首次报告写入的functions.exec调用因JavaScript模板中的Markdown反引号引起SyntaxError: Unexpected strict mode reserved word，在shell分发前失败，无内层进程、无报告写入，不能伪造innerexit。本次以11-write-report新前缀改用不冲突的文本构造恢复，exclusive create。
其余已保存exit文件为0；两必要测试与fulltype均实际innerexit0。

## Coverage复用与README N/A

未重跑1342大矩阵或coverage采集，未新增字符串镜像测试。direct_events既有无排除398/447=89.03803131991052%，excluded_lines=0。仅指定class docstring改变，执行AST连同位置完全相同、行数不变，复用原执行覆盖率；该数值不是本轮重新测得。

七其它prod精确SHA与冻结/accepted相同，复用既有无排除数据；CLI使用既有A1/A2修复后的cli-coverage-no-exclusions.json，不误用早期195statements摘要。完整记录见identity-end.json：

| 文件 | 本轮SHA256 | 复用无排除coverage |
| --- | --- | --- |
| dayu/fins/direct_events.py | 6db072215b02a1d048fe895e8aa493bffc044d754ed5ef37497be2c62abe232a | 89.038% |
| dayu/fins/storage/source_integrity.py | a237079f3708c4208a2d715d95b1e468b696a72873412d143f868c19ee7d8b73 | 93.0233% |
| dayu/fins/storage/__init__.py | 3a4957c7a8cda0db2cb1fcbac035f21a384a037343c07271d62e8aa1f96cc764 | 100.0% |
| dayu/fins/pipelines/cn_download_workflow.py | b1fea03b437cb49e0619044ad8a6b75fd278d6664d7378067dfc33305a1618bc | 91.9118% |
| dayu/fins/pipelines/sec_download_workflow.py | c3d6dd3d8f7c72160f24ca839e1086e78cc25cfbb94b7f3c0f947dccb4b4dbcb | 86.8512% |
| dayu/fins/pipelines/sec_pipeline.py | 4d3c7def13aeac93f46a0ee75eb2f59896f622ad023afa778f3f9a8a21d3f63d | 86.383% |
| dayu/fins/ingestion_runtime.py | 45b16a2c77327ab522e3e4a728dca9a5739b3fbe9ccb7059c6c5bc2ba2691a1e | 90.796% |
| dayu/cli/output.py | 2839f1b58bdfbd418fe2f69e688b6ce25438346a505d0830e0ab673bb0929a2a | 85.0% |

README职责N/A：已读dayu/fins/README.md的Agent更新约束，本fix只纠正契约描述，不改变能力/架构/public输出schema或用户工作流；三README严格冻结。tests合同不变，复核现有owner级测试，不写docstring镜像测试。

## 输入/产物索引

| 输入 | 实际SHA256 |
| --- | --- |
| AGENTS.md | cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e |
| docs/gateflow/pr-197-r1-f6-aggregate-review-adjudication-20261001.md | e35ae5d5e3fcaf573dc389f7e603832747cfa967dce5cdc02e19c4149a9f4df6 |
| workspace/tmp/pr197-f6-aggregate-docfix-sol-20261001-01/freeze.json | 1322d05a97d61f34d1d3844fb45ce4ebb79056b2ee91fa67ff108b069ae4ad45 |
| workspace/tmp/pr197-f6-s1-implement-sol-20261001-01/coverage-no-exclusions.json | 3fd2d54c939e6a3e592e75d83821730ce17de9f645f42a39a5633809c95325cf |
| workspace/tmp/pr197-f6-s1-review-fix-sol-20261001-01/cli-coverage-no-exclusions.json | 8fb8ba1d5e7e0846b1ba05a805087f3677c1ef448443854236fd4f33928ba0bf |

freeze实际hash完整匹配用户指定1322d05a…ae4ad45，combined实际SHA匹配freeze；identity-start.json与identity-end.json保存全部372路径expected/current/original SHA。coverage输入均匹配首末freeze。

evidence-manifest.json有206件，SHA：bc285c583874b9653ed7c1b7534724f48fd5e43cafac1930072e0da6306027d6。列出至prefix08完成的命令及freeze/raw/AST/identity证据；不重复列372originals字节、不纳入pytest cache/basetemp、manifest自身及后续生成/报告/交付seal日志，避免自引用。报告SHA和后续完整正式产物索引另以delivery-manifest.json记录，root据此核收；不回写本报告或旧报告。

## 残余分类、owner与destination

| 残余 | 分类 | owner / destination |
| --- | --- | --- |
| F6-AG-A1本行 | fixed candidate；required fix已落本版，未自判gatepass | public failure contract；交root安排同版MiMo/Kimi窄复审，核本行及原21slice意见适用性 |
| 首轮A1/A2、SEC275 | 已有accepted修复，未重开 | 原F6 slice/single-filing owner既有证据 |
| job完整structuredreason/hint持久化、publication indeterminate | assigned to later work unit | jobcontract/store、storagepublication既有独立目标 |
| 早期cancel/helper/行级常量/testhelper治理 | requiring new issue or explicit user decision | workflow/协议/tests owner；不统一cancel/rejected/helper、不顺手修 |
| 正常helper防御TypeError/ValueError未动态击中 | 既有局部覆盖限制 | 公共类型保证、owner静态校验/旧测试；不制造非法生产状态补覆盖 |
| F5Q1 | 用户选择pending | 用户/F5后续裁决，不代选 |
| 最终真实CLI CI/materialregistry/oracle/scenarios/readiness、最终commit完整新矩阵及PRreview/closeout | covered by later approved slice，尚待执行 | root收口；全部批准修复后对最终commit重做正式证据，旧Raw删除不补造 |

writer完成必要证据后停止交root。同版MiMo/Kimi独立窄复审仍必需，当前不派发、不stage/commit、不进入下一gate；不宣称aggregate pass/readiness/final closeout。
