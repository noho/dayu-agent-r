#!/bin/bash
# 源码安装 owner：Bash 3.2 编排 venv/pip、有限入口发布及真实正常 shell 检查。
# 参数：--shell bash|zsh [--python executable]；成功返回 0，任一阶段失败返回非零。
set -euo pipefail

INSTALL_STAGE=预检
INSTALL_TEMP=
PATH_MARKER='dayu source install PATH'
SHELL_PATH=$PATH

# 参数：错误说明；输出到 stderr；始终以非零终止。
fail() { printf '安装失败 [%s]: %s\n' "$INSTALL_STAGE" "$*" >&2; exit 1; }

# 参数：无；返回原退出码；只清理本进程尚未发布的临时文件。
cleanup() {
    local status=$?
    if [[ -n "$INSTALL_TEMP" && -e "$INSTALL_TEMP" ]]; then
        rm -f -- "$INSTALL_TEMP" || printf '清理失败，残留: %s\n' "$INSTALL_TEMP" >&2
    fi
    if [[ $status -ne 0 ]]; then
        printf '安装未完成 [%s]；已发生的 pip/profile/入口变更未回滚。\n' "$INSTALL_STAGE" >&2
    fi
    return "$status"
}

# 参数：pip console 的绝对路径；stdout 为仅 exec 的普通 launcher；写失败非零。
launcher_text() { printf '#!/bin/bash\nexec %q "$@"\n' "$1"; }

# 参数：无；stdout 为唯一 PATH block；写失败非零。
profile_block() {
    cat <<'BLOCK'
# >>> dayu source install PATH >>>
if [ "${PATH%%:*}" != "$HOME/.local/bin" ]; then
    export PATH="$HOME/.local/bin:$PATH"
fi
# <<< dayu source install PATH <<<
BLOCK
}

# 参数：目的地目录；不存在允许，symlink/其它类型/不可写拒绝，不写文件。
check_directory() {
    [[ ! -L "$1" ]] || fail "目录不能为 symlink: $1"
    if [[ -e "$1" ]]; then
        [[ -d "$1" && -w "$1" && -x "$1" ]] || fail "目录不可安全写入: $1"
    fi
}

# 参数：profile 路径；缺席或唯一精确 block 允许；不改写；冲突非零。
inspect_profile() {
    local path=$1 count block
    [[ ! -L "$path" ]] || fail "profile 不能为 symlink: $path"
    [[ -e "$path" ]] || return 0
    [[ -f "$path" && -r "$path" && -w "$path" ]] || fail "profile 类型或权限冲突: $path"
    count=$(grep -c -F "$PATH_MARKER" "$path" || true)
    [[ "$count" != 0 ]] || return 0
    [[ "$count" == 2 ]] || fail "profile marker 重复或残缺: $path"
    block=$(awk '/^# >>> dayu source install PATH >>>$/,/^# <<< dayu source install PATH <<<$/' "$path")
    [[ "$block" == "$(profile_block)" ]] || fail "profile block 被改写: $path"
}

# 参数：入口路径、目标 console、Python OS；只接受缺席、安全 symlink 或相同 launcher。
inspect_entry() {
    local dest=$1 target=$2 os=$3
    if [[ -L "$dest" ]]; then
        [[ ! -d "$dest" ]] || fail "入口为目录型 symlink: $dest"
    elif [[ -e "$dest" ]]; then
        [[ -f "$dest" ]] || fail "入口类型冲突: $dest"
        launcher_text "$target" | cmp -s - "$dest" || fail "未知普通入口冲突: $dest"
        [[ -x "$dest" ]] || fail "已有相同入口不可执行: $dest"
    fi
    # Git Bash 的命令解析还会搜索 .exe；不允许另一个同名入口抢占。
    if [[ "$os" == win32 ]]; then
        [[ ! -e "$dest.exe" && ! -L "$dest.exe" ]] || fail "入口 .exe 碰撞: $dest.exe"
    fi
}

