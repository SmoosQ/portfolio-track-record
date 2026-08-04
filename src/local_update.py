"""Run the local report pipeline and optionally publish generated files to GitHub."""

from __future__ import annotations

import argparse
import fcntl
import logging
import os
import stat
import subprocess
from pathlib import Path
from typing import IO, Sequence

from .generate_report import main as generate_report

LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
LOCK_PATH = ROOT / ".local_update.lock"
REQUIRED_CREDENTIALS = {"BINANCE_API_KEY", "BINANCE_API_SECRET"}
OPTIONAL_CREDENTIALS = {"GITHUB_TOKEN"}
ASKPASS_PATH = ROOT / "scripts" / "git_askpass.sh"
GENERATED_PATHS = (ROOT / "reports", ROOT / "data" / "processed")
REQUIRED_OUTPUTS = (
    ROOT / "reports" / "normalized_equity_curve.png",
    ROOT / "reports" / "cumulative_pnl_curve.png",
    ROOT / "reports" / "drawdown_curve.png",
    ROOT / "reports" / "daily_returns.png",
    ROOT / "reports" / "monthly_returns.png",
    ROOT / "reports" / "key_metrics.png",
    ROOT / "reports" / "performance_summary.json",
    ROOT / "reports" / "performance_summary.md",
    ROOT / "data" / "processed" / "normalized_daily_equity.csv",
    ROOT / "local_reports" / "detailed_daily_performance.csv",
    ROOT / "local_reports" / "total_equity_curve.png",
    ROOT / "local_reports" / "pnl_components.png",
    ROOT / "local_reports" / "daily_total_returns.png",
    ROOT / "local_reports" / "monthly_total_returns.png",
    ROOT / "local_reports" / "detailed_summary.json",
)


def main(argv: Sequence[str] | None = None) -> int:
    """Load local credentials, update reports, and push generated changes."""

    parser = argparse.ArgumentParser(
        description="Update local USDC performance reports and publish generated files."
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Generate and validate reports without creating a Git commit or pushing.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    lock_file = _acquire_lock(LOCK_PATH)
    try:
        _load_local_credentials(ENV_PATH)
        if not args.no_push and not os.getenv("GITHUB_TOKEN"):
            raise RuntimeError("GITHUB_TOKEN is required for automatic publishing.")
        if not args.no_push:
            _prepare_repository()
        generate_report()
        _verify_outputs()
        if not args.no_push:
            _publish_generated_files()
    finally:
        lock_file.close()
    return 0


def _load_local_credentials(path: Path) -> None:
    """Load only the allowed credentials from a private local environment file."""

    if not path.is_file():
        raise RuntimeError(f"Local credential file is missing: {path}")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise RuntimeError("Local credential file must have mode 600 or stricter.")

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not separator or key not in REQUIRED_CREDENTIALS | OPTIONAL_CREDENTIALS or not value:
            raise RuntimeError(f"Invalid credential entry on line {line_number}.")
        if key in values:
            raise RuntimeError(f"Duplicate credential entry for {key}.")
        values[key] = value

    missing = REQUIRED_CREDENTIALS - values.keys()
    if missing:
        raise RuntimeError("Local credential file is missing required variables.")
    os.environ.update(values)


def _acquire_lock(path: Path) -> IO[str]:
    """Prevent manual and scheduled updates from running at the same time."""

    lock_file = path.open("w", encoding="utf-8")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock_file.close()
        raise RuntimeError("Another local performance update is already running.") from exc
    return lock_file


def _prepare_repository() -> None:
    """Require a clean index on main and fast-forward from origin before updating."""

    branch = _git("rev-parse", "--abbrev-ref", "HEAD", capture_output=True).stdout.strip()
    if branch != "main":
        raise RuntimeError("Automatic publishing is allowed only from the main branch.")
    staged = _git("diff", "--cached", "--quiet", check=False)
    if staged.returncode not in (0, 1):
        raise RuntimeError("Unable to inspect the Git index.")
    if staged.returncode == 1:
        raise RuntimeError("The Git index already contains staged changes; refusing to publish.")
    status = _git(
        "status",
        "--porcelain",
        "--untracked-files=all",
        capture_output=True,
    ).stdout.splitlines()
    allowed_prefixes = ("reports/", "data/processed/")
    unsafe_changes = [
        line[3:]
        for line in status
        if not line[3:].startswith(allowed_prefixes)
    ]
    if unsafe_changes:
        raise RuntimeError(
            "Uncommitted non-report files are present; refusing to publish: "
            + ", ".join(unsafe_changes)
        )
    _git("pull", "--ff-only", "origin", "main")


def _verify_outputs() -> None:
    missing = [str(path.relative_to(ROOT)) for path in REQUIRED_OUTPUTS if not path.is_file() or path.stat().st_size == 0]
    if missing:
        raise RuntimeError("Required generated files are missing or empty: " + ", ".join(missing))


def _publish_generated_files() -> None:
    """Commit only generated public artifacts and push when content changed."""

    relative_paths = [str(path.relative_to(ROOT)) for path in GENERATED_PATHS]
    _git("add", "--", *relative_paths)
    changes = _git("diff", "--cached", "--quiet", "--", *relative_paths, check=False)
    if changes.returncode == 0:
        LOGGER.info("Generated reports are unchanged; no commit was created.")
        return
    if changes.returncode != 1:
        raise RuntimeError("Unable to inspect generated Git changes.")
    _git("commit", "-m", "chore: update USDC performance", "--", *relative_paths)
    _git("push", "origin", "main")
    LOGGER.info("Published updated reports to origin/main.")


def _git(
    *args: str,
    check: bool = True,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["GIT_ASKPASS"] = str(ASKPASS_PATH)
    environment["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=check,
        capture_output=capture_output,
        env=environment,
        text=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
