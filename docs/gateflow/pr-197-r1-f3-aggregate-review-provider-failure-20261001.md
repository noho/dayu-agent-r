# F3 aggregate：Kimi 额度失败与已授权 DS 备份

Kimi label=`pr197-f3-aggregate-kimi-20261001-01`，runtime=`claude`，显式 workspace=`/Users/leo/workspace/dayu-agent-r`。预检通过后托管 session35525 取得 outer exit1；独立 JSON 可解析，`is_error=true`、`terminal_reason=api_error`、`api_error_status=403`、`num_turns=1`、modelUsage 空。虽然 subtype 字面为 success，不能判任务成功。result 明确 `You've reached your 5-hour usage limit`，没有有效审查报告或工具取证、未取得 canary 匹配，结果拒收。stderr 精确 unrecognized_model 只是 warning，不豁免 API 失败；实际执行模型不可核，不从 stderr 路由名推断。

原独立 output／stderr／prompt 保留于 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.k3VJA9/`。不重试到成功、不将本次失败替换为其它 provider 通过。

用户已有 Kimi 真实额度失败时 ds-flash 备份授权，及全部 runner runtime/provider 派发授权；因此同版冻结 `workspace/tmp/pr197-f3-aggregate-review-20261001/freeze.json`（1117 current／1117 originals，accepted slice `03e8b9b013a30298ba3055b900368102db05e22c`）派发新 label=`pr197-f3-aggregate-dsflash-20261001-01`。其绝对 cwd、新双流、唯一 instance、no-persist／canary／只读 scope 已独立预检；托管 session65682 在途，原输出目录 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.Sqh27k/`。未取得终态，不记录备份审查通过。

MiMo aggregate session50118 与 F6 Sol 实施69038 并行，写入范围互斥；F6 是唯一产品源码写入者。下一入口是完整两路终态和 root 结构化／实际源码／证据核收，再裁 aggregate gate。既有业务裁决、main 和 PR197 draft 状态不变。
