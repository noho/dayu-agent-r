RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-2801fa27

# macOS 运行时集中收尾报告

label `upload-material-macos-runtime-consolidated-sol-20261002-01`。工具实际读取本轮指定canary，逐字写在上面；运行环境未暴露实际模型精确名称，unknown不能由任务指定路由或canary推断。

**交付集中可执行harness与同版计划ready候选；generation-ready仍false，待root必要同版矩阵核证。没有执行新OS矩阵，不是产品验收、accepted plan或正式双审通过。** root确认必要可行性后冻结并进入正式MiMo/ds-flash双审。普通产品install/productionspawn/CLI/coverage只在S3实施验收，不前置为计划阻塞。本次到此交付即停止，不派子Agent。

## 范围与现场身份

唯一workspace `/Users/leo/workspace/dayu-agent-r`、branch `codex/upload-material-oracle`、HEAD `619d092ab4278645203c7ebe08515f7697d92b71`首末一致。已有dirty完整保留，不创建branch/worktree，不stage/commit/push/PR/外发。17标签+O20F02仍单一统一修复WU、三完整行为slices；不复裁业务、不重复公开MLAC合法性或标准安装，macOS先验收、Linux/Windows延期，完整CLIcampaign/registry在WU后。

本轮写入精确白名单：

- `docs/gateflow/upload-material-unified-repair-plan-20261002.md`：仅S3及必要overall状态/交叉引用；S1/S2逐字节不变。
- `docs/gateflow/upload-material-macos-runtime-consolidated-report-20261002.md`：本报告。
- `workspace/tmp/upload-material-macos-runtime-consolidated-sol-20261002-01/`：复制修正脚本、配置、合同自检、独占票据与首末hash。公开selftest根也在此目录，不新增其它临时根。

实际读AGENTS、gateflow/sub-agents技能、统一plan S3与latest runtime-boundary-goal-amendment、final-plan-report/root-adjudication/literal-root-read-observation；收尾再次用工具读取root两个最新观测，明确含librarydir成功结果。直接读指定root librarycommand/policy/actualchild/stdout/stderr及旧spawn actualchild/stdout/stderr；内核原因来自root精确owned证据文档，作者不再读内核/其它进程日志。没有memory/privatecredentials读取，无ps/pgrep/kill0、嵌套sandbox/log或提权试探。

没有修改dayu/tests/utils/deps/README/registry；主.venv仅现成python用于pyright，没有安装/升级/改配置。前轮脚本、父层run与历史研究全保全。保护清单12004项首末SHA一致，18件必要source、14件公开input、6件新脚本/config首末一致；`final-verification.json`及各before/after清单可逐项核证。主venv配置在保护清单中；不冒称全venv每个cache都已内容审计。S1/S2组合SHA `35014dae911391b309566b494a5a434f5ec95a5db0ac4fd4165a5f9b3dcba81c`，不是只比结构或行数。

## 直接因果、收敛规则与权限语义

P0-R03/R07既有literal根目录、exactancestor metadata、Python.app exec、独占work cwd修正继续保留。root真实plain-path的rich getcwd失败来自继承workspace cwd；worker先chdir本请求work，再applypolicy/复验，真实第三方导入之后。spawn bootstrap、target模块和现有Queue重建在policy前，不承诺所有业务模块都在policy后导入。

P0-R08已成立：旧最终parent-run-20261002-01的spawn driver PID91310 actualchild1，stdout证spawnchild91312已applypolicy且文件/穿越/symlink/readonly写/network负向均EPERM，stderr在Queue.put/_sem.acquire报EPERM；root精确ownedkernel记录为ipc-posix-sem-wait /mp-tgb50ceh。问题owner是中立runtime policy及直接上游既有IPC配置，不是Docling内容/缺包。集中profile新增 **`(allow ipc-posix-sem)`**，这是本机系统公开安装profile `/System/Library/Sandbox/Profiles/com.apple.appstored.sb:144`实际已有的POSIX信号量类别。保现有Queue put/feeder/join/close，不新建IPC架构/事件总线，不读Queue私有字段提取名称。该类别许可涵盖信号量操作，不是单PID/单对象独占；没有证据证明更细operation/name过滤已可用，因此不发明或盲试。没有ipc总许可、ipc-posix-shm或network许可；新同版实际Queue成功仍待root矩阵。既有process-fork/mach-lookup/signal/sysctl-read规则保留，不把其中mach-lookup伪称精确服务名单。

root-controlled-runtime-library-01实际child0、stderr空、stdout真实Stream `ConversionStatus.SUCCESS/errors=[]`，输入SHA `04a015790c25d5a5371117bc64100335e65bfe1b3acdb71b4f2240c97e09cdf1`，产出SHA `c95431f8fd4321aea6276ff32dc179a81331b81325991726c5535d291e9e5c7c`。该事实已直接复核，不靠key_value_items阈值判成功。旧单文件alias修正仍遗漏mpdecimal多级alias，不能称已全面修复。新profile只从实际otool所列declared.parent与strictresolved.parent产生精确library目录只读，静态校验与root command的10目录逐项相等：

