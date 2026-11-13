import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import re

# ==========================================
# PAGE CONFIGURATION
# ==========================================

st.set_page_config(
    page_title="Kerala Temperature Explorer",
    page_icon="🌡️",
    layout="wide"
)

st.title("🌡️ Kerala Temperature Explorer")

st.markdown("""
Explore historical temperature patterns across all
14 districts of Kerala using NASA POWER data.
""")

# ==========================================
# DISTRICT COORDINATES
# ==========================================

DISTRICTS = {
    "Thiruvananthapuram": (8.5241, 76.9366),
    "Kollam": (8.8932, 76.6141),
    "Pathanamthitta": (9.2648, 76.7870),
    "Alappuzha": (9.4981, 76.3388),
    "Kottayam": (9.5916, 76.5222),
    "Idukki": (9.8494, 76.9720),
    "Ernakulam": (9.9816, 76.2999),
    "Thrissur": (10.5276, 76.2144),
    "Palakkad": (10.7867, 76.6548),
    "Malappuram": (11.0510, 76.0711),
    "Kozhikode": (11.2588, 75.7804),
    "Wayanad": (11.6854, 76.1320),
    "Kannur": (11.8745, 75.3704),
    "Kasaragod": (12.4996, 74.9869)
}

# ==========================================
# NASA POWER API
# ==========================================

@st.cache_data(ttl=3600)
def get_temperature_data(start_year, end_year):

    all_data = []

    api_url = (
        "https://power.larc.nasa.gov/api/temporal/monthly/point"
    )

    for district, coordinates in DISTRICTS.items():

        latitude, longitude = coordinates

        params = {
            "parameters": "T2M",
            "community": "RE",
            "longitude": longitude,
            "latitude": latitude,
            "start": start_year,
            "end": end_year,
            "format": "JSON"
        }

        try:

            response = requests.get(
                api_url,
                params=params,
                timeout=60
            )

            response.raise_for_status()

            result = response.json()

            temperatures = (
                result.get("properties", {})
                .get("parameter", {})
                .get("T2M", {})
            )

            if not temperatures:
                raise ValueError(
                    "NASA returned no temperature data."
                )

            for date, temperature in temperatures.items():

                # Accept only valid YYYYMM months.
                # Excludes annual records like 202413.

                if not re.fullmatch(
                    r"\d{4}(0[1-9]|1[0-2])",
                    str(date)
                ):
                    continue

                if temperature is None:
                    continue

                if float(temperature) <= -900:
                    continue

                month_date = pd.to_datetime(
                    str(date),
                    format="%Y%m"
                )

                all_data.append({
                    "District": district,
                    "Date": month_date,
                    "Year": month_date.year,
                    "Month": month_date.month,
                    "Temperature": float(temperature),
                    "Latitude": latitude,
                    "Longitude": longitude
                })

        except Exception as error:

            raise RuntimeError(
                f"NASA data error for {district}: {error}"
            )

    df = pd.DataFrame(all_data)

    if df.empty:
        raise ValueError("No valid temperature records received.")

    return df


# ==========================================
# GEOJSON DISTRICT BOUNDARIES
# ==========================================

GEOJSON_URL = (
    "https://raw.githubusercontent.com/"
    "geohacker/kerala/master/geojsons/district.geojson"
)


@st.cache_data(ttl=86400)
def get_kerala_boundaries():

    response = requests.get(
        GEOJSON_URL,
        timeout=40
    )

    response.raise_for_status()

    geojson = response.json()

    if geojson.get("type") != "FeatureCollection":
        raise ValueError("Invalid district boundary GeoJSON.")

    return geojson


# ==========================================
# DISTRICT NAME MATCHING
# ==========================================

def normalize_name(name):

    return re.sub(
        r"[^a-z]",
        "",
        str(name).lower()
    )


def prepare_map_data(df, geojson):

    temperature_summary = (
        df.groupby("District")["Temperature"]
        .mean()
        .reset_index()
    )

    temperature_summary.columns = [
        "District",
        "Temperature"
    ]

    canonical_names = {
        normalize_name(name): name
        for name in DISTRICTS
    }

    # Common alternative spellings

    aliases = {
        "kasargod": "Kasaragod",
        "trivandrum": "Thiruvananthapuram",
        "palghat": "Palakkad"
    }

    for alias, canonical in aliases.items():
        canonical_names[normalize_name(alias)] = canonical

    map_rows = []

    for feature in geojson["features"]:

        properties = feature.get("properties", {})

        geo_name = properties.get("DISTRICT")

        if not geo_name:
            continue

        normalized = normalize_name(geo_name)

        canonical = canonical_names.get(normalized)

        if canonical is None:
            continue

        map_rows.append({
            "GeoDistrict": geo_name,
            "District": canonical
        })

    boundary_names = pd.DataFrame(map_rows)

    if boundary_names.empty:
        raise ValueError(
            "No district names matched the boundary dataset."
        )

    map_data = boundary_names.merge(
        temperature_summary,
        on="District",
        how="inner"
    )

    if len(map_data) != 14:
        missing = sorted(
            set(DISTRICTS) - set(map_data["District"])
        )

        raise ValueError(
            f"Expected 14 districts but matched "
            f"{len(map_data)}. Missing: {missing}"
        )

    return map_data


# ==========================================
# SIDEBAR SETTINGS
# ==========================================

st.sidebar.header("⚙️ Settings")

years = list(range(1981, 2026))

start_year = st.sidebar.selectbox(
    "Starting Year",
    years,
    index=years.index(1981)
)

end_year = st.sidebar.selectbox(
    "Ending Year",
    years,
    index=years.index(2025)
)

