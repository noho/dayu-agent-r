"""适配器内部异常类型。

这些异常用于让迁移后的 OLD 工具代码和适配器边界表达配置、参数与文件访问
失败。它们不复刻 OLD Engine 异常层级，也不作为公共兼容导入暴露。
"""

from __future__ import annotations

from dayu.contracts.json_value import JsonValue


class LegacyAdapterError(Exception):
    """适配器内部错误基类。"""


class ConfigError(LegacyAdapterError):
    """工具声明配置错误。

    :param config_name: 配置项名称。
    :param config_file: 配置文件路径；无文件来源时为 ``None``。
    :param details: 详细错误说明。
    """

    def __init__(
        self,
        config_name: str | None = None,
        config_file: str | None = None,
        details: str = "",
    ) -> None:
        """初始化配置错误。

        :param config_name: 配置项名称。
        :param config_file: 配置文件路径。
        :param details: 详细错误说明。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.config_name = config_name
        self.config_file = config_file
        self.details = details
        parts: list[str] = []
        if config_name is not None:
            parts.append(f"配置 {config_name!r}")
        if config_file is not None:
            parts.append(f"文件 {config_file!r}")
        if details:
            parts.append(details)
        super().__init__(" ".join(parts) if parts else "配置错误")


class ToolArgumentError(LegacyAdapterError):
    """工具参数错误。

    :param tool_name: 工具名。
    :param arg_name: 参数名。
    :param arg_value: 参数值。
    :param details: 详细错误说明。
    """

    def __init__(
        self,
        tool_name: str,
        arg_name: str | None = None,
        arg_value: JsonValue | None = None,
        details: str = "",
    ) -> None:
        """初始化工具参数错误。

        :param tool_name: 工具名。
        :param arg_name: 参数名。
        :param arg_value: 参数值。
        :param details: 详细错误说明。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.tool_name = tool_name
        self.arg_name = arg_name
        self.arg_value = arg_value
        self.details = details
        message = f"Tool {tool_name!r} argument error"
        if arg_name is not None:
            message = f"{message}: {arg_name}"
        if details:
            message = f"{message}: {details}"
        super().__init__(message)


class FileAccessError(LegacyAdapterError):
    """文件访问或路径权限错误。

    :param path: 相关路径。
    :param filename_or_details: 文件名或详细错误说明。
    :param details: OLD 三参调用形状中的详细错误说明。
    """

    def __init__(
        self,
        path: str,
        filename_or_details: str,
        details: str | None = None,
    ) -> None:
        """初始化文件访问错误。

        :param path: 相关路径。
        :param filename_or_details: 二参调用时为详细错误说明；三参调用时为文件名。
        :param details: 三参调用时的详细错误说明。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        detail_text = filename_or_details if details is None else details
        filename = "" if details is None else filename_or_details
        display_path = path if filename == "" else f"{path}/{filename}"
        self.path = display_path
        self.details = detail_text
        super().__init__(f"{display_path}: {detail_text}")
