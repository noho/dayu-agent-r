# upload_material registry S1 实施

Task：upload-material-registry-s1-implement-sol-20261004-01。Gate：implementation S1。状态：complete。S1 全部实施完成；registry readiness=ready，仅表示登记闭合。停止交 root 进入 code review；本轮不执行 review/commit。

起始 HEAD d054c0fece08d3fb5b3ed71207b3dbb8ec7f5d8c，branch codex/upload-material-oracle，main fac32ecbff9bfe792b63ee9667c8697826b631f4；初始工作区干净。冻结计划 SHA896762824e3de6ba7538fc710fc13fb8a5f33838788dd84335b7efea7f3ddad0，完整270行已读；authority 按既有用户裁决，不升级 reviewer 建议。

## 实施内修复登记

- REG-IMPL-01：一次性 scratch 导出脚本直接运行时 sys.path 不含 repository，import utils 失败（actual exit1）；尚未导出/scan。修复仅执行定位：由仓库 cwd 的 runpy 执行；不改旧helper。原 stdout/stderr 保 implementation-sol-01/export.{stdout,stderr}，恢复独立双流为 export-recovery.*。
- 读取工具输出截断：combined remaining-plan、README/文档、raw run samples 与错误匹配根标题的 authority 输出。已拆成 bounded 段/keys/types/精确 Accepted 正文恢复；截断输出不信用为全文。无业务运行失败被遮为0。

- REG-IMPL-02：SIGINT真实结果没有readback键，错误地按成功shape索引造成导出恢复actual exit1；未scan/backup/freeze。按原件键集合构建观察对象，仅带已存在的owner事实，不补取消readback默认值。修复允许覆盖本轮未冻结的partial export，开始时断言sole scan/backup均未存在；原失败双流保留，恢复用export-recovery-02.*。

- REG-IMPL-03：一次bounded核查命令引号SyntaxError actual1，已原命令修正后读取owner schema与scan身份；无业务执行。原source-plan rg输出截断改按必要line段恢复。
- REG-IMPL-04：prepare数据遇root-parser源command=null，拼文本TypeError actual1；禁止猜业务leaf。原root无leaf行只保存assignment观察，不进formal；command/null与exactargv保持，coverage不造command ID，补明确不计信用原因。恢复prepare-recovery-01独立双流。

- REG-IMPL-05：初次full pyright actual1定位三处JsonValue集合/容器不变性；已在唯一validator按严格text与显式JsonValue容器修正，不ignore或扩产品。
- REG-IMPL-06：候选内部核查发现coverage需独立按冻结matrix/PAIR66重派生、Service/shell实际role与schema对账、source-final历史全值/报告SHA及focused测量字段需加强同源核验。先登记，集中修在registry验证owner与候选准备；不增业务规则/owner、不重跑产品。候选未写正式registry。

- REG-IMPL-07：增强对账后producer actual1定位USAGE-REMOVED-INTERNAL-EMPTY，argv合法包含显式空字符串，非空stable ID helper不适用于argv。修复分离严格argv字符串列表（保空值）与非空identity列表，不loose parse或补默认值；原双流prepare-recovery-02保留。

- REG-IMPL-08：producer增强后actual1定位SUP-ROOT-PRIMARY-00-0：合法root日志参数在leaf前，argv[1]不是command。按冻结parser root action的明确arity定位完整leaf，不按首token/目录猜；只读14-leaf inventory对账，不增加产品parser行为。原prepare-recovery-03双流保留。

- REG-IMPL-09：producer actual1定位OWNER2-CONTENT-00：原selected标签是Service upload_material，正式schema按accepted plan必须service.upload_material。保source_command_label与exactargv，依据已批准Service-owner职责显式投影正式command；不将它伪装CLI，也不改原selected。pytest第二轮actual1（110pass/1fail）定位gap错误缺字段名；改owner错误定位为predicate.evidence_status，不放松测试。

