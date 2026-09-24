"""
Point Break Unified Tool Registry
=================================
Central catalog for all agent capabilities across Computer, Browser, Travel,
Communications, Office, and System administration.
Provides parameter validation, schema export, and dynamic dispatch.
"""

from typing import Dict, Any, Callable, Optional, List
from dataclasses import dataclass, field
import inspect

@dataclass
class ToolDefinition:
    name: str
    func: Callable
    description: str = ""
    parameters_schema: Dict[str, Any] = field(default_factory=dict)
    risk_level: str = "R0"

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        func: Callable,
        description: str = "",
        parameters_schema: Optional[Dict[str, Any]] = None,
        risk_level: str = "R0"
    ):
        """Registers a tool function in the global registry."""
        self._tools[name.lower()] = ToolDefinition(
            name=name.lower(),
            func=func,
            description=description,
            parameters_schema=parameters_schema or {},
            risk_level=risk_level
        )

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name.lower())

    def list_tools(self) -> List[ToolDefinition]:
        return list(self._tools.values())

    def execute(self, _tool_name: str, **kwargs) -> Any:
        tool_def = self.get_tool(_tool_name)
        if not tool_def:
            raise ValueError(f"Tool '{_tool_name}' is not registered in ToolRegistry.")

        # Filter kwargs to match function signature
        sig = inspect.signature(tool_def.func)
        filtered_kwargs = {}
        for k, v in kwargs.items():
            if k in sig.parameters:
                filtered_kwargs[k] = v

        return tool_def.func(**filtered_kwargs)

tool_registry = ToolRegistry()

def register_tool(name: str, description: str = "", risk_level: str = "R0", parameters_schema: Optional[Dict[str, Any]] = None):
    def decorator(fn: Callable):
        tool_registry.register(name, fn, description, parameters_schema, risk_level)
        return fn
    return decorator
