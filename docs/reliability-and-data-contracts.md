# 结果可靠性与数据契约

最近更新于 2026-11-20。遗留事项和报告二次筛选见 [最新遗留待办与 AI 路线](follow-up-and-ai-review.md)。

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

- queued：已排队，尚未开始运行。
- running：当前工作线程正在运行。
- completed：所请求且可枚举的股票全部成功分析。
- partial：部分股票成功，但有缺失、过期、历史不足、错误或失败任务。
- failed：没有股票成功分析，或者必要的输入快照、结果、报告、清单无法写入。
- cancelling：已请求停止，当前工作线程尚未退出。
- cancelled：排队时被取消，或当前工作线程已结束并可以移交队列。
- interrupted：启动时检测到上次进程遗留的queued/running/cancelling记录。

空股票池在 API 预检阶段拒绝。股票池无法读取时，任务错误写入 `task_errors`，整体覆盖率 `coverage` 为 `null`。已读入范围的分析比例由 `enumerated_coverage` 单独记录。报告会分别展示这两个口径。

JSON、报告和输入快照采用临时文件、fsync 与原子替换，写入异常向上抛出。Web 先写入最终产物清单，再提交和发布运行终态。最终清单写入失败时，运行状态为 `failed`。CLI 退出码为 0（完成）、2（部分完成）、1（失败）或 130（取消）。

Web 启动时先绑定端口，再取得 Runs 数据库对应的排他锁。只有锁的持有者可以接管队列并处理上次中断的记录。正常关闭会请求当前工作线程停止，线程退出后释放锁。产物清单已经落盘但数据库尚未提交时，重启会检查运行 ID、文件归属、哈希和报告，再恢复终态。清单或产物无法验证时，状态记为 `interrupted`。

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
- 日期解析后裁剪到请求区间，区间内数据经过排序、重复日期、必需列、非有限数、正价格、成交量和 OHLC 范围校验。复权计算造成的浮点末位误差会校正到价格范围边界，超出浮点误差的违反仍报错。
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

不同供应商的调整算法、精度和修订仍可能不同。Yahoo 的 `none` 采用已按拆股比例归一、未进行现金分红复权的 Close，`qfq` 采用分红和拆股调整。快照的 `price_adjustment_basis` 记录这两个口径，便于重放时识别。

顺序和批量下载会检查实际用于计算的日线输入。从首根已观察到的日线到目标交易日，缺失交易日或出现非交易日行情时记作 `data_gap`，逐股覆盖文件记录对应日期。BaoStock 日线保存 `tradestatus`。明确标为停牌的历史行用于核对日期完整性，指标计算时排除这些行。首根行情晚于查询期的首个交易日时，BaoStock 会尝试查询上市日期并记录来源。有可信上市日期时，从上市日与请求起点中较晚的日期检查前部缺口。无证据时按已有有效历史长度及区间内缺口处理。目标日零成交量记为 `suspended`，目标日缺失记为 `stale`。

空表、过期、内部缺口及历史长度不足都会尝试备源。末根相同且主源有缺口或长度不足时，只有日线连续且长度满足要求的备源才能替换主源。每只股票始终使用同一供应商的整段数据。仍有缺口的股票不计算信号。

## 断点恢复与重放

恢复按钮使用后端的资格检查。终态候选为 `failed`、`partial`、`cancelled` 和 `interrupted`。请求续跑时重新验证整次运行的有序任务清单、股票池、策略和指标参数、实际回看窗口、数据源及复权、批次设置、实现和数据依赖版本。任务执行前还会再次核验。缺少整次计划验证的旧断点只有在没有缓存结果时可以继续，已有缓存的旧断点需新开运行。未下载股票的上游历史修订仍受抓取时间和保存快照约束。