# 参数：profile 路径；原子替换单文件并保留原字节/权限；I/O 失败非零。
publish_profile() {
    local path=$1
    inspect_profile "$path"
    if [[ -f "$path" ]] && grep -q -F "$PATH_MARKER" "$path"; then return 0; fi
    INSTALL_TEMP=$(mktemp "${path}.dayu.XXXXXX")
    if [[ -f "$path" ]]; then
        cp -p -- "$path" "$INSTALL_TEMP"
        if [[ -s "$path" && $(tail -c 1 "$path" | wc -l | tr -d ' ') == 0 ]]; then
            printf '\n' >> "$INSTALL_TEMP"
        fi
    else
        chmod 600 "$INSTALL_TEMP"
    fi
    profile_block >> "$INSTALL_TEMP"
    mv -f -- "$INSTALL_TEMP" "$path"
    INSTALL_TEMP=
}

# 参数：入口、console、Python OS；只替换目录项，绝不沿旧 symlink 写目标；失败非零。
publish_entry() {
    local dest=$1 target=$2 os=$3
    inspect_entry "$dest" "$target" "$os"
    if [[ ! -L "$dest" && -f "$dest" ]] && launcher_text "$target" | cmp -s - "$dest"; then
        [[ -x "$dest" ]] || fail "已有相同入口不可执行: $dest"
        return 0
    fi
    INSTALL_TEMP=$(mktemp "${dest}.dayu.XXXXXX")
    launcher_text "$target" > "$INSTALL_TEMP"
    chmod 700 "$INSTALL_TEMP"
    mv -f -- "$INSTALL_TEMP" "$dest"
    INSTALL_TEMP=
    launcher_text "$target" | cmp -s - "$dest" || fail "入口读回不一致: $dest"
}

# 参数：规范源码根；构造正常 shell PATH，仅移除明确的活动/本源码 venv scripts。
# 返回：设置 SHELL_PATH；保留其它目录、空项及其顺序，不改调用方环境。
prepare_shell_path() {
    local source=$1 remaining=$PATH part separator= active=${VIRTUAL_ENV-}
    SHELL_PATH=
    while :; do
        part=${remaining%%:*}
        if [[ "$part" != "$source/.venv/bin" && "$part" != "$source/.venv/Scripts" &&
              ! "$part" -ef "$source/.venv/bin" && ! "$part" -ef "$source/.venv/Scripts" ]] &&
           { [[ -z "$active" ]] || [[ "$part" != "$active/bin" && "$part" != "$active/Scripts" &&
              ! "$part" -ef "$active/bin" && ! "$part" -ef "$active/Scripts" ]]; }; then
            SHELL_PATH="$SHELL_PATH$separator$part"
            separator=:
        fi
        [[ "$remaining" == *:* ]] || break
        remaining=${remaining#*:}
    done
}

# 参数：--shell 所选名称；stdout 为安装进程 SHELL 或正常 PATH 中的真实可执行路径。
# 返回：找不到外部可执行文件时失败；不读取其它项目或 shell 配置来猜测。
resolve_shell() {
    local name=$1 executable
    if [[ -n "${SHELL-}" && "${SHELL##*/}" == "$name" ]]; then
        executable=$SHELL
    else
        executable=$(PATH="$SHELL_PATH" type -P "$name") || fail '目标 shell 不可用'
    fi
    [[ -f "$executable" && -x "$executable" ]] || fail "目标 shell 不可执行: $executable"
    printf '%s/%s\n' "$(CDPATH= cd -- "$(dirname "$executable")" && pwd -P)" "${executable##*/}"
}

# 参数：shell 名/绝对 executable、阶段 preflight|published、入口；真实 -ic/-lic。
# 返回：两种模式都符合才为 0；保留启动配置和继承 ZDOTDIR，失败非零。
check_shell() {
    local name=$1 executable=$2 phase=$3 dest=$4 mode code
    code='[[ -z "${VIRTUAL_ENV-}" && "$HOME" -ef "$4" ]] || exit 1
if [[ "$1" == zsh ]]; then
  printf "effective_zdotdir=%s\n" "${ZDOTDIR-$HOME}"
  [[ -n "${ZDOTDIR-$HOME}" && "${ZDOTDIR-$HOME}" -ef "$HOME" ]] || exit 1
fi
if [[ "$2" == published ]]; then
  command -v dayu-cli || exit 1
  if [[ "$1" == zsh ]]; then
    [[ "$(whence -w dayu-cli)" == "dayu-cli: command" ]] || exit 1
    resolved=$(whence -p dayu-cli) || exit 1
  else
    [[ "$(type -t dayu-cli)" == file ]] || exit 1
    resolved=$(type -P dayu-cli) || exit 1
  fi
  printf "external_entry=%s\n" "$resolved"
  [[ "$resolved" == "$3" ]] || exit 1
  dayu-cli --help
  help_status=$?
  printf "help_exit=%s\n" "$help_status"
  exit "$help_status"
fi'
    for mode in -ic -lic; do
        (cd /; env -u VIRTUAL_ENV -u PYTHONPATH -u PYTHONHOME PATH="$SHELL_PATH" \
            "$executable" "$mode" "$code" dayu-install "$name" "$phase" "$dest" "$HOME") || fail "正常 $name $mode 检查失败 ($phase)"
    done
}

# 参数：Bash host、Python OS 和架构；stdout 为现有锁名；无匹配非零。
select_lock() {
    case "$1:$2:$3" in
        Darwin:darwin:arm64) printf '%s\n' lock-macos-arm64-py311.txt ;;
        Linux:linux:x86_64) printf '%s\n' lock-linux-x64-py311.txt ;;
        MINGW*:win32:amd64|MSYS*:win32:amd64) printf '%s\n' lock-windows-x64-py311.txt ;;
        *) fail "无匹配 Python/OS/架构约束: $1:$2:$3" ;;
    esac
}

