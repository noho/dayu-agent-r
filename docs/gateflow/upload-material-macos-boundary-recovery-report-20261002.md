RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/unknown
CANARY=gpt-6-sol-193e0877

# macOS 强制边界集中恢复：plan 补证交付

本轮 label `upload-material-macos-boundary-recovery-sol-20261002-01`。provider 为用户指定 runner 路由；本轮运行事件未暴露实际模型名称，记 unknown，不能由 canary 补推。canary 来自本轮指定文件的实际工具读取，未复用旧轮身份。

当前 gate 仍是统一修复 WU 的 plan 候选。**generation-ready=false；未 accepted、未正式 review、未实现产品。** 本轮一次集中交付新 harness、三个有界候选策略、直接反例、S3 接口必要补口及本报告后停止。下一入口是总控外层执行/核证与 Documents 资源准入方案核收，随后才能判断是否进入同版 MiMo/ds-flash planreview。

## 授权、状态与修改范围

唯一 workspace `/Users/leo/workspace/dayu-agent-r`，branch `codex/upload-material-oracle`，HEAD `619d092ab4278645203c7ebe08515f7697d92b71`，main `fac32ecbff9bfe792b63ee9667c8697826b631f4`。首核身份一致；原有 dirty 文档/未追踪 gate artifacts 保留，不把历史 control 的 clean 当当前事实。

已读实际 AGENTS.md、control、同日期 goal-amendment、统一计划 §7–8、macos-plan-completion-report、macos-probe-root-observations 和指定父层失败目录。统一计划原 SHA 为 `57beaee8f59b396d7bc748fe1115270d3b18f4b11b2b2d65a46340574360ea80`，读取时一致。本轮按 Gateflow 的证据与 owner 要求工作；用户本轮限定停止点覆盖通用自动推进指令。

只修改统一计划的 S3/整体 blocked 状态及必要交叉引用；新增本报告及独占 `workspace/tmp/upload-material-macos-boundary-recovery-sol-20261002-01/`。S1/S2 文本字节核验一致；17 标签/现成 UM 裁决、单 WU/三行为 slices、PR review 在全部 slices/aggregate 后、完整 CLI campaign/registry 在 WU 后均保留。Linux/Windows 按用户修订延期。

产品、tests、utils、依赖/锁、README、主 .venv、系统/provider 配置均未修改；不安装、不下载、不读私有财报/凭据/无关 memory，不派 Agent，不执行 sandbox_init/sandbox-exec，不创建 branch/worktree/clone，不 commit/push/PR/merge/评论。原前轮脚本、报告、rootcontrol/观察和票据只读，首末保护清单见新证据根 `protected-readonly-before.json` / `protected-readonly-after.json`。

## 旧失败的直接结论

`parent-run-20261002-01/root-driver-receipt.json` 保存 driver exit1、child exit unknown；旧 collector 对每个 argv 做 Path.is_file，将长 profile 当文件名触发 ENAMETOOLONG。child 实际执行后未落 exit，双流空不能推断成功。本轮不修写旧脚本，不补造旧 child exit。

总控 `root-startup-diagnosis-01` 的 native true、sandbox-exec Python print、直接 sandbox_init exec Python print 均实际 exit=-6/SIGABRT、双流空，policy SHA `778c910fbdc1b5959d5f9107c842adc1b56af53cb6ef14a6185de04cd0e4b6c9`。只判旧 policy 不可用。缺 executable read、opt/Cellar symlink、dyld/Cryptex 是有根据的候选，尚不是已证根因。旧 nested Operation not permitted 未重试；不能据此说 macOS 强制机制不存在或 Docling 有缺陷。

## 集中 harness 与精确父层入口

主脚本 `workspace/tmp/upload-material-macos-boundary-recovery-sol-20261002-01/parent_harness.py`；child 为 `boundary_child.py`；新目录复制并修正 `probe_convert.py`，复制无 hook `convert_plain.py`，以显式 `pyrightconfig.json` 检查四份脚本。全部依赖来自前轮 freshvenv，公开 instance/taxonomy 直接复制到本轮新 `/private/tmp` 根，不写原来源。

总控的 cwd 必须为 `/Users/leo/workspace/dayu-agent-r`。以下输出目录尚不存在；执行必须外层，若失败保留目录，重跑换全新名称，不覆盖：

