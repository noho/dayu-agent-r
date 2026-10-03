RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-96268bfa

# S3 受控 XBRL 实施报告

label：upload-material-unified-s3-implement-sol-20261003-01。实际工具未提供可独立核验的模型 ID；unknown 不从 canary 或派发名称反推模型。已读取本轮 canary 原始字节。

## 结论及身份

S3 集中实现与本轮必要验收已完成，交 root 同版双 review；本报告不赋 accepted、WU 完成或 aggregate。无子 Agent、stage/commit/push/PR/merge/外发、分支/worktree/clone/detached 操作。原 S1/S2、原机制 Raw、97 票据/continuation11及两份许可资源保持。

- HEAD：a514dea14c0ce66722da034502f3af54a54c3238；main：fac32ecbff9bfe792b63ee9667c8697826b631f4；branch：codex/upload-material-oracle。首末直接 Git/字节检查一致，仍为未提交 S3 工作树。
- 初始 inputs 11793 / protected 11769 / allowed 31；首核与末核 protected 均 drift=[]。root control 与 S2-checkpoint 的合法 dirty 已在冻结输入中，未由本实施修改。
- 原清单 SHA：input 756c41f4f1482fb20437b53d38dadbc5139460476f571cc44aae140aed8d8067；protected 7ef6b6b70bc23f7402f15f76190ae855c35b5d86122787827a9dd5d4c33d9e1a；allowed 59259be1eeebe678f1717b3807687a477edcbcdb703e488914db5b88d9812e07。
- 已接受计划 SHA c99c35adba919a8baf371b0142e0ab1abf256a951e89b2fc15e8a2d38988e8ea。root 已在 upload-material-unified-s3-task-reference-correction-20261003.md 裁“V15–V20”是派发引用错误；按实际 §7.2–§7.6/§8/§9验收，未创造编号。
- 首核 `workspace/tmp/upload-material-unified-s3-implement-sol-20261003-01/preflight.json`；末核 `workspace/tmp/upload-material-unified-s3-implement-sol-20261003-01/evidence-closure-final.json`。精确 changed SHA 见下表及 `workspace/tmp/upload-material-unified-s3-implement-sol-20261003-01/changed-files-final.json`；安装/CLI 的源码绑定位于实际 command、Path/Stream stdout 与最终身份票据。

## 修改及 owner

Documents 唯一拥有绝对管理员配置、exact JSON 字段、UTC/HTTPS provenance、完整目录/ZIP 清单、文件/成员 size/hash、O_NOFOLLOW/fstat/同 fd 复验、只复制声明文件及 worker 解析前再复验。未声明条目、重复 JSON 字段、篡改、symlink/hardlink、不可信权限或目录重叠均拒绝。没有新增 XML/XBRL 闭包解析器或 namespace graph。

Fins 的唯一 converter factory 读取 DAYU_XBRL_CONFIG 并复用 Documents loader；三处实际默认装配统一接线。ProcessDoclingConverter 的 xbrl_config 为必传，全部既有实际 constructor/caller 与涉及的 fixture 已迁移；不涉及 constructor 的 instance-check 测试未强迁。XML_XBRL 从共享 capability 路由，.xml/.xbrl 都仅走该分支。unset、配置/prepare/policy/worker复验错误沿既有 CONVERTER_CONSTRUCTION；无通用转换 fallback。非 XBRL 保持原通用接口。

runtime 是仅依赖 stdlib 的中立 OS 策略 owner，无 Engine/Host/Service/Fins 反 import。实际解释器/stdlib extension/递归绝对 dylib 用有限 otool 检查，保存 alias/canonical/hash；策略只读精确运行库根与实际 aliases/OS needs、请求 input/taxonomy，只有请求 work 可写。literal / 仅自身 data，祖先仅 literal metadata；无 whole workspace/home/Homebrew、default read 或 network allow。

生产顺序：受信 spawn/Queue bootstrap → worker chdir(work) → apply真实内核策略 → verify snapshot → 导入/构造第三方 → 单次转换 → export → finally 实际 backend.unload 一次。SimplePipeline._unload 保留为 no-op 事实，不冒 model closed。父 handle 原 wait/interrupt/join/close 语义复用，未改 runtime 生命周期公共 API。

