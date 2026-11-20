# 结果可靠性与数据契约

最近更新于 2026-11-20。

本说明适用于2026-11-18后的可靠性修复，覆盖诊断D01—D09、D11，并修复共用lookback路径和股票代码校验。AI研究层、新闻/公告采集和新增完整财报采集不在本次实现范围。

运行环境要求Python 3.10及以上；当前项目现有虚拟环境为Python 3.12，已安装交易日历依赖。

## 配置与信号

- CLI和Web单股扫描调用同一个scanner；watchlist/task调用同一个Executor。
- ConfigLoader按项目配置加载市场主备源、Token与默认复权方式；未配置市场继承默认值，显式null关闭fallback。
- 指标由策略依赖声明和IndicatorFactory生成，运行期间使用配置快照；界面或YAML参数修改应用到下一次运行。
- 每个策略独立消费同一份指标数据，只统计该策略的输出方向；策略顺序不能改变买卖计数。
- RSI明确处理纯上涨=100、纯下跌=0、平盘=50的边界。

## 完成状态与覆盖率

每只股票记录一种结果：signal、no_signal、no_data、stale、data_gap、suspended、insufficient、error。只有前两项算成功分析；其他项不计入“无信号”。

- completed：所请求且可枚举的股票全部成功分析。
- partial：部分股票成功，但有缺失、过期、历史不足、错误或失败任务。
- failed：没有股票成功分析，或者必要的输入快照、结果、报告、清单无法写入。
- cancelling：已请求停止，当前工作线程尚未退出。
- cancelled：工作线程已退出；此时才移交队列。
- interrupted：启动时检测到上次进程遗留的queued/running/cancelling记录。

空股票池在 API 预检阶段拒绝。股票池无法读取时，任务错误写入 `task_errors`，整体覆盖率 `coverage` 为 `null`。已读入范围的分析比例由 `enumerated_coverage` 单独记录。报告会分别展示这两个口径。

JSON、报告和输入快照采用临时文件、fsync 与原子替换，写入异常向上抛出。Web 先写入最终产物清单，再提交和发布运行终态。最终清单写入失败时，运行状态为 `failed`。CLI 退出码为 0（完成）、2（部分完成）、1（失败）或 130（取消）。

Web 启动时先绑定端口，再取得 Runs 数据库对应的排他锁。只有锁的持有者可以接管队列并处理上次中断的记录。正常关闭会请求当前工作线程停止，线程退出后释放锁。

取消是协作式的：股票之间、批次回调、重试和等待都会检查；已发送的网络请求需要先返回或超时，不能承诺立刻中断供应商服务端请求。Yahoo/Tushare 请求设置超时。YahooQuery 在会话初始化结束后会检查取消状态，再决定是否请求日线。BaoStock 在自己的 socket 工厂内使用 30 秒 I/O 超时和取消检查。

## 输出与旧版本兼容

`--output`或界面的Output Directory现在表示基础目录，实际产物在：

```text
<base>/[YYYY-MM-DD/ 可选daily模式]/runs/<run_id>/
  manifest.json
  Run_Summary.json
  <task>.json / <task>.md
  <task>_coverage.json
  <task>_context.json
  snapshots/<task>/<code>.json
  logs/<run_type>_*.log
```

task_run还生成Combined_Results.json和Daily_Report.md。单股扫描生成`<code>_indicators.json`、`<code>_context.json`和`<code>_snapshot.json`，目录仍然按run独占。

Web历史中的output_path指向实际run目录，config.output_path保留用户选择的基础目录。文件列表按manifest读取，删除按manifest中的归属和内容hash执行，不再根据当前任务文件或股票池猜文件名。

用户在run目录里新增的文件、修改过的产物、符号链接目标不会被清理。运行中需要先取消并等待停止，才允许删除。

**旧运行没有manifest，无法证明共享文件属于哪次运行。因此删除旧记录保留磁盘文件；旧报告本身也无法被自动重建成历史快照。** 已配置读取扁平文件的外部脚本需要改成读取对应run目录/manifest，不再依赖覆盖同名文件的行为。

## Runs 备份与验证

从项目目录运行以下命令。默认在 `~/.quantflow/backups/` 新建带时间戳的目录，也可以用 `--output-dir` 指定备份位置。

```bash
python -m quantflow.backup
python -m quantflow.backup --verify /path/to/backup
```

备份包含 SQLite 的在线快照、可读取的已登记产物、断点和预设。清单记录原路径、SHA-256、缺失文件以及备份时仍活跃的运行。验证会检查文件哈希并将数据库恢复到内存中，可在服务运行时执行。旧共享目录只按记录关联的报告和日志取文件。

## 行情契约

