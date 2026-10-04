# PR197 F3 输入链接环审查裁决

## 当前结论

F3-CR1-A1，**低 / accepted / 未修复**。属于已批准F3输入owner及原计划中文输入拒绝合同的必要修复，不创建独立WU、不新增业务oracle。仅修输入路径解析的链接环异常归属；不扩大到执行后mkdir失败、链接事务、缓存鉴权或全Unicode文件系统规则。

当前MiMo65815仍在途，不能先判整个code gate；Kimi87199已outer0、42turns JSON success/is_error=false，模型metadata kimi-k3[1m]，报告 `docs/reviews/code-review-20261001-102054.md`。本artifact即刻登记已成立修复，待两路终态及完整核收后合并fix任务。

## 直接证据与合同

- 已接受739行plan“路径与输入错误”规定操作者输入不可用在执行前以中文argparse错误2拒绝。新loader明确声明OSError/ValueError失败；四main通过这两类接入输入拒绝边界。
- `analysis_sample_inputs.py` 的root/manifest/PDF解析以及四main out解析调用Path.resolve；Python3.11链接环抛RuntimeError，逃离输入边界。不是Docling内容错误或分析算法失败。
- root独立四模块实际CLI：有效合成PDF路径/manifest、仅out组件构成真正两向链接环，均exit1＋英文RuntimeError traceback，无业务目录/产物/转换。完整命令双流与退出在 `workspace/tmp/pr197-controller-collection-20261001/f3-out-root-loop-probe/commands.json`。
- Kimi独立报告同根因并补root/manifest/记录路径面。root实际重算35当前+35review原件+4初始原件+5fix前原件，共79身份匹配；报告本轮随机读取凭据与基准相等。

纯症状证明不替代owner判断：Path.resolve调用边界拥有“输入路径无法解析”事实，须将精确链接环RuntimeError链接为中文具名ValueError，交既有main的输入错误处理；不能在main加入宽RuntimeError分类覆盖分析阶段异常，不能吞掉错误或修改输入以成功继续。多入口共用该输入解析事实时复用单一helper，不四份重复异常语义。

## 实施边界及验证

沿既有F3-S1五utils、输入共享helper和全部原算法/参数/缓存合同；具体最小方案由Sol按已接受计划及本必要fix裁决实现，有新业务/公共规则变更需求再交root，不自加新goal。目前代码零修改、同版双审输入字节保持。

补真实CLI的root/manifest/record/out链接环中文exit2/零业务副作用；旧完整909断言/263子命令及C01/C02保留，最终显式临时类型+默认全量pyright同版0；utils永久pytest/cov仍免，不机械新增永久镜像测试。修后MiMo/Kimi同版复审及root再裁决才可accepted slice。

## Kimi证据可见性与执行偏差

Claude只有完整汇总JSON，没有逐工具轨迹。报告自述的8项抽查及4项临时探针未在独占tmp目录留下可核验日志（root实际目录为空），不作为“root已核收实跑”证据；本finding成立依root独立四CLI、实源与已接受合同。其余审查意见仍须结合MiMo与root实源核查，未因JSON成功判code gate pass。

报告如实记录错误相对symlink夹具触发一次Docling转换尝试，合成字节在解析入口拒绝，声称无OCR/网络/模型下载；完整逐调用轨迹不可得，root不独立认证这些可见性之外的断言，不计为真实转换CI通过。后续验证必须显式拦截转换，在触发病态输入前核对真实链接环；不重复该错误夹具。此处为任务取证偏差，不修改产品oracle或扩大真实CI范围。

已有dangling-out mkdir I/O Open Question保持非本必要fix范围，不按“链接”名称相同扩张输入规则。先前大目标约束中本root观察的candidate状态由本正式裁决更新为上述accepted修复；最终真实CI/registry收口照用户约束继续。