UP-RR-T01 新副本 special case 全部显式 actualURI + exact sentinel target；原技术采集器和原票据不改。临时采集器只观察实际函数调用、公开进程方法及同 PID kernel/errno；不更改第三方、业务 result、策略或仓储。

README 已先读职责：根写当前安装/配置/限制/排障，Fins 写候选转换/完整发布，dayu 写中立依赖与装配，tests 写 owner tests 与 external 许可输入。Documents无README不新增；未改Config默认配置。

## 标准安装和可信输入

主 .venv 只激活用于入口，未执行安装/升级；标准环境 `workspace/tmp/upload-material-unified-s3-implement-sol-20261003-01/standard-venv` 是新建完整产品环境。实际 Python 3.11.15 (main, Mar  3 2026, 00:52:57) [Clang 17.0.0 (clang-1700.6.3.2)]，macOS-26.6.2-arm64-arm-64bit，解释器 `/Users/leo/workspace/dayu-agent-r/workspace/tmp/upload-material-unified-s3-implement-sol-20261003-01/standard-venv/bin/python`。

venv-create exit0；standard-install exit0；pip-check exit0。安装实际 argv 为 `pip install -e .[test,dev,browser] -c constraints/lock-macos-arm64-py311.txt --report .../standard-install-report.json`，无 --no-deps。实际 Docling/docling-slim 2.127.0、Core 2.96.0、Arelle 2.45.3、jaconv 0.5.0。共 173 份实际发行 METADATA 原字节及 hash 保存在 `workspace/tmp/upload-material-unified-s3-implement-sol-20261003-01/installed-metadata-recovery02/`、`installed-metadata-index-recovery02.json`；resolver report、pip-check双流、部署锁回读见同根。锁中 170 条已安装 pin 的版本逐项相等；13 条未被本安装选中的 pin 保 actual=null，不冒已安装/已验证。macOS锁和requirements原字节不需改变；产品启用 docling[xbrl]，公共锁补实际完整 resolver 所需五项。

管理员独占根 `/private/tmp/dayu-xbrl-s3-admin-qmid1407`，0700；有效配置 config.json、manifest.json、taxonomy/、原件 mlac-20251231.xml 均为本轮副本。有效 manifest SHA 5a1cc9986b36724cd5752b0b9389571e0fcdc31eeda9680c215213b5ecaa36af；config 的路径三个显式字段，无 HOME/sidecar发现。有效来源与部署记录 `workspace/tmp/upload-material-unified-s3-implement-sol-20261003-01/admin-input-v2.json`，第一版 admin-input.json 保历史而未作为最终输入。

仅官方 Docling commit f1c42e394e3f5c40375c83edf01f8de762bb64f9 的 MLAC 2025-12-31 instance，原件 SHA 04a015790c25d5a5371117bc64100335e65bfe1b3acdb71b4f2240c97e09cdf1；五份 issuer XSD/linkbase及 taxonomy_package.zip 的文件/完整 ZIP entry size/hash 从批准双备份逐字节核收后复制。两份原资源各618files不改；逐 URL/UTC/响应/许可来源仍指原冻结 provenance，不冒本轮 SEC 直取。原件及 FASB/XBRL/SEC 混合许可包仅在 ignored 技术资源及专用管理员根，不入 Git/testfixture/材料taxonomy资产。许可来源沿已采 Docling LICENSE 与 FASB 官方 terms；不创造新的许可授权。

Arelle 最终标准解释器离线 `--validate --validationExitCode --internetConnectivity offline` 实际 exit0，日志 error/warning=[]，完整同级输入只复制声明资源；argv/XDG_CONFIG_HOME/日志位置在 arelle-validation-final-command。受控最终 Path/Stream 均 exit0、原件同 SHA，JSON SHA de12db8941c659d4160068d09e80afaf5382b8188573150fed7c2dfa3f79bad9，1200672bytes，各实际 model closed，backend显式finally卸载一次，源码 hash 在 path-after-c01-command / stream-after-c01-command stdout。

## 真实 CLI / 仓储 / 生命周期