- 内部日期区间为闭区间；Yahoo源在适配器内将end转换为供应商的排他边界。
- date代表交易所本地交易日；价格为同一复权口径的OHLC；volume统一为股。
- 日期解析后裁剪到请求区间，区间内数据经过排序、重复日期、必需列、非有限数、正价格、成交量和 OHLC 范围校验。
- 最近完整日线由交易所日历及UTC收盘时间计算，考虑假日、时区和夏令时。请求行情前按交易所确定最近完整交易日。同一个批次只包含相同查询窗口的股票。分析前再次校验末根，旧数据和零成交量末根不会产生当日新候选。
- 交易日历优先使用 exchange_calendars。若上游缺少 2027 年沪深日历，使用国务院公布的放假日期与沪深正常交易规则生成暂定覆盖。调休工作周末仍视为休市。临近年底会提示下年度覆盖状态，使用暂定日历时在运行摘要、报告和单股快照中记录警告。缺少已知覆盖的其他年份明确失败。 [国务院放假通知](https://www.gov.cn/zhengce/content/202611/content_7085101.htm) · [上交所休市安排](https://www.sse.com.cn/disclosure/dealinstruc/closed/) · [深交所交易规则](https://www.szse.cn/lawrules/rule/trade/current/t20260424_620190.html)
- 运行入口当前只执行日线策略；非日线策略明确拒绝。

| 适配器 | 周期能力 | 复权能力 | 说明 |
|---|---|---|---|
| BaoStock | d/w/m | qfq/hfq/none | qfq重新锚定请求末根交易日原始收盘，避免未来除权改变窗口价格基准 |
| Tushare | d | qfq/hfq/none | daily原始价+adj_factor，qfq按请求末端因子，hfq按累计因子；手转换为股 |
| YFinance | d/w/m | qfq/none | 显式auto_adjust；hfq拒绝 |
| YahooQuery | d/w/m | qfq/none | 显式adj_ohlc；hfq拒绝 |
| AKShare 港股 | d | qfq/hfq/none | 新浪返回历史数据后按日期裁剪，复权基准由上游提供 |

不同供应商的调整算法、精度和修订仍可能不同；保存source/adjust/输入快照，不能承诺跨供应商逐点完全相等。

顺序和批量下载会检查实际用于计算的日线输入。从首根已观察到的日线到目标交易日，缺失交易日或出现非交易日行情时记作 `data_gap`，逐股覆盖文件记录对应日期。首根之前的缺失按有效历史长度判断，避免仅凭行情把新上市或停牌归错类。目标日零成交量记为 `suspended`，目标日缺失记为 `stale`。

空表、过期、内部缺口及历史长度不足都会尝试备源。末根相同且主源有缺口或长度不足时，只有日线连续且长度满足要求的备源才能替换主源。每只股票始终使用同一供应商的整段数据。仍有缺口的股票不计算信号。

## 断点恢复与重放

- 成功项保存结果、StockOutcome及输入快照；新run恢复时复制成功项快照并重试未成功项。
- 配置指纹包含股票池内容、策略名、指标参数、数据源配置、lookback、复权和代码hash。参数/代码变化时拒绝混合恢复，提示新建完整运行。
- task_run 及其恢复使用同一个 as_of，新开始的任务也使用原始截止时刻。每只股票快照保存查询起点、目标交易日和下载时间。运行摘要及 Markdown 报告显示行情截止时刻。成功项可按冻结输入重放。
- as_of是分析的交易日截止约束，不等于供应商历史版本可得性保证。恢复时新下载股票记录实际fetched_at，供应商修订依然可能影响其历史数据。
- 旧checkpoint缺少指纹，或原成功项快照缺失，不能安全恢复，需要新建运行。原run删除前应先完成恢复快照复制。

## 基本面事实模型

FundamentalData保留原字段，并增加code、currency、source、source_url、as_of、period_end、published_at、available_at、fetched_at、status、quality_flags、units与missing_fields。

- total_mv/circ_mv/enterprise_value统一为原币基本单位；Tushare万元乘10000。
- PE TTM与forward_pe分别存储；市值与enterprise_value分别存储，不互相回填。
- 缺失、非数值和NaN/Inf归为null，不默认0；合法的0保留。
- Tushare按指定交易日取daily_basic，按trade_date排序并过滤越界值；这些是估值日快照，不是完整财务报告。
- Yahoo基本面为当前快照，拒绝把它用于历史日期；报表期末/公告时刻未知时保留null，不用抓取时间伪造公告时间。
- 当前事实仍是partial，并标注financial_statements_not_collected。尚不足以判断完整企业质量或近期重大事件，后续研究层需要补财报和公告证据。

## 回归验证

新增测试覆盖：非默认配置、运行中参数修改、策略顺序、RSI边界、批次/顺序逐股异常隔离、覆盖率、落盘失败、取消队列、初始化失败、历史文件归属、恢复指纹、假日/时区/未收盘、拆股因子与基本面单位和时间语义。

Web API测试使用临时数据库、checkpoint/preset目录，不隐式启动后台下载；工作线程测试显式启动并等待退出。浏览器端到端测试为每个用例启动自己的回环服务、临时项目和用户状态目录。测试实例重启时只关闭自己的子进程。