if start_year > end_year:

    st.error(
        "Starting year cannot be greater than ending year."
    )

    st.stop()


# ==========================================
# LOAD TEMPERATURE DATA
# ==========================================

with st.spinner(
    "Downloading NASA temperature data..."
):

    try:

        df = get_temperature_data(
            start_year,
            end_year
        )

    except Exception as error:

        st.error("Temperature data could not be loaded.")

        st.exception(error)

        st.stop()


st.success(
    f"Successfully loaded {len(df):,} monthly records."
)


# ==========================================
# OVERVIEW
# ==========================================

st.header("📊 Kerala Temperature Overview")

col1, col2, col3 = st.columns(3)

with col1:

    st.metric(
        "Total Districts",
        df["District"].nunique()
    )

with col2:

    st.metric(
        "Average Temperature",
        f"{df['Temperature'].mean():.2f} °C"
    )

with col3:

    st.metric(
        "Highest Monthly Average",
        f"{df['Temperature'].max():.2f} °C"
    )


# ==========================================
# KERALA DISTRICT BOUNDARY MAP
# ==========================================

st.header("🗺️ Kerala District Temperature Map")

try:

    with st.spinner("Loading Kerala district boundaries..."):

        geojson = get_kerala_boundaries()

        map_data = prepare_map_data(
            df,
            geojson
        )

    fig_map = px.choropleth_map(
        map_data,

        geojson=geojson,

        locations="GeoDistrict",

        featureidkey="properties.DISTRICT",

        color="Temperature",

        color_continuous_scale="Turbo",

        map_style="carto-positron",

        center={
            "lat": 10.5,
            "lon": 76.2
        },

        zoom=6.3,

        opacity=0.70,

        hover_name="District",

        hover_data={
            "Temperature": ":.2f",
            "GeoDistrict": False
        },

        labels={
            "Temperature": "Average Temperature (°C)"
        },

        title="Temperature Distribution Across Kerala"

    )

    fig_map.update_traces(

        marker_line_color="black",

        marker_line_width=1.5

    )

    fig_map.update_layout(

        height=750,

        margin={
            "r": 0,
            "t": 50,
            "l": 0,
            "b": 0
        }

    )

    st.plotly_chart(
        fig_map,
        use_container_width=True
    )

    st.success(
        "All 14 district  loaded successfully!"
    )

    st.caption(
        "Hover over a district to view its name "
        "and average temperature."
    )

except Exception as error:

    st.error("District boundary map could not load.")

    st.exception(error)


# ==========================================
# DISTRICT SELECTION
# ==========================================

st.header("📍 District Temperature Analysis")

selected_district = st.selectbox(
    "Select a District",
    list(DISTRICTS.keys())
)

district_df = df[
    df["District"] == selected_district
].sort_values("Date")


# ==========================================
# MONTHLY TEMPERATURE CHART
# ==========================================

st.subheader(
    f"Monthly Temperature - {selected_district}"
)

fig_monthly = px.line(

    district_df,

    x="Date",

    y="Temperature",

    markers=True,

    title=f"Monthly Temperature in {selected_district}",

    labels={
        "Date": "Year",
        "Temperature": "Temperature (°C)"
    }

)

fig_monthly.update_layout(
    height=450
)

st.plotly_chart(
    fig_monthly,
    use_container_width=True
)


# ==========================================
# ANNUAL TEMPERATURE CHART
# ==========================================

st.subheader("📅 Annual Average Temperature")

annual_data = (
    district_df.groupby("Year")["Temperature"]
    .mean()
    .reset_index()
)

fig_annual = px.bar(

    annual_data,

    x="Year",

    y="Temperature",

    title=f"Annual Temperature - {selected_district}",

    labels={
        "Temperature": "Average Temperature (°C)"
    }

)

fig_annual.update_layout(
    height=450
)

st.plotly_chart(
    fig_annual,
    use_container_width=True
)


# ==========================================
# DISTRICT COMPARISON
# ==========================================

st.header("⚖️ Compare All Kerala Districts")

comparison = (
    df.groupby("District")["Temperature"]
    .mean()
    .reset_index()
    .sort_values("Temperature")
)

fig_comparison = px.bar(

    comparison,

    x="District",

    y="Temperature",

    color="Temperature",

    color_continuous_scale="Turbo",

    title="Average Temperature Comparison"

)

fig_comparison.update_layout(

    xaxis_tickangle=-45,

    height=500

)

st.plotly_chart(
    fig_comparison,
    use_container_width=True
)


# ==========================================
# TEMPERATURE SUMMARY
# ==========================================

st.header("📋 Temperature Summary")

summary = (
    df.groupby("District")["Temperature"]
    .agg(
        Average="mean",
        Minimum="min",
        Maximum="max"
    )
    .round(2)
    .reset_index()
)

st.dataframe(
    summary,
    use_container_width=True
)


# ==========================================
# RAW DATA
# ==========================================

with st.expander("View Complete Temperature Dataset"):

    st.dataframe(
        df,
        use_container_width=True
    )


# ==========================================
# DOWNLOAD CSV
# ==========================================

st.header("📥 Download Temperature Data")

csv = df.to_csv(
    index=False
).encode("utf-8")

st.download_button(

    label="Download Temperature Data (CSV)",

    data=csv,

    file_name="kerala_temperature_data.csv",

    mime="text/csv"

)


# ==========================================
# FOOTER
# ==========================================

st.divider()

st.markdown("""
### Kerala Temperature Explorer

**Data Source:** NASA POWER

**Parameter:** T2M - Temperature at 2 Metres

**Data Type:** Monthly Temperature Data

**Map Source:** Kerala District GeoJSON

**Technologies:** Python, Streamlit, Pandas and Plotly
""")