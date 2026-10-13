# Cámaras Trampa (Streamlit)

App web para organizar, generar el master sheet y analizar fotos de cámaras trampa. Corre online en Streamlit Community Cloud y también local. Encabezado con el logo de BioMap y paleta institucional (verde #69BE28 / #007934).

## Qué incluye

- KPIs (registros, eventos independientes, especies, sitios).
- Actividad por hora (apilada por especie) y eventos por especie.
- Matriz sitio x especie.
- Índices de diversidad por sitio (riqueza, Shannon, equitatividad, Simpson).
- Galería de fotos filtrable.
- Mapa (si las fotos traen GPS).
- Galería y descarga del master sheet.
- Modo **Subir ZIP**: procesa tus propias fotos (EXIF + nombre de archivo) sin tocar el repo.

## Estructura

```
app.py                  la app
requirements.txt        dependencias (las instala Streamlit Cloud)
.streamlit/config.toml  tema y servidor
prepare_data.py         regenera data/ (CSV + miniaturas) desde la carpeta cruda
pipeline/               common.py + ingest.py (parseo EXIF + eventos)
config/                 species_map.csv, sites.csv, pipeline.json
data/                   master_sheet.csv, events.csv, etc. + fotos/ (miniaturas)
```

## Correr local

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Abre http://localhost:8501.

## Regenerar los datos del repo

Cuando tengas fotos nuevas o cambie el master sheet, desde la carpeta de tu pipeline local:

```bash
# 1) en tu carpeta pipeline/ (con los datos crudos), generar out/*.csv
python3 scripts/ingest.py && python3 scripts/analyze.py
# 2) copiar los CSV y construir las miniaturas dentro del repo
cp ../pipeline/out/*.csv data/
python3 prepare_data.py --raw-dir "../CÁMARAS TRAMPA-.../CÁMARAS TRAMPA"
```

Las miniaturas (`data/fotos/`, ~4 MB) son las que se ven en la galería online. Las fotos originales no se suben al repo.

## Publicar en share.streamlit.io

1. Crear el repositorio en GitHub (ej. `biomapmp/camaras-trampa-app`), público o privado:
   ```bash
   git init
   git add .
   git commit -m "App catedra camaras trampa"
   git branch -M main
   git remote add origin https://github.com/biomapmp/camaras-trampa-app.git
   git push -u origin main
   ```
2. Entrar a https://share.streamlit.io con la cuenta **biomap.mp@gmail.com** (login con GitHub).
3. **New app** → elegir el repositorio, branch `main`, main file `app.py` → **Deploy**.
4. Streamlit instala `requirements.txt` y publica la URL (algo como `https://biomapmp-camaras-trampa-app.streamlit.app`).

Cualquier `git push` posterior redespliega solo.

## Nota sobre datos en el repo

Streamlit Cloud no ve tu disco local: la app solo puede leer lo que está en el repo. Por eso el master sheet y las miniaturas van versionadas en `data/`. Si no querés publicar las fotos, subí solo los CSV y ocultá la pestaña Galería (o dejá `data/fotos/` vacío: la galería simplemente no muestra imágenes).
