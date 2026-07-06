#!/usr/bin/env python3
"""RPA Core — Generic Multi-Tenant Judicial Intimation Capture System.

Usage::

    python -m src.main --client-id escritorio_alpha
    python -m src.main --client-id escritorio_alpha --no-headless
    python -m src.main --list-clients
    python -m src.main --client-id escritorio_alpha --remote-selenium http://localhost:4444

Environment::

    CLIENT_ID=escritorio_alpha python -m src.main
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Ensure the project root is on sys.path so `src.*` imports resolve
# when running as `python src/main.py` (without -m).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="RPA Core — Judicial Intimation Capture",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.main --client-id escritorio_alpha
  python -m src.main --client-id escritorio_alpha --no-headless
  python -m src.main --list-clients
  python -m src.main --client-id escritorio_alpha --remote-selenium http://localhost:4444
        """,
    )

    p.add_argument(
        "--client-id",
        default=os.getenv("CLIENT_ID", ""),
        help="Client identifier matching a JSON in src/configs/ (or set CLIENT_ID env var).",
    )
    p.add_argument(
        "--no-headless",
        action="store_true",
        help="Show the browser window (disable headless mode). Useful for debugging.",
    )
    p.add_argument(
        "--remote-selenium",
        default=os.getenv("SELENIUM_REMOTE_URL"),
        help="Remote Selenium Grid / WebDriver URL (e.g. http://localhost:4444).",
    )
    p.add_argument(
        "--list-clients",
        action="store_true",
        help="List available client configurations and exit.",
    )
    p.add_argument(
        "--configs-dir",
        default="src/configs",
        help="Directory where client JSON files are stored (default: src/configs).",
    )

    return p


async def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    # -- Early exits ------------------------------------------------------
    from dotenv import load_dotenv

    load_dotenv()

    if args.list_clients:
        from src.config_manager import ConfigManager

        clients = ConfigManager.list_clients(args.configs_dir)
        if clients:
            print("Available clients:")
            for c in clients:
                print(f"  • {c}")
        else:
            print(f"No .json configs found in {args.configs_dir}/")
        return

    if not args.client_id:
        parser.error(
            "--client-id is required (or set CLIENT_ID env var). "
            "Use --list-clients to see available configurations."
        )

    # -- Prime logging ----------------------------------------------------
    from src.utils.logger import get_logger

    logger = get_logger("main")
    logger.info("RPA Core starting — client=%s", args.client_id)

    # -- Run pipeline -----------------------------------------------------
    from src.orchestrator import RPAOrchestrator

    orchestrator = RPAOrchestrator(
        client_id=args.client_id,
        headless=not args.no_headless,
        remote_selenium_url=args.remote_selenium,
    )

    output_path = await orchestrator.run()

    if output_path:
        logger.info("✓ Done — %s", output_path)
        print(f"\n✓ Output: {output_path}")
    else:
        logger.info("✓ Done — no records generated")
        print("\n✓ Done — no intimations found today.")


if __name__ == "__main__":
    asyncio.run(main())
