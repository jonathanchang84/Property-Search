# Property Evaluation Hub

This application is a real-time property pipeline tracking and metadata ingestion platform designed to parse, aggregate, and monitor real estate listings from Otodom. It integrates advanced metadata extraction via large language models, structured geocoding pipelines, and automated availability synchronization.

---

## Features

### 📊 Parser & Evaluator
* **Intelligent Metadata Ingestion:** Extracted structural element tags from active listing URLs are analyzed to populate core property attributes (e.g., price, area, room count, floor details, construction year).
* **Automated Revival Detection:** If a listing previously marked as "No Longer Available" is rescanned and the deactivation banner is no longer present on the webpage, this application automatically resets its operational status back to "Interested."
* **Data Enrichment:** Financial tracking layers support inputting auxiliary transaction outlays such as individual garage or storage space costs to evaluate a true total budget requirement.

### 🗺️ Portfolio Map Explorer
* **Geocoded Map Layer:** Validated properties are resolved into latitude and longitude coordinates via an integrated geocoding lookup engine and mapped as spatial data points. Map markers dynamically update color schemes based on performance ratings and track status indicators.
* **Pipeline Maintenance Tools:** An automated integrity console scans active database rows to look for explicit listing deactivation signatures (`<span class="css-5ujp2z etuedte2">To ogłoszenie jest już niedostępne</span>`).
  * **Two-Way Status Synchronization:** Properties that have been pulled from the market are transitioned to **"No Longer Available"**. Properties that return to the market have their tracking status resurrected back to **"Interested"**.
* **Inline Data Grid Editing:** Interactive data grids support immediate modifications to property criteria, metrics, personal notes, and status fields with immediate database write-backs.

### 📥 Bulk Parser
* **Batch Processing Fleet:** Supports concurrent processing of multiple asset listing links uploaded via a CSV file source or pasted directly into a batch input queue.
* **Staging Inspection Deck:** Extracted rows are routed into an intermediate staging grid where parameter variations can be adjusted, audited, or pruned prior to database commitment.

---

## Technical Architecture

* **Frontend Framework:** Streamlit
* **Database Layer:** Supabase (PostgreSQL engine tracking temporal versioning via `is_current`, `valid_from`, and `valid_to` horizons)
* **Parsing Engine:** BeautifulSoup4 (HTML structural hunting) and Google GenAI API (`gemini-2.5-flash` with fallback to `gemini-2.0-flash` utilizing structured Pydantic schema generation)
* **Geospatial Processing:** Geopy (Nominatim location resolution with structured district fallback logic)

---

## Database Configuration Requirements

This application expects a `properties` table structure configured in Supabase. The required schema fields include:

| Field Name | Data Type | Description |
| :--- | :--- | :--- |
| `id` | BigInt / UUID | Primary Key |
| `url` | Text | Unique source listing link |
| `title` | Text | Captured headline text |
| `address` | Text | Resolved location identifier |
| `price` | Numeric | Base listing currency valuation |
| `area` | Text / Numeric | Property size in square meters |
| `rooms` | Text | Total room count |
| `floor` | Text | Level placement |
| `floors` | Text | Total structure height |
| `year_built` | Text | Construction timeframe |
| `garage_cost` | Numeric | Supplementary parking cost |
| `storage_cost` | Numeric | Supplementary storage unit cost |
| `my_notes` | Text | Narrative evaluation logs |
| `rating` | Integer | Scaled score indicator (1–10) |
| `ranking` | Integer | Absolute priority pipeline sorting index |
| `status` | Text | Context state (`Interested`, `No Longer Available`, etc.) |
| `latitude` | Float | Resolved map coordinate |
| `longitude` | Float | Resolved map coordinate |
| `is_current` | Boolean | Active tracking version flag |
| `valid_from` | Timestamp | Record creation marker |
| `valid_to` | Timestamp | Deprecation marker for audit history tracking |
---

## 1. Initial Scope

The core objective is to centralize and standardize unstructured real estate listings into an actionable investment dashboard.

### Core Deliverables
* **Intelligent Scraping Pipeline:** Automated raw data structure harvesting targeting DOM containers from major listings platform endpoints.
* **Semantic Parameter Extraction:** Integration with large language models via structured schema compliance blueprints to map unstructured text content into uniform property definitions.
* **Geocoding Resolution Engine:** Multi-tiered address translation using spatial dictionary definitions to look up and apply geospatial coordinates.
* **Dynamic Visualization Interface:** A central portfolio exploration view containing synchronized data tables, localized spatial tracking points, and granular condition-filtering consoles.
* **Persistent State Synchronization:** Complete version ledger entries managed via a relational database backend.

---



## 2. Operational Mechanics

