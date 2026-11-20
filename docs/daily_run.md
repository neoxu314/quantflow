# 日常运行与维护

从项目根目录使用项目虚拟环境。先用单股或小观察列表检查行情和输出，再运行完整任务。

```bash
.venv/bin/python -m quantflow.cli scan --code AAPL.US --indicator kdj,dual_line
.venv/bin/python -m quantflow.cli tasks --config config/tasks_general_asia.yaml --output ./output/asia --daily
.venv/bin/python -m quantflow.cli tasks --config config/tasks_general_us.yaml --output ./output/us --daily
.venv/bin/python -m quantflow.cli tasks --config config/tasks_A_share_indices.yaml --output ./output/cn --daily
```

`--daily` 使用运行机器的本地日期生成 `<base>/YYYY-MM-DD/runs/<run_id>/`。报告里的信号日期
是各市场最新的完整交易日。某市场当日未收盘时会使用上一完整交易日。跨市场任务应安排在
所需市场收盘并完成供数之后。

使用 cron 时，把下面的路径替换为项目的绝对路径。此示例按 cron 所在机器的本地时区在
工作日 20:00 调度亚洲任务。先创建并确认输出目录可写。调度触发日和交易日由不同的规则处理。

```cron
0 20 * * 1-5 cd /path/to/quantflow && .venv/bin/python -m quantflow.cli tasks --config config/tasks_general_asia.yaml --output ./output/asia --daily >> ./output/asia-scheduler.log 2>&1
```

1. 使用 `Daily_Report.md` 阅读组合报告，机器处理使用 `Combined_Results.json`。
2. 查看 `Run_Summary.json` 和各任务的 `*_coverage.json` 区分零命中、部分完成和数据失败。
   调度器应记录退出码。部分完成返回 2，失败返回 1，取消返回 130。
3. Web 中打开 Runs 的 Progress、Report、Files 查看同一次运行的记录和产物。
   日常备份与恢复条件见 [运行契约](reliability-and-data-contracts.md)。

代码更新前让当前工作结束，并检查是否有待续跑的 checkpoint。检查点会校验原计划、
指标参数、依赖版本及 Python 源文件内容。修改 Python 注释同样会改变内容哈希。
若恢复资格不通过，使用 **Run Again** 新建运行。它使用新的数据截止时点。
