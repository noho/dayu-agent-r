# 父投递计划集中修订：DN-R7 与已决非阻塞措辞

任务：`upload-material-converter-diagnostics-plan-fix-sol-20261003-02`。当前 gate 仍为 plan fix；本产物是候选修订完成记录，不是 plan acceptance、产品 pass 或 accepted gate。总控持有所有 gate；本轮到此停止，下一入口由总控安排新 delta 的同版双 plan re-review。

唯一 workspace `/Users/leo/workspace/dayu-agent-r`；branch `codex/upload-material-oracle`；HEAD `79977b3a52f8566672e3b462f786f1004dfd3f89`。输入 SHA `33c00f8543a42c438e315f3294e8f8399cee972722b49ab55bde2bb041d6a141`；新版 SHA `cbd771224d4fc88bcafa6a03c8e786d4e1cef6dc22e15937ed38d7dc73461709`。root 裁决 SHA `318649e9701f3caad2497e0c221ed4f37a98e23890bb21dd3a52c337752e1950` 已匹配。

CANARY=gpt-6-sol-c6cca620

## 判断与唯一 owner 方案

DN-R7 动机成立：新 root finding 的真实 probe/stderr 与现有 `_build_marker_handler` 及 Python 3.11 stdlib 源码同源，普通 StreamHandler.emit 自行 catch Exception 后 handleError，已复现公开 stderr 878 bytes。helper 外层 catch 不能阻止它。原 root finding 保持 accepted / 未修复，不回写历史裁决；这里只提交计划候选修复，待同版复审与总控核验。

§4.1 规定唯一最小方案：现有 runtime 日志 owner 的 marker handler 换为私有 typed StreamHandler 子类；专用 `try_deliver_process_record` 只用于转换诊断，使用该实例原 level/filter/formatter/stream 和 stdlib 锁，不走 emit/handleError。普通调用仍继承原 emit。helper 只选 namespace 唯一 typed owner，缺失或非唯一返回 False，不触 root/lastResort/第三方 handler；此处关闭原“未 configure 走 stdlib”公共 stderr 逃逸。marker 属性值/原去重、source_name/level/created、selector 映射、目的地与格式保持。无全局 raiseExceptions 改动、无 monkeypatch、无 CLI 过滤、无第二套 selector policy。Python 3.11 类型 base 的 TYPE_CHECKING alias 是运行类不可下标化所需静态声明，不是兼容接口。

普通 format/write/flush 故障返回 False，Fins 不兜底、不重试、不回写 outcome；控制流不在普通 Exception containment 中，同对象传播。§5.2 保原结果与 cleanup 优先级；§6.1 要求未来真实 configure owner 的 stream/formatter 负例和真实 converter 业务联验。仅现有 owner，原三生产 allowfiles 不扩大；§5.1 的 handler 身份指原 marker 装配/去重身份，内部子类换型不改该身份。

## 精确措辞收紧

- DS OQ1，§4.2 项7：healthy 已 reservation 的 emit 必须追加，CLOSING 本身不准 drop；真实投影/编码/spool fault 才按既定 incident/transport 缺口处理。
- DS OQ2，§4.2 项8：只有持 writer 引用但未 reservation 而被关闭态拒绝者走 raw；已 reservation 者不转 raw。
- DS OQ3，§4.2 项1：records 打开失败仍装 faulted writer capture 并 drop；parent 可观察缺 carrier，介质坏不承诺完整留存或逐项自报。
- MiMo OQ1，§5.2：True 先固定内存流式严格完整校验再回读 yield；False 流式 yield 合法前缀，残缺/非法内容抛 typed transport error。无模式提升业务成功门槛。
- MiMo OQ2，§4.2 项8：pre-footer Python stdio/额外 raw handle flush/close 普通故障统一 scope_flush；post-footer 无 carrier 的既有可观察保证不变。

仅上述 §§4.1/4.2/5.2/6.1 变动，自动比较证实其余字节相同；保留一个 S1，不微切、不重设计 DN-R1..R6/D0、不引入新业务 oracle。未改其它 sections、draft 名、历史快照、生产、tests、README、registry/locks/control 或 frozen source。

## 实际验证、错误与未覆盖项

输入全文/最终全文、SHA、精确 diff、source SHA 与结构化结果都位于 `workspace/tmp/upload-material-converter-diagnostics-20261003/plan-fix-sol-02/`。`parent_delivery_proof.py` 是专用方法 stdlib 小证明：借用真实 configure 创建的 handler 的 level、同一 filter/formatter 对象，但候选实例不安装到 logger，故不宣真实新增生产 owner 已实现。三项真实普通 write/flush/Formatter 故障均 False，公共双流 0 bytes；四类控制流仅对真实 write 路径证明同对象传播；healthy 原字段与一次写入、error/quiet 正常拒绝 True 通过。logging.raiseExceptions 原值不变。proof exit 0；激活 `.venv` 后局部 pyright exit 0，0 errors/0 warnings（另有工具版本更新提示，未修改 venv）。业务 outcome 仅调用者保持的模型检查，不是 converter/publication pass；未做跨线程锁释放证明或其它控制流阶段配方。

实际工具错误均保留在 result：typeshed 猜定位置读取不存在（rg exit2），改以局部 pyright 实测 typed base；独占输出目录已由上游建为空，mkdir exist_ok=False exit1，检查为空且 plan SHA 未变后使用该目录。根 probe 原漏 debug_stream 的 TypeError 是输入证据自身历史，不是本轮重跑。没有重跑旧 coverage/closure/8 控制流配方或旧 diff。

未运行产品 pytest/full pyright、真实 CLI、Docling、provider/network、coverage 或 spawn collector；未 commit/push/PR/merge/创建分支/派发 Agent。真实业务 outcome、完整生产每文件 ≥80% 与真实 spawn collector 保留为原一个 S1 的未来 gate，不降标。跨平台仍是用户既有延期。所有未验证产品项 owner 为后续获总控批准的 S1；同版双复审 owner 为总控，尚未执行。

## 输出定位

- 本轮新 fix artifact：`docs/gateflow/upload-material-converter-diagnostics-parent-delivery-plan-fix-20261003.md`。
- `result.json`：finding/措辞映射、changed files、proof、源 SHA、工具错误恢复、no-product 与下一入口。
- `input-plan.md` / `input-plan.sha256`、`final-plan.md` / `final-plan.sha256`、`final.diff`：完整候选与精确变更。
- `scope-verification.json`、`source-sha.json`、`proof-result.json`、proof 命令 stdout/stderr/exit 与局部 pyright：本轮验证证据。

本轮停止条件已完成；没有 plan acceptance，DN-R7 最终修复状态留待 re-review/root 裁决。
