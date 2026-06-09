import streamlit as st
import requests
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from geopy.geocoders import Nominatim
from supabase import create_client
import pandas as pd
import time
import folium
import re
from streamlit_folium import st_folium
from datetime import datetime

# --- INITIALIZE DATABASE CONNECTION ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 1. SPECIFIC SPECIFICATION BLUEPRINT FOR GEMINI EXTRACTION
class PropertyDetails(BaseModel):
    title: str = Field(description="The main headline or title of the property listing")
    address: str = Field(description="The full address location hierarchy found on the listing webpage.")
    price: str = Field(description="The listed price string, e.g., '850 000 zł' or '750000'")
    area: str = Field(description="The total area/surface size of the property in square meters (m²)")
    rooms: str = Field(description="The number of rooms in the property")
    floor: str = Field(description="The specific floor level of the property, e.g., '1st floor', 'Ground floor', 'Top floor', '3'")
    floors: str = Field(description="The total number of floors/stories present in the entire building block, e.g., '4', '10'")
    year_built: str = Field(description="The year the building/property was constructed. Use 'Unknown' if missing.")
    description: str = Field(description="A brief summary of key features or selling points from the listing text.")

# HELPER: Robust Monetary Extraction Engine
def clean_monetary_value(value_str: str) -> float:
    if not value_str:
        return 0.0
    cleaned = re.sub(r'[^\d.,]', '', str(value_str))
    if not cleaned:
        return 0.0
    if ',' in cleaned and '.' in cleaned:
        cleaned = cleaned.replace(',', '')
    elif ',' in cleaned:
        parts = cleaned.split(',')
        if len(parts[-1]) == 2:  
            cleaned = cleaned.replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')
    try:
        return float(cleaned)
    except ValueError:
        return 0.0

# HELPER: Clean Numerical Area Extraction Engine
def clean_area_value(area_str: str) -> float:
    if not area_str:
        return 0.0
    cleaned = re.sub(r'[^\d.,]', '', str(area_str))
    if ',' in cleaned and '.' in cleaned:
        cleaned = cleaned.replace(',', '')
    elif ',' in cleaned:
        parts = cleaned.split(',')
        if len(parts[-1]) == 2:
            cleaned = cleaned.replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')
    try:
        return float(cleaned)
    except ValueError:
        return 0.0

# 2. INTELLIGENT SCRAPER TARGETING METADATA ATTRIBUTES (TAB 1 USE CASE)
def intelligent_scraper(url: str):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        response = requests.get(url, headers=headers, timeout=10)
        
        soup = BeautifulSoup(response.text, "html.parser")
        extracted_chunks = []
        
        container_elements = soup.find_all(attrs={"data-sentry-element": "Container"})
        for container in container_elements:
            container_text = container.get_text(strip=True)
            if any(city in container_text for city in ["Wrocław", "Kraków", "Warszawa"]):
                extracted_chunks.append(f"[Header Location Container]: {container_text}")
        
        targeted_elements = soup.find_all(lambda tag: tag.has_attr('data-sentry-element'))
        for element in targeted_elements:
            element_type = element['data-sentry-element']
            element_text = element.get_text(strip=True)
            if element_type == "Container" and len(element_text) > 300:
                continue
            if element_text:
                extracted_chunks.append(f"[{element_type}]: {element_text}")
                
        if extracted_chunks:
            clean_text = "\n".join(extracted_chunks)
        else:
            clean_text = soup.get_text(separator="\n", strip=True)
            
        clean_text = clean_text[:6000] 
        
    except Exception as e:
        st.error(f"Failed to read the website: {e}")
        return None

    try:
        client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
        
        prompt = f"""
        You are an expert real estate data engineer. Carefully read the text below, which contains 
        structured element tags extracted from a property listing. 
        Analyze the key parameters and fill out the required schema details flawlessly.
        
        Extracted Elements & Content:
        {clean_text}
        """
        
        models_to_try = ['gemini-2.5-flash', 'gemini-2.0-flash']
        ai_response = None
        
        for model_name in models_to_try:
            try:
                ai_response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=PropertyDetails,
                        temperature=0.1
                    ),
                )
                break
            except Exception as model_error:
                error_str = str(model_error)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    if model_name == 'gemini-2.5-flash':
                        st.warning("Primary model tier baseline exhausted. Moving to secondary pipeline variant...")
                        time.sleep(1)
                        continue
                    else:
                        st.error("⚠️ Gemini API Daily Quota Exhausted completely across all operational free tier tracking models.")
                        return None
                else:
                    raise model_error
                    
        if ai_response:
            return ai_response.parsed
        return None
        
    except Exception as e:
        st.error(f"Gemini API Error: {e}")
        return None

