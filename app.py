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
    floor: str = Field(description="The floor level of the property, e.g., '1st floor', 'Ground floor', 'Top floor'")
    year_built: str = Field(description="The year the building/property was constructed. Use 'Unknown' if missing.")
    description: str = Field(description="A brief summary of key features or selling points from the listing text.")

# HELPER: Robust Monetary Extraction Engine
def clean_monetary_value(value_str: str) -> float:
    if not value_str:
        return 0.0
    # Strip everything except numbers, periods, and commas
    cleaned = re.sub(r'[^\d.,]', '', value_str)
    if not cleaned:
        return 0.0
    # Handle European comma decimals if present, otherwise treat as thousands separator
    if ',' in cleaned and '.' in cleaned:
        cleaned = cleaned.replace(',', '')
    elif ',' in cleaned:
        parts = cleaned.split(',')
        if len(parts[-1]) == 2:  # looks like cents/grosze
            cleaned = cleaned.replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')
    try:
        return float(cleaned)
    except ValueError:
        return 0.0

# 2. INTELLIGENT SCRAPER TARGETING METADATA ATTRIBUTES
def intelligent_scraper(url: str):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=10)
        
        soup = BeautifulSoup(response.text, "html.parser")
        targeted_elements = soup.find_all(lambda tag: tag.has_attr('data-sentry-element'))
        
        extracted_chunks = []
        for element in targeted_elements:
            element_type = element['data-sentry-element']
            element_text = element.get_text(strip=True)
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
        
        models_to_try = ['gemini-2.5-flash', 'gemini-2.5-flash-lite']
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
                if model_name == 'gemini-2.5-flash':
                    st.warning("Gemini 2.5 Flash is busy. Rerouting to backup processing channels...")
                    time.sleep(1) 
                    continue
                else:
                    raise model_error
                    
        if ai_response:
            return ai_response.parsed
        return None
        
    except Exception as e:
        st.error(f"Gemini API Error: {e}")
        return None

# 3. ROBUST HYPER-RESILIENT GEOCODING LAYERED ENGINE
def get_coordinates(address_string: str):
    geolocator = Nominatim(user_agent="property_tracker_hub_live_production_v14")
    address_string = address_string.strip("'\" []")
    
    # Extract structural chunks safely
    parts = [p.strip() for p in address_string.split(",")] if "," in address_string else [address_string]
    street_candidate = parts[0]
    
    # Deduce the city anchor
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

    # Clean the street name variable by removing explicit words like "ulica" if duplicated
    clean_street = re.sub(r'^(ul\.|ulica|os\.|osiedle)\s+', '', street_candidate, flags=re.IGNORECASE)

    # =========================================================================
    # STRATEGY 1: Strict Structured Query (with 'ul.' prefix forced)
    # =========================================================================
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

    # =========================================================================
    # STRATEGY 2: Broad Structured Query (raw street name without prefixes)
    # =========================================================================
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

    # =========================================================================
    # STRATEGY 3: Cleaned Flat String Fallback (strips intermediate district noise)
    # =========================================================================
    try:
        flat_string_fallback = f"ul. {clean_street}, {city_candidate}, Poland"
        location = geolocator.geocode(flat_string_fallback, timeout=10)
        if location:
            return float(location.latitude), float(location.longitude)
    except Exception:
        pass
        
    return None, None

# --- STREAMLIT PAGE SETUP ---
st.set_page_config(layout="wide", page_title="Property Evaluation Hub")
st.title("🏡 Property Hub Tracker Workspace")

tab_scraped, tab_map_view = st.tabs(["📊 Parser & Evaluator", "🗺️ Portfolio Map Explorer"])

