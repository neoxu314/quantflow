"""Markdown Report Generator."""

import os
from pathlib import Path
from typing import List, Any, Tuple
from datetime import datetime

from .base import Reporter
from quantflow.execution.storage import ExecutionResultItem


class MarkdownReporter(Reporter):
    def _get_stock_info(self, watchlist):
        tag_map = {}
        for item in watchlist.items:
            code_str = item.code.standard
            tag_map[code_str] = {
                "market": item.code.exchange,
                "tags": item.tags if hasattr(item, 'tags') else [],
                "name": getattr(item.code, 'name', None) or (getattr(item, 'name', None) if hasattr(item, 'name') else ""),
            }
        return tag_map

    def _count_watched(self, watchlist):
        return watchlist.length if hasattr(watchlist, 'length') else len(watchlist.items)

    def _group_by_strategy(self, items: List[ExecutionResultItem], signal_type: str) -> List[Tuple[Tuple[str, ...], List[ExecutionResultItem]]]:
        groups = {}
        for item in items:
            strategies = tuple(item.matched_buy_strategies) if signal_type == "buy" else tuple(item.matched_sell_strategies)
            if strategies not in groups:
                groups[strategies] = []
            groups[strategies].append(item)
        
        sorted_groups = sorted(groups.items(), key=lambda x: len(x[0]), reverse=True)
        return sorted_groups

    def _format_strategy_name(self, strategies: Tuple[str, ...]) -> str:
        if len(strategies) == 1:
            return strategies[0]
        return " & ".join(strategies)

    def _render_signal_groups(self, items: List[ExecutionResultItem], signal_type: str, stock_map: dict) -> List[str]:
        lines = []
        groups = self._group_by_strategy(items, signal_type)
        
        for combo, group_items in groups:
            group_name = self._format_strategy_name(combo)
            buy_label = "🔵 Buy" if signal_type == "buy" else "🔴 Sell"
            header = f"### {buy_label} - {group_name} ({len(group_items)})"
            lines.append(header)
            
            lines.append("| Code | Name | Market | Resonance | Reasons | Tags |")
            lines.append("|---|---|---|---|---|---|")
            
            for item in group_items:
                info = stock_map.get(item.code, {"market": "-", "tags": [], "name": ""})
                display_name = item.name or info.get("name", "-")
                is_buy = signal_type == "buy"
                count = item.buy_signals if is_buy else item.sell_signals
                resonance = f"x{count}" if count > 1 else "-"
                reasons = "; ".join(item.reasons)
                tags = ", ".join(info.get("tags", [])) or "-"
                lines.append(f"| {item.code} | {display_name} | {info['market']} | {resonance} | {reasons} | {tags} |")
        
        return lines

    def generate(
        self,
        task_name: str,
        strategies: List[Any],
        results: List[ExecutionResultItem],
        watchlist: Any,
        output_dir: str,
        date_str: str,
    ) -> str:
        stock_map = self._get_stock_info(watchlist)
        total_watched = self._count_watched(watchlist)
        strat_names = [s.name if hasattr(s, 'name') else type(s).__name__ for s in strategies]

        buy_items = [r for r in results if r.buy_signals > 0]
        sell_items = [r for r in results if r.sell_signals > 0]

        lines = [
            f"# {task_name} Scan Report",
            f"**Date**: {date_str}",
            "",
            "## Task Coverage",
            "| Watchlist | Stocks Covered | Strategies |",
            "|---|---|---|",
            f"| {watchlist.name} | {total_watched} | {', '.join(strat_names)} |",
            f"\n**Total Monitored**: {total_watched}",
            "\n## Statistics",
            f"- **Buy Signals**: {len(buy_items)}",
            f"- **Sell Signals**: {len(sell_items)}",
            f"- **No Signals**: {max(0, total_watched - len(results))}",
        ]

        if buy_items:
            lines.extend(self._render_signal_groups(buy_items, "buy", stock_map))

        if sell_items:
            lines.extend(self._render_signal_groups(sell_items, "sell", stock_map))

        lines.append("\n## ⚠️ Data Availability")
        lines.append(f"- Stocks without data or signals: {max(0, total_watched - len(results))}")

        os.makedirs(output_dir, exist_ok=True)
        file_path = os.path.join(output_dir, f"{task_name}.md")
        Path(file_path).write_text("\n".join(lines))
        return file_path

    def generate_combined(
        self,
        date_str: str,
        task_runs: list[tuple],
        output_dir: str,
    ) -> str:
        """Generate a combined report for multiple tasks."""
        total_buys = 0
        total_sells = 0
        total_watched = 0
        total_no_signal = 0

        lines = [
            f"# Daily Scan Summary",
            f"**Date**: {date_str}",
            f"**Tasks Executed**: {len(task_runs)}",
            "",
            "## Overall Statistics",
        ]

        for name, results, watchlist, _ in task_runs:
            wl_count = self._count_watched(watchlist)
            total_watched += wl_count
            b = len([r for r in results if r.buy_signals > 0])
            s = len([r for r in results if r.sell_signals > 0])
            total_buys += b
            total_sells += s
            total_no_signal += max(0, wl_count - len(results))

        lines.append(f"- **Total Watched**: {total_watched}")
        lines.append(f"- **Buy Signals**: {total_buys}")
        lines.append(f"- **Sell Signals**: {total_sells}")
        lines.append(f"- **No Signals**: {total_no_signal}")

        for name, results, watchlist, strategies in task_runs:
            stock_map = self._get_stock_info(watchlist)
            strat_names = [s.name if hasattr(s, 'name') else type(s).__name__ for s in strategies]
            buy_items = [r for r in results if r.buy_signals > 0]
            sell_items = [r for r in results if r.sell_signals > 0]
            
            lines.append(f"\n---\n")
            lines.append(f"## {name}")
            lines.append(f"| Watchlist | Stocks | Strategies |")
            lines.append("|---|---|---|")
            lines.append(f"| {watchlist.name} | {self._count_watched(watchlist)} | {', '.join(strat_names)} |")
            
            if buy_items:
                lines.extend(self._render_signal_groups(buy_items, "buy", stock_map))

            if sell_items:
                lines.extend(self._render_signal_groups(sell_items, "sell", stock_map))

        os.makedirs(output_dir, exist_ok=True)
        file_path = os.path.join(output_dir, "Daily_Report.md")
        Path(file_path).write_text("\n".join(lines))
        return file_path
