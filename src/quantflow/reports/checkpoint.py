"""Render the historical checkpoint without executing a current strategy or writing to the run."""


def partial_report(checkpoint, source_root):
    plan = checkpoint.get_context("run:plan")
    if not plan or not checkpoint.done_count():
        return None
    if "tasks" in plan:
        tasks = [(entry["name"], entry.get("watchlist")) for entry in plan["tasks"]]
    else:
        tasks = [("watchlist", plan["watchlist"])]

    verified = {(task, code) for task, code, _, _ in checkpoint.verified_snapshots(source_root)}
    planned = {
        (task, item["code"])
        for task, watchlist in tasks
        if watchlist
        for item in watchlist["items"]
    }
    if not verified.issubset(planned):
        raise ValueError("Checkpoint contains stocks outside the frozen plan")

    total = sum(len(w["items"]) for _, w in tasks if w is not None)
    denominator = str(total) if all(w is not None for _, w in tasks) else "unknown"
    lines = [
        "# Partial QuantFlow report",
        "",
        f"Run ID: {checkpoint.run_id}",
        f"Verified coverage: {len(verified)}/{denominator}",
        "Only completed stocks are included. Pending stocks have unknown signals.",
        "",
    ]
    for task, watchlist in tasks:
        if watchlist is None:
            lines.extend([f"## {task}", "Original watchlist unavailable.", ""])
            continue
        done = checkpoint.get_done(task)
        cutoff = (checkpoint.get_context(f"execution:{task}") or {}).get("as_of", "unknown")
        lines.extend(
            [
                f"## {task} ({len(done)}/{len(watchlist['items'])})",
                f"Market data cutoff: {cutoff}",
                "",
            ]
        )
        results = {row["code"]: row for row in checkpoint.get_results(task)}
        signals = set()
        for item in watchlist["items"]:
            code = item["code"]
            if code not in done:
                continue
            outcome = checkpoint.get_stats(task, code)["outcome"]
            if outcome["status"] == "no_signal":
                continue
            if outcome["status"] != "signal" or code not in results:
                raise ValueError(f"Inconsistent checkpoint outcome for {code}")
            signals.add(code)
            row = results[code]
            buy = ", ".join(row.get("matched_buy_strategies", [])) or "—"
            sell = ", ".join(row.get("matched_sell_strategies", [])) or "—"
            lines.append(
                f"- {code} {row.get('name', '')} | {outcome.get('bar_date')} | "
                f"{outcome.get('source')} | close {row.get('price')} | "
                f"Buy: {buy} | Sell: {sell} | {'; '.join(row.get('reasons', []))}"
            )
        if signals != set(results):
            raise ValueError(f"Inconsistent checkpoint signals for {task}")
        no_signal = len(done) - len(signals)
        lines.extend(
            [
                "",
                f"Signal stocks: {len(signals)}. Analyzed without signal: {no_signal}.",
                "",
            ]
        )
    return "\n".join(lines)
