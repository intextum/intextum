#!/usr/bin/env python3
"""Manual smoke-test for the SMB CHANGE_NOTIFY watcher.

Usage:
    python scripts/test_smb_notify.py \
        --server fileserver.local \
        --share documents \
        [--port 445] \
        [--username user] \
        [--password pass] \
        [--domain WORKGROUP] \
        [--mount-path /mnt/share] \
        [--timeout 60]

The script connects to the SMB share, subscribes to CHANGE_NOTIFY events,
and prints every detected change until --timeout seconds elapse or you
press Ctrl-C.  Create / rename / delete a file on the share to confirm
events are received.

Exit codes:
    0  — at least one change event was received
    1  — timeout expired with no events (or connection failed)
"""

import argparse
import asyncio
import logging
import sys
import time

# Allow running from repo root: `python scripts/test_smb_notify.py`
sys.path.insert(0, ".")

from models.connector_types import LocalFsDataConnector  # noqa: E402
from services.smb_watcher import SmbNotifyWatcher  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("smb-notify-test")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--server", required=True, help="SMB server hostname or IP")
    p.add_argument("--share", required=True, help="SMB share name")
    p.add_argument("--port", type=int, default=445, help="SMB port (default 445)")
    p.add_argument("--username", default="", help="SMB username")
    p.add_argument("--password", default="", help="SMB password")
    p.add_argument("--domain", default="", help="SMB/AD domain")
    p.add_argument(
        "--mount-path",
        default="/mnt/share",
        help="Local mount point (used for path mapping, default /mnt/share)",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Seconds to wait for events (default 60)",
    )
    return p.parse_args()


async def run(args: argparse.Namespace) -> bool:
    folder = LocalFsDataConnector(
        uuid="test-smb-notify",
        name="smb-smoke-test",
        path=args.mount_path,
        watch=True,
        watcher_type="smb_notify",
        smb_server=args.server,
        smb_share=args.share,
        smb_port=args.port,
        smb_username=args.username or None,
        smb_password=args.password or None,
        smb_domain=args.domain or None,
        poll_interval_seconds=5,
    )

    watcher = SmbNotifyWatcher(folder)
    received_events = False
    start = time.monotonic()

    log.info("Connecting to \\\\%s\\%s:%d ...", args.server, args.share, args.port)
    log.info(
        "Waiting up to %ds for file change events (Ctrl-C to stop) ...", args.timeout
    )
    log.info(">>> Create, rename, or delete a file on the share to see events <<<")

    try:
        async for batch in watcher.watch():
            if not batch:
                log.warning("Buffer overflow — full reconcile would be needed")
                continue

            for change_type, path in batch:
                log.info("  %s  %s", change_type.name.upper(), path)
                received_events = True

            elapsed = time.monotonic() - start
            if elapsed >= args.timeout:
                log.info("Timeout reached after %.0fs", elapsed)
                break
    except KeyboardInterrupt:
        log.info("Interrupted by user")
    except Exception:
        log.exception("SMB watcher failed")
        return False

    if received_events:
        log.info("SUCCESS — SMB CHANGE_NOTIFY is working")
    else:
        log.warning("No events received within the timeout period")

    return received_events


def main() -> None:
    args = parse_args()
    ok = asyncio.run(run(args))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