```text
/opt/homebrew/Cellar/mpdecimal/4.0.1/lib
/opt/homebrew/Cellar/openssl@3/3.6.3/lib
/opt/homebrew/Cellar/python@3.11/3.11.15/Frameworks/Python.framework/Versions/3.11
/opt/homebrew/Cellar/sqlite/3.51.3/lib
/opt/homebrew/Cellar/xz/5.8.3/lib
/opt/homebrew/opt/mpdecimal/lib
/opt/homebrew/opt/openssl@3/lib
/opt/homebrew/opt/python@3.11/Frameworks/Python.framework/Versions/3.11
/opt/homebrew/opt/sqlite/lib
/opt/homebrew/opt/xz/lib
```

其它只读根精确为既有freshvenv、实际Python版本根、`/usr/lib`、`/System/Library/Frameworks`、本请求input/taxonomy/work；脚本/executable/设备为明确literal。真实同版完整清单在`contract-checks/policy.json`，root每run重新保存`runtime-inventory.json`和`tier-0-policy.json`。依赖alias/resolved同SHA绑定；读根canonical去重，祖先仅literal file-read-metadata。literal `/`只允许该目录自身file-read-data，不是subpath `/`。实际Python.app显式literal exec及SHA保留。独占work和`/dev/null`为明确写例外；原件与taxonomy无写权。没有整个Homebrew/home/workspace data读或出站网络许可。

用户binding允许XML读取明确运行库公开文件；**policy可允许runtime库读取不等于taxonomy独占**，runtime文件不投影为财报事实。P0-R04仍rejected-with-reason，旧成功openFileStream事实保留，不冒已修或读取被拒。可信taxonomy管理员来源/许可/provenance、manifest全文件/ZIPentry hash、受控复制/转换前复验继续由Documents owner负责。没有XML资源闭包parser/typedgraph/namespace模拟、第三方patch或财务准确性修复；旧研究原型不在本轮运行脚本/config include或产品白名单。

## typed公开接口与未来产品精确白名单

同版plan §7.2/7.3/7.5/7.6可直接指导实现，所有接口均是计划候选，尚未实施：

- `apply_macos_sandbox(profile: str) -> None`，非0读/free原OS错误，抛`MacosSandboxError`，不回退。
- `build_macos_sandbox_profile(*, readonly_roots: tuple[Path, ...], readonly_files: tuple[Path, ...], writable_root: Path, executable_files: tuple[Path, ...], allow_existing_posix_semaphores: bool) -> str`，参数全部显式；当前XBRL装配True生成上述sem类别，False不授予。只处理明确runtime清单，层中立无Fins/Host/Engine依赖。
- `RuntimeReadFile(declared_path: Path, resolved_path: Path, sha256: str)`与`inspect_macos_runtime_dependencies(executable_file: Path, python_base_root: Path) -> tuple[RuntimeReadFile, ...]`，otool10秒/160文件预算，无未闭合依赖的全根fallback；上游将declared/resolved的parent纳readonly_roots并复验同文件hash。
- Documents持有`XbrlConversionConfig`/`PreparedXbrlInput`、`prepare_xbrl_input(...) -> PreparedXbrlInput`与`convert_xbrl_bytes_with_docling(...) -> ConversionResult`的已有计划完整字段/参数；Process显式传配置，worker按chdir→policy→snapshot复验→第三方import/单次转换→export顺序。真实backend.unload finally一次，取消/IPC/cleanup复用现有owner；失败同源stored0/无成功manifest。

生产精确允许文件：`pyproject.toml`、`requirements.txt`（仅安装说明必要同步）、`constraints/lock-common-py311.txt`、`constraints/lock-macos-arm64-py311.txt`；`dayu/documents/docling_runtime.py`，新增`dayu/documents/xbrl_config.py`；`dayu/fins/pipelines/docling_process_converter.py`，新增`dayu/fins/pipelines/docling_converter_factory.py`，`dayu/fins/service_runtime.py`、`dayu/fins/pipelines/cn_pipeline.py`、`dayu/fins/pipelines/sec_pipeline.py`（三处实际装配）；`dayu/fins/upload_format_contract.py`（唯一候选文案投影）；新增`dayu/runtime/macos_sandbox.py`。现有`dayu/runtime/interruptible_process.py`只在父层实际IPC/隔离继承证明需要通用原语调整时进入plan/fix另列准确变更，不授权实施者自扩。CLI/tool不用新增taxonomy参数或自己读配置；已有共享投影继续消费，候选格式不删除。

测试精确允许：`tests/documents/test_docling_runtime.py`、`tests/documents/test_import_boundary.py`，新增`tests/documents/test_xbrl_config.py`；`tests/fins/test_docling_process_converter.py`、`tests/fins/test_docling_upload_service_integration.py`、`tests/fins/test_upload_format_contract.py`、`tests/fins/test_cn_pipeline.py`、`tests/fins/test_sec_pipeline_upload_material_stream.py`、`tests/fins/test_sec_pipeline_upload_filing_stream.py`、`tests/fins/test_sec_pipeline_download.py`、`tests/fins/test_sec_pipeline_download_stream.py`，新增`tests/fins/test_docling_converter_factory.py`与`tests/fins/test_xbrl_controlled_upload_integration.py`；新增`tests/runtime/test_macos_sandbox.py`。真实公开财报/taxonomy不进PR，机制fixture只能自行合成并明确非positive。不存在测试路径先按本plan创建，不以旧fake倒逼默认/兼容分支。


