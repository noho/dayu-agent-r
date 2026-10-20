# PR206 源码安装默认入口增量交付

工程增量已通过双路完整审核、必要修复与双路受影响面复审，并完成同draftPR206总控交付核对。包版本保持0.1.5。当前是工程交付，尚未真实sync，须portfolio-manager核收并明确通知安装；merge仍另授权。

## 改动与使用

新增 `scripts/install-source.sh`（Bash3.2+）编排现有venv/pip/平台constraints，README从源码安装入口改用该脚本。无需先activate：macOS zsh执行 `bash scripts/install-source.sh --shell zsh`，正常Bash用 `--shell bash`。脚本安装到本源码 `.venv`，由流程发布 `~/.local/bin/dayu-cli` 并配置所选shell启动PATH，最后以新正常shell `-ic/-lic` 裸命令/help及真实metadata校验成功才报完成。Windows须Git Bash或WSL；WSL安装于子系统。现有锁仅macOSarm64/Linuxx64/Windowsx64，其他组合写前拒绝，不能推成所有平台实测通过。

默认入口、安装来源及版本owner明确：Bash安装编排负责venv/pip/有限入口与profile发布；只读stdlib helper验证实际pip解释器Python3.11/位宽/OS/arch、真实dist-info/editable/module/console同源，唯一版本声明仍 `pyproject.toml [project].version = "0.1.5"`，不新增CLI版本参数或第二份安装数据库。正常PATH只去明确venv污染，保留正常工具和合法homebin；旧入口symlink只替换目录项、保全目标，可完整重复安装。未知普通入口/必要路径symlink/特殊file/profile冲突写前拒绝；不删除其他工具环境，不更改调用方配置。

根README同步用户安装/默认入口/链接限制/Bash启动文件/副作用/可选浏览器安装与wheel同目标检查；testsREADME同步安装边界与无参pyright，配置纳入helper。不触业务分层；dayu/其他架构README无职责变更触发。原R1–R3完整原文与业务判断边界、storage snapshot/processor/read runtime唯一真源不变。

## 实际验证与版本绑定

已审安装源码：`95beb85312712d55fea8febf8531dd8bbf63c143`，branch `fix/public-original-read-r1-r3-20261020`。首轮完整审核为1856cf8d→5c179fdc；C1–C6修复复审为5c179fdc→95beb853（12文件完整diff126815 bytes，SHA256 `ca8b661594ae5f8f136179591f53698ab4ed126c97537b031ef6b0565555c788`）。后续提交仅审核/交付记录，最终PR精确head由下述final回执记录；不将后续文档commit冒充源码复审OID。

- gpt-6-sol作者：92安装测试通过，helper完整文件106stmt/4miss96%，全量pyright839文件零诊断，Bash语法/help0。
- MiMo独立复审：96项受影响测试通过，helper96%，pyright839零诊断；DS Codex独立复审：92项安装测试通过、helper96%、pyright839零诊断，Bash与有效normalPATH反例通过。所有必要检查均按要求先激活现有venv运行，未借此作真实安装。
- 隔离HOME/完整源码副本真实pip含依赖，fresh与legacy各安装及repeat共4次；另4metadata、4shadowmetadata、8新正常shell-ic/-lic，共20交付进程实际exit0。metadata为真实0.1.5 editable，与脚本/helper/module/console/源外查询同源；假cwd/PYTHONPATH/PYTHONHOME/999metadata影子不影响。不是no-deps、fake安装或借live site。
- 494实际安装输入×当前/保存快照/fresh/legacy四位置逐字相等，8writer文件匹配manifest/被审blob；合成旧树含根目录前后两轮字节、权限、mtime及路径/链接指纹保全。作者、MiMo、主控均实际核验适用范围。
- 原失败和无效反例保存，明确INVALID的缺Homebrew探针/早期struct注入负例不作证据；shell-wrapper实际exec本机Bash3.2.57，不声称Homebrew5。README平台受控分支不冒充跨OS真机。

原R1–R3/0.1.5已核收版本与有效证据保留：业务dayu源码相对f7eee0c5无变化，版本声明/依赖不变；895版本快照、原真实读取/完整ASML证据按实际范围适用，未重跑或伪称新增业务验收。上次1856cf8d按原README仅本线venv安装和项目方后来人工改默认链接是历史，不能当本脚本已在真实HOME运行。

