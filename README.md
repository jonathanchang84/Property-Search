# Real Estate Analytics & Evaluation Hub

This application serves as a dedicated workspace for real estate investment analysis. The platform automates data extraction from primary property listings, manages a persistent tracking matrix, and provides localized spatial insights.

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

## 3. Architectural Design

The application utilizes a decoupled pattern separating the client execution environment, computational service layers, and the persistent storage backend.



### Components Framework

* **Presentation Layer (Streamlit):** Coordinates state parameters via a wide-mode multi-tab interface. It captures source references, processes manual inputs, handles micro-updates via structured data grids, and projects geographic marker elements.
* **Extraction & Inference Pipeline (BeautifulSoup & Gemini API):** Sanitizes and drops unneeded data layers from raw listing bodies before using Pydantic schema validation structures (`PropertyDetails`) via a generative inference routing loop.
* **Geospatial Processing Hub (GeoPy / Nominatim):** Standardizes local address blocks into specific geographic location pairs (Latitude, Longitude) through sequential structured text processing and recursive city district lookups.
* **Visualization Layer (Folium):** Embeds custom map markers inside the client viewport, color-coded by performance parameters and state filters.
* **Data Persistence Layer (Supabase):** Manages a system of record utilizing timestamped version tracking constraints (`is_current`, `valid_from`, `valid_to`) to secure real-time changes made directly inside the user interface panels.

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
