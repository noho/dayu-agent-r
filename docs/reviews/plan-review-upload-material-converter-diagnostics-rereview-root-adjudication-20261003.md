# 诊断计划同版复审：总控裁决

两路已取得真实 managed exit 0：MiMo 42 calls/results，ds-flash 37 calls/results。两份报告分别 `docs/reviews/plan-review-20261003-185739.md` 与 `docs/reviews/plan-review-20261003-190419.md`；两路源身份、报告SHA、完整轨迹、普通工具错误/嵌入式错误恢复、canary均总控核验并双份私有保全。actual backend事件名为 mimo-v2.6-pro / deepseek-flash；SDK配置诊断的 [1m] 不是独立后台上下文能力证明。

## 已有 findings 状态

当前计划 SHA 33c00f8543a42c438e315f3294e8f8399cee972722b49ab55bde2bb041d6a141。DN-R1..DN-R6、DN-D0、控制流补充均**已修复（计划级）且双路同版复审验证**；不宣产品实施或覆盖率80已经通过。

## 当前阻塞：DN-R7

总控独立真实handler负例发现 StreamHandler.emit/handleError 的公共stderr逃逸，已登记 accepted / 未修复，见 `docs/reviews/plan-review-upload-material-converter-diagnostics-parent-handler-finding-20261003.md`。因此两审 pass 不等于当前 Gateflow plan pass。下一入口是 gpt-6-sol 集中补足父投递契约，同一个S1，之后只对新delta双路复审，旧相同字节证据复用；没有 plan commit 或产品修改。

## 非阻塞措辞：实施前集中收紧

DS OQ1：healthy已取得reservation的emit必须完成，只有真实格式化/编码/媒体fault可drop，不能因CLOSING任意丢诊断。OQ2：仅持writer引用但未取reservation者走原raw路由。OQ3：records打开失败仍装faulted writer/drop；只能保证父可观察不完整，不假承诺媒体坏的自报。

MiMo OQ1：明确唯一读策略：require_complete=True先流式严格校验完整structured spool（含end/footer后无内容）再回读yield；False流式yield合法完整前缀，遇残缺或非法内容抛typed transport error。无模式可把诊断完整性变业务成功门槛，父普通错误仅safe secondary。固定内存/无全量缓存，不改业务descriptor。MiMo OQ2：pre-footer额外raw handle普通close/flush故障统一scope_flush code；post-footer无carrier不承诺自报。以上是已决诊断内部合同收敛，不新增业务oracle/更强留存保证，不新slice。

当前 gate=plan fix；next=新delta同版双re-review→acceptedplancommit→一个S1实施。原unifiedrepair/frozen802/两个旧registry/main不动。跨平台验证仍用户延期；抽取质量上游；所有outsidegoal仍仅未来明确决定，不冒授权laterWU。
