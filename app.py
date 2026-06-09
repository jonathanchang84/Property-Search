import streamlit as st
import requests
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from geopy.geocoders import Nominatim
import pandas as pd
import time

# 1. TELL GEMINI EXACTLY WHAT DATA WE WANT
class PropertyDetails(BaseModel):
    title: str = Field(description="The main headline or title of the property listing")
    address: str = Field(description="The full physical address of the property, including city and country if available")
    price: str = Field(description="The listed price, including the currency symbol")
    description: str = Field(description="A brief summary of key features like bedrooms, bathrooms, garden, etc.")

# 2. CREATE THE INTELLIGENT SCRAPER FUNCTION
def intelligent_scraper(url: str):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=10)
        
        soup = BeautifulSoup(response.text, "html.parser")
        page_text = soup.get_text(separator="\n", strip=True)
        clean_text = page_text[:8000] 
        
    except Exception as e:
        st.error(f"Failed to read the website: {e}")
        return None

    try:
        client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
        
        prompt = f"""
        You are an expert real estate assistant. Carefully read the following raw text pulled 
        from a property listing website. Extract the key details perfectly.
        
        Website Content:
        {clean_text}
        """
        
        ai_response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=PropertyDetails,
                temperature=0.1
            ),
        )
        return ai_response.parsed
        
    except Exception as e:
        st.error(f"Gemini API Error: {e}")
        return None

# 3. CREATE THE GEOCODING FUNCTION (Address -> Coordinates)
def get_coordinates(address_string: str):
    try:
        # Initialize the free OpenStreetMap locator service
        # 'user_agent' can be any unique name for your application identity
        geolocator = Nominatim(user_agent="property_tracker_hub_app")
        
        # Ask the service to find the address
        location = geolocator.geocode(address_string, timeout=10)
        
        if location:
            return location.latitude, location.longitude
        else:
            return None, None
            
    except Exception as e:
        st.warning(f"Geocoding notice: Could not convert address to coordinates automatically. ({e})")
        return None, None

# 4. STREAMLIT INTERFACE
st.set_page_config(layout="wide") # Switches the app layout to use the full screen width
st.title("🏡 Property Tracker Hub - Mapping Module")

# Using columns to create a clean, side-by-side layout
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Extract New Property")
    # Pre-fill with your example URL for easier initial testing
    default_url = "https://www.otodom.pl/pl/oferta/2m-narozny-taras-komorka-lok-miejsca-post-tylko-u-nas-ID4ByvR"
    target_url = st.text_input("Property URL:", value=default_url)
    
    if st.button("Process & Pin Property"):
        if target_url:
            with st.spinner("1. Gemini is extracting listing data..."):
                extracted_data = intelligent_scraper(target_url)
                
            if extracted_data:
                st.success("Gemini Data Extracted!")
                st.write(f"**Extracted Title:** {extracted_data.title}")
                st.write(f"**Extracted Price:** {extracted_data.price}")
                st.write(f"**Extracted Address:** {extracted_data.address}")
                
                with st.spinner("2. Locating physical coordinates on map..."):
                    # Give the geocoder an extra pause to be a good internet citizen
                    time.sleep(1) 
                    lat, lon = get_coordinates(extracted_data.address)
                
                if lat and lon:
                    st.success(f"Coordinates found: {lat}, {lon}")
                    
                    # Store data temporarily in a session state so the map on the right can see it
                    st.session_state["temp_property"] = {
                        "title": extracted_data.title,
                        "latitude": lat,
                        "longitude": lon,
                        "price": extracted_data.price
                    }
                else:
                    st.error("Could not find this address on the map. Try standardizing the address format.")
        else:
            st.warning("Please paste a URL link first.")

with col2:
    st.subheader("Live Map Visualization")
    
    # Check if we have successfully found a property location to map
    if "temp_property" in st.session_state:
        prop = st.session_state["temp_property"]
        
        # Streamlit maps require a Pandas DataFrame containing columns named 'latitude' and 'longitude'
        map_data = pd.DataFrame([{
            "latitude": prop["latitude"],
            "longitude": prop["longitude"],
            "name": f"{prop['title']} ({prop['price']})"
        }])
        
        st.write(f"Showing location for: **{prop['title']}**")
        
        # Display the native Streamlit interactive map
        st.map(map_data, zoom=13)
    else:
        st.info("No active property coordinates found yet. Click 'Process & Pin Property' on the left to see it on the map.")