- REG-IMPL-10：第二次full pyright actual1为新coverage列表不变性三处；集中显式JsonValue容器，不降类型。一次Service stdout误当单JSON读actual1 Extra data，已按bytes.split(b\'\n\')逐JSONL恢复（不重跑）。

- REG-IMPL-11：最终来源信用核查：Service的32failure/3success应取public terminal而非harness exit0；新增terminal与JSONL实际terminal精确对账和业务计数，三HTML成功按转换/发布surface登记；XBRL不领取未建立converter诊断发射的信用，N01由四PDF测量覆盖。predicate与既决authority关系由validator一个固定表复用，防缺N01正文却换其它authority冒ready。CLI治理strict read白名单与明确typed Namespace已加，非新业务规则。

- REG-IMPL-12：去掉候选invocation中未由原件提供的空key_actions/unset_environment_names，不给XBRL补stdin默认；只保实际键。public descriptor拒额外键；CLI边界/ref拒绝也输出机器报告。这些是已批准strict只读与真实投影合同内修正；最后tests/type/strict核验以最终字节为准。

- REG-IMPL-13：最终stable coverage核查发现未知/已删除参数和--file观察不能生造parser parameter ID；改为只从冻结parser action的exact option→canonical ID取信用，保全部exact argv/raw claims，合法缩写仅观察不升永久alias。复用同一模块私有helper，不重建parser、不做prefix猜测；重算每维counts，未扩大义务。

## 来源与边界

原802 frozen目标799与旧五命令target256786保持；登记target22eca是源码绑定，PDF实际parent8009+dirty，XBRL独立CLI/native11仅支持。五测量modules liveguard；十一reviewsource仅固定anchor历史metadata。新focused从现成测量纯观察导出，唯一final scanner后冻结双保；保source-final历史测试差异。Exact retention559字节七键不打开内部private archive。

## 当前验证与残余

最终两组测试 `python -m pytest tests/cli/test_cli_ci_upload_material_registry.py tests/cli/test_cli_ci_run_observation.py -q` actual exit0，117 passed；完整 `python -m pyright` actual exit0，0 errors/0 warnings/0 informations。均激活 `.venv`，原 stdout/stderr 分开保留。

唯一最终 strict `--check` actual exit0；缺flag/参数/unknown均actual exit2；wrong target、missing focused copy、越界authority ref均actual exit1并定位。逐条 exact argv/实际wait/exit/双流SHA见独占 `strict-execution-ledger.json`。同一函数producer result投影两proof/status，strict重新验证已有投影；两份history各自只有 `[own original proof]`。不将产品失败观察改为业务pass。

802原行全量assignment，793计正式信用，9排除；新focused六现成测量计正式信用，故真实正式总799、oracle1、predicate19。排除为3个root-parser无leaf与6个batch消费/脚本观察；均保原exact argv/role/理由，不丢行。35 command/parameter IDs、61状态、166输入、217组合、50跨命令义务均独立闭合；direct CLI交互不适用，PAIR66独立重算66/66。Service实际terminal32 failure/3 success，不拿harness exit0替代。

机器无法判断自由文本业务语义；逐报告/逐predicate的纯观察与threshold语义由root/code review人工核验，本轮未宣该未来审查通过。

残余：focused导出、assignment、helper/tests/proof由本S1完成（fixed in current slice，完成）；Win/Linux XBRL、历史Raw及22residual assigned to later work unit，原closeout owners/目的地；Docling抽取质量 tracked by existing issue #4437。任何关键证据缺口必须停交root，不能重跑业务。

## 最终冻结与交接

唯一运行路由为 codex/gpt-6-sol；实际后台model未独立暴露，记录unknown。最初同名model展示为路由假设，不能作为后台身份证明。本轮工具读取的 CANARY=`gpt-6-sol-e09068b1`，与来源private secret probe分别记录。

新focused为39个scan catalog文件及scan本身，40文件双副本逐字节相同；36个原件/projection lineage分开记SHA。既有五PDF与独立XBRL/native11仅支持，不运行产品，不把target22eca说成PDF执行target（实际8009+dirty）。source-final十一完整历史值/测试差异保持，五live modules guard；旧test README不liveguard。559字节七键receipt exact copy不打开内部archive。旧802全树identity继承冻结核验，本轮stat catalog及必要ref/report双SHA，没有重新hash97MB整个树。

冻结review-target路径 `docs/gateflow/evidence/upload-material-registry-20261003/review-target.json`，只记code review输入，精确schema无未来pass/自hash；具体SHA见本轮result。原6 oracle/1328 scenario全部canonical fullvalue保持；原两proof分别opaque fullvalue保在各自单元素历史数组。新版本proof有intentional v6 basis，旧basis不修订。

文档决策：只改docs/cli_ci §4.6/5.1；tests/README按其职责加唯一定位条目；无生产架构、入口或最终用户工作流变化，不触发其它README扩写。完整row读取ledger/streams/public raw均留local，Git治理assignment保逐行必要ref/SHA/命令/owner surfaces，压缩空白未删除字段或更改JSON值。

REG-IMPL-14：收束时错误地把lineage数组纳入terminal summary，工具再次截断；随后仅打印count/keys/固定descriptor恢复。完整lineage只留独占JSON，不信用terminal截断。历史inline SyntaxError与误读JSONL失败只有execution trace，未独立保存双流文件；如实在result标可见性限制，不捏造缺失argv/exit。早期combined读取/编辑调用仅末命令exit对外可见，单项exit未独立暴露；保raw输出并核实际effects，不将末0投射给未观测子命令。各producer修复attempt的source脚本没有逐版冻结；只能引用当时stdout/stderr与tool trace，不用最终script SHA冒充历史版本。

所有恢复在本S1 owner完成，无新增产品规则；最终测试/type/strict均通过。缺不可复现历史Raw不宣重现。现有22 residual/WinLinux/历史迁移归原root后续WU；抽取质量归既有Docling #4437。下一步只由root启动同版code review，本轮无Git index/commit/push/PR/网络写、无Agent派发。
