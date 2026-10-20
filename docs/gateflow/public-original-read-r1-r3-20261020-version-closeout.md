# PR206 0.1.5 版本增量工程交付

## 实际变化与状态

同一 draft PR：https://github.com/noho/dayu-agent-r/pull/206 。分支 `fix/public-original-read-r1-r3-20261020`，base `8bf8daec8a022fd705e6cfe32c4283605f1fe6ca`。版本增量工程完成；安装未执行，等待 portfolio-manager 核收增量并明确通知。merge 未授权，PR保持draft/open。

唯一版本定义为 `pyproject.toml:7` 的 `[project].version = "0.1.5"`，由 setuptools 生成发行 metadata；没有新增 `__version__`、CLI version flag 或平行真源。隔离 wheel 测试核对真实 Name/Version 与声明同源、入口target不变。真实CLI测试仅去掉历史写死包版本比较并说明metadata观测边界，原源码路径、七个producer路径/hash及下载语义断言完整保留，避免把baseline代码身份与当前安装包版本混同。

R1–R3工程原head f854a6e6已由项目助手核收，源码复审f7eee0c5；本增量未改生产Python。原业务验证、原始返回和风险证据按已核收范围保留，未重开未变部分。版本增量最终复审源码为 `398afb641849e8673c0398f440838eacb8b2e55e`，其后只有审核/控制/历史提示等文档变化；最终交付OID及完整远端补丁见后述final回执，避免文档提交自引用。

## 验证与审核

修复后实际受影响测试退出0：4passed、2个真实SEC网络用例因未opt-in明确skip；不声称网络验收。全量pyright退出0、0errors/0warnings/0informations。真实wheel为dayu-agent/0.1.5，公开入口仍为dayu-cli = dayu.cli.__main__:exit_module；478包文件等于保存源码，484wheel成员与独立tracked全树构建逐字一致。895源码/测试/配置准确快照对被审398afb64及交付时工作树全符；原15份自身安装/源码metadata文件集合及指纹未变，实际安装记录仍0.1.4，不能将wheel或源码影子metadata当安装成功。

详细实际命令、双通道、退出、来源和保存版本见[version-fix](public-original-read-r1-r3-20261020-version-fix.md)，原始证据位于 `workspace/tmp/public-original-read-r1-r3-20261020/version-fix-20261020T085324Z/`。首版临时探针失败及修正、原生工具错误全部保留，不伪称所有尝试一次成功。

首审DS163643提出V1，MiMo164952将同一已知误拒列后续风险；主控接受V1并修复，不给baseline新增metadata框架。双路窄复审DS170445（83969，0/0 success271.580271秒）和MiMo171452（56884，0/0 success984.882153秒）均确认V1已修复、无实质新问题；完整报告及final已读，最终裁决见[version-adjudication](public-original-read-r1-r3-20261020-version-adjudication.md)。无未修accepted、needs-more-evidence或blocking open question。MiMo所说全部命令0限定为最终有效验证；raw中两次shell分隔符`==`错误和一次临时证据字段读取错误仍保留，未用于放行结论。

## 文档与交付核对

tests README更新现有包测试与真实CLI provenance职责。根README的最终用户安装命令/入口/工作流不变，未机械增加固定版本或内部流程。初版version-implementation原正文保留且加纠正提示，准确旧字节可从090eb4f5取回；当前方案与纠正回执在version-increment/version-fix，原独立报告不改。

PR title/body已按真实R1–R3加0.1.5范围更新，无关联GitHub issue（来自本地handoff），不创建issue/comment。初次增量交付核对已通过：head d2977b12ce9f73ae7a116294ec5ab647f4b45037，base8bf8daec，72文件完整GitHub补丁835799字节，SHA256 `679bfe4a01540eb7a58bb7a1f5e341219259fb10d04f44b11da2beb7f663819c`；GitHub/local全部hunk范围/mode/content相同，仅index hash缩写与hunk尾标签格式不同，两份raw均保存。精确repo/headrepo、draft/open、前后OID、title/body与远端push均核符。main受保护但required checks为空，无workflow/check run/status context；不声称远端CI执行，必需本地检查已满足。

初次回执：`workspace/tmp/public-original-read-r1-r3-20261020/pr-delivery-verification-version-initial.json`。本closeout审计记录提交/push后再对最终精确head/base重复交付身份/完整diff/CI/push核对，最终事实以 `pr-delivery-verification-version-final.json` 与其raw `pr-compare-version-final.diff` 为准，不重开代码审核。工程增量进入final closeout pass，实际推送与最终核对结果和停止通知一并报告。

## 版本查询与安装接续

发行声明：`pyproject.toml [project].version`。在需要核对的自身安装解释器下，标准查询为：

```bash
source .venv/bin/activate
python -I -c 'from importlib.metadata import version; print(version("dayu-agent"))'
python -m pip show dayu-agent
```

`-I` 排除cwd/PYTHONPATH的源码egg-info影子；还应报告安装位置与metadata来源，不能只看当前目录默认查询。当前未安装0.1.5。获增量核收和明确安装通知后，按根README从核收的精确源码执行安装，仅交自身命令/退出/commit/安装位置/实际安装包版本与dayu-cli --help。sync成功需实际包0.1.5且对应核收源码；本线不查调用方环境或live入口，不重复业务回归，不增原用例/LLM出站门槛。项目实际live关联由portfolio-manager核对，merge另授权。

## 剩余风险与owner

- 实际0.1.5安装检查：covered by later approved slice；owner本线及portfolio-manager安装接续，等待核收增量与明确安装通知。
- SEC真实网络矩阵：assigned to later work unit；owner Fins真实CLI验收负责人，后续显式安排，非本线sync门槛。
- 隔离构建输入清单未来扩展：assigned to later work unit；owner CLI packaging test维护者，在实际构建配置扩展时同步核验，当前无缺件反例。
- 原S1真实供应商接受度：assigned to later work unit；owner Provider/Engine与portfolio-manager，调用方后续补验，既有非阻塞defer不变。

下一入口：使用tmux-agents fresh discovery核对title为portfolio-manager的项目协作助手后，报最终commit/版本定义/查询/验证/证据及未安装停点；等待增量核收与明确安装通知。
