"""
Command-line entry point. Two commands:

  python src/main.py estimate --corpus-hours 2000 --budget-hours 72 --cloud aws --env prod
  python src/main.py sweep --env prod --out results/sweep.csv

'estimate' prints one scenario. 'sweep' runs many scenarios and saves them to a CSV file.
"""
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calculator  # noqa: E402

SWEEP_CORPUS_HOURS = [100, 250, 500, 1000, 2000, 5000, 10000]
SWEEP_BUDGET_HOURS = [24, 72, 168]


def print_estimate(result, corpus_hours, budget_hours, cloud, env, customers):
    print(f"Corpus: {corpus_hours:,g} video-hours, budget {budget_hours:g} hours, "
          f"cloud {cloud}, environment {env}, customers {customers}")
    print()
    print("Compute (one customer):")
    for label, pool in (("GPU", result["gpu"]), ("CPU", result["cpu"])):
        print(f"  {label}: {pool['machines']} machines at the same time, "
              f"{pool['billed_hours']:,.1f} machine-hours billed, ${pool['cost']:,.2f}")
    print()
    print("Cost for one customer:")
    print(f"  compute  ${result['compute_cost']:,.2f}")
    print(f"  storage  ${result['storage_cost']:,.2f}")
    print(f"  egress   ${result['egress_cost']:,.2f}")
    print(f"  subtotal ${result['customer_cost']:,.2f}")
    print()
    shared = result["shared"]
    print(f"Shared cost for the environment ({shared['window_hours']:g}-hour window):")
    print(f"  control plane       ${shared['control_plane']:,.2f}")
    print(f"  baseline machines   ${shared['baseline_machines']:,.2f}")
    print(f"  foundation services ${shared['foundation_services']:,.2f}")
    print(f"  subtotal            ${shared['total']:,.2f}")
    print()
    print(f"TOTAL: ${result['total']:,.2f} "
          f"(shared ${shared['total']:,.2f} + customers ${result['customers_cost']:,.2f})")
    print(f"Cost per video-hour: ${result['cost_per_video_hour']:,.2f}")
    for warning in result["warnings"]:
        print(f"WARNING: {warning}")


def run_estimate(args, config):
    result = calculator.estimate(config, args.corpus_hours, args.budget_hours, args.cloud,
                                 args.env, customers=args.customers, egress_gb=args.egress_gb,
                                 shared_window_hours=args.shared_window_hours)
    print_estimate(result, args.corpus_hours, args.budget_hours, args.cloud, args.env, args.customers)


def run_sweep(args, config):
    rows = []
    for cloud in args.clouds:
        for corpus_hours in args.corpus_hours:
            for budget_hours in args.budget_hours:
                r = calculator.estimate(config, corpus_hours, budget_hours, cloud, args.env,
                                        customers=args.customers, egress_gb=args.egress_gb)
                rows.append({
                    "cloud": cloud,
                    "env": args.env,
                    "corpus_hours": corpus_hours,
                    "budget_hours": budget_hours,
                    "customers": args.customers,
                    "gpu_machines": r["gpu"]["machines"],
                    "cpu_machines": r["cpu"]["machines"],
                    "customer_cost_usd": round(r["customer_cost"], 2),
                    "shared_cost_usd": round(r["shared"]["total"], 2),
                    "total_cost_usd": round(r["total"], 2),
                    "cost_per_video_hour_usd": round(r["cost_per_video_hour"], 4),
                    "within_limits": not r["warnings"],
                })

    folder = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(folder, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {len(rows)} scenarios to {args.out}")


def build_parser(config):
    parser = argparse.ArgumentParser(description="Estimate the cost of processing a video corpus.")
    commands = parser.add_subparsers(dest="command")

    est = commands.add_parser("estimate", help="Cost of one scenario, with a breakdown.")
    est.add_argument("--corpus-hours", type=float, required=True, help="Hours of video.")
    est.add_argument("--budget-hours", type=float, required=True, help="Hours we allow for processing.")
    est.add_argument("--cloud", choices=sorted(config["clouds"]), default="aws")
    est.add_argument("--env", choices=sorted(config["environments"]), default="prod")
    est.add_argument("--customers", type=int, default=1, help="Number of customers with this corpus size.")
    est.add_argument("--egress-gb", type=float, default=50.0, help="GB sent out to each customer.")
    est.add_argument("--shared-window-hours", type=float, default=None,
                     help="Hours of shared cost to charge (default: the budget hours).")
    est.set_defaults(run=run_estimate)

    sweep = commands.add_parser("sweep", help="Many scenarios, saved to a CSV file.")
    sweep.add_argument("--clouds", nargs="+", choices=sorted(config["clouds"]),
                       default=sorted(config["clouds"]))
    sweep.add_argument("--env", choices=sorted(config["environments"]), default="prod")
    sweep.add_argument("--corpus-hours", nargs="+", type=float, default=SWEEP_CORPUS_HOURS)
    sweep.add_argument("--budget-hours", nargs="+", type=float, default=SWEEP_BUDGET_HOURS)
    sweep.add_argument("--customers", type=int, default=1)
    sweep.add_argument("--egress-gb", type=float, default=50.0)
    sweep.add_argument("--out", default="results/sweep.csv")
    sweep.set_defaults(run=run_sweep)
    return parser


def main():
    config = calculator.load_config()
    parser = build_parser(config)
    args = parser.parse_args()
    if not hasattr(args, "run"):
        parser.print_help()
        return 0
    try:
        args.run(args, config)
    except ValueError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
