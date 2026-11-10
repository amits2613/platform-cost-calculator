"""
Tests. Each test checks one simple rule the calculator must follow.
Run with:  python -m unittest discover -s src/tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import calculator  # noqa: E402


class CalculatorTests(unittest.TestCase):

    def setUp(self):
        self.config = calculator.load_config()

    def test_video_type_shares_add_up_to_one(self):
        total = sum(vt["share"] for vt in self.config["video_types"].values())
        self.assertAlmostEqual(total, 1.0)

    def test_pool_size_example_from_the_comments(self):
        # 200 hours of work, every machine fully busy, 72-hour budget -> 3 machines.
        settings = {"usable_share_of_machine": 1.0, "startup_hours_per_machine": 0.0,
                    "max_machines_per_pool": 200}
        pool = calculator.size_pool(200, 1, 1.0, 72, settings)
        self.assertEqual(pool["machines"], 3)

    def test_longer_budget_needs_fewer_gpu_machines(self):
        short = calculator.estimate(self.config, 1000, 24, "aws", "prod")
        long = calculator.estimate(self.config, 1000, 168, "aws", "prod")
        self.assertGreater(short["gpu"]["machines"], long["gpu"]["machines"])

    def test_double_the_corpus_means_double_the_work(self):
        small = calculator.estimate(self.config, 1000, 72, "aws", "prod")
        big = calculator.estimate(self.config, 2000, 72, "aws", "prod")
        ratio = big["gpu"]["busy_hours"] / small["gpu"]["busy_hours"]
        self.assertAlmostEqual(ratio, 2.0)

    def test_shared_cost_does_not_depend_on_corpus_size(self):
        small = calculator.estimate(self.config, 100, 72, "gcp", "qa")
        big = calculator.estimate(self.config, 10000, 72, "gcp", "qa")
        self.assertAlmostEqual(small["shared"]["total"], big["shared"]["total"])

    def test_more_customers_multiply_only_customer_costs(self):
        one = calculator.estimate(self.config, 500, 72, "aws", "dev", customers=1)
        three = calculator.estimate(self.config, 500, 72, "aws", "dev", customers=3)
        self.assertAlmostEqual(three["customers_cost"], 3 * one["customers_cost"])
        self.assertAlmostEqual(three["shared"]["total"], one["shared"]["total"])

    def test_unknown_cloud_is_rejected(self):
        with self.assertRaises(ValueError):
            calculator.estimate(self.config, 100, 24, "oracle", "prod")


if __name__ == "__main__":
    unittest.main()
