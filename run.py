#!/usr/bin/env python3
"""Unified CLI entry point for Python Tools.

Usage:
    python run.py                          # List all tools
    python run.py <tool_name> [options]    # Run a specific tool
    python run.py <tool_name> --help       # Show tool help
"""

import sys
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent))

from core.registry import discover_tools, CATEGORY_LABELS


def main():
    tools_by_cat = discover_tools()
    all_tools = {t.name: t for tools in tools_by_cat.values() for t in tools}

    tool_name = sys.argv[1] if len(sys.argv) > 1 else None

    if not tool_name or tool_name in ("--help", "-h", "help") or tool_name not in all_tools:
        _print_help(tools_by_cat, all_tools)
        if tool_name and tool_name not in ("--help", "-h", "help") and tool_name not in all_tools:
            print(f"\n[錯誤] 找不到工具：'{tool_name}'")
            sys.exit(1)
        sys.exit(0)

    import argparse
    tool = all_tools[tool_name]
    parser = argparse.ArgumentParser(
        prog=f"python run.py {tool_name}",
        description=tool.description,
    )
    tool.add_cli_args(parser)
    args = parser.parse_args(sys.argv[2:])
    tool.run_cli(args)


def _print_help(tools_by_cat: dict, all_tools: dict):
    print("\nPython Tools — 可用工具列表\n")
    for cat, label in CATEGORY_LABELS.items():
        tools = tools_by_cat.get(cat, [])
        if not tools:
            continue
        print(f"  [{label}]")
        for t in tools:
            print(f"    {t.name:<25} {t.description}")
        print()
    print("使用方式：")
    print("  python run.py <工具名稱> [選項]")
    print("  python run.py <工具名稱> --help")
    print()


if __name__ == "__main__":
    main()