最终必要正例根 `workspace/tmp/upload-material-unified-s3-implement-sol-20261003-01/production-after-c01-positive/positive`。实际 argv/cwd/env/source SHA、双流、实际 wait在 command.json/receipt.json；CLI PID56117 exit0。worker PID56287，公开 wait 为 Completed 时 exitcode=null，随后原 runtime close 的公开 BaseProcess.close 采样 actual exit=-9、close成功；绝不把 CLI0 写作 worker0，也不从 -9 推业务失败。原 handle 在回传结果后仍活时会 kill 回收，业务结果已导出/闭合，actual life events 分别保存 runtime-lifecycle.json/owned-process-close.json/actual-child.json。

同次真实 loader 2211 ModelDocument.load、32 ZipFile.read；无采集异常；1次 SimplePipeline no-op，实际 backend unload call1/return1、model.isClosed=true。原件/Docling/meta/manifest 完整通过公共 Fs read_material_upload_state、read_source_snapshot；manifest 原字节通过 storage LocalFileStore公共 get_object读取，未fake仓储。

- public status=complete；document/internal ID=mat_a515363258ba438c5f2e5582e749223ae8676d93；version=v1；primary=mlac-20251231.xml_docling.json；amended=false、active。
- original SHA=04a015790c25d5a5371117bc64100335e65bfe1b3acdb71b4f2240c97e09cdf1；实际仓储 Docling JSON SHA=03cff17b63d3a532de6a8e33778b39bf0317e9ae682a8c119098ddf6ba4a1f33，1950364bytes；这是生产序列化，和上述紧凑JSON对照的序列化字节形式不同。
- 权威 manifest SHA=0606c3089f09cbb0a1af487d50453c7d09ff4108e63e747d0f6412fa54b9d0ef，storage key=portfolio/MLAC/materials/material_manifest.json；其中 ID、primary、version、amended 与公共 state/source meta一致；源 fingerprint=e3f6eb33110d10764b4dcab333dfc4de52d9de7b4009bf287804eac7f8cdf85c；opaque revision仅作为技术一致性标签，不作财报事实。
- 最终正例独占 shadow 文件/network真实请求均 errno EPERM，内核同PID56287/同窗口精确 file-read-data 与 network-outbound 拒绝。原精确kernel命令/双流 `workspace/tmp/upload-material-unified-s3-implement-sol-20261003-01/kernel-after-c01-positive-command`，绑定摘要 evidence-closure-final.json。

必要坏部署/内容 CLI `workspace/tmp/upload-material-unified-s3-implement-sol-20261003-01/failclosed-managed03`：unset、坏配置、坏manifest摘要、普通XML、linkbase 各实际CLI exit1/public状态missing，无本请求部分材料或成功manifest；unset/内容失败可保 S2 独立公司，坏装配配置在公司之前失败。worker可观察的policy/life独占在对应case目录，未产生worker的配置失败不造PID。typed owner另覆盖坏JSON、损坏XML、snapshot篡改、启动策略失败、export/IPC/cleanup既有异常。坏容器/CRC 最新 owner/factory tests锁 CONVERTER_CONSTRUCTION和完整cause。

取消真实票据 `workspace/tmp/upload-material-unified-s3-implement-sol-20261003-01/production-e01-final05/cancel`：CLI130与worker54137实际 -15分开；policy应用后发送SIGINT，原公开interrupt exited=true、close完成；public state missing、无材料发布。未观察到 cancellation 的完整backend finally事件，保未观察，不造closed=true。

## UP-RR-T01 / I/O 判据与允许例外

同次必要 XML 关系票据 `workspace/tmp/upload-material-unified-s3-implement-sol-20261003-01/production-e01-final05`，旧97/continuation11完全保留：

