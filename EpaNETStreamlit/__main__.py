"""Local EPANET, MSX and MIKE URBAN Streamlit workbench."""
from __future__ import annotations
import sqlite3
import struct
import sys
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from epanet_addons.engine import EpanetWrapper
from epanet_addons.mike_urban.importer import import_mike_urban_mdb
from epanet_addons.projects import LocalProjectStore

ROOT = Path(__file__).parent.parent
STORE = LocalProjectStore(ROOT / "projects")
st.set_page_config(page_title="EPANET Workbench", layout="wide")
st.title("EPANET Workbench")
st.caption("Local hydraulic, MSX and MIKE URBAN GeoPackage workspace")

def stage(upload):
    folder = Path(tempfile.mkdtemp(prefix="epanet-upload-")); path = folder / upload.name
    path.write_bytes(upload.getbuffer()); return path

def load(path):
    st.session_state.epanet.close(); st.session_state.epanet.load_file(path)
    st.session_state.loaded = True; st.session_state.hydraulic = False; st.session_state.msx_done = False

def node_frame(net):
    ids = net.getNodeNameID()
    return pd.DataFrame({"id": ids, "elevation": [float(net.getNodeElevations(i)) for i in range(1, len(ids)+1)]})

def link_frame(net):
    ids = net.getLinkNameID()
    return pd.DataFrame({"id": ids, "diameter": [float(net.getLinkDiameter(i)) for i in range(1, len(ids)+1)], "length": [float(net.getLinkLength(i)) for i in range(1, len(ids)+1)], "roughness": [float(net.getLinkRoughnessCoeff(i)) for i in range(1, len(ids)+1)]})

def draw_gpkg_map(path):
    """Draw the imported asset geometry without requiring GIS server packages."""
    fig, ax = plt.subplots(figsize=(13, 8))
    with sqlite3.connect(path) as con:
        srs_ids = pd.read_sql_query("SELECT DISTINCT srs_id FROM gpkg_contents WHERE data_type='features'", con).srs_id.tolist()
        layers = pd.read_sql_query("SELECT table_name FROM gpkg_contents WHERE data_type='features'", con).table_name
        for layer in layers:
            for (geom,) in con.execute(f'SELECT geom FROM "{layer}" WHERE geom IS NOT NULL'):
                wkb = geom[8:]; kind = struct.unpack_from("<I", wkb, 1)[0]
                if kind == 1:
                    x, y = struct.unpack_from("<dd", wkb, 5); ax.plot(x, y, ".", ms=2, label=layer)
                elif kind == 2:
                    count = struct.unpack_from("<I", wkb, 5)[0]; points = struct.unpack_from(f"<{count * 2}d", wkb, 9)
                    ax.plot(points[::2], points[1::2], lw=.35, color="#2878b5")
    label = "EPSG:5514 — S-JTSK / Krovak East North" if srs_ids == [5514] else "local / unrecognised CRS"
    ax.set_aspect("equal", adjustable="datalim"); ax.set_title(f"Imported MIKE URBAN assets ({label})")
    ax.set_xlabel("X (projected metres)"); ax.set_ylabel("Y (projected metres)")
    return fig

if "epanet" not in st.session_state or not hasattr(st.session_state.epanet, "load_mike_urban_mdb"):
    # Streamlit preserves session objects across hot reloads. Replace a wrapper
    # created by an older application version when its public API changes.
    try:
        st.session_state.epanet.close()
    except Exception:
        pass
    st.session_state.epanet = EpanetWrapper(); st.session_state.loaded = False
    st.session_state.hydraulic = False; st.session_state.msx_done = False
    st.session_state.msx_path = None; st.session_state.gpkg_path = None; st.session_state.source_crs = None

