# 固定入口与后续必要操作（模板未执行）

当前绝对入口 `/Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli` 是 editable 安装，加载本仓当前生产源码；固定入口外cwd离线smoke和真实import hash已核验。没有修改其安装、生产workspace或现有来源；其他checkout/非editable安装需采用修复commit，不据本机证据宣称已部署。draft PR不代表合并。

旧8项身份/PDF阶段可恢复，原因、日期、URL及期间不在留存证据或published meta中。不能以新观测替代旧运行；本轮没有新观测。现有CLI不能只按旧失败ID重试。巡检线先明确新观测的日期/表单范围及对现有来源影响，再运行批准范围的普通增量命令；不能据本模板盲重跑原整批，也不能加overwrite。

以下只给获批之后的捕获模板，`APPROVED_START`、`APPROVED_END` 必须由巡检线的具体范围替换；需要指定表单时也按批准范围添加 `--forms`。

```zsh
approved_start='APPROVED_START'
approved_end='APPROVED_END'
diagnostic_dir=$(mktemp -d /Users/leo/workspace/dayu-agent-r/workspace/tmp/0700-observation.XXXXXX)
if /Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli \
  --base /Users/leo/workspace/portfolio-manager-v2/workspace \
  --log-file "$diagnostic_dir/dayu.log" \
  download --ticker 0700 --start "$approved_start" --end "$approved_end" \
  >"$diagnostic_dir/stdout.txt" 2>"$diagnostic_dir/stderr.txt"; then
  result_code=0
else
  result_code=$?
fi
printf '%s\n' "$result_code" >"$diagnostic_dir/exit-code.txt"
```

该操作可能发现/下载批准范围内的新候选，已有来源按普通增量规则跳过；无overwrite并不等于没有新获取影响，须先批准范围。日志只作辅助，完整业务诊断无需日志参数。捕获stdout和stderr全部内容，提取唯一以 `Fins download diagnostics: ` 开头的物理行并解析JSON；无行/多行不能当正常终态。核对 `summary.filters`、`summary.counts.failed` 与 `failed_documents` 行数及身份、安全原因/未知metadata、`summary.terminal_disposition` 和整体 `failure`。退出0仍可能为partial_failure，未处理候选不作结论。

腾讯业务侧G0恢复、影响判断及通知workflow-run-tencent由巡检线核实后执行；本单元不代批G5/G6，不发送外部消息。