```text
/Users/leo/workspace/dayu-agent-r/workspace/tmp/upload-material-macos-plan-completion-sol-20261002-01/venv/bin/python /Users/leo/workspace/dayu-agent-r/workspace/tmp/upload-material-macos-boundary-recovery-sol-20261002-01/parent_harness.py /Users/leo/workspace/dayu-agent-r/workspace/tmp/upload-material-macos-boundary-recovery-sol-20261002-01/parent-run-20261002-01
```

此命令无 selftest/control flag，才是集中 OS campaign；本作者没有运行它。可读 `control-delivery-run/tier-{0,1,2}.sb` 了解同版生成策略，但这些策略引用无隔离 control 的独占公开根，不可错当正式 parent-run 的策略。

采集协议：全新 outputdir、全新 case 子目录、`command.json`、独立 `stdout`/`stderr`；实际 wait/timeout/exec 异常之后先保存 `actual-child.json`，然后保存 `streams.json`，最后判定。未启动 exit=null 且 spawned=false，不能用 driver exit 代替。profile 作为 `sandbox-exec -f <明确文件>`，从不把文本作为文件名。freeze 仅明确定义的脚本、配置、公开输入、taxonomy、解释器和 pyvenv.cfg 路径；variants 另存 input path/hash 和 policy hash。首末 inputs/policy SHA 和 harness-final 在失败也保存。

每条转换最多 90s，cancel/readiness/cleanup 各有 8s 有界 wait，网络 syscall 2s，otool 每条 10s/最多160个 binary。三档启动 sweep 固定上限；采集/timeout异常，或已运行的边界断言失败，保存后 stop，不扩大白名单刷通过。必要正对照失败立即 stop；第三方负例保实际 exit，不靠 exit 判断 OS 拒绝。每个 case 若无法收回后代 wait，票据明确未证明，不能从 parent 退出推断 child 清理。

只操作本 run 自建 Popen session；cancel 先等子进程真实 readiness，再发本组 SIGTERM，由受管 parent 实际 wait 子进程，driver 实际 wait parent。不用 kill-0 或进程列表。超时需 SIGKILL 时记录实发 signal/actual wait，不能称正常取消成功。

## 三档候选与执行范围

共同 deny-default、无 network allow。exec 只允许 literal Python alias/真实 binary 和 `/usr/bin/true`；额外 `/usr/bin/false` 为明确拒绝执行哨兵。sysctl/mach-lookup/signal 是本原型通用运行期候选能力，并非隔离所有 IPC 的新承诺。read/write 区明确分开：input 和 taxonomy snapshot readonly；work 承载 backend tmp/output/Arelle任务配置且可写。runtime 读属于公开例外，不能等同于 taxonomy 读权。

| 档位 | 新增读取范围及理由 |
| --- | --- |
| 0 | 现成 freshvenv、真实 Cellar Python 版本根、otool 明确依赖文件、`/usr/lib`、`/System/Library/Frameworks`，指定脚本/设备与公开任务根；纠正旧 executable/alias 输入。 |
| 1 | 仅 dyld/cache/Cryptex 指定位置；保 declared/resolved/exists/is_symlink，shared-cache 虚拟路径无磁盘文件不冒已核访问。 |
| 2 | 仅 PrivateFrameworks、locale、SystemVersion.plist；最后候选，未证明需要，不扩大至全系统读取。 |

`runtime-inventory.json` 是现场 actual Python/otool，而不是猜测：base_prefix 为 opt symlink，真实根是 `/opt/homebrew/Cellar/python@3.11/3.11.15/Frameworks/Python.framework/Versions/3.11`；外部 dependency literal 为 mpdecimal4.0.1、openssl3.6.3 的 crypto/ssl、Python framework、sqlite3.51.3、xz5.8.3，共六文件。未允许整个 Homebrew/Cellar、workspace、home、global cache，也没有 allow default/所有 file-read。

每档保存 native/Python/direct-init 和真实根内成功、根外绝对/穿越/symlink 拒绝、readonly 写拒绝、listener connect 拒绝、exec 子进程继承和拒绝执行。拒绝必须为 EPERM/EACCES，不能把 ENOENT/ECONNREFUSED 当强制边界。首个全部成立档只称“最小已测试档”，不称数学最小；三档失败 stop。

