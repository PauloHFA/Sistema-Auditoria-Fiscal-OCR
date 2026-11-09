from scripts.load_test import _percentile


def test_percentile_uses_nearest_rank_for_small_samples() -> None:
    assert _percentile([4.0, 1.0, 3.0, 2.0], 0.5) == 2.0
    assert _percentile([float(value) for value in range(1, 101)], 0.95) == 95.0
    assert _percentile([], 0.95) == 0.0
