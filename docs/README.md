# Platform Cost Calculator

Estimates the cost of processing a corpus of video, split into shared costs
(per environment) and per-customer costs (compute, storage, data out).

- [architecture.md](architecture.md): the pipeline, the cost model, the calculation steps, the design decisions, and the limits.

## How the code is organised

```
src/
├── config.json              # all numbers: stage timings, video mix, cloud prices, environments
├── calculator.py            # the cost logic (four functions, read top to bottom)
├── main.py                  # command-line entry point: "estimate" and "sweep"
└── tests/
    └── test_calculator.py   # checks that the logic behaves as expected
```

`calculator.py` has four parts:

| Function | What it does |
|---|---|
| `load_config()` | Reads `config.json` and checks it |
| `work_per_video_hour()` | Works out how much computer work one hour of video needs, averaged over the video mix |
| `size_pool()` | Decides how many machines to run and what they cost |
| `estimate()` | Runs the six numbered steps and returns the total |

`main.py` reads the command-line options, calls `estimate()`, and prints the
result or saves it to a CSV file.

## Requirements

- Python 3.9 or newer. Nothing else: the project uses only the standard library.

## How to run locally

From the repository root:

```bash
# 1. Check the Python version (nothing to install)
python3 --version

# 2. Show the help
python3 src/main.py --help

# 3. Estimate one scenario
python3 src/main.py estimate --corpus-hours 2000 --budget-hours 72 --cloud aws --env prod

# 4. Estimate with more customers, or a different cloud or environment
python3 src/main.py estimate --corpus-hours 10000 --budget-hours 24 --cloud azure --env prod --customers 3

# 5. Run many scenarios and save them to a CSV file
python3 src/main.py sweep --env prod --out results/sweep.csv

# 6. Run the tests
python3 -m unittest discover -s src/tests -v
```

Expected output for step 3 ends with:

```
TOTAL: $2,207.81 (shared $1,293.75 + customers $914.06)
Cost per video-hour: $1.10
```

## Options

| Option | Meaning | Default |
|---|---|---|
| `--corpus-hours` | Hours of video (required for `estimate`) | none |
| `--budget-hours` | Hours allowed for processing (required for `estimate`) | none |
| `--cloud` | `aws`, `gcp`, or `azure` | `aws` |
| `--env` | `dev`, `qa`, `preprod`, or `prod` | `prod` |
| `--customers` | Number of customers with this corpus size | `1` |
| `--egress-gb` | GB sent to each customer | `50` |
| `--shared-window-hours` | Hours of shared cost to charge | the budget hours |

`sweep` takes `--clouds`, `--corpus-hours`, `--budget-hours` (each accepts
several values), plus `--env`, `--customers`, `--egress-gb`, and `--out`.

## Changing the numbers

Edit `src/config.json`, not the code. For example:

- `stages`: seconds of work per video hour for each stage.
- `video_types`: the share of each video type, and any stage factors. Shares must add up to 1.0.
- `clouds`: machine prices, GPU speed, storage and data-out prices.
- `environments`: clusters, baseline machines, and monthly foundation cost.
- `settings`: usable machine share, startup time, machine limit, storage per hour, and months kept.

All prices and timings are placeholders. Replace them with measured values and current prices before using the results.

## Troubleshooting

- `unknown cloud` or `unknown environment`: check the spelling against `config.json`.
- `video type shares must add up to 1.0`: the `share` values in `video_types` don't total 1.0.
- A warning that a pool needs too many machines: lengthen the budget, or raise `max_machines_per_pool` in `config.json`.
