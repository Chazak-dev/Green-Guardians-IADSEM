"""CLI: replay one or more sample_data/scenarios/*.json mock mission
scenarios through the real MissionController, writing to the same
results/mission_log.jsonl the live app uses. Handy for demoing or
populating the dashboard without Webots or a trained model.
See sample_data/README.md.

Usage:
    python run_scenario.py confirmed_fire_alert
    python run_scenario.py --all
"""
import argparse
import json

from backend.scenario_runner import SCENARIOS_DIR, discover_scenarios, run_scenario


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scenario", nargs="?",
                         help="Scenario name (without .json). Omit and pass --all to run every scenario.")
    parser.add_argument("--all", action="store_true", help="Run every scenario in sample_data/scenarios/")
    return parser.parse_args()


def main():
    args = parse_args()
    available = discover_scenarios()
    available_names = ", ".join(p.stem for p in available)

    if args.all:
        if not available:
            raise SystemExit(f"No scenario files found in {SCENARIOS_DIR}")
        paths = available
    elif args.scenario:
        path = SCENARIOS_DIR / f"{args.scenario}.json"
        if not path.exists():
            raise SystemExit(f"Unknown scenario {args.scenario!r}. Available: {available_names}")
        paths = [path]
    else:
        raise SystemExit(f"Pass a scenario name or --all. Available: {available_names}")

    for path in paths:
        summary = run_scenario(path)
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
