import os
import sys
import tempfile
import zipfile
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / "pipeline"))
sys.path.insert(0, str(BASE / "config"))

import ingest as ingest_mod  # noqa: E402

DATA = BASE / "data"
FOTOS = DATA / "fotos"
CONFIG = BASE / "config"

SPECIES_COLORS = [
    "#007934", "#69be28", "#2d5a27", "#76bc21", "#3f7d20", "#9f9480",
    "#c1902e", "#8a6d3b", "#4b7f8c", "#5b7c99", "#7a8b3a", "#b5613a",
    "#6f5b3e", "#3e6b4f", "#a8a29e", "#556b2f",
]

st.set_page_config(page_title="Cámaras Trampa", layout="wide")


def thumb_path(relpath):
    if not isinstance(relpath, str):
        return None
    p = FOTOS / relpath.replace("/", "__")
    return str(p) if p.exists() else None


@st.cache_data(show_spinner=False)
def load_bundled():
    df = pd.read_csv(DATA / "master_sheet.csv", dtype=str, keep_default_na=False)
    df["img_path"] = df["relpath"].map(thumb_path)
    return df


def build_cfg(raw_dir):
    return {
        "raw_dir": raw_dir,
        "species_map": str(CONFIG / "species_map.csv"),
        "sites": str(CONFIG / "sites.csv"),
        "image_ext": [".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"],
        "media_ext": [".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".mp4", ".avi", ".mov", ".mkv"],
        "event_interval_min": 60,
    }


def from_zip(uploaded):
    tmp = tempfile.mkdtemp(prefix="camaras_")
    zpath = os.path.join(tmp, "subida.zip")
    with open(zpath, "wb") as fh:
        fh.write(uploaded.getbuffer())
    with zipfile.ZipFile(zpath) as z:
        z.extractall(tmp)
    roots = [r for r, d, f in os.walk(tmp) if any(x.lower().endswith((".jpg", ".jpeg", ".png")) for x in f)]
    raw_dir = roots[0] if roots else tmp
    records = ingest_mod.run_ingest(build_cfg(raw_dir))
    df = pd.DataFrame(records)
    df["img_path"] = df["filepath"]
    return df


def apply_filters(df):
    sites = sorted(s for s in df["site"].dropna().unique() if str(s).strip())
    cats = sorted(s for s in df["species"].dropna().unique() if str(s).strip())
    with st.sidebar:
        st.header("Filtros")
        f_sites = st.multiselect("Sitios", sites, default=sites)
        f_cats = st.multiselect("Especies", cats, default=cats)
        fechas = pd.to_datetime(df["date"].replace("", pd.NA), errors="coerce")
        dmin, dmax = fechas.min(), fechas.max()
        rango = st.date_input("Rango de fechas", value=(dmin.date(), dmax.date())) if pd.notna(dmin) else None
    out = df[df["site"].isin(f_sites) & df["species"].isin(f_cats)].copy()
    if rango and len(rango) == 2:
        d = pd.to_datetime(out["date"].replace("", pd.NA), errors="coerce").dt.date
        out = out[(d >= rango[0]) & (d <= rango[1])]
    return out


def events_of(df):
    ev = df[(df["species"] != "") & (df["event_id"] != "")].copy()
    ev = ev.drop_duplicates("event_id")
    ev["hour_n"] = pd.to_numeric(ev["hour"], errors="coerce")
    return ev


def diversity_table(ev):
    rows = []
    for site in sorted(ev["site"].unique()):
        counts = ev[ev["site"] == site]["species"].value_counts()
        n = counts.sum()
        s = len(counts)
        if n == 0 or s == 0:
            continue
        import math
        p = counts / n
        h = -sum(pi * math.log(pi) for pi in p)
        hmax = math.log(s) if s > 1 else 1.0
        rows.append({
            "Sitio": site, "Riqueza (S)": s, "Shannon H'": round(h, 3),
            "Equitat. E": round(h / hmax, 3), "Simpson 1-D": round(1 - sum(pi * pi for pi in p), 3),
            "Eventos": int(n),
        })
    return pd.DataFrame(rows)


def kpis(df, ev):
    c = st.columns(4)
    c[0].metric("Registros", len(df))
    c[1].metric("Eventos", ev["event_id"].nunique())
    c[2].metric("Especies", ev["species"].nunique())
    c[3].metric("Sitios", df["site"].nunique())


def tab_resumen(df, ev):
    left, right = st.columns([3, 2])
    with left:
        st.subheader("Actividad por hora")
        h = ev.dropna(subset=["hour_n"]).groupby(["hour_n", "species"]).size().reset_index(name="n")
        if not h.empty:
            cmap = {s: SPECIES_COLORS[i % len(SPECIES_COLORS)] for i, s in enumerate(sorted(ev["species"].unique()))}
            chart = alt.Chart(h).mark_bar().encode(
                x=alt.X("hour_n:O", title="Hora", axis=alt.Axis(labelAngle=0)),
                y=alt.Y("sum(n):Q", title="Eventos"),
                color=alt.Color("species:N", scale=alt.Scale(domain=list(cmap), range=list(cmap.values())), title="Especie"),
                tooltip=["species", "hour_n", "n"],
            ).properties(height=320)
            st.altair_chart(chart, width="stretch")
    with right:
        st.subheader("Eventos por especie")
        byc = ev["species"].value_counts().rename_axis("species").reset_index(name="n")
        cmap = {s: SPECIES_COLORS[i % len(SPECIES_COLORS)] for i, s in enumerate(sorted(ev["species"].unique()))}
        chart = alt.Chart(byc).mark_bar().encode(
            x=alt.X("n:Q", title="Eventos"),
            y=alt.Y("species:N", sort="-x", title=""),
            color=alt.Color("species:N", scale=alt.Scale(domain=list(cmap), range=list(cmap.values())), legend=None),
            tooltip=["species", "n"],
        ).properties(height=max(320, len(byc) * 26))
        st.altair_chart(chart, width="stretch")

    st.subheader("Matriz sitio x especie (eventos)")
    piv = ev.pivot_table(index="species", columns="site", values="event_id", aggfunc="count").fillna(0).astype(int)
    piv["Total"] = piv.sum(axis=1)
    piv = piv.sort_values("Total", ascending=False)
    st.dataframe(piv, width="stretch")


def tab_diversidad(ev):
    st.subheader("Diversidad por sitio (alpha)")
    st.dataframe(diversity_table(ev), width="stretch", hide_index=True)


def tab_galeria(df):
    st.subheader("Galería de registros")
    cmap = {s: SPECIES_COLORS[i % len(SPECIES_COLORS)] for i, s in enumerate(sorted(df["species"].unique()))}
    cols = st.columns(4)
    shown = 0
    for _, r in df.sort_values("datetime").iterrows():
        if not r.get("img_path"):
            continue
        with cols[shown % 4]:
            st.image(r["img_path"], width="stretch")
            extra = f" · Pto {r['point']}" if str(r.get("point", "")).strip() else ""
            st.markdown(
                f"<span style='color:{cmap.get(r['species'], '#333')};font-weight:700'>{r['species']}</span><br>"
                f"<small>{r['site']}{extra}<br>{r['datetime']}</small>",
                unsafe_allow_html=True,
            )
        shown += 1
    if shown == 0:
        st.info("No hay fotos para los filtros seleccionados.")


def tab_mapa(df):
    geo = df.copy()
    geo["lat"] = pd.to_numeric(geo["lat"], errors="coerce")
    geo["lon"] = pd.to_numeric(geo["lon"], errors="coerce")
    geo = geo.dropna(subset=["lat", "lon"])
    if geo.empty:
        st.info("Las fotos de este conjunto no traen coordenadas GPS en el EXIF. Completá config/sites.csv con lat/lon por punto para habilitar el mapa.")
        return
    st.subheader("Ubicación de registros")
    st.map(geo.rename(columns={"lat": "latitude", "lon": "longitude"})[["latitude", "longitude"]])


def tab_datos(df, ev):
    st.subheader("Master sheet")
    st.dataframe(df.drop(columns=["img_path"], errors="ignore"), width="stretch", hide_index=True)
    st.download_button("Descargar master_sheet.csv", df.to_csv(index=False).encode("utf-8"), "master_sheet.csv", "text/csv")
    st.download_button("Descargar events.csv", ev.to_csv(index=False).encode("utf-8"), "events.csv", "text/csv")


def main():
    logo = BASE / "banner.png"
    if logo.exists():
        st.image(str(logo), width=260)
    st.title("Cámaras Trampa")
    st.caption("Organización, master sheet y análisis de fotos de cámaras trampa · BioMap")

    with st.sidebar:
        st.header("Datos")
        fuente = st.radio("Fuente", ["Datos incluidos", "Subir ZIP de fotos"])
        if fuente == "Subir ZIP de fotos":
            up = st.file_uploader("ZIP con la carpeta de fotos", type=["zip"])
            if not up:
                st.stop()
            with st.spinner("Procesando fotos (EXIF + nombres)..."):
                df = from_zip(up)
        else:
            df = load_bundled()

    if df.empty:
        st.warning("No se encontraron registros.")
        st.stop()

    df = apply_filters(df)
    if df.empty:
        st.warning("Los filtros no devuelven registros.")
        st.stop()

    ev = events_of(df)
    kpis(df, ev)

    tabs = st.tabs(["Resumen", "Diversidad", "Galería", "Mapa", "Datos"])
    with tabs[0]:
        tab_resumen(df, ev)
    with tabs[1]:
        tab_diversidad(ev)
    with tabs[2]:
        tab_galeria(df)
    with tabs[3]:
        tab_mapa(df)
    with tabs[4]:
        tab_datos(df, ev)

    st.caption("Metodología abierta (ingesta EXIF → eventos independientes → inventario/actividad/diversidad). No usa código de terceros.")


if __name__ == "__main__":
    main()
