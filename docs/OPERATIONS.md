# Local Operations

The updater is scheduled daily at **08:10 Asia/Shanghai**, but it is disabled after every machine reboot. There is no continuously running background process.

Run these commands from `/data/disk1/portfolio-track-record`:

```bash
# Enable future scheduled updates and update immediately
./scripts/scheduler.sh start

# Check whether scheduling is enabled and whether an update is active
./scripts/scheduler.sh status

# Disable future scheduled updates
./scripts/scheduler.sh stop

# View recent output
tail -n 30 local_update.log

# List private detailed reports, including unrealized PnL
ls -la local_reports
```

The private `minute_performance.csv`, `total_equity_curve.png`, and `pnl_components.png` use one-minute sampling. Raw trade and mark-price caches stay under the ignored `data/private/` directory.

Open `local_reports/detailed_report.md` for the private metric summary and chart index.

`stop` does not interrupt an update already in progress; it prevents later scheduled runs. After a reboot, run `start` manually when you want automatic daily updates to resume.