# =========================================================================
# PAGE WORKSPACE 1: PARSER & EVALUATOR
# =========================================================================
with tab_scraped:
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Step 1: Parse Listing URL")
        default_url = "https://www.otodom.pl/pl/oferta/2m-narozny-taras-komorka-lok-miejsca-post-tylko-u-nas-ID4ByvR"
        target_url = st.text_input("Property URL Link:", value=default_url, key="input_target_url")
        
        if st.button("Analyze with Intelligent Parsing", key="btn_run_scraper"):
            if target_url:
                with st.spinner("Scanning webpage metadata elements..."):
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
            
            # --- CONVERTED TO INTERACTIVE MONETARY NUMBER INPUT FIELD ---
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

            # --- MAP COORDINATE INSPECTION BANNER ---
            if cache["latitude"] and cache["longitude"]:
                st.success(f"✅ Map Match Found! Coordinates resolved to: {cache['latitude']}, {cache['longitude']}")
            else:
                st.error("❌ Geocoding Failed! Try cleaning up the text block to just: 'ul. Popowicka, Wrocław'")
            
            metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
            with metric_col1:
                st.text_input("Area (m²):", value=cache["area"], disabled=True, key="field_area")
            with metric_col2:
                st.text_input("Rooms:", value=cache["rooms"], disabled=True, key="field_rooms")
            with metric_col3:
                st.text_input("Floor:", value=cache["floor"], disabled=True, key="field_floor")
            with metric_col4:
                st.text_input("Year Built:", value=cache["year_built"], disabled=True, key="field_year")
            
            # --- MONETARY AMENDMENT VALUE FIELDS ---
            st.markdown("### 💰 Additional Transaction Outlays (Numeric Polish Złoty)")
            cost_col1, cost_col2 = st.columns(2)
            with cost_col1:
                garage_input = st.number_input("Additional Cost - Garage (zł):", min_value=0.0, value=0.0, step=1000.0, format="%.2f", key="field_garage_numeric")
            with cost_col2:
                storage_input = st.number_input("Additional Cost - Storage (zł):", min_value=0.0, value=0.0, step=500.0, format="%.2f", key="field_storage_numeric")

            st.markdown("### Your Custom Input Evaluation Metrics")
            user_notes = st.text_area("Your Comments Field (Personal Evaluation Notes):", placeholder="e.g., Close to Popowicki Park, great layout.", key="field_notes")
            user_rating = st.slider("Your Personal Property Rating (Out of 10):", min_value=1, max_value=10, value=5, key="field_rating")
            current_status = st.selectbox("Pipeline Track Status:", ["Interested", "Viewing Arranged", "Offer Submitted", "Archived"], key="field_status")
            
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
                        "price": price_input,           # Pushing clean numerical float to DB
                        "area": cache["area"],
                        "rooms": cache["rooms"],
                        "floor": cache["floor"],
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
    st.subheader("Active Current Track Records Index")
    try:
        db_query = supabase.table("properties").select("*").execute()
        properties_list = db_query.data
    except Exception:
        properties_list = []

    if properties_list:
        df_all = pd.DataFrame(properties_list)
        df_current = df_all[df_all["is_current"] == True].copy()
        
        if not df_current.empty:
            df_current["price"] = pd.to_numeric(df_current["price"], errors='coerce').fillna(0.0)
            df_current["garage_cost"] = pd.to_numeric(df_current["garage_cost"], errors='coerce').fillna(0.0)
            df_current["storage_cost"] = pd.to_numeric(df_current["storage_cost"], errors='coerce').fillna(0.0)
            df_current["Total Outlay"] = df_current["price"] + df_current["garage_cost"] + df_current["storage_cost"]
            
            display_columns = ["rating", "title", "price", "garage_cost", "storage_cost", "Total Outlay", "status", "my_notes", "area", "rooms", "floor", "address"]
            existing_cols = [c for c in display_columns if c in df_current.columns]
            
            st.dataframe(
                df_current[existing_cols].sort_values(by="rating", ascending=False),
                column_config={
                    "price": st.column_config.NumberColumn("Base Price", format="%.2f zł"),
                    "garage_cost": st.column_config.NumberColumn("Garage Cost", format="%.2f zł"),
                    "storage_cost": st.column_config.NumberColumn("Storage Cost", format="%.2f zł"),
                    "Total Outlay": st.column_config.NumberColumn("Total Budget Outlay", format="%.2f zł"),
                },
                use_container_width=True
            )
            
        st.markdown("---")
        st.write("### Complete Audit Timeline (SCD Type 2 History)")
        df_sorted = df_all.sort_values(by=["url", "valid_from"], ascending=[True, False]).copy()
        df_sorted["price"] = pd.to_numeric(df_sorted["price"], errors='coerce').fillna(0.0)
        st.dataframe(
            df_sorted[["url", "price", "status", "rating", "my_notes", "is_current", "valid_from"]],
            column_config={"price": st.column_config.NumberColumn("Price Level History", format="%.2f zł")},
            use_container_width=True
        )
    else:
        st.info("No records present in your tracking ledger index yet.")

