# Bash 安装入口增量：复审停点回执

本次按用户选择以 Bash 脚本安装到源码 `.venv`，由安装流程发布默认 `dayu-cli` 入口并配置所选 Bash/zsh 的 PATH，保持包版本0.1.5。Windows执行Bash需Git Bash或WSL，WSL属于Linux环境；当前实测macOS，未声称Windows/Linux全部依赖已实测。当前不是工程交付核收请求或安装通知。

## 精确版本与变更

- branch：`fix/public-original-read-r1-r3-20261020`
- 本地源码HEAD：`95beb85312712d55fea8febf8531dd8bbf63c143`
- 首轮完整审核：1856cf8d → 5c179fdc，22文件完整diff317031 bytes，SHA256 `1ea55eae804392dc80f6a1b08daf86caf84d8d907d048424834c41d7e76c6378`。
- 修复复审：5c179fdc → 95beb853，12文件完整diff126815 bytes，SHA256 `ca8b661594ae5f8f136179591f53698ab4ed126c97537b031ef6b0565555c788`。
- PR206仍draft/open，远端head1856cf8d97468423c6a3ece5558a312d31802b20；本增量尚未push或交付。main/base8bf8daec8a022fd705e6cfe32c4283605f1fe6ca。

主要文件为 `scripts/install-source.sh`、只读身份/metadata核验 `scripts/install_source_query.py`、对应安装测试和根README/testsREADME。处理旧入口且保全旧目标、重复执行、正常SHELL/PATH、CDPATH、目标venv身份选锁、源外隔离metadata、普通shell裸命令与help退出。业务dayu源码、版本声明及依赖未改，保留原R1–R3和0.1.5有效证据。

## 已完成的验证与审核

gpt-6-sol修复writer真实外层/runtime0/0；92安装测试通过，helper106 statements/4 miss、96%，全量pyright839文件零errors/warnings/infos，bash-n/help退出0。全依赖真实pip的fresh/legacy各安装及重复共4次，metadata/shadow/normal-ic/-lic合计20个delivery子进程均退出0；494实际输入四位置字节一致，旧树含根目录前后两次相等。全部发生于隔离HOME/源码副本，未执行真实live安装；早期失败/无效探针已保留并纠正，不当成功证据。

首轮MiMo与DS完整审核均已结束并由主控采纳C1–C6必要修复。修复版MiMo91314外层/runtime0/0，完整报告 `docs/reviews/code-review-20261020-214553.md`；逐项认可六项修复，无新material finding，独立96项受影响测试、helper96%、pyright839零诊断、Bash语法/help均通过。

修复版DS82588外层/runtime1，377.102078秒，final：`Failed to authenticate. API Error: 403 The package is disabled or you do not have invocation permission. Please check the package status in the console.` 原始terminal标签success伴is_error/api_error，不能当审核pass。无Write/Edit报告事件，无durable复审报告。两路现均已退出，未擅自换模型或盲重试。

## 证据路径

- 修复回执：`docs/gateflow/public-original-read-r1-r3-20261020-install-entry-bash-code-fix.md`
- 主控裁决：`docs/gateflow/public-original-read-r1-r3-20261020-install-entry-bash-code-adjudication.md`
- 真实安装/测试/快照：`workspace/tmp/install-entry-bash-code-fix-20261020-210107/`
- 当前审核主目录：`workspace/tmp/public-original-read-r1-r3-20261020/install-entry-20261020T101200Z/`
- 该目录 `controller-code-fix-readback.json`：主控重核8 writer文件、494输入四位置与20退出。
- `bash-code-rereview-version.json` / `bash-code-rereview-full.diff`：精确复审对象。
- `bash-code-rereview-ds-flash.jsonl` / `.stderr`：DS原始403/真实退出，无有效复审结论。
- `bash-code-rereview-mimo-flash.jsonl` / `.stderr` 与上述MiMo报告：成功复审。
- `stop-pr-facts.json` / `stop-evidence-fingerprints.json`：远端draft事实及停止时源码/报告/log指纹。

## 停点、风险与后续

current gate / next entry point：受影响面re-review。C1–C6实现与单路复审支持已修复，正式双路终裁尚待DS。gateflow要求“必要独立 review 已完成”，本任务用户明确指定MiMo/DS双路，当前证据不足以放行。本线不push本增量、不宣称PR交付或可用、不sync、不merge。

DS服务恢复或替代审核路由需外部状态改变/明确用户裁决；不自行降低门槛。恢复后对同95冻结版补第二路，未变MiMo和验证可复用。双路满足后完成裁决及同PR206交付核对，工程核收且收到明确安装通知后才按更新README真实sync；merge仍另授权。项目调用方环境核验不属本线。

Linux/Windows、跨架构及其他Bash版本、wheel user-site全矩阵和并发profile写等为安装维护者后续有具体需求再验证的工作单元，不声称已过。真实自身安装证据由后续已授权但尚待核收通知的安装阶段提供。无额外业务回归/调用方核验门槛。所有原历史记录保留。

## 停点通知回执

已重新原生discovery并核portfolio-manager-v2-0:1.1的title、node命令、项目cwd及Codex界面；同任务follow-up未clear。`tmux-cli send`实际exit0；随后wait_idle超时exit1，capture exit0明确显示完整停点报告已进入目标会话，项目协作助手正在核对证据与路由规则。超时不作核收/批准，当前尚无恢复DS、替代路由或安装通知。`tmux-cli status`虽打印通用remote-cli-session提示，原生session列表确认未创建该session。实际命令、退出、发送正文和捕获保存于审核目录 `stop-report-message.txt`、`stop-report-send.json`、`stop-report-wait.json`、`stop-report-capture.json`。

## 用户授权 DS Codex 接续（保留原403历史）

用户明确确认原ds-flash Claude额度耗尽，授权改用 `codex-agent-run --provider ds-flash --cwd /Users/leo/workspace/dayu-agent-r`，补同95冻结版第二路受影响面复审，不改变审核范围、版本0.1.5及先工程核收通知再安装边界。新的独立任务书显式禁止读取同轮MiMo报告/日志及主控后加结论，要求独立直接证据判断、逐项C1–C6状态与durable报告；原403及停点记录保持。派发前HEAD95、8writer文件manifest和完整126815字节diff均实际重核相符。新调用实际已启动，会话36382；独立输入/日志/最终消息目录 `workspace/tmp/public-original-read-r1-r3-20261020/install-entry-20261020T101200Z/ds-codex-continuation-20261020T145955Z/`。current gate保持受影响面re-review，收齐真实退出与完整结果后裁决；旧停点是历史，不表示本次接续完成。

## 本停点已解除（仅审核接续）

用户授权ds-flash Codex替代调用后，同95版本第二路实际0/0完成，报告 `docs/reviews/code-review-20261020-230343.md`，C1–C6均已实质修复。主控已读取完整答复/报告并终裁，双路review-pass；原403与本停点记录保持为历史。当前进入同PR206工程交付链，真实安装仍待工程核收及明确通知。详见control与bash-code-adjudication末节，不把本节理解为已安装或merge。