with st.sidebar:
    st.header("Workspace")
    inp = st.file_uploader("EPANET model (.inp)", type="inp")
    if inp and st.button("Open uploaded model", width="stretch"):
        try: load(stage(inp)); st.success(f"Opened {inp.name}")
        except Exception as e: st.error(str(e))
    projects = STORE.list()
    chosen = st.selectbox("Local project", [""] + projects)
    if chosen and st.button("Open local project", width="stretch"):
        try:
            project = STORE.load(chosen); load(project["inp"])
            st.session_state.msx_path, st.session_state.gpkg_path = project.get("msx"), project.get("geopackage")
            st.success(f"Opened {project['name']}")
        except Exception as e: st.error(f"Could not open project: {e}")
    st.divider(); st.header("MIKE URBAN assets")
    mdb = st.file_uploader("Import water model (.mdb)", type="mdb")
    if mdb and st.button("Convert to GeoPackage", width="stretch"):
        try:
            source = stage(mdb); target = source.with_suffix(".gpkg")
            counts = import_mike_urban_mdb(source, target); st.session_state.gpkg_path = target
            st.success("GeoPackage: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
        except Exception as e: st.error(f"MDB import failed: {e}")
    if mdb and st.button("Open MDB as calculation model", width="stretch"):
        try:
            source = stage(mdb)
            with st.spinner("Translating MIKE URBAN model to EPANET…"):
                report = st.session_state.epanet.load_mike_urban_mdb(source)
                gpkg = source.with_suffix(".gpkg")
                import_mike_urban_mdb(source, gpkg)
            st.session_state.loaded = True; st.session_state.hydraulic = False; st.session_state.msx_done = False
            st.session_state.gpkg_path = gpkg; st.session_state.source_crs = report.get("source_crs")
            crs = (st.session_state.source_crs or {}).get("name", "Unknown/local CRS")
            st.success(f"Loaded converted model ({crs}). Reconstructed nodes: {len(report.get('virtual_junctions', []))}; excluded components: {len(report.get('excluded_components', []))}.")
        except Exception as e: st.error(f"MDB calculation-model conversion failed: {e}")
    if st.session_state.loaded:
        st.divider(); st.header("Calculations")
        if st.button("Run EPANET hydraulics", width="stretch"):
            try:
                with st.spinner("Solving hydraulics…"): st.session_state.epanet.run_simulation()
                st.session_state.hydraulic = True; st.success("Hydraulic run completed")
            except Exception as e: st.error(str(e))
        msx = st.file_uploader("MSX chemistry (.msx)", type="msx")
        if msx: st.session_state.msx_path = stage(msx)
        if st.button("Run MSX quality", disabled=st.session_state.msx_path is None, width="stretch"):
            try:
                with st.spinner("Solving multi-species quality…"): st.session_state.epanet.run_msx(st.session_state.msx_path)
                st.session_state.msx_done = True; st.success("MSX run completed")
            except Exception as e: st.error(str(e))
        st.divider(); name = st.text_input("Save local project as", placeholder="example-network")
        if st.button("Save project", disabled=not name, width="stretch"):
            try:
                location = STORE.save(name, st.session_state.epanet, st.session_state.msx_path, st.session_state.gpkg_path)
                st.success(f"Saved locally in {location.relative_to(ROOT)}")
            except Exception as e: st.error(f"Project save failed: {e}")

if not st.session_state.loaded:
    gpkg = st.session_state.gpkg_path
    if gpkg and Path(gpkg).is_file():
        st.subheader("Imported MIKE URBAN asset map")
        st.caption("The GeoPackage is ready. Open an EPANET model later to run calculations and view their result map.")
        figure = draw_gpkg_map(gpkg)
        st.pyplot(figure, clear_figure=True)
        plt.close(figure)
        with sqlite3.connect(gpkg) as con:
            layers = pd.read_sql_query("SELECT table_name, data_type, srs_id FROM gpkg_contents ORDER BY table_name", con)
        st.dataframe(layers, hide_index=True, width="stretch")
        selected = st.selectbox("Inspect imported layer", layers.table_name.tolist())
        with sqlite3.connect(gpkg) as con:
            preview = pd.read_sql_query(f'SELECT * FROM "{selected}" LIMIT 50', con)
        st.dataframe(preview.drop(columns=["geom"], errors="ignore"), hide_index=True, width="stretch")
    else:
        st.info("Import a MIKE URBAN .mdb to view its GeoPackage asset map, or open an EPANET .inp model to calculate.")
    st.stop()

wrapper, net = st.session_state.epanet, st.session_state.epanet.get_network()
stats = wrapper.get_statistics(); a, b, c = st.columns(3)
a.metric("Nodes", stats.get("node_count", 0)); b.metric("Links", stats.get("link_count", 0)); c.metric("Status", "MSX complete" if st.session_state.msx_done else "Hydraulics complete" if st.session_state.hydraulic else "Ready")
viewer, editor, results, assets = st.tabs(["Network viewer", "Parameters", "Results", "GeoPackage assets"])
with viewer:
    source_crs = st.session_state.get("source_crs")
    if source_crs:
        st.caption(f"Coordinates: {source_crs['name']}. The viewer preserves the projected metre coordinates; it does not mistake them for longitude/latitude.")
    colour = st.selectbox("Colour network by", ["Topology", "Elevation", "Pressure", "Flow"])
    if colour in {"Pressure", "Flow"} and not st.session_state.hydraulic: st.warning("Run hydraulics first.")
    else:
        fig, ax = plt.subplots(figsize=(13, 8))
        if colour == "Topology": wrapper.plot_network_topology(ax=ax, nodesID=True)
        else: wrapper.plot_network_attributes(ax=ax, attribute=colour.lower())
        st.pyplot(fig, clear_figure=True); plt.close(fig)
with editor:
    st.caption("Apply edits to memory, then Save project to persist them locally.")
    nt, lt = st.tabs(["Node elevations", "Pipe/link parameters"])
    with nt:
        nodes = st.data_editor(node_frame(net), hide_index=True, disabled=["id"])
        if st.button("Apply node elevations"):
            for i, row in nodes.iterrows(): net.setNodeElevations(i+1, float(row.elevation))
            st.session_state.hydraulic = False; st.success("Updated; rerun calculations.")
    with lt:
        links = st.data_editor(link_frame(net), hide_index=True, disabled=["id"])
        if st.button("Apply link parameters"):
            for i, row in links.iterrows():
                net.setLinkDiameter(i+1, float(row.diameter)); net.setLinkLength(i+1, float(row.length)); net.setLinkRoughnessCoeff(i+1, float(row.roughness))
            st.session_state.hydraulic = False; st.success("Updated; rerun calculations.")
with results:
    if st.session_state.hydraulic:
        data = wrapper.get_computed_time_series(); st.subheader("Hydraulic results"); st.write(f"{len(data.Time)} time steps; use the viewer to inspect pressure and flow.")
    else: st.info("Run EPANET hydraulics to view results.")
    if st.session_state.msx_done:
        data = wrapper.get_msx_results(); st.subheader("MSX results")
        st.write(f"Species: {', '.join(data['species'])}; {len(data['time'])} time steps.")
with assets:
    gpkg = st.session_state.gpkg_path
    if gpkg and Path(gpkg).is_file():
        with sqlite3.connect(gpkg) as con: layers = pd.read_sql_query("SELECT table_name, data_type, srs_id FROM gpkg_contents ORDER BY table_name", con)
        st.dataframe(layers, hide_index=True, width="stretch"); table = st.selectbox("Inspect layer", layers.table_name.tolist())
        if st.button("Show asset map"):
            figure = draw_gpkg_map(gpkg); st.pyplot(figure, clear_figure=True); plt.close(figure)
        with sqlite3.connect(gpkg) as con: preview = pd.read_sql_query(f'SELECT * FROM "{table}" LIMIT 50', con)
        st.dataframe(preview.drop(columns=["geom"], errors="ignore"), hide_index=True, width="stretch")
    else: st.info("Import an MDB to inspect its local GeoPackage layers.")
