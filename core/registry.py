import importlib
import pkgutil
from collections import defaultdict

import tools
from core.base_tool import BaseTool

CATEGORY_LABELS = {
    "av":         "影音工具",
    "divination": "占卜工具",
    "data":       "資料整理",
}


def discover_tools() -> dict:
    """Scan tools/ subpackages and return {category: [BaseTool instances]}."""
    by_category = defaultdict(list)
    seen = set()

    for _, name, _ in pkgutil.walk_packages(tools.__path__, "tools."):
        try:
            mod = importlib.import_module(name)
        except Exception:
            continue
        for attr_name in dir(mod):
            obj = getattr(mod, attr_name)
            if (
                isinstance(obj, type)
                and issubclass(obj, BaseTool)
                and obj is not BaseTool
                and obj.__module__ == mod.__name__
                and id(obj) not in seen
            ):
                seen.add(id(obj))
                try:
                    instance = obj()
                    if instance.name:
                        by_category[instance.category].append(instance)
                except Exception:
                    continue

    return dict(by_category)
