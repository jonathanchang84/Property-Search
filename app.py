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
from datetime import datetime

# --- INITIALIZE DATABASE CONNECTION ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 1. SPECIFIC SPECIFICATION BLUEPRINT FOR GEMINI EXTRACTION
class PropertyDetails(BaseModel):
    title: str = Field(description="The main headline or title of the property listing")
    address: str = Field(description="The full physical address of the property, including city and country if available")
    price: str = Field(description="The listed price, including the currency symbol")
    area: str = Field(description="The total area/surface size of the property in square meters (m²)")
    rooms: str = Field(description="The number of rooms in the property")
    floor: str = Field(description="The floor level of the property, e.g., '1st floor', 'Ground floor', 'Top floor'")
    year_built: str = Field(description="The year the building/property was constructed. Use 'Unknown' if missing.")
    description: str = Field(description="A brief summary of key features or selling points from the listing text.")

# 2. INTELLIGENT SCRAPER TARGETING METADATA ATTRIBUTES
def intelligent_scraper(url: str):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=10)
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Isolate element structures containing 'data-sentry-element' attributes
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

# 3. PRODUCTION CLOUD GEOCODING ENGINE
def get_coordinates(address_string: str):
    try:
        # Running live on Linux cloud containers bypasses local operating system certificate issues natively
        geolocator = Nominatim(user_agent="property_tracker_hub_live_production")
        location = geolocator.geocode(address_string, timeout=10)
        if location:
            return location.latitude, location.longitude
        return None, None
    except Exception as e:
        st.warning(f"Geocoding note: Address coordinates could not be computed on this version. ({e})")
        return None, None

# --- STREAMLIT USER INTERFACE CONFIGURATION ---
st.set_page_config(layout="wide")
st.title("🏡 Property Evaluation & History Tracker")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Step 1: Parse Listing URL")
    default_url = "https://www.otodom.pl/pl/oferta/2m-narozny-taras-komorka-lok-miejsca-post-tylko-u-nas-ID4ByvR"
    target_url = st.text_input("Property URL Link:", value=default_url)
    
    if st.button("Analyze with Intelligent Parsing"):
        if target_url:
            with st.spinner("Scanning webpage metadata elements and calculating geographic point placement..."):
                extracted = intelligent_scraper(target_url)
                if extracted:
                    # Capture exact latitude and longitude live
                    lat, lon = get_coordinates(extracted.address)
                    
                    st.session_state["scraped_cache"] = {
                        "url": target_url,
                        "title": extracted.title,
                        "address": extracted.address,
                        "price": extracted.price,
                        "area": extracted.area,
                        "rooms": extracted.rooms,
                        "floor": extracted.floor,
                        "year_built": extracted.year_built,
                        "description": extracted.description,
                        "latitude": lat,
                        "longitude": lon
                    }
                    st.success("Web metadata extraction and geocoding complete!")
        else:
            st.warning("Please input a valid listing link.")

    if "scraped_cache" in st.session_state:
        cache = st.session_state["scraped_cache"]
        st.markdown("---")
        st.subheader("Step 2: Self-Input & Data Enrichment")
        
        # --- LOCKED EXTRACTED PARAMETERS (READ-ONLY) ---
        st.text_input("Listing Title (Read-Only):", value=cache["title"], disabled=True)
        st.text_input("Listing Price (Read-Only):", value=cache["price"], disabled=True)
        st.text_input("Listing Address (Read-Only):", value=cache["address"], disabled=True)
        
        metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
        with metric_col1:
            st.text_input("Area (m²):", value=cache["area"], disabled=True)
        with metric_col2:
            st.text_input("Rooms:", value=cache["rooms"], disabled=True)
        with metric_col3:
            st.text_input("Floor:", value=cache["floor"], disabled=True)
        with metric_col4:
            st.text_input("Year Built:", value=cache["year_built"], disabled=True)
        
        # --- EDITABLE CUSTOM USER INPUT FIELDS ---
        st.markdown("### Your Custom Input Evaluation Metrics")
        user_notes = st.text_area("Your Comments Field (Personal Evaluation Notes):", placeholder="e.g., Close to Popowicki Park, great layout.")
        user_rating = st.slider("Your Personal Property Rating (Out of 10):", min_value=1, max_value=10, value=5)
        current_status = st.selectbox("Pipeline Track Status:", ["Interested", "Viewing Arranged", "Offer Submitted", "Archived"])
        
        if st.button("Commit This Record Version to Database"):
            now_iso = datetime.utcnow().isoformat() + "Z"
            
            try:
                # --- SCD TYPE 2 VERSION MANAGEMENT LOGIC ---
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
                    "price": cache["price"],
                    "area": cache["area"],
                    "rooms": cache["rooms"],
                    "floor": cache["floor"],
                    "year_built": cache["year_built"],
                    "my_notes": user_notes,
                    "rating": user_rating,
                    "status": current_status,
                    "valid_from": now_iso,
                    "is_current": True,
                    "latitude": cache["latitude"],  # Commit coordinates to DB
                    "longitude": cache["longitude"]
                }
                
                supabase.table("properties").insert(property_payload).execute()
                st.success("Successfully logged property entry version parameters!")
                del st.session_state["scraped_cache"]
                st.rerun()
                
            except Exception as database_error:
                st.error(f"Failed to log entry into database table: {database_error}")

with col2:
    st.subheader("Tracking Ledger Grid & Interactive Location Map")
    
    try:
        db_query = supabase.table("properties").select("*").execute()
        properties_list = db_query.data
    except Exception as query_error:
        st.error(f"Could not reach database table connection: {query_error}")
        properties_list = []

    if properties_list:
        df_all = pd.DataFrame(properties_list)
        df_current = df_all[df_all["is_current"] == True]
        
        # --- RE-INTEGRATED INTERACTIVE MAP VISUALIZATION ---
        st.write("### Active Property Pins")
        if "latitude" in df_current.columns and "longitude" in df_current.columns:
            df_map_pins = df_current.dropna(subset=['latitude', 'longitude'])
            if not df_map_pins.empty:
                st.map(df_map_pins[['latitude', 'longitude']], zoom=12)
            else:
                st.info("No active properties contain valid positioning coordinates yet.")
        else:
            st.info("Map indexing columns are initializing across data fields.")
            
        st.markdown("---")
        st.write("### Active Current Track Records Index")
        if not df_current.empty:
            display_columns = ["rating", "title", "price", "status", "my_notes", "area", "rooms", "floor", "year_built", "address"]
            existing_cols = [c for c in display_columns if c in df_current.columns]
            st.dataframe(df_current[existing_cols].sort_values(by="rating", ascending=False), use_container_width=True)
            
        st.markdown("---")
        st.write("### Complete Audit Timeline (SCD Type 2 History)")
        df_sorted = df_all.sort_values(by=["url", "valid_from"], ascending=[True, False])
        st.dataframe(df_sorted[["url", "price", "status", "rating", "my_notes", "is_current", "valid_from"]], use_container_width=True)
    else:
        st.info("No records present in your tracking ledger index yet.")