| case | worker PID / actual close exit | 实际 URI 与技术结果 |
| --- | --- | --- |
| file-uri | 53073 / -9 | actualURI 为该case精确 private-sentinel.xsd 的 file URI；真实loader请求且返回false，独立同PID内核在shadow及loader窗口各有file-read-data deny。旧无kernel票据unknown保留；新增 loader-io-kernel-final-bound-verdict.json 为 denied。 |
| ftp | 53252 / -9 | actualURI=ftp://127.0.0.1/blocked.xsd，exact sentinel_target是本轮private-sentinel.xsd；真实ModelDocument.load请求观察到，无该URI的OS拒绝证据 → unknown，绝非not-attempted；不据CLI0/false/timeout/无连接推denied。 |
| runtime-schema | 53431 / -9 | 实际 arelle/config/disclosuresystems.xsd 请求、openFileStream=true → allowed；处已批准运行库例外，原P0-R04 stronger closure finding为rejected-with-reason，不写“已拒”。 |
| entity-file | 53607 / -9 | 指定file URI未观察请求 → not-attempted。 |
| xinclude-file | 53786 / -9 | 指定file URI未观察请求 → not-attempted。 |
| stylesheet-pi | 53960 / -9 | 指定file URI未观察请求 → not-attempted。 |

每case input.json保存actualURI/exactsentineltarget/输入SHA/expectedprimary/ID；profile.json绑定真实PID和实际加载请求；actual-child.json绑定公开worker close终态；内核原件sha/window精确核收。已有成功状态与读取拒绝可同时存在，不能拿模型准确性或DoclingSUCCESS反推权限。

实际策略readonly runtime有13条路径拼写（8个canonical资源组及相应安装库/Python aliases），另请求input/taxonomy各1，write仅work。精确路径均在policy.json，实际6条加载文件alias/canonical/SHA在actual-runtime-aliases-final.json；这里只按§7.6实际库目录/别名与OS needs公式表达，不把路径拼写数假写成固定10，也未增加新runtime资源类别。OSneeds为 /usr/lib、/System/Library/Frameworks；精确exe包括Python.app真实路径及别名。ipc-posix-sem是已接受现有Queue类别许可，未宣称单Queue/PID独占。祖先metadata、literal /自身data、devnull写为接受例外，不概括所有file-read。

## 测试 / 覆盖 / 类型

最终产品变更后 `source .venv/bin/activate`，用标准fresh Python执行 final-after-c01-regression-command：668 passed、1 skipped、3warnings、actualexit0；JUnit/独占COVERAGE_FILE/cacheoff/basetemp/JSON与双流完整。跳过仅既有 opt-in PDF integration，理由 DAYU_RUN_DOCLING_UPLOAD_INTEGRATION 未启用；本轮必要外部 XBRL 正例和实际负例均执行。无fake positive/金融准确性门禁。

full-pyright-after-c01-command 是全仓配置 dayu/tests/utils、显式 --pythonpath 标准fresh解释器，actualexit0、0errors/0warnings；未改pyrightconfig/exclude/ignore，主环境未补依赖。临时helpers用局部nonemptyinclude显式检查，不拿根配置排除workspace后的空检查冒pass，最终helper检查同样0。pyright版本升级提示非类型告警，保原双流。

| 实际修改生产 Python | 最终覆盖率 |
| --- | --- |
| dayu/documents/docling_runtime.py | 91.06% |
| dayu/documents/xbrl_config.py | 95.93% |
| dayu/fins/pipelines/cn_pipeline.py | 93.68% |
| dayu/fins/pipelines/docling_converter_factory.py | 100.00% |
| dayu/fins/pipelines/docling_process_converter.py | 93.75% |
| dayu/fins/pipelines/sec_pipeline.py | 87.45% |
| dayu/fins/service_runtime.py | 81.15% |
| dayu/fins/upload_format_contract.py | 93.02% |
| dayu/runtime/macos_sandbox.py | 85.09% |

## 失败保留 / 恢复 / finding

以下均保原actualexit/stdout/stderr，不刷旧失败：

