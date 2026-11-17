from types import SimpleNamespace

from engine import fit, setting

HERE = setting.of_workspace(
    ["Areas: Olive orchard (0.64 km²).", "The areas lie near 36.51° N, 8.56° E."],
    ["Olive orchard"],
)


def rated(title, abstract=""):
    record = fit.record_of(SimpleNamespace(title=title, abstract=abstract))
    return record, fit.rate(record, HERE)


def test_the_researchers_setting_is_read_from_where_the_areas_lie_and_their_names():
    assert HERE.describe() == "Tunisia, on olive"
    assert "the Mediterranean" in HERE.regions and "Mediterranean" in HERE.climates


def test_same_region_and_like_vegetation_is_near():
    _, f = rated("Drought stress in rainfed olive groves of southern Spain")
    assert f.level == "near" and f.usable


def test_same_region_and_other_vegetation_is_partly():
    _, f = rated("Drought and forest NDVI in Spain")
    assert f.level == "partly" and f.usable
    assert any(d.startswith("vegetation (forest") for d in f.differs)


def test_another_region_with_no_climate_in_common_is_far():
    _, f = rated("Greening of tundra in northern Alaska", "Warming lengthens the green season.")
    assert f.level == "far" and not f.usable
    assert any(d.startswith("region (North America") for d in f.differs)


def test_another_crop_where_no_place_is_stated_is_far():
    _, f = rated("NDVI combinations for maize grain yield")
    assert f.level == "far"


def test_a_worldwide_study_is_general_not_far():
    _, f = rated("Global trends of vegetation greening", "Across the globe NDVI increased.")
    assert f.level == "partly"


def test_nothing_stated_is_unknown():
    _, f = rated("Classifying land use with convolutional networks")
    assert f.level == "unknown" and not f.usable


def test_sensors_and_variables_are_read_without_taking_ndvi_for_another_index():
    record, _ = rated(
        "Normalized difference vegetation index from MODIS and Sentinel-2",
        "We relate NDVI to land surface temperature and SPEI.",
    )
    assert record.sensors == ["MODIS", "Sentinel-2"]
    assert record.variables == ["NDVI", "LST", "drought index"]


def test_the_summary_says_when_no_cited_paper_fits():
    record, f = rated("Greening of tundra in northern Alaska")
    part = fit.summary({1: ("May et al., 2020", record, f)}, HERE)
    assert part.startswith("**Does the evidence fit your setting (Tunisia, on olive)?**")
    assert "- [1] May et al., 2020" in part and "far" in part
    assert "none of them explains your data" in part
    near_record, near = rated("Olive groves under drought in Tunisia")
    part = fit.summary({1: ("Ali, 2022", near_record, near)}, HERE)
    assert "none of them explains" not in part


def test_the_model_is_told_how_to_use_a_far_paper():
    record, f = rated("Greening of tundra in northern Alaska")
    said = fit.line(3, record, f)
    assert said.startswith("About [3]: made in")
    assert "never as an explanation of the researcher's data" in said