- 成功项保存结果、StockOutcome及输入快照；新run恢复时复制成功项快照并重试未成功项。
- 文件指纹包含 `src/quantflow` 中 Python 文件的原始字节。即使只改注释或文档字符串，下次校验也可能拒绝旧断点。校验会读取磁盘上的源码，服务已在运行时也会受影响。参数或文件指纹变化时可新开运行。
- task_run 及其恢复使用同一个 as_of，新开始的任务也使用原始截止时刻。每只股票快照保存查询起点、目标交易日和下载时间。运行摘要及 Markdown 报告显示行情截止时刻。成功项可按冻结输入重放。
- as_of是分析的交易日截止约束，不等于供应商历史版本可得性保证。恢复时新下载股票记录实际fetched_at，供应商修订依然可能影响其历史数据。
- 缓存的成功项需要可验证的原始输入快照。日志可用于定位失败，无法单独恢复完整行情和结果。保留原运行及其快照，直到新运行已验证并复制成功项。

## 基本面事实模型

FundamentalData保留原字段，并增加code、currency、source、source_url、as_of、period_end、published_at、available_at、fetched_at、status、quality_flags、units与missing_fields。

- total_mv/circ_mv/enterprise_value统一为原币基本单位；Tushare万元乘10000。
- PE TTM与forward_pe分别存储；市值与enterprise_value分别存储，不互相回填。
- 缺失、非数值和NaN/Inf归为null，不默认0；合法的0保留。
- Tushare按指定交易日取daily_basic，按trade_date排序并过滤越界值；这些是估值日快照，不是完整财务报告。
- Yahoo基本面为当前快照，拒绝把它用于历史日期；报表期末/公告时刻未知时保留null，不用抓取时间伪造公告时间。
- 当前事实仍是partial，并标注financial_statements_not_collected。尚不足以判断完整企业质量或近期重大事件，后续研究层需要补财报和公告证据。

## 1–2 周超跌反弹验证

运行研究工具时，输入固定的、复权口径一致的日线 CSV。必填列为 `code,date,open,high,low,close,volume`，非美股还需提供 `buy_allowed,sell_allowed` 来描述当日可成交性。可选 `trade_status` 用于标记停牌。

```bash
python -m quantflow.backtest.rebound --input snapshot.csv --output study.json \
    --start 2019-01-01 --holdout-start 2024-01-01 --end 2025-12-31
```

比较首次进入超卖、持续满足超卖和回升确认三种固定入场方式。信号确认后，最多检查两个交易日的可成交开盘。以入场日为第一个交易日，第 5 或 10 个交易日收盘退出。未知行情或受限交易单独计数，缺少退出行情的事件保留为未完成。同一股票、规则和期限在持有中跳过重复入场。缺失日线会重置指标预热。费用和滑点默认分别为每边 2 和 5 个基点。样本外日期由运行参数指定，结果记录输入哈希和指标参数。

## 回归验证

新增测试覆盖：非默认配置、运行中参数修改、策略顺序、RSI边界、批次/顺序逐股异常隔离、覆盖率、落盘失败、取消队列、初始化失败、历史文件归属、恢复指纹、假日/时区/未收盘、拆股因子与基本面单位和时间语义。

Web API测试使用临时数据库、checkpoint/preset目录，不隐式启动后台下载；工作线程测试显式启动并等待退出。浏览器端到端测试为每个用例启动自己的回环服务、临时项目和用户状态目录。测试实例重启时只关闭自己的子进程。

## 下载进度与网络恢复

- Runs 在下载和计算阶段分别发布进度。SSE 和 Runs API 共享同一进度快照，浏览器在 SSE 断开时继续轮询。进度条显示当前阶段和该阶段的已处理数量。
- 批量策略任务最多下载 50 只后开始计算并逐只落盘。一批保存之后再拉取下一批。
- 主源请求失败或历史覆盖不足时，备用源只查询受影响的股票。明确失败且备用源仍未恢复时，主源做一次补查。各供应商仍按自己的有限重试策略执行。
- 行情最终无法通过验证时，报告保留逐股失败和覆盖率。Resume 继承原数据时点，并复用通过验证的计算结果，继续处理未完成股票。配置或代码变化时仍校验恢复计划。
- 回归测试在第二只股票暂停时检验浏览器进度，在断网恢复后检验仅重拉未完成股票，并用真实指标计算结果验证 checkpoint 写入。
