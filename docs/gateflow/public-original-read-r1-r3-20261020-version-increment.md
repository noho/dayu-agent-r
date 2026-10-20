# PR206 包版本 0.1.5 增量

## 授权与目标

用户已核收 R1–R3 工程 f854a6e6ff3e3a1cee24745eaae96148843d6401，直接确认本增量：在同一 PR206 将 dayu-agent 包版本 0.1.4 升至 0.1.5，以实际包 metadata 查询；不新增 CLI version flag、平行版本真源或业务改动。安装须增量核收后再获明确通知，merge 另授权。通知历史保留在 authorization-update.md。

## 直接证据与最小计划（主控核对通过）

preflight：工作分支 fix/public-original-read-r1-r3-20261020，HEAD f854a6e6ff3e3a1cee24745eaae96148843d6401，初始工作树干净。pyproject.toml [project].version 当前0.1.4为唯一版本定义，setuptools.build_meta产出distribution metadata；dayu/__init__.py无重复定义。tests/fins/test_sec_html_image_assets_real_cli.py observer已从importlib.metadata.version("dayu-agent")记录实际版本，但断言写死0.1.4，因此发布升级会使其错误拒绝新版本。此为本次实际受影响面。

一个 slice：修改唯一声明；将真实CLI provenance断言改为按对应源码版本核对，不机械硬编码0.1.5。复用tests/cli/test_public_package_entrypoints.py的真实wheel构建验证，并核wheel METADATA/name/version与公开entrypoint；运行受影响测试及全量pyright。构建不安装本包，不把源码/wheel版本冒充实际安装版本。依README职责决定是否更新文档。保存增量源码快照、命令、真实退出和结果，按既定gpt-6-sol writer与MiMo/DS独立双路审核路由，聚焦本增量；R1–R3未变部分复用已核收证据。

主控判断：动机成立，版本声明属于包元数据owner，直接修改即可，不需新API/版本模块；没有架构、schema或状态机重要决策，最小计划由主控核对，不另起planreview。用户明确目标/成功信号与边界，无blocking open question。必要验证通过并审核裁决后精确提交/push，更新同PR206，再核对最终OID/diff/实际CI/push，完成增量交付。

## 风险与接续

实际安装包版本与README安装检查：covered by later approved slice，仅收到增量核收及明确安装通知后执行，不宣称当前已安装0.1.5。原S1真实vendor接受度维持assigned to later work unit，owner为Provider/Engine与portfolio-manager，destination调用方后续补验，不重开业务回归。其它R1–R3有效验证/风险见既有final-closeout和code-adjudication。
