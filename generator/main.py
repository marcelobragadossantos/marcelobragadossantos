"""Entry point for the Galaxy Profile README generator."""

import argparse
import json
import logging
import os
import sys

import yaml

from generator.config import ConfigError, validate_config
from generator.github_api import GitHubAPI
from generator.svg_builder import SVGBuilder

logger = logging.getLogger(__name__)

DEMO_STATS = {"commits": 1847, "stars": 342, "prs": 156, "issues": 89, "repos": 42}
DEMO_LANGUAGES = {
    "Python": 450000,
    "TypeScript": 380000,
    "JavaScript": 120000,
    "Go": 95000,
    "Rust": 45000,
    "Shell": 30000,
    "Dockerfile": 15000,
    "CSS": 10000,
}
DEMO_LANG_META = {
    "Python": {"repos": 12, "last_activity": "2026-04-10T12:00:00Z"},
    "TypeScript": {"repos": 8, "last_activity": "2026-04-09T10:00:00Z"},
    "JavaScript": {"repos": 6, "last_activity": "2026-04-08T10:00:00Z"},
    "Go": {"repos": 4, "last_activity": "2026-03-20T10:00:00Z"},
    "Rust": {"repos": 2, "last_activity": "2026-02-15T10:00:00Z"},
    "Shell": {"repos": 10, "last_activity": "2026-04-05T10:00:00Z"},
    "Dockerfile": {"repos": 5, "last_activity": "2026-03-28T10:00:00Z"},
    "CSS": {"repos": 3, "last_activity": "2026-03-10T10:00:00Z"},
}
DEMO_COMMIT_WEEKS = [
    3, 5, 2, 7, 8, 4, 6, 9, 12, 8, 5, 3, 7, 11, 15, 10, 6, 4, 8, 14, 18, 12,
    7, 5, 9, 13, 20, 16, 11, 7, 4, 8, 15, 22, 18, 14, 9, 6, 10, 16, 24, 19,
    13, 8, 5, 11, 17, 25, 21, 14, 9, 12,
]
DEMO_FLIGHT_LOG = [
    {"sha": "a1b2c3d", "message": "feat(api): add telemetry bundle endpoint",
     "timestamp": "2026-04-10T14:32:00Z", "repo": "marcelobragadossantos/galaxy-profile"},
    {"sha": "e4f5g6h", "message": "fix(auth): token refresh race condition",
     "timestamp": "2026-04-09T09:11:00Z", "repo": "marcelobragadossantos/api-core"},
    {"sha": "i7j8k9l", "message": "chore: bump deps",
     "timestamp": "2026-04-08T16:45:00Z", "repo": "marcelobragadossantos/infra"},
    {"sha": "m0n1o2p", "message": "refactor: extract telemetry bundle",
     "timestamp": "2026-04-07T11:20:00Z", "repo": "marcelobragadossantos/galaxy-profile"},
    {"sha": "q3r4s5t", "message": "docs: GH_TOKEN setup instructions",
     "timestamp": "2026-04-06T08:00:00Z", "repo": "marcelobragadossantos/galaxy-profile"},
]

HISTORY_FILENAME = ".telemetry_history.json"


def _load_previous_stats(history_path: str) -> dict:
    """Load the previous stats snapshot from disk, or return empty dict."""
    if not os.path.exists(history_path):
        return {}
    try:
        with open(history_path, "r") as f:
            data = json.load(f)
        return data.get("stats", {}) if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not read telemetry history (%s); starting fresh.", e)
        return {}


def _write_history(history_path: str, stats: dict) -> None:
    """Write the current stats snapshot for the next run to compute deltas."""
    try:
        with open(history_path, "w") as f:
            json.dump({"stats": stats}, f, indent=2)
    except OSError as e:
        logger.warning("Could not write telemetry history (%s).", e)


def generate(args):
    """Generate SVGs from config (existing behavior extracted into a function)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    demo = getattr(args, "demo", False)

    # Load config
    if demo:
        config_path = os.path.join(os.path.dirname(__file__), "..", "config.example.yml")
    else:
        config_path = os.path.join(os.path.dirname(__file__), "..", "config.yml")

    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        if demo:
            logger.error("config.example.yml not found.")
        else:
            logger.error("config.yml not found. Copy config.example.yml to config.yml and edit it.")
        sys.exit(1)

    try:
        config = validate_config(config)
    except ConfigError as e:
        logger.error("Invalid config: %s", e)
        sys.exit(1)

    username = config["username"]

    logger.info("Generating profile SVGs for @%s...", username)

    output_dir = os.path.join(os.path.dirname(__file__), "..", "assets", "generated")
    os.makedirs(output_dir, exist_ok=True)
    history_path = os.path.join(output_dir, HISTORY_FILENAME)

    # Load the previous snapshot BEFORE generating so we can compute deltas.
    previous_stats = _load_previous_stats(history_path)

    if demo:
        logger.info("Demo mode: using hardcoded telemetry data.")
        bundle = {
            "stats": DEMO_STATS,
            "languages": DEMO_LANGUAGES,
            "lang_meta": DEMO_LANG_META,
            "commit_weeks": DEMO_COMMIT_WEEKS,
            "flight_log": DEMO_FLIGHT_LOG,
        }
    else:
        api = GitHubAPI(username)
        bundle = api.fetch_telemetry_bundle()

    stats = bundle["stats"]
    languages = bundle["languages"]
    lang_meta = bundle.get("lang_meta", {})
    commit_weeks = bundle.get("commit_weeks", [])
    flight_log = bundle.get("flight_log", [])

    logger.info("Stats: %s", stats)
    logger.info("Languages: %d found", len(languages))
    logger.info("Commit weeks: %d", len(commit_weeks))
    logger.info("Flight log entries: %d", len(flight_log))

    # Build SVGs
    builder = SVGBuilder(
        config,
        stats,
        languages,
        previous_stats=previous_stats,
        commit_weeks=commit_weeks,
        lang_meta=lang_meta,
        flight_log=flight_log,
    )

    svgs = {
        "galaxy-header.svg": builder.render_galaxy_header(),
        "stats-card.svg": builder.render_stats_card(),
        "tech-stack.svg": builder.render_tech_stack(),
        "flight-log.svg": builder.render_flight_log(),
        "projects-constellation.svg": builder.render_projects_constellation(),
    }

    for filename, content in svgs.items():
        path = os.path.join(output_dir, filename)
        with open(path, "w") as f:
            f.write(content)
        logger.info("Wrote %s", path)

    # Persist the new snapshot so the next run can compute 7d deltas.
    _write_history(history_path, stats)

    logger.info("Done! %d SVGs generated.", len(svgs))


def main():
    parser = argparse.ArgumentParser(description="Generate Galaxy Profile SVGs")
    subparsers = parser.add_subparsers(dest="command")

    # Subcommand: init
    subparsers.add_parser("init", help="Interactive setup wizard to create config.yml")

    # Subcommand: generate
    gen_parser = subparsers.add_parser("generate", help="Generate SVGs from config")
    gen_parser.add_argument(
        "--demo",
        action="store_true",
        help="Generate SVGs with demo data (no API calls, uses config.example.yml)",
    )

    # Top-level --demo for backward compatibility (python -m generator.main --demo)
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Generate SVGs with demo data (no API calls, uses config.example.yml)",
    )

    args = parser.parse_args()

    if args.command == "init":
        from generator.cli_init import run_init
        run_init()
    else:
        # Default behavior: generate (supports both `generate --demo` and `--demo`)
        generate(args)


if __name__ == "__main__":
    main()
