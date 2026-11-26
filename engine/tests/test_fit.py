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


def test_settings_are_read_as_labelled_by_hand_on_abstracts_not_used_to_write_the_reader():
    # 30 abstracts sampled and labelled on 17 Nov, after the reader was written. Measured then:
    # region 22/30 (the misses are mostly not read: towns, "Northern Europe", "NW ITALY" in
    # capitals; one wrong: "countries such as China"), vegetation 29/30
    import json
    from pathlib import Path

    data = json.loads((Path(__file__).parent / "data" / "fit_abstracts.json").read_text())
    region = vegetation = 0
    for x in data["abstracts"]:
        s = fit.record_of(SimpleNamespace(title=x["title"], abstract=x["abstract"])).setting
        read = min(s.regions) if len(s.regions) == 1 else None
        region += read == x["region"]
        vegetation += (s.covers[0] if s.covers else None) == x["vegetation"]
    assert region >= 22 and vegetation >= 29


def test_a_far_paper_applied_to_the_researchers_area_is_marked_by_code():
    text = (
        "**What it could mean here**: [1] found a longer green season in Alaska. "
        "NDVI in your orchard may fall in hot months [1]. Warming lengthens seasons there [1]."
    )
    out, flagged = fit.flag_transfers(text, {1: "North America, on tundra"}, ["Olive orchard"])
    assert [f["sentence"] for f in flagged] == ["NDVI in your orchard may fall in hot months [1]."]
    assert (
        out.count("This applies a finding from a far setting ([1] North America, on tundra)") == 1
    )
    assert "[1] found a longer green season in Alaska." in out  # what was found there stays


def test_an_area_named_by_the_researcher_counts_as_their_own_and_near_papers_are_not_marked():
    text = "Olive orchard greens in March, as in Spain [2]. Olive orchard dries in July [1]."
    out, flagged = fit.flag_transfers(text, {1: "Canada, on tundra"}, ["Olive orchard"])
    assert len(flagged) == 1 and flagged[0]["cites"] == [1]
    assert "[2]" in out and out.index("This applies") > out.index("[1]")
