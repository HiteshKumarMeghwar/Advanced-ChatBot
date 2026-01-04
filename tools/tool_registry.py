# core/tool_registry.py
import asyncio

class ToolRegistry:
    def __init__(self):
        self._tools_by_name = {}
        self._version = 0
        self._lock = asyncio.Lock()

    @property
    def version(self) -> int:
        return self._version

    async def refresh(self, tools: list):
        async with self._lock:
            self._tools_by_name = {t.name: t for t in tools}
            self._version += 1

    def get_by_names(self, names: set[str]):
        return [self._tools_by_name[n] for n in names if n in self._tools_by_name]
