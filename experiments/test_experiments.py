"""Independent checks of retrieval completeness, overflow and exact Hamming."""
import itertools
import unittest

import numpy as np

from run_experiments import block_values, distances, identify, make_index, retrieve
from evaluate_float_binary import threshold_from_calibration, scores_for


class RetrievalTests(unittest.TestCase):
    def test_integer_hamming_matches_direct_512_bits(self):
        rng = np.random.default_rng(101)
        g = rng.integers(0, 2, (17, 512), dtype=np.uint8)
        q = rng.integers(0, 2, (9, 512), dtype=np.uint8)
        np.testing.assert_array_equal(distances(q, g), np.count_nonzero(q[:, None] != g, 2))

    def test_exact_search_exhaustively_for_all_six_bit_probes(self):
        roots = np.asarray(list(itertools.product([0, 1], repeat=6)), dtype=np.uint8)
        rng = np.random.default_rng(303)
        for _ in range(8):
            gallery = roots[rng.choice(len(roots), 11, replace=False)]
            scores = distances(roots, gallery)
            for width in (1, 2, 3):
                index = make_index(gallery, width)
                for capacity in (1, 3, 11):
                    for q, vals in enumerate(block_values(roots, width)):
                        winner, _, _, _ = identify(index, vals, scores[q], capacity, certified=True)
                        self.assertEqual(winner, int(np.argmin(scores[q])))

    def test_duplicate_locator_occurrences_are_deduplicated(self):
        g = np.asarray([[0, 0, 0, 0], [1, 1, 1, 1]], dtype=np.uint8)
        rows, _, occurrences = retrieve(make_index(g, 1), np.asarray([0, 0, 0, 0]))
        self.assertEqual(rows.tolist(), [0])
        self.assertEqual(occurrences, 4)

    def test_overflow_falls_back_instead_of_silently_dropping(self):
        g = np.asarray([[0, 0, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]], dtype=np.uint8)
        q = g[1:2]
        vals = block_values(q, 2)[0]
        winner, _, fallback, _ = identify(make_index(g, 2), vals, distances(q, g)[0], 1, certified=True)
        self.assertTrue(fallback)
        self.assertEqual(winner, 1)

    def test_complete_candidates_need_no_extra_fallback(self):
        g = np.asarray([[0, 0, 0, 0], [0, 0, 0, 1]], dtype=np.uint8)
        q = g[1:2]
        winner, candidates, fallback, _ = identify(make_index(g, 2), block_values(q, 2)[0], distances(q, g)[0], 1, certified=True)
        self.assertEqual(len(candidates), len(g))
        self.assertFalse(fallback)
        self.assertEqual(winner, 1)

    def test_empty_candidates_fall_back(self):
        g = np.zeros((1, 6), dtype=np.uint8)
        q = np.ones((1, 6), dtype=np.uint8)
        winner, candidates, fallback, _ = identify(make_index(g, 2), block_values(q, 2)[0], distances(q, g)[0], 1, certified=True)
        self.assertTrue(fallback)
        self.assertEqual(len(candidates), 0)
        self.assertEqual(winner, 0)


class UtilityTests(unittest.TestCase):
    def test_calibration_threshold_respects_ties(self):
        scores = np.asarray([1, 1, 1, 2, 3, 3, 4, 5, 5, 5])
        for target in (0, 0.01, 0.1, 0.3, 0.5, 1):
            threshold = threshold_from_calibration(scores, target)
            self.assertLessEqual(np.mean(scores >= threshold), target)

    def test_float_and_binary_scores_use_same_prototypes(self):
        g = np.asarray([[1., -1., 2.], [-1., 1., -2.]])
        q = np.asarray([[2., -2., 4.]])
        self.assertEqual(np.argmax(scores_for(g, q, "float_cosine")), 0)
        np.testing.assert_array_equal(scores_for(g, q, "binary_hamming"), [[0, -3]])


if __name__ == "__main__":
    unittest.main()