The application functions across two isolated execution scopes that communicate via a central remote data table.

### Workspace A: Parser & Evaluator Engine
[Listing URL] -> [BeautifulSoup Scraper] -> [Gemini API Extraction] -> [Enrichment Engine] -> [Supabase DB]

1. **Target Capture:** The workspace accepts a primary listing URL asset inside the collection window.
2. **Metadata Scraping:** A document request fetches HTML content, parsing target markers to capture specific location segments.
3. **Structured Mapping:** The text payload is dispatched via API alongside a strict JSON formatting model. This transforms unstructured text blocks into clean parameter categories: base price, total area size, rooms count, building construction year, and floor metrics.
4. **Enrichment and Local Storage:** Numerical engines sanitize numeric currencies and calculate real-time ratios like cost per square meter. Manual modifiers are applied for additional transaction parameters (garage, storage costs, individual evaluations, and pipeline workflow tracking updates).
5. **Database Entry Creation:** Saving a property deactivates older reference rows for that URL and registers a new active database row with updated tracking dates.

### Workspace B: Portfolio Map Explorer

[Supabase Active Records] -> [5-Stage Filter Console] -> [Interactive Folium Map] -> [Editable Data Grid] -> [Auto-Sync to DB]

1. **Dynamic Pipeline Pull:** The mapping panel runs a global database query fetching all active records (`is_current = true`).
2. **Multi-Parameter Filtering Matrix:** The workspace feeds the pulled dataset through a five-stage console to refine records live across multiple dimensions:
   * **Pipeline Status:** Isolates active leads from archived historical logs.
   * **Text Content Search:** Scans text substrings inside title strings, property location descriptions, or saved evaluation commentary blocks.
   * **Total Budget Range:** Screens assets using total transaction outlays (Base Price + Outlays).
   * **Priority & Preference Scales:** Filters rows using dual numeric slider configurations matching custom-assigned Rankings and performance Ratings.
3. **Map Visualization and Updates:** Valid rows render directly as geometric points using interactive, color-coded map markers.
4. **Two-Way Table Updates:** Modifying cells directly within the data index triggers immediate background updates to the database table, refreshing the view automatically.

---



## 3. Architectural Design

The application utilizes a decoupled pattern separating the client execution environment, computational service layers, and the persistent storage backend.



### Components Framework

* **Presentation Layer (Streamlit):** Coordinates state parameters via a wide-mode multi-tab interface. It captures source references, processes manual inputs, handles micro-updates via structured data grids, and projects geographic marker elements.
* **Extraction & Inference Pipeline (BeautifulSoup & Gemini API):** Sanitizes and drops unneeded data layers from raw listing bodies before using Pydantic schema validation structures (`PropertyDetails`) via a generative inference routing loop.
* **Geospatial Processing Hub (GeoPy / Nominatim):** Standardizes local address blocks into specific geographic location pairs (Latitude, Longitude) through sequential structured text processing and recursive city district lookups.
* **Visualization Layer (Folium):** Embeds custom map markers inside the client viewport, color-coded by performance parameters and state filters.
* **Data Persistence Layer (Supabase):** Manages a system of record utilizing timestamped version tracking constraints (`is_current`, `valid_from`, `valid_to`) to secure real-time changes made directly inside the user interface panels.
* * **Parsing Engine:** BeautifulSoup4 (HTML structural hunting) and Google GenAI API (`gemini-2.5-flash` with fallback to `gemini-2.0-flash` utilizing structured Pydantic schema generation)

### System Topology

```text
+-------------------------------------------------------------+
|                     STREAMLIT FRONTEND                      |
|  +--------------------------+  +--------------------------+  |
|  |    Parser & Evaluator    |  |  Portfolio Map Explorer  |  |
|  +--------------------------+  +--------------------------+  |
+------------------------------+------------------------------+
                               |
                 HTTP / Web API JSON Interactions
                               |
                               v
+-------------------------------------------------------------+
|                    COMPUTATIONAL SERVICES                   |
|   +------------------+  +------------------+  +----------+  |
|   |  BeautifulSoup   |  |    Gemini API    |  |  GeoPy   |  |
|   | (DOM Harvesting) |  | (Structured JSON)|  | (Geo-up) |  |
|   +------------------+  +------------------+  +----------+  |
+------------------------------+------------------------------+
                               |
                   Secure Connection Protocol
                               |
                               v
+-------------------------------------------------------------+
|                     PERSISTENT STORAGE                      |
|   +-----------------------------------------------------+   |
|   |                  Supabase Database                  |   |
|   |          (Property Records Storage Engine)          |   |
|   +-----------------------------------------------------+   |
+-------------------------------------------------------------+
---