- initial-owner-tests exit1：stderr退出恢复原首因与fixture required字段问题；owner修复后95pass，最终回归通过。
- cli-positive-first / cli-controlled-first exit1：/var→/private canonical请求目录不一致；allocator owner修canonical后恢复。cli-controlled02 exit1为当前工具外层沙箱不允许sandbox_init；正常 require_escalated 审批执行 native02成功，未绕过权限。native01 exit2为命令写错管理员路径，保票据，读取实际deploy v2后必要恢复。
- pyright-first exit1（US3-T01 output_path unbound）、pyright02 exit1（测试Json列表不变性）均owner修复，全量最终0。helper-pyright01/02 exit1的签名/公共仓储API/Json类型迁移修复，最终明确nonemptyinclude0。
- production-acceptance01 exit1：临时采样以函数名误命中ZipExtFile.read造成KeyError；修为精确ZipFile.read code。02 exit1：真实CLI已成功但公共revision对象未转token导致临时读回序列化失败；修公共投影、原成功/失败分开保留。
- US3-E01（root accepted）：旧采集器把CLI exit写到worker PID，无效child exit声明保原但不沿用。recovery04原公开wait正常exitcode=None，明确unknown；最终05/current positive通过原公开BaseProcess.close采样核actual -9，cancel原公开interrupt核 -15。未读Queue私有字段、无ps/pgrep/kill0或他人进程操作。
- target-tests03 exit1：唯一fixture在/var记录而产品canonical到/private；fixture记录返回路径的canonical值，fixture定向恢复通过；不为旧fixture在产品补兼容。
- deployment-audit-command exit1：误要求锁中所有可选pin都安装（altair未安装）；改为逐已安装pin严格回读，未安装项明确null；无安装补包造成功。metadata-capture-command exit1：METADATA候选不唯一；只收发行根dist-info精确METADATA后173份原字节完成。helper-after-c01 exit1是metadata.locate_file抽象路径类型；断言实际filesystem Path后正确强类型，未Any/getattr降格。
- failclosed-final-command exit1：临时断言把actual CLI stored_files="0"写成错误显示文本；采用实际字段后恢复并再以managed collector补完整worker观察，产品不改。
- evidence-closure-command exit1：临时kernel精确字符串漏Sandbox:前缀；补实际字面前缀和同窗口后核收。native-kernel49168 exit0空数组来自首条local-time解析窗口错误，未当作无拒绝；后明确local窗口+UTC输出命令及实际事件核收。
- CN覆盖首次68%不足；定向既有owner集219pass后93.68%。第一次补跑复用了COVERAGE_FILE而非独占，这是执行协议偏差；原final JSON和所有双流未覆盖，随后独占定向恢复+独占最终全受影响回归，最终覆盖只采用after-C01单次集合，不依赖复用产物。
- US3-C01（root accepted）：BadZipFile越过Documents校验owner。现在在_verify_archive捕实际BadZipFile为XbrlConfigurationError并保cause，loader/prepare/worker和factory一律复用；实际坏容器/CRC六面反例＋公开construction测试通过，49owner tests0，最终668pass。状态为已实施且实证恢复、待root同版裁决，未擅自改root finding文件。
- 若干只读路径定位命令曾因猜测不存在的summary/allowed/仓储模块/新case目录而非零（compound后续成功不抹前错）；改读实际身份清单/公开接口及目录后恢复，无产品或保护文件影响。一条rg --files RUN曾枚举fresh venv文件名，未读取其内容；此为不必要范围扩大，后续只读精确安装METADATA及approved资源，未全扫私有根。

逐命令全部实退出码、argv/cwd/env、actualwait、双流SHA及receiptSHA在command-ledger-final.json；必要负例CLI1/取消CLI130是预期终态，driver0不代替case原exit。初期runner仅记录必要环境子集，不能冒完整env录制；有效真实driver保存必要DAYU配置/影子哨兵环境，stdin为实际DEVNULL。子进程只对本Popen-owned对象wait/cancel/cleanup；日志采集只按精确ownedPID/operation/path/window。

## changed files / 边界与剩余项

精确实现差异（未修改的allowed路径不列）：