选中后一次跑无 hook/取证的真实 MLAC Path/Stream、直接 sandbox_init 后同进程 runpy 导入/转换、stdlib spawn+Queue、实际 catalogZIP/entry函数调用、file URI/绝对/穿越/编码/remote、ENTITY/XInclude/stylesheet PI/其它 scheme、hardlink nlink 可信复制预检、受管 cancel。hardlink不能由路径沙箱识别，owner是上游复制合同。特殊引用若只见函数调用或 converter exit，保持 unknown；不存在全 OS 访问 trace。

## 本轮实际验证、失败与恢复

最终同版票据为 `selftest-delivery.json`、`control-delivery.json`、`pyright-prototypes-delivery.json`；各独立双流/exit，内部完整目录为 `selftest-delivery-run`、`control-delivery-run`。

- 最终 collector selftest driver0：10,000字符 argv 正常保存；nonzero 实际7且 stdout/stderr独立；不存在 executable 为未启动/null+FileNotFoundError；timeout 记录 timed_out=true、实际 SIGTERM/wait exit=-15；正常取消 parent0/child-15/cancel_received=true。它验证票据与取消协议，不是 OS 边界通过。
- 最终无隔离 control driver0：候选 policy 生成，均 executed=false；公开 MLAC instance SHA `04a015790c25d5a5371117bc64100335e65bfe1b3acdb71b4f2240c97e09cdf1`，无 hook Stream SUCCESS、errors=[]、1 key_value_item，document SHA `c95431f8fd4321aea6276ff32dc179a81331b81325991726c5535d291e9e5c7c`。只验证转换可行与 probe 取证无干扰，不重做依赖或Arelle合法性下载。
- 同版函数取证 Stream SUCCESS、2255 events：2211 ModelDocument.load calls、32 ZipFile.read calls、9 openFileStream return events、原 SimplePipeline no-op边界快照和 before/after原backend unload各1。collection_errors=[]，显式原 unload 一次、model.isClosed=true、profiler恢复、原method身份未变。新增流返回事件也不是全 bytes 消费证明。
- 第一次显式 prototype pyright exit1（`pyright-prototypes-01`）：四处 list/dict JSON invariance 类型错误。改为当前 JSON 真源类型的逐项构造后 `-02`/final/delivery均0；失败票据不覆盖。早期按根exclude跑的直接文件pyright0不作为脚本覆盖证明，最终独占config显式include全部四文件。
- 激活主 `.venv` 后全量产品 `python -m pyright` baseline0（`pyright-product-baseline`），主环境未安装/修改。原型最终显式project pyright0，无 ignore/exclude 掩盖新代码。无产品改动，因此没有运行/声称生产 pytest、覆盖率或正式 CLI 已通过；本轮对应验证是采集器真实contract selftest和公开转换对照。
- 定位时误用不存在的 `dayu/documents/process_converter.py`，sed/rg报路径错误；随后读真实 `dayu/fins/pipelines/docling_process_converter.py`，非产品失败。第一次广泛rg --files进入venv，输出被工具截断；该输出不作证据，后续均限定实际脚本/源码/票据。上述定位输出未独立持久化，不能冒完整验收票据。

所有本轮 `/private/tmp` 根及 stdout/stderr/错误/失败均保留，不删除以换绿字。最终 selftest/control 的首末 input hash 均一致。本轮没有任何新强制策略实际执行结果。

## runtime-schema 反例与 S3 必要接口缺口

同版 `control-delivery-run/runtime-reference-control-result.json`：只改公开 MLAC 的 schemaRef，指向 freshvenv 中 `arelle/config/disclosuresystems.xsd`，该runtime文件SHA `07029644bde0650128caf8da230679389b3a1f845428cc6b3755b866d68643be`；实际 openFileStream 返回该文件流，转换 actualexit0/SUCCESS。没有OSpolicy，不把它冒隔离反例；但新runtime白名单明确允许该文件，说明“runtime文件可读”与“XML资源仅受控taxonomy”不能自动等价。转换SUCCESS不代表财务抽取准确性，也不能作为资源读取安全判据。

