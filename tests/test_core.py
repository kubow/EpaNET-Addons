"""Core (UI-neutral) checks using EPyT's bundled example networks."""
import os
import shutil
from pathlib import Path

import numpy as np
import pytest

epyt = pytest.importorskip("epyt")
from epanet_addons import crs, msx, network  # noqa: E402
from epanet_addons.engine import EpanetWrapper  # noqa: E402

EXAMPLES = Path(os.path.dirname(epyt.__file__)) / "networks" / "msx-examples"


@pytest.fixture()
def wrapper(tmp_path):
    for name in ("net2-cl2.inp", "net2-cl2.msx"):
        shutil.copy(EXAMPLES / name, tmp_path / name)
    w = EpanetWrapper()
    w.load_file(tmp_path / "net2-cl2.inp")
    yield w
    w.close()


def test_msx_round_trip_and_validation():
    for path in EXAMPLES.glob("*.msx"):
        model = msx.parse(path.read_text())
        again = msx.parse(msx.write(model))
        assert again.rows == model.rows and again.options == model.options
    for name in msx.TEMPLATES:
        assert not [i for i in msx.template(name).validate() if i.level == "error"], name
    broken = msx.parse("[SPECIES]\nBULK A MG\n[PIPES]\nRATE A -k*A\n")
    assert any("unknown symbol k" in i.message for i in broken.validate())


def test_crs_detection_and_transform():
    krovak = [(-901507.4, -1002329.1), (-897068.7, -1003144.6)]
    detected = crs.detect_crs(krovak)
    assert detected.code == "EPSG:5514"
    wx, wy = detected.to_world([p[0] for p in krovak], [p[1] for p in krovak])
    lon, lat = detected.world_to_lonlat(float(wx[0]), float(wy[0]))
    assert 12 < lon < 19 and 48 < lat < 51  # Czechia
    assert crs.detect_crs([(1000.0, 2000.0), (1500.0, 2500.0)]).is_local


def test_edit_run_compare(wrapper):
    net = wrapper.network
    topo = network.read_topology(net)
    table = network.property_table(net, topo, "link")
    assert len(table) == len(topo.link_ids) and table["diameter"].notna().all()
    wrapper.run_simulation()
    base = network.Scenario("A", network.Results.from_engine(topo, wrapper.get_computed_time_series()))
    field = network.field_by_key("link", "diameter")
    assert network.bulk_edit(net, "link", range(5), field, "multiply", 0.5) == 5
    wrapper.run_simulation()
    edited = network.Scenario("B", network.Results.from_engine(topo, wrapper.get_computed_time_series()))
    diff = network.compare(base, edited, "node", "pressure", "Minimum", 0)
    assert (diff["delta"].abs() > 1e-6).any()
    assert "Min pressure" in network.kpis(edited, topo)


def test_msx_run_and_results_persistence(wrapper, tmp_path):
    topo = network.read_topology(wrapper.network)
    wrapper.run_simulation()
    out = wrapper.run_msx(tmp_path / "net2-cl2.msx")
    res = network.Results.from_engine(topo, wrapper.get_computed_time_series(), out)
    assert "CL2" in res.msx_node and res.msx_node["CL2"].shape[1] == len(topo.node_ids)
    res.save(tmp_path / "r.npz")
    loaded = network.Results.load(tmp_path / "r.npz")
    assert np.allclose(loaded.msx_node["CL2"], res.msx_node["CL2"])
    assert loaded.node_ids == res.node_ids
