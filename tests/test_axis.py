import pytest

from wraith_trainer.axis import (
    AxisProcessor,
    Calibration,
    Response,
    TravelCapture,
    moved_axis,
    normalize,
    shape,
)


@pytest.mark.parametrize(
    ("raw", "expected"), [(-0.9, -1), (-0.35, -0.5), (0.1, 0), (0.4, 0.5), (1, 1)]
)
def test_asymmetric_normalization_and_clipping(raw, expected):
    assert normalize(raw, Calibration(-0.8, 0.1, 0.7)) == pytest.approx(expected)


def test_signed_power_curve_and_deadzone_rescaling():
    response = Response(inner=0.1, outer=0.1, exponent=2)
    assert shape(0.08, response) == 0
    assert shape(0.5, response) == pytest.approx(0.25)
    assert shape(-0.5, response) == pytest.approx(-0.25)
    assert shape(0.91, response) == 1


def test_inversion_gain_and_output_ceiling():
    response = Response(inner=0, exponent=1, inverted=True, sensitivity=2, maximum=0.6)
    assert shape(0.1, response) == pytest.approx(-0.2)
    assert shape(-0.5, response) == pytest.approx(0.6)


def test_exponential_smoothing_is_independent_of_poll_spacing_for_constant_input():
    response = Response(inner=0, exponent=1, smoothing_seconds=0.1)
    coarse = AxisProcessor(response=response)
    fine = AxisProcessor(response=response)
    coarse.update(0, 0)
    fine.update(0, 0)
    for _ in range(10):
        fine.update(1, 0.01)
    assert coarse.update(1, 0.1)[1] == pytest.approx(fine.output)


def test_validation():
    with pytest.raises(ValueError):
        Calibration(center=1)
    with pytest.raises(ValueError):
        Response(inner=0.7, outer=0.4)
    with pytest.raises(ValueError):
        Response(exponent=float("inf"))


def test_mapping_and_travel_capture():
    assert moved_axis((0.1, 0, -0.8), (0.15, 0.03, -0.6)) is None
    assert moved_axis((0.1, 0, -0.8), (0.35, -0.62, -0.7)) == 1
    travel = TravelCapture.start((0, 0))
    travel.update((0.75, -0.02))
    travel.update((-0.7, 0.6))
    assert travel.calibration_for(0, 0.001) == Calibration(-0.7, 0.001, 0.75)
    assert travel.calibration_for(1, 0) is None
