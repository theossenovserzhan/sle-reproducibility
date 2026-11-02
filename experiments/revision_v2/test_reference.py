import math
import random
import unittest

import numpy as np

from reference import P, PARAMETERS, encrypt, decrypt, masks, evolve, key_contributions


class ReferenceTests(unittest.TestCase):
    def test_field_and_round_arithmetic(self):
        self.assertEqual(P.bit_length(), 128)
        self.assertEqual(math.gcd(3, P - 1), 1)
        self.assertLess((1 << 128) - P, 1 << 32)
        self.assertGreaterEqual(3 ** PARAMETERS["rounds"], P)

    def test_round_trip_full_field_edges(self):
        rng = random.Random(20261029)
        values = [0, 1, P - 1, P - 2, 1 << 64, (1 << 127), (1 << 64) - 1]
        values += [rng.randrange(P) for _ in range(20)]
        for key in (0, P - 1, rng.randrange(P)):
            for value in values:
                self.assertEqual(decrypt(encrypt(value, key), key), value)

    def test_full_width_contributions_and_independent_keys(self):
        shares, keys = key_contributions()
        self.assertEqual(len(keys), 9)
        for j, key in enumerate(keys):
            self.assertEqual(key, sum(row[j] for row in shares) % P)
        self.assertTrue(all(0 <= value < P for row in shares for value in row))
        # Structural check: no 30-bit cap remains. Not an entropy test.
        self.assertTrue(any(value >= (1 << 96) for row in shares for value in row))

    def test_rekey_and_all_candidate_scores(self):
        rng = np.random.default_rng(20261029)
        roots = rng.integers(0, 2, (7, 512), dtype=np.uint8)
        probes = rng.integers(0, 2, (11, 512), dtype=np.uint8)
        _, old_keys = key_contributions()
        _, new_keys = key_contributions()
        old_locs = [0, 1, P-1, 1<<64, 1<<127, P-2, 19]
        new_locs = evolve(new_keys[0], old_locs)
        self.assertEqual(len(set(new_locs)), len(new_locs))
        old_masks = masks(old_keys, old_locs)
        new_masks = masks(new_keys, new_locs)
        old_c = roots ^ old_masks
        new_c = old_c ^ old_masks ^ new_masks
        np.testing.assert_array_equal(new_c, roots ^ new_masks)
        for probe in probes:
            np.testing.assert_array_equal(np.count_nonzero((probe ^ new_masks) != new_c, axis=1),
                                          np.count_nonzero(roots != probe, axis=1))


if __name__ == "__main__":
    unittest.main()