具体正式源码路径：ModelDocument.load 经 WebCache.normalizeUrl、FileSource.file/openFileStream 到 io.open；XBRLBackendOptions 无 resource resolver/controller 注入。Arelle FileSource.File/CustomLoader 是插件扩展点，但 Docling 内部自行构造 Cntlr，无现成可传controller/plugin参数；TransformURL 只覆盖 getfilename 部分路径，不能覆盖全部本地读取。不能 monkeypatch/覆写第三方抽取绕过此缺口。

唯一 owner 是 Documents 解析资源输入准入，最小候选为直接上游 `validate_xbrl_resources(input_bytes, *, stream_name, prepared_input) -> ValidatedXbrlResources`，typed地址明确区分 relative file/ZIP member，引用含源element/attribute/raw URI/批准目标。原件、manifest XML/XSD/linkbase、ZIP catalog的所有实际资源引用归同一 source of truth，XMLParser关闭实体/DTD/网络；taxonomy URL只能经真实manifest catalog映射到声明member。它不校验财务事实、不修改原件、不将普通事实URL当资源，不用任意标签 blanket 拒绝增加新业务目标。精确字段/API/路径在统一计划 §7.6。

尚未证明该上游 validator 覆盖 Arelle全部真实引用语法：effective xml:base、percent/file/fragment、schemaRef/linkbaseRef/roleRef/arcroleRef/loc、XSD import/include/redefine、xsi schemaLocation、DiscoveringClassLookup namespace回补、catalog映射及特殊输入。**不能把接口草案当已解决，也不能把runtime例外悄悄改成“允许XML读取runtime资源”。** 最小剩余决策是总控核反例后，证明此输入闭包足以约束本受控instance路径；若无法证明，需要Docling正式resolver/controller注入的上游方案，继续blocked，不patch第三方、不另建slice。owner Documents/总控，仍在本WU必要plan/fix。

S3接线顺序已纠正：parent分配readonly原件、readonly snapshot、writablework三个互不包含的区域；Fins storage是原件bytes真源，管理员taxonomy只作部署输入；prepare显式传snapshot_root和writable_root。spawn会在policy前完成Python/主模块/Fins target/runtime/契约重建及IPC传入，不能承诺所有import都在policy后。target开头apply→复验→资源准入→实际Docling/Arelle导入→一次XBRL转换→export；现有Queue.put/feeder/join/close在policy后。bootstrap代码路径不应变成应用后的workspace读权。新stdlib spawn+Queue原型只能补机制/IPC证据；production `InterruptibleProcessHandle/_DoclingProcessTarget`尚未验，exec继承不替代生产spawn验收。

## 原件保全、副作用、风险与停止点

前轮freshdeps、合法性、无hook/v4成功与SimplePipeline._unload no-op证据不改；新路径只是复制脚本和公开输入，新增任务缓存/输出。双份原件保全仍引用前轮报告，不宣称本轮新增备份/异盘灾备。新公开对照只写独占tmp与授权文档，未清理任何历史或其它owner文件。

| 风险/未覆盖 | 分类与 owner / 解除入口 |
| --- | --- |
| 三档启动policy及直接init/网络/文件/exec/特殊引用/取消的OS结果 | 当前plan blocking / 总控外层执行新harness，runtime/Documents核票据；本作者未执行。 |
| runtime-schema资源准入覆盖性 | 当前plan blocking / Documents与总控，§7.6正式接口候选或可支持上游注入；不缩目标。 |
| production spawn导入/IPC/实际目标/cleanup | covered by S3候选实施验收；机制原型由父层先补必要设计证据；若暴露必需runtime调整，先精确回plan。 |
| 标准产品安装、真实CLI→Docling→manifest、owner tests/覆盖/README | covered by S3候选及完整WU正常gates；未实施/未验证，不前置成当前必须改产品的plan循环。 |
| typed XBRL抽取 | tracked by existing #4437 / Docling上游；无typed正样本不冒任意instance成功。 |
| Linux/Windows | 用户已授权延期 / 平台部署、依赖与Documents后续验证；不外推macOS。 |
| 完整CLI campaign/registry | WU后独立阶段 / CI/oracle总控；本轮未提前执行。 |

交付 hash、首末身份、只读保护、S1/S2字节不变和新证据索引在本轮根 `delivery-hashes.json` / `final-verification.json`。父层命令待总控核证；本轮完成到授权停止点，立即交总控，不自行review/implementation，不宣布整计划ready。