证据：作者回执 `public-original-read-r1-r3-20261020-install-entry-bash-code-fix.md`，实际命令/快照 `workspace/tmp/install-entry-bash-code-fix-20261020-210107/`；主控494输入/8writer/20退出重核在审核主目录 `workspace/tmp/public-original-read-r1-r3-20261020/install-entry-20261020T101200Z/` 的 `controller-code-fix-readback.json`、`ds-codex-continuation-reused-evidence.json`。原始日志可回取，不用hash代替版本快照。

## 审核、裁决与风险

完整首审报告204535/204928，修复版MiMo报告 `docs/reviews/code-review-20261020-214553.md`，用户明确授权ds-flash Codex接续报告 `docs/reviews/code-review-20261020-230343.md`。DS新调用真实外层/runtime0/0、turn.completed、267.137095秒；完整final及报告均已读取，独立上下文未读同轮MiMo结论。原Claude因额度耗尽403/exit1记录不覆盖，不当审核pass；新日志/最终答复与完整调查失败回执在审核目录 `ds-codex-continuation-20261020T145955Z/`。本线按直接证据裁决，不按多数票。

C1实际解释器锁同源、C2正常shell/PATH、C3CDPATH、C4用户文档链接/启动文件、C5pyright唯一scope、C6exe平台策略均accepted/已修复，已由两路实质复审核销；BP1a/BP3a/旧DSF1维持已修复。无accepted未修、needs-more-evidence、blocker或blocking Open Question。详见 `public-original-read-r1-r3-20261020-install-entry-bash-code-adjudication.md`。

| 未覆盖/风险 | 分类 | Owner / destination |
| --- | --- | --- |
| Linux/WSL/native Windows真机、跨架构/32位、真实其他Bash/TTY、wheel-user-site整轮矩阵 | assigned to later work unit | 安装维护者；有具体runner/复现时验证，不声称已过 |
| 未知rc配置、并发profile写、PATH完全unset退化输入 | assigned to later work unit | 安装/init维护者；具体正常使用需求后接续，当前退化输入写前失败 |
| 部分失败无跨文件事务、PATH优先级、源码移动失效 | fixed in current slice | 安装owner阶段错误与用户手册已诚实披露，不新增回滚框架 |
| 自身真实sync、精确源码/metadata/默认入口/help验收 | covered by later approved slice | 本线主控；工程核收并明确通知后才执行，调用方环境不属本线 |
| 原S1供应商接受度 | assigned to later work unit | Provider/Engine owner与项目协作助手后续补验，不新增安装业务门槛 |

## Draft PR 核对与下一入口

Draft PR：[PR206](https://github.com/noho/dayu-agent-r/pull/206)，保持open/draft，未merge。初次实际交付head `11e41db41a3087077ae41e9ca5a7f99a7a2b98fc`，base `8bf8daec8a022fd705e6cfe32c4283605f1fe6ca`，repo/headrepo均noho/dayu-agent-r；完整99文件/1308222字节remote compare与本地patch全部hunk/权限/blob索引一致，仅index缩写/hunk尾标签格式不同。title/body、前后OID、最终push、源码与95对应关系均实核通过。main protected但required checks空，无远端CI/workflows，不声称CI执行。

初核 `workspace/tmp/public-original-read-r1-r3-20261020/pr-delivery-verification-install-entry-initial.json` 已通过。此closeout与control记录提交/push后，再实际生成 `pr-delivery-verification-install-entry-final.json` 记录最终精确交付commit及完整diff、OID/push/CI再核；最终回执不再以Git提交改变自身指向，避免自引用循环。此后若核对失败必须停在交付核对，不以本段预告当成功。

本任务为本地上游handoff，无指定GitHub issue；issue link/closeout comment不适用，不擅自创建或评论。工程work unit在初核后已完成draft-PR-pass/final closeout，最后必要文档commit的再次核对完成后通过tmux fresh discovery核portfolio-manager身份报精确交付版本。next entry point是项目方工程核收与明确安装通知；然后本线按更新README负责自身默认入口安装、实际metadata位置/版本/源码绑定及新正常shell裸help真实退出回执。禁止在通知前sync；不核调用方项目入口，不以PR merge作安装先决条件，merge本身仍需另授权。
