"""Tests for the sigmoid price function and scaling utilities."""

import math

from src.sigmoid import (
    NODE_FLOAT_SCALING_FACTOR,
    from_node_int,
    sigmoid_price,
    to_node_int,
)


class TestScaling:
    def test_to_node_int(self):
        assert to_node_int(0.26) == 2600
        assert to_node_int(28.5) == 285000
        assert to_node_int(0.0) == 0

    def test_from_node_int(self):
        assert from_node_int(2600) == 0.26
        assert from_node_int(285000) == 28.5
        assert from_node_int(0) == 0.0

    def test_roundtrip(self):
        for val in [0.0, 0.26, 1.0, 8.0, 28.5, 100.0]:
            assert abs(from_node_int(to_node_int(val)) - val) < 1e-9


class TestSigmoidPrice:
    """Test the sigmoid function against known values from simulation.py."""

    K_UPPER = 28.5
    K_LOWER = 8.0
    THETA = 1.0
    STEEPNESS = 2.5

    def _reference_sigmoid(self, ratio):
        """Reference implementation matching simulation.py _price_function."""
        if self.K_UPPER <= self.K_LOWER:
            return self.K_LOWER
        denominator = 1 + math.exp(-self.STEEPNESS * (ratio - self.THETA))
        if denominator == 0:
            return self.K_LOWER
        return self.K_UPPER - ((self.K_UPPER - self.K_LOWER) / denominator)

    def test_balanced_market(self):
        """ratio=1.0 (balanced) should give midpoint price."""
        price = sigmoid_price(1.0, self.K_UPPER, self.K_LOWER, self.THETA, self.STEEPNESS)
        # At ratio=theta, sigmoid is at 0.5, so price = K_upper - (K_upper-K_lower)/2
        expected = self.K_UPPER - (self.K_UPPER - self.K_LOWER) / 2
        assert abs(price - expected) < 0.01

    def test_excess_supply(self):
        """High supply ratio → price drops toward K_lower."""
        price = sigmoid_price(3.0, self.K_UPPER, self.K_LOWER, self.THETA, self.STEEPNESS)
        assert price < 15.0  # Well below midpoint
        assert price >= self.K_LOWER

    def test_excess_demand(self):
        """Low supply ratio → price rises toward K_upper."""
        price = sigmoid_price(0.1, self.K_UPPER, self.K_LOWER, self.THETA, self.STEEPNESS)
        assert price > 20.0  # Well above midpoint
        assert price <= self.K_UPPER

    def test_clamping_bounds(self):
        """Price should always be within [K_lower, K_upper]."""
        for ratio in [0.001, 0.01, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 100.0]:
            price = sigmoid_price(
                ratio, self.K_UPPER, self.K_LOWER, self.THETA, self.STEEPNESS
            )
            assert self.K_LOWER <= price <= self.K_UPPER

    def test_k_upper_equals_k_lower(self):
        """When K_upper == K_lower, return K_lower."""
        price = sigmoid_price(1.0, 10.0, 10.0, 1.0, 2.5)
        assert price == 10.0

    def test_k_upper_less_than_k_lower(self):
        """When K_upper < K_lower, return K_lower."""
        price = sigmoid_price(1.0, 5.0, 10.0, 1.0, 2.5)
        assert price == 10.0

    def test_matches_reference_implementation(self):
        """Cross-validate against the simulation.py reference."""
        for ratio in [0.1, 0.5, 0.8, 1.0, 1.2, 1.5, 2.0, 3.0]:
            our_price = sigmoid_price(
                ratio, self.K_UPPER, self.K_LOWER, self.THETA, self.STEEPNESS
            )
            ref_price = self._reference_sigmoid(ratio)
            assert abs(our_price - ref_price) < 0.001, (
                f"Mismatch at ratio={ratio}: ours={our_price}, ref={ref_price}"
            )

    def test_monotonically_decreasing(self):
        """Price should decrease as supply/demand ratio increases."""
        ratios = [0.1, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0]
        prices = [
            sigmoid_price(r, self.K_UPPER, self.K_LOWER, self.THETA, self.STEEPNESS)
            for r in ratios
        ]
        for i in range(len(prices) - 1):
            assert prices[i] >= prices[i + 1], (
                f"Not monotonic: price({ratios[i]})={prices[i]} > "
                f"price({ratios[i+1]})={prices[i+1]}"
            )