# 参数：CLI argv；执行完整安装。安装、metadata、入口和正常 shell 均正确才成功。
main() {
    local shell_name= python=python3.11 source native_source native_venv helper native_helper
    local host platform_info os arch lock venv_python console scripts_path shell_executable login candidate
    local profiles=()
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --shell) [[ $# -ge 2 ]] || fail '--shell 缺少值'; shell_name=$2; shift 2 ;;
            --python) [[ $# -ge 2 ]] || fail '--python 缺少值'; python=$2; shift 2 ;;
            --help) printf '用法: bash scripts/install-source.sh --shell bash|zsh [--python executable]\n'; return 0 ;;
            *) fail "未知参数: $1" ;;
        esac
    done
    [[ "$shell_name" == bash || "$shell_name" == zsh ]] || fail '必须指定 --shell bash|zsh'
    [[ -n "$python" ]] || fail 'Python executable 不能为空'
    source=$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
    helper="$source/scripts/install_source_query.py"
    native_source=$source; native_helper=$helper; native_venv="$source/.venv"
    host=$(uname -s)
    case "$host" in
        MINGW*|MSYS*)
            [[ "$shell_name" == bash ]] || fail 'Windows Git Bash 仅支持 Bash'
            command -v cygpath >/dev/null || fail '缺少 Git Bash cygpath'
            native_source=$(cygpath -w "$source"); native_helper=$(cygpath -w "$helper")
            native_venv=$(cygpath -w "$source/.venv") ;;
        Darwin|Linux) ;;
        *) fail "不支持的 Bash 平台: $host" ;;
    esac
    prepare_shell_path "$source"
    shell_executable=$(resolve_shell "$shell_name") || fail '目标 shell 解析失败'
    [[ -d "${HOME:?需要 HOME}" && ! -L "$HOME" ]] || fail 'HOME 必须为实际目录'
    check_directory "$HOME"; check_directory "$HOME/.local"; check_directory "$HOME/.local/bin"
    [[ ! -L "$source/.venv" ]] || fail '目标 .venv 不能为 symlink'
    case "$host" in
        MINGW*|MSYS*) venv_python="$source/.venv/Scripts/python.exe"; console="$source/.venv/Scripts/dayu-cli.exe" ;;
        *) venv_python="$source/.venv/bin/python"; console="$source/.venv/bin/dayu-cli" ;;
    esac
    if [[ -e "$source/.venv" ]]; then
        [[ -d "$source/.venv" && -f "$source/.venv/pyvenv.cfg" && -x "$venv_python" ]] || fail '已有 .venv 类型或身份无效'
        platform_info=$("$venv_python" -I "$native_helper" venv "$native_source") || fail '已有 .venv 身份无效'
    else
        platform_info=$("$python" -I "$native_helper" platform "$native_source") || fail 'Python 平台查询失败'
    fi
    IFS='|' read -r os arch scripts_path <<< "$platform_info"
    lock=$(select_lock "$host" "$os" "$arch") || fail '无适用平台锁'
    [[ -f "$source/constraints/$lock" && -f "$source/constraints/lock-common-py311.txt" ]] || fail '适用约束缺失'
    inspect_entry "$HOME/.local/bin/dayu-cli" "$console" "$os"
    if [[ "$shell_name" == zsh ]]; then profiles=("$HOME/.zshrc")
    else
        login="$HOME/.bash_profile"
        for candidate in "$HOME/.bash_profile" "$HOME/.bash_login" "$HOME/.profile"; do
            if [[ -e "$candidate" || -L "$candidate" ]]; then login=$candidate; break; fi
        done
        profiles=("$HOME/.bashrc" "$login")
    fi
    for candidate in "${profiles[@]}"; do inspect_profile "$candidate"; done
    check_shell "$shell_name" "$shell_executable" preflight "$HOME/.local/bin/dayu-cli"
    INSTALL_STAGE='venv/pip（失败可能留下部分安装）'
    if [[ ! -d "$source/.venv" ]]; then "$python" -I -m venv "$native_venv"; fi
    platform_info=$("$venv_python" -I "$native_helper" venv "$native_source") || fail '目标 venv 身份无效'
    IFS='|' read -r os arch scripts_path <<< "$platform_info"
    [[ "$(select_lock "$host" "$os" "$arch")" == "$lock" ]] || fail '实际 pip 解释器与预检平台锁不一致'
    if [[ "$os" == win32 ]]; then scripts_path=$(cygpath -u "$scripts_path"); fi
    [[ "$scripts_path" == "$(dirname "$console")" ]] || fail '实际 scripts 路径与目标不符'
    # pip 自行解析项目唯一版本；脚本不维护安装数据库或第二份版本声明。
    local native_lock="$source/constraints/$lock"
    if [[ "$os" == win32 ]]; then native_lock=$(cygpath -w "$native_lock"); fi
    "$venv_python" -I -m pip install -e "$native_source[test,dev,browser]" -c "$native_lock"
    INSTALL_STAGE=安装来源核验
    (cd /; "$venv_python" -I "$native_helper" installed "$native_source")
    (cd /; env -u VIRTUAL_ENV -u PYTHONPATH -u PYTHONHOME "$console" --help)
    INSTALL_STAGE=profile发布
    mkdir -p "$HOME/.local/bin"
    for candidate in "${profiles[@]}"; do publish_profile "$candidate"; done
    INSTALL_STAGE=入口发布
    publish_entry "$HOME/.local/bin/dayu-cli" "$console" "$os"
    INSTALL_STAGE=新正常shell核验
    check_shell "$shell_name" "$shell_executable" published "$HOME/.local/bin/dayu-cli"
    printf '安装完成。目标: %s\n默认入口: %s\n请重新打开终端。\n' "$source/.venv" "$HOME/.local/bin/dayu-cli"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    trap cleanup EXIT
    main "$@"
fi
