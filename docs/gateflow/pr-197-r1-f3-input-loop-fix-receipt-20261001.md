# PR197 F3 输入路径链接环修复交付核收

只接受候选实现和证据交付，F3-CR1-A1 最终状态待同版完整 code re-review。未经门禁的五源码不提交。

```yaml
setup_status: ok
agent_status: completed
tool_evidence: yes
tool_trace: complete
required_evidence: complete
canary_status: match
result_status: accepted
warnings:
  - actual model unknown，流没有模型元数据
  - collision run1 在依赖生成前误并发启动，失败原件保存，run2 按顺序恢复
  - item_48 提前读取不存在终态文件，后真实终态和退出文件恢复
evidence_gaps: []
retry_class: none
```

- runtime/provider/label：codex/gpt-6-sol/`pr197-f3-s1-input-loop-fix-sol-20261001-03`。托管7594已返回 outer0，111 行合法 JSONL，明确 turn.completed。root 核所有完成 command、file-change、非零事件和末消息；stderr 空。
- 原流和 canary 位于 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.Fnnmua`，真实 cat 读取、expected、报告和 last 匹配。此前两次 routing 失败仍保持原件，不回写通过。
- 正式报告 `docs/gateflow/pr-197-r1-f3-s1-input-loop-fix-20261001.md`，SHA256 `f08cc381270aac1a301eda9d175f5ff9280110cad180e0e23863d07ed7c626cc`。完整报告、临时 loop_acceptance/sitecustomize/evidence_audit、实际共享 owner 源码及相对五 original 的全部 diff 已实读。
- root 独立重算39 originals、34 readonly，全匹配；当前五源码逐项匹配最终 algorithm-default-audit/report SHA。实际改动只有共享 resolve helper 与 root/manifest/PDF/产物身份/四输出根复用；RuntimeError 转 ValueError 仅包 Path.resolve，cause 保持；OSError 和执行期 RuntimeError 不宽 catch。原 ASCII/samefile/算法/default/worker/cache/selected-only 规则保全。
- root 逐项检查287条真实模块 CLI 的 expected/actual exit 与独立 stdout/stderr/exit 原件，conversion guard 全部启动，无 sitecustomize 错误或 sentinel 触发。旧175命令/504断言、collision88/405、新loop24/189，共1098/287；旧909/263未削弱。内层49个0/3个1/235个2均按各用例预期，不声称所有 CLI exit0。新16负例具名中文环诊断、空stdout、无traceback；8正例exit0。16组 bytes/inode/link 前后记录逐项一致。
- 真环夹具为同目录相对双向 basename 链，两端真实 resolve 先证明 RuntimeError；root/manifest/record/out × 四入口全覆盖。执行期异常及 PermissionError 的同对象传播是明确 injection owner contract，不能冒称真实系统权限故障；合成缓存/stub 不冒称真实 Docling CI。
- 项目默认 pyright 实际783files/0errors/0warnings/exit0；显式临时配置11files/0errors/0warnings/exit0，六实际验证脚本+五 utils，include相对/exclude=[]。各最终验证 exit0且stderr空。未把 workspace 排除后的0files当通过。
- item_27 collision run1 exit1/依赖 assertions.json 尚未生成，原失败和22中间命令保 `collision-run1-failed-originals`，逐件 SHA root 重算匹配。item_24 原矩阵0后 item_41 顺序run2 outer0、405/88恢复。item_48进度查询cat缺exit文件为读取时序错误，后item_41和独立run2.exit0消除缺口。五 no-index whitespace1双流空是预期差异；普通 diff check0。无必要失败隐去、无源码为夹具时序修改。

README：utils 开发分析输入不在根 README 最终用户手册职责；无 dayu/tests 变更，无 README 改动。永久 pytest/coverage 按 AGENTS 的 utils 豁免，完整临时验收证据已核收。

Residual 保持 accepted plan：未证明的 fresh Unicode 别名、跨运行缓存来源/统计 quirk、执行期写盘和外部换链属于既有独立 owner/待 goal，不在输入环修复中扩规则。F3 仍需同版完整 code re-review→accepted slice→aggregate deepreview；最终 exact PR head 的 PR review/closeout 及所有修复后的真实 CLI CI/registry 尚未完成。