# =========================================================================
# PAGE WORKSPACE 2: PORTFOLIO MAP EXPLORER
# =========================================================================
with tab_map_view:
    st.subheader("🗺️ Global Saved Portfolio Location Tracker")
    
    try:
        db_query_map = supabase.table("properties").select("*").execute()
        map_properties = db_query_map.data
    except Exception:
        map_properties = []

    wroclaw_center_view = [51.1079, 17.0385]
    folium_explorer_map = folium.Map(location=wroclaw_center_view, zoom_start=12, control_scale=True)
    
    marker_group = folium.FeatureGroup(name="Properties")
    saved_pins_count = 0
    
    if map_properties:
        df_map_all = pd.DataFrame(map_properties)
        df_map_current = df_map_all[df_map_all["is_current"] == True].copy()
        
        if "latitude" in df_map_current.columns and "longitude" in df_map_current.columns:
            df_map_current["latitude"] = pd.to_numeric(df_map_current["latitude"], errors='coerce')
            df_map_current["longitude"] = pd.to_numeric(df_map_current["longitude"], errors='coerce')
            df_pins_to_render = df_map_current.dropna(subset=['latitude', 'longitude'])
            
            for _, row in df_pins_to_render.iterrows():
                try:
                    lat_coord = float(row['latitude'])
                    lon_coord = float(row['longitude'])
                    
                    p_base = float(row['price']) if row['price'] else 0.0
                    p_gar = float(row['garage_cost']) if row['garage_cost'] else 0.0
                    p_stor = float(row['storage_cost']) if row['storage_cost'] else 0.0
                    p_total = p_base + p_gar + p_stor
                    
                    html_popup_markup = f"""
                    <div style='font-family: Arial, sans-serif; min-width: 220px;'>
                        <h4 style='margin:0 0 5px 0; color:#1f77b4;'>{row['title']}</h4>
                        <b>Base Price:</b> {p_base:,.2f} zł<br>
                        <b>Garage space:</b> {p_gar:,.2f} zł<br>
                        <b>Storage Unit:</b> {p_stor:,.2f} zł<br>
                        <hr style='margin: 4px 0;'>
                        <b>Total Budget Outlay:</b> <span style='color:#d9534f; font-weight:bold;'>{p_total:,.2f} zł</span><br>
                        <b>Rating Score:</b> ⭐ {row['rating']}/10<br>
                        <b>Pipeline Status:</b> <span style='color:green; font-weight:bold;'>{row['status']}</span><br>
                        <b>Personal Notes:</b> <i>{row['my_notes']}</i>
                    </div>
                    """
                    
                    folium.Marker(
                        location=[lat_coord, lon_coord],
                        popup=folium.Popup(html_popup_markup, max_width=350),
                        icon=folium.Icon(color="red" if row['rating'] >= 8 else "blue", icon="home")
                    ).add_to(marker_group)
                    
                    saved_pins_count += 1
                except Exception:
                    continue

    marker_group.add_to(folium_explorer_map)

    st_folium(folium_explorer_map, use_container_width=True, height=550, key=f"fullscreen_map_pins_{saved_pins_count}")
    st.caption(f"Showing **{saved_pins_count}** active property pin points dropping into database coordinates tracking indexes.")

    if map_properties:
        st.markdown("---")
        st.subheader("📋 Explorer Quick-Reference Index")
        df_map_all = pd.DataFrame(map_properties)
        df_map_current = df_map_all[df_map_all["is_current"] == True].copy()
        
        df_map_current["price"] = pd.to_numeric(df_map_current["price"], errors='coerce').fillna(0.0)
        df_map_current["garage_cost"] = pd.to_numeric(df_map_current["garage_cost"], errors='coerce').fillna(0.0)
        df_map_current["storage_cost"] = pd.to_numeric(df_map_current["storage_cost"], errors='coerce').fillna(0.0)
        df_map_current["Total Outlay"] = df_map_current["price"] + df_map_current["garage_cost"] + df_map_current["storage_cost"]

        display_columns_map = ["rating", "status", "price", "garage_cost", "storage_cost", "Total Outlay", "title", "my_notes", "area", "address"]
        existing_cols_map = [c for c in display_columns_map if c in df_map_current.columns]
        st.dataframe(
            df_map_current[existing_cols_map].sort_values(by="rating", ascending=False),
            column_config={
                "price": st.column_config.NumberColumn("Base Price", format="%.2f zł"),
                "garage_cost": st.column_config.NumberColumn("Garage Cost", format="%.2f zł"),
                "storage_cost": st.column_config.NumberColumn("Storage Cost", format="%.2f zł"),
                "Total Outlay": st.column_config.NumberColumn("Total Budget Outlay", format="%.2f zł"),
            },
            use_container_width=True
        )