# --- BULK PROCESSING NON-AI API SCRAPER ENGINE ---
def deterministic_bulk_api_scraper(url: str):
    """
    Scrapes listing raw properties using Otodom's public JSON endpoint 
    by resolving the alphanumeric ID tracking string via pattern regex.
    """
    try:
        # Step 2 & 3 implementation: Extract structural tracking string
        id_match = re.search(r"-(ID[a-zA-Z0-9]+)$", url.strip())
        if not id_match:
            return None
        
        listing_slug_id = id_match.group(1)
        api_target_endpoint = f"https://www.otodom.pl/api/v1/estate/page/{listing_slug_id}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.otodom.pl/"
        }
        
        response = requests.get(api_target_endpoint, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
            
        data = response.json()
        
        # Safe breakdown parsing from structural dictionary targets
        title = data.get("title", "Unknown Title")
        description = data.get("description", "")[:200]
        
        price_val = str(data.get("price", {}).get("value", "0"))
        area_val = str(data.get("area", {}).get("value", "0"))
        
        # Pull localization context
        loc_data = data.get("location", {})
        address_parts = [
            loc_data.get("street", {}).get("name", ""),
            loc_data.get("district", {}).get("name", ""),
            loc_data.get("city", {}).get("name", "")
        ]
        address = ", ".join([p for p in address_parts if p]) or "Wrocław, Poland"
        
        # Pull structural characteristics
        characteristics = {item["key"]: item["value"] for item in data.get("characteristics", []) if "key" in item}
        rooms = str(characteristics.get("rooms_num", "1"))
        floor = str(characteristics.get("floor_no", "Ground"))
        floors = str(characteristics.get("building_floors_num", "Unknown"))
        year_built = str(characteristics.get("build_year", "Unknown"))
        
        return {
            "url": url, "title": title, "address": address, "price": clean_monetary_value(price_val),
            "area": area_val, "rooms": rooms, "floor": floor, "floors": floors, "year_built": year_built,
            "description": description
        }
    except Exception:
        return None

# 3. ROBUST HYPER-RESILIENT GEOCODING ENGINE WITH DISTRICT FALLBACK
def get_coordinates(address_string: str):
    geolocator = Nominatim(user_agent="property_tracker_hub_live_production_v16")
    address_string = address_string.strip("'\" []")
    
    parts = [p.strip() for p in address_string.split(",")] if "," in address_string else [address_string]
    street_candidate = parts[0]
    
    city_candidate = "Wrocław"
    for part in parts:
        lower_part = part.lower()
        if "wrocław" in lower_part:
            city_candidate = "Wrocław"
            break
        elif "kraków" in lower_part or "krakow" in lower_part:
            city_candidate = "Kraków"
            break
        elif "warszawa" in lower_part:
            city_candidate = "Warszawa"
            break

    clean_street = re.sub(r'^(ul\.|ulica|os\.|osiedle)\s+', '', street_candidate, flags=re.IGNORECASE)

    try:
        structured_query_1 = {
            "street": f"ul. {clean_street}",
            "city": city_candidate,
            "country": "Poland"
        }
        location = geolocator.geocode(structured_query_1, timeout=10)
        if location:
            return float(location.latitude), float(location.longitude)
    except Exception:
        pass

    try:
        structured_query_2 = {
            "street": clean_street,
            "city": city_candidate,
            "country": "Poland"
        }
        location = geolocator.geocode(structured_query_2, timeout=10)
        if location:
            return float(location.latitude), float(location.longitude)
    except Exception:
        pass

    try:
        flat_string_fallback = f"ul. {clean_street}, {city_candidate}, Poland"
        location = geolocator.geocode(flat_string_fallback, timeout=10)
        if location:
            return float(location.latitude), float(location.longitude)
    except Exception:
        pass

    try:
        district_query = f"{clean_street}, {city_candidate}, Poland"
        location = geolocator.geocode(district_query, timeout=10)
        if location:
            return float(location.latitude), float(location.longitude)
    except Exception:
        pass
        
    return None, None

# --- CONSTANT PIPELINE CONFIGURATION ---
STATUS_OPTIONS = ["Interested", "Viewing Arranged", "Offer Submitted", "No Longer Available", "No Longer Interested", "Archived"]

# --- STREAMLIT PAGE SETUP ---
st.set_page_config(layout="wide", page_title="Property Evaluation Hub")
st.title("🏡 Property Hub Tracker Workspace")

# Added Tab 3 to layout row container allocation mappings
tab_scraped, tab_map_view, tab_bulk_parser = st.tabs(["📊 Parser & Evaluator", "🗺️ Portfolio Map Explorer", "📥 Bulk Parser"])

# =========================================================================
# PAGE WORKSPACE 1: PARSER & EVALUATOR
# =========================================================================
with tab_scraped:
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Step 1: Parse Listing URL")
        default_url = "https://www.otodom.pl/pl/oferta/okazja-3-pokoje-2-balkony-krzyki-ID4AN0H"
        target_url = st.text_input("Property URL Link:", value=default_url, key="input_target_url")
        
        if st.button("Analyze with Intelligent Parsing", key="btn_run_scraper"):
            if target_url:
                with st.spinner("Scanning webpage metadata elements with AI..."):
                    extracted = intelligent_scraper(target_url)
                    if extracted:
                        lat, lon = get_coordinates(extracted.address)
                        numeric_price = clean_monetary_value(extracted.price)
                        
                        st.session_state["scraped_cache"] = {
                            "url": target_url,
                            "title": extracted.title,
                            "address": extracted.address,
                            "price": numeric_price,
                            "area": extracted.area,
                            "rooms": extracted.rooms,
                            "floor": extracted.floor,
                            "floors": extracted.floors,
                            "year_built": extracted.year_built,
                            "description": extracted.description,
                            "latitude": lat,
                            "longitude": lon
                        }
                        st.success("Web metadata extraction complete!")
            else:
                st.warning("Please input a valid listing link.")

        if "scraped_cache" in st.session_state:
            cache = st.session_state["scraped_cache"]
            st.markdown("---")
            st.subheader("Step 2: Self-Input & Data Enrichment")
            
            st.text_input("Listing Title (Read-Only):", value=cache["title"], disabled=True, key="field_title")
            
            price_input = st.number_input(
                "Base Property Price (zł):", 
                min_value=0.0, 
                value=float(cache["price"]), 
                step=5000.0, 
                format="%.2f", 
                key="field_price_numeric"
            )
            
            user_edited_address = st.text_input(
                "Property Address (Editable):", 
                value=cache["address"], 
                key="field_address_editable"
            )
            
            if user_edited_address != cache["address"]:
                new_lat, new_lon = get_coordinates(user_edited_address)
                cache["address"] = user_edited_address
                cache["latitude"] = new_lat
                cache["longitude"] = new_lon

            if cache["latitude"] and cache["longitude"]:
                st.success(f"✅ Map Match Found! Coordinates resolved to: {cache['latitude']}, {cache['longitude']}")
            else:
                st.error("❌ Geocoding Failed! Try cleaning up the text block to just: 'ul. Popowicka, Wrocław'")
            
            metric_col1, metric_col2, metric_col3, metric_col4, metric_col5 = st.columns(5)
            with metric_col1:
                st.text_input("Area (m²):", value=cache["area"], disabled=True, key="field_area")
            with metric_col2:
                st.text_input("Rooms:", value=cache["rooms"], disabled=True, key="field_rooms")
            with metric_col3:
                st.text_input("Floor:", value=cache["floor"], disabled=True, key="field_floor")
            with metric_col4:
                st.text_input("Total Floors:", value=cache.get("floors", "Unknown"), disabled=True, key="field_floors")
            with metric_col5:
                st.text_input("Year Built:", value=cache["year_built"], disabled=True, key="field_year")
            
            st.markdown("### 💰 Additional Transaction Outlays (Numeric Polish Złoty)")
            cost_col1, cost_col2 = st.columns(2)
            with cost_col1:
                garage_input = st.number_input("Additional Cost - Garage (zł):", min_value=0.0, value=0.0, step=1000.0, format="%.2f", key="field_garage_numeric")
            with cost_col2:
                storage_input = st.number_input("Additional Cost - Storage (zł):", min_value=0.0, value=0.0, step=500.0, format="%.2f", key="field_storage_numeric")

            st.markdown("### Your Custom Input Evaluation Metrics")
            user_notes = st.text_area("Your Comments Field (Personal Evaluation Notes):", placeholder="e.g., Close to Popowicki Park, great layout.", key="field_notes")
            user_rating = st.slider("Your Personal Property Rating (Out of 10):", min_value=1, max_value=10, value=5, key="field_rating")
            
            current_status = st.selectbox("Pipeline Track Status:", STATUS_OPTIONS, key="field_status")
            
            if st.button("Commit This Record Version to Database", key="btn_commit_db"):
                now_iso = datetime.utcnow().isoformat() + "Z"
                
                try:
                    existing_check = supabase.table("properties")\
                        .select("id")\
                        .eq("url", cache["url"])\
                        .eq("is_current", True)\
                        .execute()
                    
                    if existing_check.data:
                        old_record_id = existing_check.data[0]["id"]
                        supabase.table("properties")\
                            .update({"is_current": False, "valid_to": now_iso})\
                            .eq("id", old_record_id)\
                            .execute()
                    
                    property_payload = {
                        "url": cache["url"],
                        "title": cache["title"],
                        "address": cache["address"],
                        "price": price_input,           
                        "area": cache["area"],
                        "rooms": cache["rooms"],
                        "floor": cache["floor"],
                        "floors": cache.get("floors", "Unknown"),
                        "year_built": cache["year_built"],
                        "garage_cost": garage_input,
                        "storage_cost": storage_input,
                        "my_notes": user_notes,
                        "rating": user_rating,
                        "status": current_status,
                        "valid_from": now_iso,
                        "is_current": True,
                        "latitude": cache["latitude"],  
                        "longitude": cache["longitude"]
                    }
                    
                    supabase.table("properties").insert(property_payload).execute()
                    st.success("Successfully logged property entry version parameters!")
                    del st.session_state["scraped_cache"]
                    st.rerun()
                    
                except Exception as database_error:
                    st.error(f"Failed to log entry into database table: {database_error}")

    with col2:
        st.subheader("Saved Property Records Overview")
        st.info("💡 Go to the 'Portfolio Map Explorer' tab to apply real-time filtering, cross-examine properties on the map, and edit track details!")

# =========================================================================
# PAGE WORKSPACE 2: PORTFOLIO MAP EXPLORER (THE MASTER CONTROL CENTER)
# =========================================================================
with tab_map_view:
    try:
        db_query_map = supabase.table("properties").select("*").execute()
        map_properties = db_query_map.data
    except Exception as e:
        st.error(f"Failed to fetch maps pipeline data: {e}")
        map_properties = []

    df_current = pd.DataFrame()
    if map_properties:
        df_all = pd.DataFrame(map_properties)
        if "is_current" in df_all.columns:
            df_current = df_all[df_all["is_current"] == True].copy()

    # --- GLOBAL FILTERS INTERFACE PANEL ---
    st.markdown("### 🔍 Live Portfolio Filter Console")
    
    filter_col1, filter_col2, filter_col3, filter_col4, filter_col5 = st.columns([1.0, 1.0, 1.2, 1.1, 1.1])
    df_filtered = pd.DataFrame()
    
    if not df_current.empty:
        df_current["price"] = pd.to_numeric(df_current["price"], errors='coerce').fillna(0.0)
        df_current["garage_cost"] = pd.to_numeric(df_current["garage_cost"], errors='coerce').fillna(0.0)
        df_current["storage_cost"] = pd.to_numeric(df_current["storage_cost"], errors='coerce').fillna(0.0)
        df_current["numeric_area"] = df_current["area"].apply(clean_area_value)
        df_current["Cost per m²"] = df_current.apply(
            lambda r: r["price"] / r["numeric_area"] if r["numeric_area"] > 0 else 0.0, axis=1
        )
        df_current["Total Cost"] = df_current["price"] + df_current["garage_cost"] + df_current["storage_cost"]
        
        df_current["rating"] = pd.to_numeric(df_current.get("rating", 5), errors='coerce').fillna(5).astype(int)
        
        if "ranking" not in df_current.columns:
            df_current["ranking"] = 0
        else:
            df_current["ranking"] = pd.to_numeric(df_current["ranking"], errors='coerce').fillna(0).astype(int)

        df_current["title"] = df_current["title"].astype(str).fillna("")
        df_current["address"] = df_current["address"].astype(str).fillna("")
        df_current["my_notes"] = df_current["my_notes"].astype(str).fillna("")
        
        df_filtered = df_current.copy()

        with filter_col1:
            status_filter = st.multiselect("Filter by Status:", options=STATUS_OPTIONS, default=STATUS_OPTIONS)
            if status_filter:
                df_filtered = df_filtered[df_filtered["status"].isin(status_filter)]
            else:
                df_filtered = pd.DataFrame(columns=df_current.columns)
                
        with filter_col2:
            text_search = st.text_input("Filter by Text Match:", placeholder="e.g. Krzyki or Popowicka")
            if text_search and not df_filtered.empty:
                search_lower = text_search.lower()
                df_filtered = df_filtered[
                    df_filtered["title"].str.lower().str.contains(search_lower) | 
                    df_filtered["address"].str.lower().str.contains(search_lower) |
                    df_filtered["my_notes"].str.lower().str.contains(search_lower)
                ]

        with filter_col3:
            min_p = float(df_current["Total Cost"].min()) if not df_current.empty else 0.0
            max_p = float(df_current["Total Cost"].max()) if not df_current.empty else 1500000.0
            if min_p == max_p:
                max_p += 10000.0
            
            budget_range = st.slider(
                "Filter by Budget (zł):",
                min_value=0.0,
                max_value=max_p,
                value=(0.0, max_p),
                step=10000.0,
                format="%d zł"
            )
            if not df_filtered.empty:
                df_filtered = df_filtered[(df_filtered["Total Cost"] >= budget_range[0]) & (df_filtered["Total Cost"] <= budget_range[1])]

        with filter_col4:
            min_r = int(df_current["ranking"].min()) if not df_current.empty else 0
            max_r = int(df_current["ranking"].max()) if not df_current.empty else 100
            if min_r == max_r:
                max_r = max(min_r + 10, 10)
                
            ranking_range = st.slider("Filter by Ranking:", min_value=0, max_value=max_r, value=(0, max_r), step=1)
            if not df_filtered.empty:
                df_filtered = df_filtered[(df_filtered["ranking"] >= ranking_range[0]) & (df_filtered["ranking"] <= ranking_range[1])]

        with filter_col5:
            rating_range = st.slider("Filter by Rating (1-10):", min_value=1, max_value=10, value=(1, 10), step=1)
            if not df_filtered.empty:
                df_filtered = df_filtered[(df_filtered["rating"] >= rating_range[0]) & (df_filtered["rating"] <= rating_range[1])]

    # --- DYNAMIC SYNCHRONIZED MAP ENGINE ---
    wroclaw_center_view = [51.1079, 17.0385]
    folium_explorer_map = folium.Map(location=wroclaw_center_view, zoom_start=12, control_scale=True)
    marker_group = folium.FeatureGroup(name="Properties")
    saved_pins_count = 0
    
    if not df_filtered.empty and "latitude" in df_filtered.columns and "longitude" in df_filtered.columns:
        df_pins = df_filtered.dropna(subset=['latitude', 'longitude'])
        for _, row in df_pins.iterrows():
            try:
                lat_coord = float(row['latitude'])
                lon_coord = float(row['longitude'])
                
                html_popup_markup = f"""
                <div style='font-family: Arial, sans-serif; min-width: 250px;'>
                    <h4 style='margin:0 0 5px 0; color:#1f77b4;'>{row['title']}</h4>
                    <b>⭐ Ranking:</b> {int(row.get('ranking', 0))}<br>
                    <b>📊 Rating:</b> {int(row.get('rating', 5))}/10<br>
                    <b>📍 Address:</b> {row['address']}<br>
                    <b>📐 Area Size:</b> {row['area']}<br>
                    <b>🏢 Structural Level:</b> Floor {row.get('floor', 'N/A')} of {row.get('floors', 'N/A')}<br>
                    <b>🧱 Year Built:</b> {row.get('year_built', 'N/A')}<br>
                    <b>💰 Base Price:</b> {row['price']:,.2f} zł<br>
                    <b>📉 Cost per m²:</b> {row['Cost per m²']:,.2f} zł/m²<br>
                    <b>🚗 Garage Cost:</b> {row['garage_cost']:,.2f} zł<br>
                    <b>📦 Storage Cost:</b> {row['storage_cost']:,.2f} zł<br>
                    <hr style='margin: 6px 0;'>
                    <b>💳 Total Budget Outlay:</b> <span style='color:#d9534f; font-weight:bold;'>{row['Total Cost']:,.2f} zł</span><br>
                    <b>🚦 Track Status:</b> <span style='color:green; font-weight:bold;'>{row['status']}</span><br>
                    <b>📝 My Notes:</b> <i>{row['my_notes']}</i>
                </div>
                """
                marker_color = "blue"
                if row['status'] in ["No Longer Available", "No Longer Interested"]:
                    marker_color = "gray"
                elif row.get('rating', 5) >= 8:
                    marker_color = "red"

                folium.Marker(
                    location=[lat_coord, lon_coord],
                    popup=folium.Popup(html_popup_markup, max_width=350),
                    icon=folium.Icon(color=marker_color, icon="home")
                ).add_to(marker_group)
                saved_pins_count += 1
            except Exception:
                continue

    marker_group.add_to(folium_explorer_map)
    st_folium(folium_explorer_map, use_container_width=True, height=450, key=f"map_workbench_pins_{saved_pins_count}")
    st.caption(f"📍 Map outputting **{saved_pins_count}** filtered investment markers.")

    # --- WORKBENCH LAYOUT DATA TABLES & MODIFIER PANELS ---
    if not df_current.empty:
        st.markdown("---")
        edit_layout, grid_layout = st.columns([1, 2])
        
        with edit_layout:
            st.markdown("### ✏️ Quick Pop-Up Editor")
            edit_target_options = df_filtered["title"].unique() if not df_filtered.empty else df_current["title"].unique()
            selected_title = st.selectbox("Select a Property to Edit Inline:", options=edit_target_options, key="map_editor_picker")
            
            if selected_title:
                selected_row = df_current[df_current["title"] == selected_title].iloc[0]
                
                with st.expander(f"Modifier Panel: {selected_title[:30]}...", expanded=True):
                    edit_ranking = st.number_input("Portfolio Ranking Metric:", min_value=0, max_value=1000, value=int(selected_row.get("ranking", 0)), step=1)
                    edit_rating = st.slider("Property Rating Metric (1-10):", min_value=1, max_value=10, value=int(selected_row.get("rating", 5)), step=1)
                    edit_status = st.selectbox("Status:", STATUS_OPTIONS, index=STATUS_OPTIONS.index(selected_row["status"]))
                    edit_price = st.number_input("Base Price (zł):", min_value=0.0, value=float(selected_row["price"]), step=5000.0)
                    edit_floor = st.text_input("Floor number:", value=str(selected_row.get("floor", "")))
                    edit_floors = st.text_input("Total building floors:", value=str(selected_row.get("floors", "")))
                    edit_year = st.text_input("Year Built:", value=str(selected_row.get("year_built", "")))
                    edit_garage = st.number_input("Garage Cost (zł):", min_value=0.0, value=float(selected_row["garage_cost"]), step=1000.0)
                    edit_storage = st.number_input("Storage Cost (zł):", min_value=0.0, value=float(selected_row["storage_cost"]), step=500.0)
                    edit_notes = st.text_area("My Notes:", value=str(selected_row["my_notes"]))
                    
                    if st.button("Save Changes Directly to Record", key="btn_save_inline_map"):
                        update_payload = {
                            "ranking": edit_ranking,
                            "rating": edit_rating,
                            "status": edit_status,
                            "price": edit_price,
                            "floor": edit_floor,
                            "floors": edit_floors,
                            "year_built": edit_year,
                            "garage_cost": edit_garage,
                            "storage_cost": edit_storage,
                            "my_notes": edit_notes
                        }
                        try:
                            supabase.table("properties").update(update_payload).eq("id", selected_row["id"]).execute()
                            st.success("Record updated successfully!")
                            time.sleep(1)
                            st.rerun()
                        except Exception as update_err:
                            st.error(f"Failed to push updates: {update_err}")

        with grid_layout:
            st.markdown("### 📊 Active Filtered Records Index")
            
            ordered_columns = [
                "id", "ranking", "rating", "title", "address", "area", "floor", "floors", "year_built", "status", "price", "Cost per m²", "garage_cost", "storage_cost", "Total Cost", "my_notes"
            ]
            
            df_display_source = df_filtered if not df_filtered.empty else pd.DataFrame(columns=ordered_columns)
            for col in ordered_columns:
                if col not in df_display_source.columns:
                    if col == "ranking":
                        df_display_source[col] = 0
                    elif col == "rating":
                        df_display_source[col] = 5
                    else:
                        df_display_source[col] = ""
                    
            df_display = df_display_source[ordered_columns].copy().sort_values(by=["ranking", "rating"], ascending=[False, False])

            edited_df = st.data_editor(
                df_display,
                column_config={
                    "id": None, 
                    "ranking": st.column_config.NumberColumn("Ranking", min_value=0, max_value=1000, step=1, disabled=False),
                    "rating": st.column_config.NumberColumn("Rating", min_value=1, max_value=10, step=1, disabled=False),
                    "title": st.column_config.TextColumn("Title", disabled=True),
                    "address": st.column_config.TextColumn("Address", disabled=True),
                    "area": st.column_config.TextColumn("Area", disabled=True),
                    "floor": st.column_config.TextColumn("Floor", disabled=False),
                    "floors": st.column_config.TextColumn("Total Floors", disabled=False),
                    "year_built": st.column_config.TextColumn("Year Built", disabled=False),
                    "status": st.column_config.SelectboxColumn("Status", options=STATUS_OPTIONS, disabled=False),
                    "price": st.column_config.NumberColumn("Base Price", format="%.2f zł", disabled=False),
                    "Cost per m²": st.column_config.NumberColumn("Cost per m²", format="%.2f zł", disabled=True),
                    "garage_cost": st.column_config.NumberColumn("Garage Cost", format="%.2f zł", disabled=False),
                    "storage_cost": st.column_config.NumberColumn("Storage Cost", format="%.2f zł", disabled=False),
                    "Total Cost": st.column_config.NumberColumn("Total Cost", format="%.2f zł", disabled=True),
                    "my_notes": st.column_config.TextColumn("My Notes", disabled=False),
                },
                use_container_width=True,
                hide_index=True,
                key="map_tab_aligned_data_grid"
            )

            if st.session_state.get("map_tab_aligned_data_grid") and st.session_state["map_tab_aligned_data_grid"]["edited_rows"]:
                changes_detected = st.session_state["map_tab_aligned_data_grid"]["edited_rows"]
                
                for row_idx_str, updated_fields in changes_detected.items():
                    row_idx = int(row_idx_str)
                    record_id = df_display.iloc[row_idx]["id"]
                    
                    try:
                        if record_id:
                            supabase.table("properties").update(updated_fields).eq("id", record_id).execute()
                    except Exception as e:
                        st.error(f"Failed to synchronize table changes: {e}")
                
                st.rerun()

# =========================================================================
# PAGE WORKSPACE 3: BULK PARSER (NEW FEATURES CONSOLE)
# =========================================================================
with tab_bulk_parser:
    st.subheader("📥 Bulk Property Processing Center")
    st.markdown("Upload a standard `.csv` file containing Otodom listing links under a column named **`url`**.")
    
    csv_file_handler = st.file_uploader("Choose CSV File Input Source", type=["csv"], key="bulk_csv_file_uploader")
    
    if csv_file_handler:
        try:
            input_dataframe = pd.read_csv(csv_file_handler)
            if "url" not in input_dataframe.columns:
                st.error("❌ The uploaded CSV file must contain a column named exactly **'url'**.")
            else:
                target_url_list = input_dataframe["url"].dropna().unique().tolist()
                st.info(f"📋 Found **{len(target_url_list)}** unique links to evaluate.")
                
                if st.button("Execute Non-AI Bulk Parsing Execution", key="btn_run_bulk_processing"):
                    staged_results_accumulator = []
                    
                    processing_progress_bar = st.progress(0)
                    status_message_placeholder = st.empty()
                    
                    for index, active_url in enumerate(target_url_list):
                        status_message_placeholder.text(f"Parsing item {index+1}/{len(target_url_list)}: {active_url[:50]}...")
                        
                        parsed_record = deterministic_bulk_api_scraper(active_url)
                        if parsed_record:
                            # Pre-populate custom workbench variables
                            parsed_record["ranking"] = 0
                            parsed_record["rating"] = 5
                            parsed_record["status"] = "Interested"
                            parsed_record["garage_cost"] = 0.0
                            parsed_record["storage_cost"] = 0.0
                            parsed_record["my_notes"] = ""
                            staged_results_accumulator.append(parsed_record)
                        
                        processing_progress_bar.progress((index + 1) / len(target_url_list))
                        time.sleep(0.2) # Courteous throttling gap delay
                        
                    status_message_placeholder.empty()
                    processing_progress_bar.empty()
                    
                    if staged_results_accumulator:
                        st.session_state["bulk_staging_dataframe"] = pd.DataFrame(staged_results_accumulator)
                        st.success(f"Successfully processed and staged **{len(staged_results_accumulator)}** properties!")
                    else:
                        st.error("No data could be extracted. Please confirm the link strings contain valid IDs.")
                        
        except Exception as csv_error:
            st.error(f"Failed to process the uploaded file format: {csv_error}")
            
    # Staging Workbench Review Interface Area
    if "bulk_staging_dataframe" in st.session_state and not st.session_state["bulk_staging_dataframe"].empty:
        st.markdown("---")
        st.subheader("📋 Temporary Staging Inspection Deck")
        st.caption("You can verify and edit fields directly in this grid before committing them permanently to Supabase.")
        
        staged_df_editor = st.data_editor(
            st.session_state["bulk_staging_dataframe"],
            column_config={
                "url": st.column_config.TextColumn("URL", disabled=True),
                "title": st.column_config.TextColumn("Title", disabled=False),
                "address": st.column_config.TextColumn("Address (Editable)", disabled=False),
                "price": st.column_config.NumberColumn("Base Price (zł)", format="%.2f", disabled=False),
                "area": st.column_config.TextColumn("Area (m²)", disabled=False),
                "rooms": st.column_config.TextColumn("Rooms", disabled=False),
                "floor": st.column_config.TextColumn("Floor", disabled=False),
                "floors": st.column_config.TextColumn("Total Floors", disabled=False),
                "year_built": st.column_config.TextColumn("Year Built", disabled=False),
                "ranking": st.column_config.NumberColumn("Ranking", min_value=0, max_value=1000, step=1),
                "rating": st.column_config.NumberColumn("Rating", min_value=1, max_value=10, step=1),
                "status": st.column_config.SelectboxColumn("Pipeline Track Status", options=STATUS_OPTIONS),
                "garage_cost": st.column_config.NumberColumn("Garage Cost (zł)", format="%.2f"),
                "storage_cost": st.column_config.NumberColumn("Storage Cost (zł)", format="%.2f"),
                "my_notes": st.column_config.TextColumn("My Notes"),
                "description": None # Hide full string columns to save layout width real estate
            },
            use_container_width=True,
            hide_index=True,
            key="bulk_staging_active_grid"
        )
        
        # Save modifications back to session state structure tracking reference
        if st.session_state.get("bulk_staging_active_grid") and st.session_state["bulk_staging_active_grid"]["edited_rows"]:
            for row_idx_str, fields_dict in st.session_state["bulk_staging_active_grid"]["edited_rows"].items():
                row_idx = int(row_idx_str)
                for key, val in fields_dict.items():
                    st.session_state["bulk_staging_dataframe"].iat[row_idx, st.session_state["bulk_staging_dataframe"].columns.get_loc(key)] = val

        # Execution Step 5 Action Panel Trigger
        commit_col1, commit_col2 = st.columns([1, 4])
        with commit_col1:
            if st.button("🚀 Commit All to Database", key="btn_commit_bulk_to_supabase_fleet"):
                with st.spinner("Resolving geo map matches and writing to database table..."):
                    now_iso = datetime.utcnow().isoformat() + "Z"
                    success_write_count = 0
                    
                    for _, row in st.session_state["bulk_staging_dataframe"].iterrows():
                        try:
                            # Historical versioning cleanups
                            existing_check = supabase.table("properties")\
                                .select("id")\
                                .eq("url", row["url"])\
                                .eq("is_current", True)\
                                .execute()
                            
                            if existing_check.data:
                                old_record_id = existing_check.data[0]["id"]
                                supabase.table("properties")\
                                    .update({"is_current": False, "valid_to": now_iso})\
                                    .eq("id", old_record_id)\
                                    .execute()
                            
                            # Geolocation evaluation loop on the fly
                            lat, lon = get_coordinates(row["address"])
                            
                            payload = {
                                "url": row["url"],
                                "title": row["title"],
                                "address": row["address"],
                                "price": float(row["price"]),
                                "area": str(row["area"]),
                                "rooms": str(row["rooms"]),
                                "floor": str(row["floor"]),
                                "floors": str(row["floors"]),
                                "year_built": str(row["year_built"]),
                                "garage_cost": float(row["garage_cost"]),
                                "storage_cost": float(row["storage_cost"]),
                                "my_notes": str(row["my_notes"]),
                                "rating": int(row["rating"]),
                                "ranking": int(row["ranking"]),
                                "status": str(row["status"]),
                                "valid_from": now_iso,
                                "is_current": True,
                                "latitude": lat,
                                "longitude": lon
                            }
                            
                            supabase.table("properties").insert(payload).execute()
                            success_write_count += 1
                        except Exception as write_err:
                            st.error(f"Failed to log entry row {row['title'][:20]}: {write_err}")
                            
                    st.success(f"Successfully integrated **{success_write_count}** new entries into your system portfolio!")
                    del st.session_state["bulk_staging_dataframe"]
                    time.sleep(1)
                    st.rerun()
                    
        with commit_col2:
            if st.button("🗑️ Clear Staging Table", key="btn_clear_bulk_staging"):
                del st.session_state["bulk_staging_dataframe"]
                st.rerun()