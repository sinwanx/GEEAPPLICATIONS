import streamlit as st
import geopandas as gpd
import geemap.foliumap as geemap
import ee
import matplotlib.pyplot as plt
import pandas as pd
import zipfile, os, tempfile
from io import BytesIO

# ========== PAGE CONFIG ==========
st.set_page_config(page_title="Explore Vegetation Indices",
                   page_icon="🌳",
                   layout="wide")

# Custom CSS for background + styling
page_bg = """
<style>
[data-testid="stAppViewContainer"] {
    background: linear-gradient(120deg, #f0f9ff, #cbebff, #a1dbff);
    background-attachment: fixed;
}
[data-testid="stHeader"] {
    background: rgba(0,0,0,0);
}
footer {
    visibility: hidden;
}
.footer-text {
    position: fixed;
    bottom: 0;
    right: 0;
    padding: 10px;
    font-size: 14px;
    color: #333333;
}
</style>
"""
st.markdown(page_bg, unsafe_allow_html=True)

# App Title
st.markdown("<h1 style='text-align: center; color: green;'>🌳 Explore Vegetation Indices App</h1>", unsafe_allow_html=True)

# Footer branding
st.markdown("<div class='footer-text'>Powered by <b>Sanwan N.</b> | GEE Applications</div>", unsafe_allow_html=True)

# ========== INITIALIZE EARTH ENGINE ==========
try:
    ee.Initialize(project='ee-sanwanrsgis')
except Exception as e:
    ee.Authenticate()
    ee.Initialize(project='ee-sanwanrsgis')

# ========== FILE UPLOAD ==========
uploaded_file = st.file_uploader(
    "Upload your AOI shapefile (.zip with .shp, .shx, .dbf, .prj)",
    type=["zip"],
    key="shapefile_uploader"
)

aoi = None
if uploaded_file:
    with open("temp.zip", "wb") as f:
        f.write(uploaded_file.read())
    with zipfile.ZipFile("temp.zip", "r") as zip_ref:
        zip_ref.extractall("temp_shp")

    shp_files = [f for f in os.listdir("temp_shp") if f.endswith(".shp")]
    if len(shp_files) > 0:
        gdf = gpd.read_file(os.path.join("temp_shp", shp_files[0]))
        st.success("✅ Shapefile loaded successfully!")
        aoi = geemap.geopandas_to_ee(gdf)

# ========== INDEX FUNCTIONS ==========
def add_index(img, index):
    if index == 'NDVI':
        return img.normalizedDifference(['B8','B4']).rename('NDVI')
    elif index == 'EVI':
        return img.expression(
            '2.5 * ((NIR - RED) / (NIR + 6*RED - 7.5*BLUE + 1))',
            {
                'NIR': img.select('B8'),
                'RED': img.select('B4'),
                'BLUE': img.select('B2')
            }
        ).rename('EVI')
    elif index == 'SAVI':
        return img.expression(
            '((NIR - RED) / (NIR + RED + 0.5)) * 1.5',
            {
                'NIR': img.select('B8'),
                'RED': img.select('B4')
            }
        ).rename('SAVI')


# ========== SIDEBAR OPTIONS ==========
index = st.sidebar.selectbox("Select Vegetation Index", ["NDVI","EVI","SAVI"], key="index_selector")
years = st.sidebar.slider("Select Year Range", 2015, 2024, (2018, 2022), key="year_slider")

# ========== MAP + CHART + DOWNLOAD ==========
if aoi:
    values, yrs = [], list(range(years[0], years[1]+1))

    for y in yrs:
        img = ee.ImageCollection("COPERNICUS/S2_HARMONIZED") \
            .filterBounds(aoi) \
            .filterDate(f"{y}-01-01", f"{y}-12-31") \
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20)) \
            .median()
        idx_img = add_index(img, index)
        val = idx_img.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=aoi,
            scale=500,
            maxPixels=1e13,
            bestEffort=True
        ).get(index).getInfo()
        values.append(val)

    # Chart
    df = pd.DataFrame({"Year": yrs, index: values})
    fig, ax = plt.subplots()
    ax.plot(df["Year"], df[index], marker="o", color="green")
    ax.set_title(f"{index} Trend ({years[0]}–{years[1]})")
    ax.set_xlabel("Year")
    ax.set_ylabel(index)
    st.pyplot(fig)

    # Map
    latest_year = years[1]
    img = ee.ImageCollection("COPERNICUS/S2_HARMONIZED") \
        .filterBounds(aoi) \
        .filterDate(f"{latest_year}-01-01", f"{latest_year}-12-31") \
        .median()
    idx_img = add_index(img, index)

    Map = geemap.Map()
    vis = {'min': 0, 'max': 1, 'palette': ['brown','yellow','green']}
    Map.addLayer(idx_img, vis, f"{index} {latest_year}")
    Map.centerObject(aoi, 7)
    Map.to_streamlit(height=500)

    # ========== DOWNLOAD OPTION ==========
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, f"{index}_{latest_year}.tif")
        geemap.ee_export_image(idx_img, filename=path, scale=30, region=aoi.geometry(), file_per_band=False)
        with open(path, "rb") as f:
            btn = st.download_button(
                label=f"⬇️ Download {index}_{latest_year}.tif",
                data=f,
                file_name=f"{index}_{latest_year}.tif",
                mime="image/tiff"
            )
