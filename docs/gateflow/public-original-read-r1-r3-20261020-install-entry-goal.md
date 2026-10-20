# PR206 默认命令入口安装增量：目标确认

## 已确认目标与直接证据

用户明确授权本增量并已确认目标：执行README“从源码安装”后，在未激活仓库.venv的新正常shell中直接运行dayu-cli，必须命中本次安装及已核收版本。默认命令入口更新由Dayu安装交付负责，portfolio-manager独立验证。本线按既有gateflow/sub-agents模型继续，同PR206，包版本保持0.1.5，merge另授权。

preflight：分支fix/public-original-read-r1-r3-20261020，HEAD1856cf8d97468423c6a3ece5558a312d31802b20，初始工作树干净。根README1.1仅venv/activate/pip editable install及help，没有默认入口配置；既有实际安装回执installation-20261020T092320Z记录自身.venv中0.1.5及help通过，未证明未激活shell的默认命令。因此缺陷动机成立，根因在安装交付owner缺少包安装与默认入口发布的完整步骤，不能在调用方环境或业务运行时补救。

用户提供的确定历史：原默认/Users/leo/.local/bin/dayu-cli指向/Users/leo/.local/share/uv/tools/dayu-agent/bin/dayu-cli（0.1.4）；此前portfolio-manager已将该链接改为本仓.venv/bin/dayu-cli。允许保留现状，但该人工修正不能充当新流程验证。禁止为复现擅自恢复真实旧入口；使用隔离测试环境验证旧入口处理和重复执行。此处只采用用户明确路径事实，不查找或推断调用方环境。

## 成功信号与验证边界

工程阶段：以最小适用安装步骤/README修复owner边界，证明从旧入口或缺席入口到当前安装的转换，以及重复执行；保留被替换入口所指其他工具环境。必要受影响测试、全量pyright及适用覆盖率要求满足，指定双路独立审核与裁决/必要修复完成，精确提交并更新同draft PR206。

工程交付核收后才按更新README在真实自身环境sync。届时从未激活仓库.venv的新正常shell保存实际command-v、解析入口、解释器、该解释器实际distribution metadata版本/位置、源码commit关联、dayu-cli --help命令和退出；默认入口和实际安装必须对应0.1.5与核收commit，排除cwd/PYTHONPATH metadata影子。现成链接可用、源码声明或激活venv后的通过均不能代替新流程证据。

## 所有权、非目标与授权停点

默认入口与本次包安装来源的关联由Dayu安装流程唯一负责；包版本声明仍属pyproject.toml，实际安装版本来自目标解释器distribution metadata。优先朴素、可维护的步骤，不给业务CLI新增查找旧环境/运行时fallback，不造第二版本真源，不扩财报业务/存储/读取契约。

禁止删除其他工具环境、修改调用方项目配置、要求调用方另补安装动作；禁止查找或推断调用方环境。现有R1–R3/0.1.5有效证据、审核历史和人工链接修正历史保留；未受影响部分不重开。包版本保持0.1.5，不新增--version。工程核收和明确安装通知之前不执行真实live安装/入口发布，merge继续另授权。

用户已经明确目标/边界/验收并授权执行，本文件记录等价binding confirmation，不重复索取确认。无blocking open question。下一入口为指定gpt-6-sol plan；主控核对后按重要决策适用性决定计划审核，最终代码审核按既定MiMo/DS并发路由。
