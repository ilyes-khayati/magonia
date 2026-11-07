import numpy as np
import pytest

from engine.purity import PurityError, purity, unmix

TREE = np.array([0.55, 0.56, 0.57, 0.56, 0.54, 0.52, 0.5, 0.5, 0.51, 0.53, 0.54, 0.55])
CROP = np.array([0.45, 0.6, 0.75, 0.7, 0.4, 0.2, 0.15, 0.15, 0.18, 0.25, 0.3, 0.38])
SQUARE = {
    "type": "Polygon",
    "coordinates": [[[8.55, 36.5], [8.56, 36.5], [8.56, 36.51], [8.55, 36.51], [8.55, 36.5]]],
}


def test_a_mixture_is_split_into_its_two_references():
    share, error = unmix(0.3 * CROP + 0.7 * TREE, TREE, CROP)
    assert share == pytest.approx(0.3) and error == pytest.approx(0)


def test_the_area_share_is_read_from_its_own_pixels():
    rng = np.random.default_rng(1)
    pixels = []
    for i in range(12):
        for j in range(12):
            lon, lat = 8.53 + i * 0.0025, 36.48 + j * 0.0025
            inside = 8.5499 <= lon <= 8.5601 and 36.4999 <= lat <= 36.5101  # floats near the edge
            f = 0.4 if inside else rng.uniform(0, 1)
            pixels.append({"lon": lon, "lat": lat, "cycle": list(f * CROP + (1 - f) * TREE)})
    pixels[0]["cycle"] = list(CROP)  # the purest pixels around become the references
    pixels[1]["cycle"] = list(TREE)
    found = purity(pixels, SQUARE, "Orchard")
    assert found.area_share == pytest.approx(0.4, abs=0.01)
    assert "40% annual crop" in found.summary[0]


def test_too_few_pixels_are_refused():
    with pytest.raises(PurityError, match="only 3 pixels"):
        purity([{"lon": 8.5, "lat": 36.5, "cycle": list(TREE)}] * 3, SQUARE, "Orchard")
