"""Sentinel for the top-level unit run (review B3, harness-followups rework 3).

scripts/verify.sh requires the line
`test_top_level_unit_suite_ran (...) ... ok` in scripts/test.sh's verbose
output. This module is a top-level test module, so the line appears only if
the top-level unittest run in test.sh actually happened. Deleting that run
line then turns the gate red even when another test package still runs
(review mutants m4, m7). Do not move this file into a sub-package."""

import unittest


class TopLevelSuiteSentinelTest(unittest.TestCase):
    def test_top_level_unit_suite_ran(self):
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
