"""
Estimates what it costs to process a collection of videos.

The file is in four parts, top to bottom:
  1. load_config()          reads the numbers from config.json
  2. work_per_video_hour()  how much computer work one hour of video needs
  3. size_pool()            how many machines to rent, and what they cost
  4. estimate()             puts it all together, with numbered steps

Units used everywhere: US dollars, hours, GB.
"""
import json
import math
import os

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
HOURS_PER_MONTH = 730  # average hours in a month; turns a monthly price into an hourly one


def load_config():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        config = json.load(f)
    check_config(config)
    return config


def check_config(config):
    """Stop early with a clear message if the config has an obvious mistake."""
    total_share = sum(vt["share"] for vt in config["video_types"].values())
    if abs(total_share - 1.0) > 0.000001:
        raise ValueError(f"video type shares must add up to 1.0, but they add up to {total_share}")

    for vt_name, vt in config["video_types"].items():
        for stage_name in vt["factors"]:
            if stage_name not in config["stages"]:
                raise ValueError(f"video type {vt_name} mentions unknown stage {stage_name}")

    for stage_name, stage in config["stages"].items():
        if stage["machine"] not in ("gpu", "cpu"):
            raise ValueError(f"stage {stage_name} must use machine 'gpu' or 'cpu'")


def work_per_video_hour(config):
    """
    How much work one hour of video needs, averaged over the mix of video types.

    Returns two numbers:
      gpu_seconds - seconds of work on one GPU
      cpu_seconds - seconds of work on one CPU core
    """
    gpu_seconds = 0.0
    cpu_seconds = 0.0

    for video_type in config["video_types"].values():
        for stage_name, stage in config["stages"].items():
            # A factor of 0 means this video type skips the stage.
            # A factor of 0.5 means it only needs half the work. Default is 1.0.
            factor = video_type["factors"].get(stage_name, 1.0)

            # Only this share of the corpus is this video type.
            seconds = stage["seconds_per_video_hour"] * factor * video_type["share"]

            if stage["machine"] == "gpu":
                gpu_seconds += seconds
            else:
                cpu_seconds += seconds

    return gpu_seconds, cpu_seconds


def size_pool(work_hours, units_per_machine, price_per_hour, budget_hours, settings):
    """
    Decide how many machines to run, and what they cost.

    work_hours        : hours of work for one unit (one GPU, or one CPU core)
    units_per_machine : how many GPUs (or CPU cores) one machine has
    price_per_hour    : what one machine costs per hour
    budget_hours      : how long we are allowed to take
    """
    if work_hours <= 0:
        return {"machines": 0, "busy_hours": 0.0, "billed_hours": 0.0,
                "cost": 0.0, "fits_limit": True}

    # Step A: machines are never 100% busy, so we need more machine-hours than raw work.
    busy_hours = work_hours / (units_per_machine * settings["usable_share_of_machine"])

    # Step B: to finish inside the budget, run enough machines at the same time.
    # Example: 200 busy hours in a 72-hour budget needs ceil(200 / 72) = 3 machines.
    machines = math.ceil(busy_hours / budget_hours)

    # Step C: each machine spends some time starting up, and we pay for that too.
    billed_hours = busy_hours + machines * settings["startup_hours_per_machine"]

    return {
        "machines": machines,
        "busy_hours": busy_hours,
        "billed_hours": billed_hours,
        "cost": billed_hours * price_per_hour,
        "fits_limit": machines <= settings["max_machines_per_pool"],
    }


def check_inputs(config, corpus_hours, budget_hours, cloud, env, customers):
    if cloud not in config["clouds"]:
        raise ValueError(f"unknown cloud {cloud!r}; choose from {sorted(config['clouds'])}")
    if env not in config["environments"]:
        raise ValueError(f"unknown environment {env!r}; choose from {sorted(config['environments'])}")
    if corpus_hours <= 0:
        raise ValueError("corpus hours must be more than 0")
    if budget_hours <= 0:
        raise ValueError("budget hours must be more than 0")
    if customers < 1:
        raise ValueError("customers must be at least 1")


