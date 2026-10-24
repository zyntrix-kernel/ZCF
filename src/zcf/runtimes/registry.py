"""
Runtime Adapter Registry for ZCF.
Maintains available adapters and handles discovery.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Type

from zcf.runtimes.base import RuntimeAdapterInterface
from zcf.runtimes.native import NativeAdapter
from zcf.runtimes.qemu import QemuUserAdapter
from zcf.runtimes.wine import WineAdapter


class RuntimeRegistry:
    """Registry coordinating available runtime adapters."""

    def __init__(self):
        self._adapters: Dict[str, RuntimeAdapterInterface] = {}
        self._register_defaults()

    def _register_defaults(self):
        self.register(NativeAdapter())
        self.register(WineAdapter())
        self.register(QemuUserAdapter())

    def register(self, adapter: RuntimeAdapterInterface):
        self._adapters[adapter.get_id()] = adapter

    def get_adapter(self, runtime_id: str) -> Optional[RuntimeAdapterInterface]:
        return self._adapters.get(runtime_id)

    def list_adapters(self) -> List[RuntimeAdapterInterface]:
        return list(self._adapters.values())
