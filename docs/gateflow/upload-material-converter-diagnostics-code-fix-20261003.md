# S1 converter diagnostics 集中 code fix

RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6-sol
CANARY=gpt-6-sol-a565ff78

任务：upload-material-converter-diagnostics-code-fix-sol-20261003-01。Gate：同一 S1 code review → fix；本轮停止于修复及完整验证，不进入 re-review 或后 gate。唯一 workspace `/Users/leo/workspace/dayu-agent-r`，branch `codex/upload-material-oracle`，checkpoint HEAD `8009ba4e100081fd1b56f64ddf5bc0c42a06e808`；候选源码未提交，HEAD 不含候选。

## 修改前成立问题及 owner

以 `docs/reviews/upload-material-converter-diagnostics-code-review-root-findings-20261003.md` 为唯一裁决源。baseline manifest SHA `524f7cc14e272a446a0d5bfac5aad41a12a394b759ba7932138e2f54f58607ef`、11 文件、两份新全文、tracked diff SHA `dc6823e99de853bf1f4390b5644226652b7451bd793b2bf2eb2bb5651042f3c4` 和 plan/acceptance/两审报告/registry SHA 已逐项匹配；见本轮 `baseline-verification.json`。

- C02 accepted / 未修复：`capture_process_diagnostics` 用 `sys.exception()` 读取外层正在处理的异常，不能证明异常穿过当前 scope。独立 root one-shot 反例成立，裸 converter target 不可达，严重性低。owner 是 runtime scope；显式记录穿过 records-open/setup/yield 的异常，保首控制流优先和完整 cleanup，不在消费者补偿。
- C03 accepted / 未修复：runtime record validation 有两个相同字段谓词。owner 是 writer 的唯一验证阶段；删除投影死校验，保字段验证与 format/encoding 分类，不引新 bag、wrapper 或弱类型。
- C01 accepted / 未修复：两个 runtime 测试缺确定性 scope exit 实际等待及干净 flush 后外层 release 负例。owner 是测试；保真实 Condition.wait、真实 inner flush/lock，观察 wait 实际释放 Condition 锁并在释放 emitter 前断言无 footer/scope completion；release 故障仅外层，验证首对象与跨线程锁回收。

本轮范围预计仅 process_diagnostics.py 与两 runtime 测试。用户日志规则和 Docling + manifest 两项业务成功条件不变。三项一次集中修改，然后最终七文件、spawn whole coverage、full pyright 与 fresh 04 macOS focused PDF/XBRL 验收；所有 actualwait 失败保原件。

## 证据目录

`workspace/tmp/upload-material-converter-diagnostics-20261003/code-fix-sol-01/` 是本轮唯一新 scratch。旧证据/implementation/control/registry/环境只读。最终状态与验证将在本文件追加，未完成验证不得声明通过。


## 最终 fix 状态（本轮当前事实）

**C01/C02/C03 均完成本轮修复和全部授权验证；已修复，待总控同版双 re-review。不是 code review gate pass、accepted slice commit 或 final closeout。** 三项仍为原 S1、低严重度；不重开原统一修复。blocking=[]。下一入口仅 root 同版双复审。本轮 stop=true。

### Finding 前后实际断言

| Finding | 修改前直接事实 | 本轮修复和实际断言 |
|---|---|---|
| C02 | 外层 except KeyboardInterrupt、正常 body/cleanup 被 sys.exception 误重抛；root 独立 one-shot 原结果只读保留 | runtime 仅保存真正穿过 records-open/setup/body 的异常。四类外层已处理控制流独立 worker 均零抛、footer 完整；156 个 body/setup/cleanup×四类控制流优先级测试保首对象、真实流关闭/filter/class 恢复，包含 records-open/setup 首对象与后续不同 cleanup 对象。|
| C03 | 投影和 try_capture 重复校验，同一字段有效性存在双 owner | 删除 _project_record 死校验，仅 writer RECORD_VALIDATION 阶段验证。独立真实 source record 的 name/level/created/message 与读回逐字段相等；7 个坏字段均 record_validation、真实坏%d为 record_format、surrogate为 record_encoding；四类格式化控制流原矩阵保留。|
| C01 | scope 退出前 release/join emitter；waiter.is_alive 未证明实际 wait；release fixture 的首次异常在 stdlib flush 内 | 真实 scope exit 等待未完成 reservation，observer 必须见 wait 入口且取得被 stdlib wait 释放的真实 Condition 锁；release 前无 footer/scope 未完成，之后 records=[log,end]。真实 inner stdlib flush 正常返回后才在外层 release 抛四类原对象，跨线程真实锁可取得；首 format 四类控制流不被 ordinary/control release 替换。|

测试 observer 只在测试中调用真实 stdlib Condition.wait，不替换等待语义，不 global patch logging。必要敏感度负例分别省略实际等待、移除外层 release fault、恢复旧 every-release-throws fixture；最终均被正确断言抓住。最后一项暴露第一轮测试只有计数而不足以证明 flush 返回，已补 healthy_flush_count 并完整重跑，第一轮全部结果保留，不冒最终版本。

