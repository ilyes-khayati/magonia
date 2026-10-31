from fastapi.testclient import TestClient

from api.main import app


def test_catalogue_lists_every_variable_with_its_metadata():
    response = TestClient(app).get("/catalogue")
    assert response.status_code == 200
    variables = {variable["key"]: variable for variable in response.json()}
    assert {"ndvi", "savi", "evi", "lai", "rain", "spei"} <= set(variables)
    assert variables["ndmi"]["learn"]["formula"].startswith("NDMI =")
    assert variables["lst"]["units"] == "°C"
    assert variables["spei"]["scales"] == [1, 3, 6, 12, 24, 48]
