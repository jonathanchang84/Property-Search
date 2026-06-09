import streamlit as st
import requests
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# 1. TELL GEMINI EXACTLY WHAT DATA WE WANT
class PropertyDetails(BaseModel):
    title: str = Field(description="The main headline or title of the property listing")
    address: str = Field(description="The full physical address of the property")
    price: str = Field(description="The listed price, including the currency symbol")
    description: str = Field(description="A brief summary of key features like bedrooms, bathrooms, garden, etc.")

# 2. CREATE THE INTELLIGENT SCRAPER FUNCTION
def intelligent_scraper(url: str):
    # Fetch the webpage data
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get(url, headers=headers, timeout=10)
        
        # If the website blocks regular downloading, we extract the text contents safely
        soup = BeautifulSoup(response.text, "html.parser")
        page_text = soup.get_text(separator="\n", strip=True)
        
        # Limit text length slightly so we don't overwhelm the system with junk code
        clean_text = page_text[:8000] 
        
    except Exception as e:
        st.error(f"Failed to read the website: {e}")
        return None

    # Connect to Gemini using the key inside your secrets.toml file
    try:
        client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
        
        prompt = f"""
        You are an expert real estate assistant. Carefully read the following raw text pulled 
        from a property listing website. Extract the key details perfectly.
        
        Website Content:
        {clean_text}
        """
        
        # Ask Gemini to process the text and format it into our structure
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

# 3. BUILD A SIMPLE BLUEPRINT USER INTERFACE
st.title("🏡 Smart Property Scraper MVP")
st.write("Paste a link to a property listing below to see Gemini extract the information live.")

# Create an entry box for the link
target_url = st.text_input("Property URL:")

if st.button("Extract Details"):
    if target_url:
        with st.spinner("Gemini is reading the page..."):
            extracted_data = intelligent_scraper(target_url)
            
            if extracted_data:
                st.success("Data successfully extracted!")
                
                # Show the neat results on screen
                st.write(f"**Title:** {extracted_data.title}")
                st.write(f"**Address:** {extracted_data.address}")
                st.write(f"**Price:** {extracted_data.price}")
                st.write(f"**Description:** {extracted_data.description}")
    else:
        st.warning("Please paste a valid URL link first.")