| 文件 | SHA-256 |
| --- | --- |
| pyproject.toml | 358eab55d4ecbf4462137dda34d0d38786a9fa907fa185979b40cf9b39bc704a |
| constraints/lock-common-py311.txt | 894cb2c76ef0fd0fc91610c4e02415d89083e5ea4f9c13b0d09f1f01d3da4d70 |
| dayu/documents/docling_runtime.py | e00f764a9720b4752abbd92fdb0a5404069dc7ac89eba6434cccf554db5414e9 |
| dayu/documents/xbrl_config.py | d59cc33f4482a54c2d0d59f949e469d22e7ae58382466d0ebbd85ae0002222dc |
| dayu/fins/pipelines/docling_process_converter.py | d6b6772e329c66045f634fb4994c76bbcb9ef0130d3fe498b2e7f044ae6cd1b8 |
| dayu/fins/pipelines/docling_converter_factory.py | 9602abfcb6476cb7eab53e9988c1f90c533fb36cdc70b52e331210eec4fd9b72 |
| dayu/fins/service_runtime.py | 7cec10edf79832a6ea7aba8a7f5989acb6710279d194fb235d864683b8bdca3a |
| dayu/fins/pipelines/cn_pipeline.py | a359c06858b2a3be0bc562e2f51d9058fa30f966d098079d05b2e04727c8dce9 |
| dayu/fins/pipelines/sec_pipeline.py | 13b59b729214a83635d41677b12df203b702a7c6ee2e8f4cab7af0d343dfafde |
| dayu/fins/upload_format_contract.py | 04ae2b2965d0d3a72b1021ad83f8d385d1beb6a97297edae93db70ca52eb702e |
| dayu/runtime/macos_sandbox.py | 0794d0390706941f76d9250a02c7503aaeaaf35a08420fe27dccf5f890dd3a54 |
| tests/documents/test_docling_runtime.py | e390073f41af147db1a1165b1bc1b30ca78e842f39f5b069e488293aded9ec8e |
| tests/documents/test_import_boundary.py | 3ca47e87f85f1f8bedf955d53ce4933b114f1049ba290bb362591f3caae6a2dc |
| tests/documents/test_xbrl_config.py | cf9655eaa7070580877c86645a47707359a158a4e2f8701d28ff42bd33767aa7 |
| tests/fins/test_docling_process_converter.py | 61d39c369ebf8f62a8379d57de8b724115a54b39c613123a55e0afbc4b72ab66 |
| tests/fins/test_docling_upload_service_integration.py | d1ac2005a28bdd400e859ff06acb77aeb6216cc1ed6b5a07a13d280b8924aa67 |
| tests/fins/test_upload_format_contract.py | a8808d310174d597eca7504a87cba548eeae5f8522bc3fdbd61e45b98f6aaa9a |
| tests/fins/test_docling_converter_factory.py | a5dbf0f516c544bc38660a31eb6eaf2656850137b00f37ac4b08c3741e3812ec |
| tests/fins/test_xbrl_controlled_upload_integration.py | 9a3748ac22a824a9e44c7e0a2c67244ffa84056d70017e197915ef0a7270aaa0 |
| tests/runtime/test_macos_sandbox.py | 9ada1906f6dfbb203fbf6525a40d0e2ce48e4d79af440b1bc5fe362f53982c51 |
| README.md | 6e900e6e9141a70a6485334eab85ebbb43a3c9d820bf8db82551d077f4b26e62 |
| dayu/fins/README.md | aa8d0e1a6140d26a98ba6901987d5e1f854d78b2903229595124189276522d9b |
| tests/README.md | 9bde6607f3ff2cff84d3823d8a75808cb88a0ba98d61e69ec2fb13ea76eb0df2 |
| dayu/README.md | 164c5b5382a7ed284f5463bafef7e851059593d05a8d019e342a190f17d46bcd |

额外允许交付为本报告；其自身SHA在最终身份JSON中，避免自引用。root新增的task correction/US3-T01/US3-E01/US3-C01裁决及原control/checkpoint均不是实施agent改动。原allowed外没有偷偷改caller/锁/README，最终保护哈希验证无漂移。

未覆盖及 owner/destination：Linux/Windows安装/隔离/继承/锁回读明确延期，由平台部署验证owner后续处理，当前没有pass claim。此MLAC无typed contexts，不承诺任意typed XBRL；Docling #4437准确性属既有上游，不本地parser/patch/阈值，也无新issue。FTP实际请求无指定OS拒证保持unknown；XML关系未尝试不推deny；取消模型关闭未观察不推closed。runtime可读取已批准公开XSD是接受例外，资源exclusive闭包不是当前goal。正式双审/aggregate/PR review由root在S3完整后推进；完整mandatory CLI campaign/正式registry仍为WU后独立阶段。不扩22 residual、不处理历史schema迁移或日期/财期裁决。

停止于S3实施交付；待root双review及结构化独立裁决。报告不是final accepted checkpoint。
