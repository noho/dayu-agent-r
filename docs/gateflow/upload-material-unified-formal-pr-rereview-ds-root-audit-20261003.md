# 正式 PR197 集中修复后 DS 复审总控核收

## 生命周期、输入和覆盖

唯一 workspace `/Users/leo/workspace/dayu-agent-r`、分支 `codex/upload-material-oracle`；baseline HEAD44c1892e7361dba799154fc01b2a4dfe43407e75、main fac32ecbff9bfe792b63ee9667c8697826b631f4、index 空。fixed workspace 的 21 冻结输入末核全部匹配，8 source SHA 与实际成功 pyright 的 source 前后相同；当前远端 HEAD44 尚未包含本地修复。

label `upload-material-unified-formal-pr-rereview-ds-flash-20261003-01`，Claude runner / ds-flash；实际 stream model `deepseek-flash`，不采自报 `[1m]` 为模型身份。托管 session67104 已返回 outerexit0，不再 poll；61394 有效 LF JSON events，success/is_error=false/50 turns；canary 实际 Read 与 expected/report 精确一致。完整 49 tools/results（31 Read、17 Bash、1 Write）逐项核收；没有 tool is_error 不能推断没有内部非零。stderr 唯一精确 `[claude-code:unrecognized_model]` SDK 诊断归 warning。

实际带行号 Read 内容与冻结原件逐字比：491 行 delta、8 source 合计2022行，全部实际覆盖，无缺口。Read 多出来的 EOF 编号空行不是源码变化；总控初算法将虚拟尾空行误算 mismatch，按显式 EOF-only 规则恢复，保留该核收错误说明。完整基线41961行继承原审核收，不重读、重取或重跑。

原 report `docs/reviews/pr-197-review-20261003-132356.md` 全文核阅。持久身份、覆盖、完整 stream 双备份 SHA：`docs/gateflow/evidence/upload-material-unified-repair-20261002/formal-pr-rereview-ds-coverage.json`；完整工具轨迹：`workspace/tmp/upload-material-unified-repair-20261002/formal-pr-review-01/root-audit/rereview-ds-flash-full-trace.json`。

## 内层失败、恢复和声明收窄

- event10487 错写 base32ec...，实际 git128被后续命令0掩盖；同工具实际 HEAD/main 已正确，54792/59226/61013同源恢复，不能采错 ref。
- event12755不存在utils/AGENTS.md，ls2被后ls0掩盖；root AGENTS实际全文Read，是适用约束，无缺失嵌套指令。
- event28808将失败中间源码与修前HEAD44比，6项MISMATCH但script0；36123实际首票据/failed-source/HEAD44 originals、41034双streams与collector差别恢复正确基准。初版source不当finalsource，失败21typed-access错误仍完整保留。
- event36123错cwd的ls root-audit2被末cat0掩盖，正确完整路径已恢复；gitshow/hash管道不能凭末hash0宣上游均0，8原件实际SHA与已核guard一致。
- event41034两collector diff实际1为预期路径/mkdir差异，管道末head0，不采自报DIFF_EXIT0证明diff0；collector Popen.wait实际1/0、PID4925/4979、双stream/source SHA由原票据核。
- event48997 GitHub只读TLS实际1被echo0掩盖；54793同次只读重试实际inner0，head44/basefac/draftOPEN，未重取全量diff。
- event28809 **成功写出任务 own tmp 之外** `/tmp/claude-501/git-delta-actual.diff`。实际491行、SHA2f52f3f0f55a66f8ff2cbcedef5101ad6e379bdb37363d39dbafac65a00e305f，与授权冻结diff相同。它仅临时diff，无产品/Git/registry修改，原文件不删除；驳回“全部仅own tmp写入”声明。必要输入同源证据仍可采，不用重派抹去偏离。
- “所有备份原件全文读”过宽：部分仅hash/list；采实际31 Read与完整必要currentsource/receipt/helper读取。报告“所有非零均记录”过宽，上述总控补足，不宣中间均成功。

## 独立裁决

部分采纳 DS 报告：UPR-R01真实DoclingDocument类型＋直接iterate；UPR-R02 owner成功类型/嵌套owner类型与最小JSON视图替代9处裸dict签名，均已修。完整生产者字段、delete ratio必写、失败partial与成功complete边界已核。count_view cast当前只读取已有base/new counts，没有提前读取派生texts_delta；cast运行时恒等，无当前成立的新finding，不新增类型框架/运行时JSON门禁/微修复。原局部变量声明、旧schema异常行为不扩大本修复范围。

本次未重跑pytest/OCR/真实转换/XBRL/CLI；生产88源码同hash，671与2841/3skip及真实XBRL5pass按accepted同版证据继承。utils按AGENTS免tests/cov，不免pyright；全量pyright实际0已核，不再次重复。原用户裁决未改变。

剩余事项均已分类：MiMo同版复审及最终总控PR裁决属于本gate；accepted PR checkpoint/push/draft-PR-pass/final closeout属于后续固定gate；完整CLI CI和oracle/scenario登记属于WU后的独立阶段；Linux/Windows XBRL按用户延期。DS本路核收不表示PR或WU已经pass。

```yaml
setup_status: ok
lifecycle_status: ended
outer_exit_code: 0
structured_status: success
canary_status: match
tool_evidence_status: verified
result_status: partially-accepted
retry_class: N/A
controller_decision: accept necessary fix evidence; narrow unsupported assertions; await MiMo and final adjudication
```
