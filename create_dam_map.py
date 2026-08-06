#!/usr/bin/env python3
"""
Folium Map Creation for South African Dam Levels
This script demonstrates how to create an interactive map showing dam locations
with their current water levels and other relevant information.
"""

import pandas as pd
import folium
from folium import plugins
import branca.colormap as cm

def create_dam_map(dam_df, location_df=None):
    """
    Create an interactive Folium map of South African dams

    Parameters:
    -----------
    dam_df : DataFrame
        Contains dam information including willDam, FSC, This Week, Last Week, Last Year
    location_df : DataFrame, optional
        Contains dam location information (Name of dam, Decimal degree latitude, Decimal degree longitude)
        If None, will attempt to extract from dam_df or use sample data

    Returns:
    --------
    folium.Map
        An interactive map object
    """

    # Filter out 'Total' rows if present
    if 'willDam' in dam_df.columns:
        dam_df = dam_df[dam_df['willDam'] != 'Total'].copy()

    # If location data is not provided, try to extract or create sample data
    if location_df is None:
        # In a real scenario, you would have this data from your geocoding efforts
        # For demonstration, I'll create sample coordinates based on dam names
        # In practice, replace this with your actual location data
        print("Warning: Using sample location data. Replace with actual dam coordinates.")
        location_df = create_sample_location_data(dam_df)

    # Clean and prepare the data
    dam_df_clean = dam_df.copy()

    # Ensure numeric columns are properly formatted
    numeric_cols = ['FSC', 'This Week', 'Last Week', 'Last Year']
    for col in numeric_cols:
        if col in dam_df_clean.columns:
            # Remove any non-numeric characters and convert to float
            dam_df_clean[col] = pd.to_numeric(
                dam_df_clean[col].astype(str).str.replace('#', ''),
                errors='coerce'
            )

    # Calculate percentage full for current week
    if 'FSC' in dam_df_clean.columns and 'This Week' in dam_df_clean.columns:
        dam_df_clean['Pct_Full'] = (dam_df_clean['This Week'] / dam_df_clean['FSC']) * 100

    # Create the base map centered on South Africa
    # Approximate center of South Africa
    sa_center = [-28.0, 24]

    m = folium.Map(
        location=sa_center,
        zoom_start=6,
        tiles='OpenStreetMap'
    )

    # Add alternative tile layers
    folium.TileLayer(
        tiles='Stamen Terrain',
        attr='Map tiles by Stamen Design, under CC BY 3.0. Data by OpenStreetMap, under ODbL.',
        name='Terrain'
    ).add_to(m)

    folium.TileLayer(
        tiles='Stamen Toner',
        attr='Map tiles by Stamen Design, under CC BY 3.0. Data by OpenStreetMap, under ODbL.',
        name='Toner'
    ).add_to(m)

    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
        name='Esri Satellite'
    ).add_to(m)

    # Create a color scale for water level percentage
    if 'Pct_Full' in dam_df_clean.columns:
        # Define color scale: red (low) -> yellow (medium) -> green (high)
        colormap = cm.LinearColormap(
            colors=['red', 'orange', 'yellow', 'lightgreen', 'green'],
            vmin=0, vmax=100,
            caption='Water Level (% of Full Supply Capacity)'
        )
        colormap.caption = 'Water Level (% Full)'
        colormap.add_to(m)

    # Feature groups for different layers
    dams_feature_group = folium.FeatureGroup(name="Dam Locations")
    high_level_group = folium.FeatureGroup(name="High Water Levels (>80%)")
    medium_level_group = folium.FeatureGroup(name="Medium Water Levels (30-80%)")
    low_level_group = folium.FeatureGroup(name="Low Water Levels (<30%)")

    # Add markers for each dam
    for idx, row in dam_df_clean.iterrows():
        # Skip if we don't have location data for this dam
        dam_name = row.get('willDam', '')
        if dam_name not in location_df['Name of dam'].values:
            continue

        # Get coordinates for this dam
        dam_location = location_df[location_df['Name of dam'] == dam_name].iloc[0]
        lat = dam_location['Decimal degree latitude']
        lon = dam_location['Decimal degree longitude']

        # Skip if coordinates are missing
        if pd.isna(lat) or pd.isna(lon):
            continue

        # Determine popup content
        popup_html = f"""
        <div style="width: 200px;">
            <h4>{dam_name}</h4>
            <hr style="margin: 5px 0;">
            <b>River:</b> {row.get('River', 'N/A')}<br>
            <b>FSC (Million m³):</b> {row.get('FSC', 'N/A'):,.0f}<br>
            <b>This Week:</b> {row.get('This Week', 'N/A'):.1f}%<br>
            <b>Last Week:</b> {row.get('Last Week', 'N/A'):.1f}%<br>
            <b>Last Year:</b> {row.get('Last Year', 'N/A'):.1f}%<br>
            <b>% Full:</b> {row.get('Pct_Full', 0):.1f}%
        </div>
        """

        # Determine marker color based on water level
        pct_full = row.get('Pct_Full', 0)
        if pd.isna(pct_full):
            color = 'gray'
        elif pct_full >= 80:
            color = 'green'
            target_group = high_level_group
        elif pct_full >= 30:
            color = 'orange'
            target_group = medium_level_group
        else:
            color = 'red'
            target_group = low_level_group

        # Create the marker
        folium.CircleMarker(
            location=[lat, lon],
            radius=8,
            popup=folium.Popup(popup_html, max_width=250),
            color='white',
            weight=2,
            fillColor=color,
            fillOpacity=0.8,
            tooltip=f"{dam_name}: {pct_full:.1f}% full"
        ).add_to(target_group)

        # Also add to main dams group for layer control
        folium.CircleMarker(
            location=[lat, lon],
            radius=8,
            popup=folium.Popup(popup_html, max_width=250),
            color='white',
            weight=2,
            fillColor=color,
            fillOpacity=0.8,
            tooltip=f"{dam_name}: {pct_full:.1f}% full"
        ).add_to(dams_feature_group)

    # Add all feature groups to the map
    dams_feature_group.add_to(m)
    high_level_group.add_to(m)
    medium_level_group.add_to(m)
    low_level_group.add_to(m)

    # Add layer control
    folium.LayerControl(collapsed=False).add_to(m)

    # Add a title
    title_html = '''
             <h3 align="center" style="font-size:16px"><b>South African Dam Levels Monitor</b></h3>
             '''
    m.get_root().html.add_child(folium.Element(title_html))

    # Add fullscreen button
    plugins.Fullscreen(
        position='topright',
        title='Expand me',
        title_cancel='Exit me',
        force_separate_button=True,
    ).add_to(m)

    # Add measure tool
    plugins.MeasureControl(
        position='topleft',
        active_color='red',
        completed_color='red'
    ).add_to(m)

    return m