def estimate(config, corpus_hours, budget_hours, cloud, env, customers=1,
             egress_gb=50.0, shared_window_hours=None):
    """
    Estimate the total cost of processing a corpus.

    corpus_hours        : hours of video in the corpus (one customer)
    budget_hours        : hours of wall-clock time we allow for processing
    cloud               : 'aws', 'gcp' or 'azure'
    env                 : 'dev', 'qa', 'preprod' or 'prod'
    customers           : how many customers have a corpus this size
    egress_gb           : GB of data sent out to each customer
    shared_window_hours : hours of shared cost to charge to this job
                          (defaults to the budget hours)
    """
    check_inputs(config, corpus_hours, budget_hours, cloud, env, customers)
    settings = config["settings"]
    prices = config["clouds"][cloud]
    environment = config["environments"][env]

    # STEP 1: how much work is in the corpus.
    gpu_seconds, cpu_seconds = work_per_video_hour(config)
    # The GPU speed factor makes a slower GPU need more hours of work.
    gpu_work_hours = corpus_hours * gpu_seconds / 3600 / prices["gpu_relative_speed"]
    cpu_work_hours = corpus_hours * cpu_seconds / 3600

    # STEP 2: size the GPU pool and the CPU pool so the work fits in the budget.
    gpu = size_pool(gpu_work_hours, prices["gpu"]["gpus"],
                    prices["gpu"]["price_per_hour"], budget_hours, settings)
    cpu = size_pool(cpu_work_hours, prices["cpu"]["vcpus"],
                    prices["cpu"]["price_per_hour"], budget_hours, settings)

    # STEP 3: storage and data sent out, for this customer.
    stored_gb = corpus_hours * (settings["raw_gb_per_video_hour"]
                                + settings["derived_gb_per_video_hour"])
    storage_cost = stored_gb * prices["storage_per_gb_month"] * settings["keep_months"]
    egress_cost = egress_gb * prices["egress_per_gb"]

    # STEP 4: cost for one customer.
    compute_cost = gpu["cost"] + cpu["cost"]
    customer_cost = compute_cost + storage_cost + egress_cost

    # STEP 5: shared cost of the environment, for the time window we charge.
    window = budget_hours if shared_window_hours is None else shared_window_hours
    shared_control_plane = environment["clusters"] * prices["control_plane_per_hour"] * window
    shared_baseline = environment["baseline_nodes"] * prices["cpu"]["price_per_hour"] * window
    shared_foundation = environment["foundational_services_monthly"] / HOURS_PER_MONTH * window
    shared_cost = shared_control_plane + shared_baseline + shared_foundation

    # STEP 6: add it all up.
    customers_cost = customer_cost * customers
    total = shared_cost + customers_cost
    cost_per_video_hour = total / (corpus_hours * customers)

    warnings = []
    for name, pool in (("GPU", gpu), ("CPU", cpu)):
        if not pool["fits_limit"]:
            warnings.append(f"{name} pool needs {pool['machines']} machines, which is above the "
                            f"limit. Make the budget longer or raise the limit in config.json.")

    return {
        "gpu": gpu,
        "cpu": cpu,
        "compute_cost": compute_cost,
        "storage_cost": storage_cost,
        "egress_cost": egress_cost,
        "customer_cost": customer_cost,
        "shared": {
            "control_plane": shared_control_plane,
            "baseline_machines": shared_baseline,
            "foundation_services": shared_foundation,
            "total": shared_cost,
            "window_hours": window,
        },
        "customers_cost": customers_cost,
        "total": total,
        "cost_per_video_hour": cost_per_video_hour,
        "gpu_seconds_per_video_hour": gpu_seconds,
        "cpu_seconds_per_video_hour": cpu_seconds,
        "warnings": warnings,
    }
