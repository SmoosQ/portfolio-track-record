# Local Operations

The updater is scheduled daily at **08:10 Asia/Shanghai**, but it is disabled after every machine reboot. There is no continuously running background process.

Scheduled runs use `/usr/bin/proxychains4` with `config/proxychains.conf`. The
local Mihomo SOCKS5 listener must be available on `127.0.0.1:7891`.

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

The private `local_reports/minute/*.csv.gz`, `total_equity_curve.png`, and `pnl_components.png` use one-minute sampling. Raw trade and mark-price caches stay under the ignored `data/private/` directory.

Open `local_reports/detailed_report.md` for the private metric summary and chart index.

Private downloads are incremental. `data/private/state.json` stores the last successful cursors, while raw income, trades, mark prices, and snapshots are partitioned by UTC date. A small overlap is re-downloaded and deduplicated to recover delayed or interrupted records.

`stop` does not interrupt an update already in progress; it prevents later scheduled runs. After a reboot, run `start` manually when you want automatic daily updates to resume.