上述是未来正式接受后S3实施白名单，不是本轮写权限。现有interruptible_process无需为P0-R08改IPC架构；必要policy表达在macos_sandbox及直接上游装配。README按plan §7.5职责只在实施触发时更新，本轮不改。产品标准install/CLI→manifest、productionspawn/cleanup、pyright/owner测试及每改生产文件coverage>=80%在正常S3实施中验收。

## 有限验证、票据与本轮错误

原型pyright5份脚本：0errors/0warnings/0informations；第一次激活主.venv直接工具exit0，最终同版独立票据 `local-validation/prototype-pyright/actual-child.json` exit0，双流及SHA完整。版本升级提示仅告知可用新版本，未安装或降格类型。

`harness_contract_checks.py`工具exit0：10库目录exact与root已证清单一致，alias/resolved同SHA、literal根目录/metadata规则、sem类别且无shm、无整个home/workspace/Homebrew subpath与networkallow全部断言通过。策略只生成、不apply。票据`contract-checks/`。

`parent_harness.py .../selftest-20261002-01 --selftest`工具exit0：长argv、双流exit7、未启动exitnull、timeout真实wait(-15)、受管child取消wait(-15)均真实保存。selftest expected非零不冒成功child；聚合0仅说明断言成立。票据`selftest-20261002-01/`各actualchild/stdout/stderr/streams/harness-final，没有执行OS sandbox。未运行生产pytest/coverage/CLI或真实新转换；不冒相应pass。

首次rg --files定位未排除原型venv，约1.18M token输出被截断，命令exit0；后续限定顶层脚本与指定文档读取恢复，不以截断证明完整覆盖。没有任务内类型/定位未恢复失败，没有provider重试/切换或子Agent派发。本轮除上述新成立P0-R08/旧literal-only不足集中登记外，未发现新需扩大目标的修复。

## 冻结哈希、一次root命令与停止点

finalplan SHA256 **`36ec1bcf0815ca96c662f159973ade3106b4af6d072389f8c8d3747512b36530`**；前版SHA `57b4ee6810cc98e3a04111d8404d79bde0505844b68b3e13c18edd75aeb741c6`。新脚本/config首末hash：

| 文件 | SHA256 |
| --- | --- |
| `parent_harness.py` | `77726e16f345f21d16cac22d057f57936dcbc1f15918f033034380729765a351` |
| `boundary_child.py` | `442736fdb764a2346c528e66cd171d36e5d43da7a5af446458a024681906f5df` |
| `convert_plain.py` | `df14010594cf8f87417488a48089f15205e8075f6e00ca722911569068be6ac8` |
| `probe_convert.py` | `b10cf0c116573b8c5b7e56d83c9335fffebb848bcf9b84b8eded85c7f0573d04` |
| `harness_contract_checks.py` | `39fff26d0b67782da951cd428a3d021a40d13a783ed29423e32c05b91512ce1f` |
| `pyrightconfig.json` | `bd3f4563a2f8cfef4e1874c1fa3bdf207fcb8cac6ae8d2917f161aa1f93444f7` |

全部deliveryhashes在新根`delivery-hashes.json`（含本报告/计划/脚本/config/根命令manifest/验证与首末清单/每张本轮票据；manifest自身不自引用）。`root-command-manifest.json`绑定同版finalplan/脚本/公开input/必要source及解释器。delivery自引用通过外部root核SHA完成，报告自身最终SHA取manifest，不把循环占位值当hash。

root仅在父层执行下列一次精确argv，cwd `/Users/leo/workspace/dayu-agent-r`，目标输出目录目前未创建：

```text
/Users/leo/workspace/dayu-agent-r/workspace/tmp/upload-material-macos-plan-completion-sol-20261002-01/venv/bin/python /Users/leo/workspace/dayu-agent-r/workspace/tmp/upload-material-macos-runtime-consolidated-sol-20261002-01/parent_harness.py /Users/leo/workspace/dayu-agent-r/workspace/tmp/upload-material-macos-runtime-consolidated-sol-20261002-01/parent-run-20261002-01
```

该次保留既有必要矩阵：native/Python/direct启动、file/network/readonly/exec继承、spawn+Queue、plain/profile真实Path/Stream、directinprocess、特殊引用/ZIP及受管取消，全部真实wait/双流/首末SHA；单档失败/timeout/collector异常立即保票据停止，不扩大许可。运行结果是必要可行性证据，不是production验收。未知仅集中同版矩阵与root裁决；边界真实不可实现目前无新直接证据，不造blockingquestion。root确认必要可行性后冻结进入正式双审，标准生产验收按正常S3推进。完成交付即停止。