def create_sample_location_data(dam_df):
    """
    Create sample location data for demonstration purposes.
    In practice, replace this with your actual geocoded data.
    """
    # Sample coordinates for some major South African dams
    # This is just for demonstration - replace with your actual data
    sample_locations = {
        'Bronkhorstspruit Dam': [-25.8065, 28.7206],
        'Roodeplaat Dam': [-25.6483, 28.3333],
        'Buffelskloof Dam': [-25.5731, 30.0999],
        'Grootdraai Dam': [-26.9833, 29.2333],
        'Heyshope Dam': [-27.1667, 30.0500],
        'Katse Dam': [-29.3000, 28.8500],
        'Mohale Dam': [-29.5000, 28.3000],
        'Vaal Dam': [-26.9500, 28.1500],
        'Gariep Dam': [-30.5000, 25.5000],
        'Vanderkloof Dam': [-29.9000, 24.8000]
    }

    # Create DataFrame from sample data
    location_data = []
    for dam_name, coords in sample_locations.items():
        if dam_name in dam_df['willDam'].values:
            location_data.append({
                'Name of dam': dam_name,
                'Decimal degree latitude': coords[0],
                'Decimal degree longitude': coords[1]
            })

    return pd.DataFrame(location_data)

# Example usage:
if __name__ == "__main__":
    # Load your dam data (adjust path as needed)
    # dam_df = pd.read_csv("path/to/your/dam_data.csv")

    # For demonstration, let's create sample data similar to yours
    sample_data = {
        'willDam': [
            'Bronkhorstspruit Dam', 'Roodeplaat Dam', 'Buffelskloof Dam',
            'Grootdraai Dam', 'Heyshope Dam', 'Katse Dam', 'Mohale Dam'
        ],
        'River': [
            'Bronkhorstspruit River', 'Pienaars River', 'Waterval River',
            'Vaal River', 'Assegaai River', 'Malibamatso River', 'Senqunyane River'
        ],
        'FSC': [57.0, 41.2, 5.3, 349.8, 445.0, 1519.2, 843.6],
        'This Week': [100.9, 100.6, 100.5, 99.9, 101.2, 93.9, 101.9],
        'Last Week': [93.9, 101.9],
        'Last Week': [101.4, 100.6, 100.6, 100.0, 101.4, 94.7, 102.1],
        'Last Year': [102.3, 100.5, 100.6, 100.9, 100.2, 99.1, 101.9]
    }

    dam_df = pd.DataFrame(sample_data)

    # Create the map
    dam_map = create_dam_map(dam_df)

    # Save to HTML file
    dam_map.save("south_african_dams_map.html")
    print("Map saved as 'south_african_dams_map.html'")

    # To display in Jupyter notebook, you would use:
    # dam_map