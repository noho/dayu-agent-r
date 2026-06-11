"""业务工具包。

本包承载 Host / Engine 之外的业务工具实现与 provider。Doc、Web 与
财报 read 工具通过当前 ``ToolDefinition`` / ``ToolCallable`` 契约暴露，
由 runtime discovery 和 Host ToolRuntime 显式装配与治理。
"""

__all__: list[str] = []
