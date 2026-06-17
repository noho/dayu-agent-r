# WU-CLI-OUTPUT-CHANNELS Final Closeout

## Scope

本 work unit 完成 CLI output channel 拆分：

- 全局 `--log-file <path>` 与 `--debug` / `--verbose` / `--info` / `--quiet` 正交。
- `prompt` 默认不显示 activity，显式 `--detail` 显示 activity，`--no-detail` 保持默认关闭。
- `interactive` 运行态 activity 从旧 stderr renderer 迁移到 CLI run view / activity sink 边界，Ctrl+T 切换 transcript/activity view，Esc 仍执行 Host cancel。

未修改 Host / Engine public API/contracts。

## Commits

- `2fccec46 gateflow: accept plan for WU-CLI-OUTPUT-CHANNELS`
- `7e22e7a8 gateflow: accept WU-CLI-OUTPUT-CHANNELS slice-a`
- `543f5975 gateflow: accept WU-CLI-OUTPUT-CHANNELS slice-b`
- `03d9809e gateflow: accept WU-CLI-OUTPUT-CHANNELS slice-c`

## Review Gates

- Plan review:
  - MiMo: `docs/reviews/wu-cli-output-channels-plan-review-mimo-20260617.md`
  - DS: `docs/reviews/wu-cli-output-channels-plan-review-ds-20260617.md`
  - Fix/rereview artifacts completed.
- Slice A:
  - 两路 code review 均完成，handler lifecycle 与异常路径已修复。
- Slice B:
  - 两路 code review 完成。
  - Controller 发现旧 outbox fallback 测试语义错误，已改为 watcher failure 场景并经两路 rereview。
- Slice C:
  - 两路 code review 完成。
  - DS 发现 run view activity 缺少 dedupe / sequence guard，已修复并经两路 rereview。

## Validation

最终验证：

- `source .venv/bin/activate && pytest tests/cli -q`
  - 196 passed, 3 warnings
- `source .venv/bin/activate && pyright dayu/ tests/ utils/`
  - 0 errors
- `git diff --check`
  - clean

分 slice 验证已记录在各 implementation / fix artifacts。

## Residual Risks

- `interactive` run view 是非 full-screen implementation；若后续需要真正 TUI panel，应拆后续 work unit 做 prompt_toolkit `Application.run_async()` 重构。
- `interactive` run view buffer 当前不做有界裁剪；长 session 大 buffer 属于本轮接受限制。
- 多进程同时写同一个 `--log-file` 时日志行可能交错；本轮按诊断日志限制接受，不加文件锁。

## Completion

Gateflow status: final closeout complete.