owner 合同原件：`workspace/tmp/upload-material-converter-diagnostics-20261003/code-fix-sol-01/owner-contract-evidence.json`，其中有真实 wait barrier 原件、4 外层零抛、156 清理优先级、release actual call profile 和敏感度负例、7bad/源字段读回；所有 worker 一例独立一次 capture，无同 process 多次 capture。

### 完整最终验证

- `source .venv/bin/activate` 后同七个完整 affected 文件 **889 passed / 6 skipped / 3 上游 deprecation warnings，actualwait exit0**；final 指 run02。run01 同889/6仅为补强断言前版本，原件保留。
- full pyright run02 **exit0、0 errors / 0 warnings**；run01也保原件，不代替final。
- 独占 coverage-run-02，显式 multiprocessing/parallel、禁用 pytest-cov；combine --keep **exit0**。三个完整生产文件：process_diagnostics **347/383=90.6005%**，log **198/210=94.2857%**，converter **404/445=90.7865%**；每个 excluded=[]。最终 **318 raw全保留：63 combined、255 duplicate-not-added、0 incomplete**；89 份当前路径/SHA绑定实际 spawned capture+target body 执行行。wait212与外层 release 错误赋值311实际覆盖。run01的318份raw独立保留，不混入final；历史1份未完成raw继续保原件，不假credit或反推中断原因。
- 根/Fins/tests README 各自职责已检查：本轮无新增用户接口、层间边界、测试分层或运行方式，原行为说明准确，**无需额外修改**。

### 本版本 fresh focused macOS 验收

复用既有准备根 `/private/tmp/dayu-cli-upload-material-diagnostics-20261003-s1-01`，运行前后43项 inputs/admin/cache 与源逐size/SHA比对、taxonomy ZIP全部entries再核；不重建或clean。91页PDF SHA `96de32a720641251b44c3e27e25ce2aa7ab035a15182b6260ef0ef06aa041dc0`。

NATIVE-DEFAULT/QUIET/LOG/ERROR-04 均真实CLI actualwait exit0，每次 Docling91页、Microsoft Corporation、source fingerprint、manifest v1/amended=false、同run Docling size/hash和主源登记均由仓储owner读回。四次公开stdout均848 bytes，仅业务；stderr0；quiet保业务。INFO log实际收到 MatchingPostProcessor WARNING（观察129，不作数量oracle），error筛WARNING；不固定Docling hash。default临时目的流按原CLI生命周期；业务成功仍只有 Docling生成+manifest登记，无诊断第三gate。

NATIVE-SIGINT-04 在本次child raw-open身份和libproc确证启动后仅signal本次CLI parent，actualwait130/canonical cancelled、无材料publication、公司独立事实保留。五case实际记录child wait后均libproc ESRCH；请求 diagnostics/dayu-docling目录与文件全回收。四次完整PDF仅留下上游空torchinductor_leo目录，明确保留且不当请求残留；SIGINT临时根完全空。

XBRL-REAL-NATIVE-04：unset全部coverage变量，11 tests actualwait exit0（无skip）。实际CLI成功，Mountain Lake Acquisition Corp.、源instance SHA `04a015790c25d5a5371117bc64100335e65bfe1b3acdb71b4f2240c97e09cdf1`、manifest v1、完整Docling/key_value_items由公共仓储读回。真实同worker内核probe descriptor=success，原work/diagnostics可写；workspace/private读取、parentlog/admin/runtime/taxonomy写入与network全部EPERM。原profile原件SHA保存，policy无修改/扩权；kernel/failure fixture work保留为测试证据，不冒产品残留。native测试PID为身份树根，实际11个parent/child来源绑定当前workspace5模块SHA，owned PID在wait后均ESRCH，真实product request raw路径回收。

所有real argv/stdout/stderr/log/result/actualwait/ownerreadback及parent/child路径SHA在 `real-verification-final.json` / `real-cleanup-final.json` 和fresh04原件。direct CLI Host Run/trace/memory为N/A；durable job store无list API，仅记录owner派生根实际空枚举，不伪造查询。不是旧802全重跑，原03case不计当前执行credit。

### 所有失败与证据界限

1. necessary-boundary-negatives-01 exit1：脚本缺仓库PYTHONPATH，独立worker导入tests失败、未进入scope；父harness读取不存在结果再失败。原script/stdout/stderr保留；首次child wait后未持久化PID/exit票据，不猜PID、不计验证credit。02补路径及先存actualwait再读结果，必要负例完成。
2. release-boundary-probe-01 exit1：四正例worker exit0；故意恢复旧inner-fault fixture仍通过计数断言，negative没有被拒，故harness失败。登记后补实际flush正常返回断言；probe02所有5独立case exit0、旧fixture被拒。补后整套test/cov/type全部run02重测，首轮成功不遮不足。
3. xbrl-real-tests-sandbox-04 exit1 / 5fail6pass：真实原件 sandbox_application_error=MacosSandboxError/Operation not permitted，并有 raw “sandbox initialization failed”。按本轮用户授权在显式权限原生环境新case重跑同11项；产品仍真实应用原deny-default策略，native11pass不覆盖原失败。

每条外层command argv/cwd/env/stdout/stderr SHA与actualwait/exit详见commands-final.json，下表逐次列出；nested敏感度与release worker逐actualwait票据在各独占子目录，PDF逐case也独立原件。中间失误属于验证harness/test断言，不归生产成功，不猜根因，不以最后0抹掉前错。

### 修改与只读边界

本轮只改 process_diagnostics.py 和两个 runtime tests；另外八候选文件SHA保持freeze。HEAD仍8009 checkpoint、dirty候选未提交。plan/acceptance/两审/总控裁决/implementation/runtime-prerequisite/control/registry及所有历史probe/失败/result只读。

12,278个既有WU/文档文件和97个旧03real artifact逐SHA未变；interruptible_process/macos_sandbox/两个registry仍同历史冻结SHA；174项恢复环境metadata逐绝对位置/version/SHA一致，本轮无pip/升级/rollback/locks/pyproject/venv显式写入。原CI准备来源43项保持只读同SHA，不宣另重跑全部旧CI内容。无subagent、commit/push/PR/merge/issue/comment/newbranch/worktree/clone/reset/stash/clean，未改main，未进review或后gate，无ps/pgrep/kill0或runner查询。

### Residual 分类

- **fixed in current slice**：C01/C02/C03、owner控制流和清理、必要敏感度、最终七文件/wholecov/type、README判定、真实focused/sourcefinal；状态已修复但仍待双re-review。
- **assigned to later work unit**：Windows/Linux验收由后续平台验收总控负责（用户明确延期）；独立registry WU由root按既有另gate链推进，本轮保持只读。
- **requiring new issue or explicit user decision**：Docling抽取准确性、quota、非标准独立Logger、逃逸daemon、实时/更强全局序和更强raw保证，由上游Docling/runtime或未来明确goal总控负责，outside当前目标，不扩张。
- 上游空torch缓存归上游runtime、outside本请求清理；保原目录，不将其升级产品缺陷。历史raw准确中断阶段仍unknown，不伪造强杀原因；本轮两个coverage run均0 incomplete，无不完整credit。

### 每次命令 actualwait

| 命令证据目录（全部本轮code-fix-sol-01下） | actualwait | exit | wall seconds |
|---|---|---:|---:|
| affected-tests-cov-final-01 | true | 0 | 354.225938 |
| affected-tests-cov-final-02 | true | 0 | 364.110622 |
| coverage-combine-final-01 | true | 0 | 0.119537 |
| coverage-combine-final-02 | true | 0 | 0.129966 |
| coverage-json-final-01 | true | 0 | 0.111073 |
| coverage-json-final-02 | true | 0 | 0.100958 |
| coverage-report-final-01 | true | 0 | 0.102452 |
| coverage-report-final-02 | true | 0 | 0.092370 |
| coverage-verification-final-01 | true | 0 | 0.421372 |
| coverage-verification-final-02 | true | 0 | 0.327172 |
| full-pyright-final | true | 0 | 37.509236 |
| full-pyright-final-02 | true | 0 | 37.769299 |
| necessary-boundary-negatives-01 | true | 1 | 0.124216 |
| necessary-boundary-negatives-02 | true | 0 | 10.271191 |
| owner-contract-evidence-final-01 | true | 0 | 0.039455 |
| pdf-matrix-04 | true | 0 | 171.376875 |
| preflight-01 | true | 0 | 1.638043 |
| real-cleanup-final-01 | true | 0 | 0.028783 |
| real-owner-verification-04 | true | 0 | 0.865221 |
| record-owner-probe-01 | true | 0 | 0.078134 |
| release-boundary-probe-01 | true | 1 | 0.584092 |
| release-boundary-probe-02 | true | 0 | 0.550090 |
| source-protected-environment-final-01 | true | 0 | 3.475750 |
| xbrl-real-tests-native-04 | true | 0 | 35.847236 |
| xbrl-real-tests-sandbox-04 | true | 1 | 24.346211 |

### 本轮三修改文件完整 SHA

- `dayu/runtime/process_diagnostics.py`：`47ed4b45a44aed212fe440347488f8bd7eded30088c81a9f2f68e5ad61c12f3d`（21774 bytes）。
- `tests/runtime/test_process_diagnostics.py`：`9b7749e0e9f0664d075232b0890372ea2da280825328f7d7f9ce73edc589da92`（33464 bytes）。
- `tests/runtime/test_log.py`：`84ea75e1e9caa5fb3f3427a49a8a7751895f84eb69c7743cc176eb5621330f5a`（41099 bytes）。

11文件完整source-final和tracked diff SHA见source-final.json/candidate-final-manifest.json；两个新文件SHA为全文，不冒HEAD包含它们。
