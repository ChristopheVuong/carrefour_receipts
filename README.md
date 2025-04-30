<<<<<<< HEAD
# carrefour_receipts
Analysis of own Carrefour receipts
=======
<p align="center">
    <a href=""><img src="https://img.shields.io/badge/python-3.7+-aff.svg"></a>
    <a href=""><img src="https://img.shields.io/badge/os-linux%2C%20win%2C%20mac-pink.svg"></a>
</p>

---

## **Carrefour Receipt Analysis Project**  
**Objective**: Extract, structure, and analyze personal Carrefour receipt data to uncover spending patterns and trends.

---

### **1. Project Setup & Requirements**  
- **Define scope** (actionable goals):  
  - Extract receipts (orders, items, loyalty data) from Carrefour’s portal.  
  - Analyze spending trends, category shares, and temporal patterns.  
  - Build a Streamlit dashboard for visualization .  

- **Tech Stack**:  
  - Python 3.8+ (Selenium, Requests, Pandas, PySpark).  
  - Parquet for storage, DuckDB/SQLite for analysis.  
  - Streamlit for visualization.  
- **Dependency management**
  - Create a new conda environment and install dependency (playwright, requests, httpx) with Python 3.10 or Python 3.11.
  - Use Poetry otherwise for this pure Python project.

---


### **2. Authentication**

#### Attempt 1: Bypass Cloudflare & Login
- **Anti-bot measures**:  
  - Find a way around Cloudfare (especially Turnstile).
  - Use `undetected_chromedriver` with Selenium to mask `navigator.webdriver` flags.  Deploy headless browsers with patched TLS fingerprints (e.g., using `selenium-stealth`). See for example https://scrapfly.io/blog/how-to-avoid-web-scraping-blocking-tls/#what-is-tls for TLS fingerprints explanation.
  - Rotate user-agents and mimic human behavior (randomized delays, mouse movements).  
  - Beware HTTP Details Most users browse the internet web pages through a few popular browsers, such as Chrome, Firefox, or Edge. These browsers intercept their configuration. Reproduce: `Accept` (`application/json` when scraping hidden APIs or `text/xml` for sitemaps), `accept-language`, `user-agent` and `cookie`.
  - Leverage Javascript for fingerprinting work (see https://scrapfly.io/blog/how-to-avoid-web-scraping-blocking-javascript/#how-does-browser-fingerprinting-work)


- **Session management**:  
  - Extract cookies post-login from browser-like tools such as Selenium or Playwright if possible.
  - Handle CAPTCHA fallback: Implement manual intervention triggers or 2Captcha integration.
  - Otherwise, log in in a browser (pass Cloudfare Turnstile) and extract them from there using for example the export button in the extension Cookie Editor and reuse them for API calls (minimize re-authentication).
  - Quit driver in order to free unused resources. 

#### Attempt 2: Log in naturally and adapt copy as curl code
One can get around the Cloudfare in-under-attack-mode by selecting 'Copy as cUrl' in the network section under developer tools of any major browser.
This copies all the required cookies so your curl can be 'authenticated'. In that case, the cookies last as long as your Carrefour account session is alive until logging out. One should copy it in a file `cookies.txt`.

The curl must be run on the same IP as you were loading the site with.

### **3. API Scraping**  
- **Rate limiting**:  
  - Use exponential backoff + jitter for failed requests.  
  - Monitor `X-RateLimit` headers (if exposed) to auto-adjust scraping frequency.  
- How to make GET requests?
  - We may use httpx over requests by following the tutorial in https://scrapfly.io/blog/how-to-scrape-hidden-apis/. Cookies are handled differently in browser-like tools and http client library such as `requests` and `httpx`.
  - If we really need to mimic a browser to avoid bot detection, we can use Selenium get method and/or execute Javascript request in order to retrieve JSON content. However Javascript execution may be detected as bot action.
  - The only viable option is to get the API response by `curl` command (actually no rate limit, even no need to pause once logged in). 
  
- **Data structure**:  
  - Parse JSON responses into three tables:  
    1. **Orders**: `order_id, datetime, total_amount, payment_method, discounts`.  
    2. **Items**: `order_id, product_name, quantity, price, category` (enrich via NLP if raw data is unstructured, for example predict the category with feature VAT).  
    3. **Loyalty**: `order_id, points_earned, rewards_used`.  
  - Expose an endpoint (FastAPI) that accesses to that database, and use it to feed a Streamlit app.

---

### **4. Data Storage & Pipelines**  
#### **Database Design**  
- **Storage strategy**:
  - Build a MongoDB database since the API response is in JSON format and can constitute a document database easy to query from with MongoDB. Use of NoSQL in the context of local data (collected from a mobile app or a laptop on a daily or weekly basis).   
  - Partition Parquet files by year/month for efficient querying (e.g., `data/year=2023/month=12/`) and generic export format if JSON is too cumbersome.  
  - Use PySpark for distributed processing if data scales beyond 1M+ rows (only plausible for purchased items). Only about a thousand rows or less for order receipts (use Pandas).    

- **Schema enforcement**:  
  - Validate data types (e.g., `decimal` for amounts, `datetime` for timestamps).  
  - Handle missing values (e.g., default `0` for discounts, payment info).  

#### **Automation & CI/CD**  
- **Pipeline orchestration**:  
  - Script extraction → transformation → storage as a Python module.  
  - Use GitHub Actions to schedule daily/weekly runs (Cron jobs).  

- **Testing**:  
  - Write unit tests for critical functions (e.g., Cloudflare bypass, link validity, HTTPS response, JSON parsing).
  - Use the Playwright Pytest plugin called pytest-playwright to write end-to-end tests.
  - Consider rate limit, log successes / failures.   
  - Validate data integrity with Great Expectations (GX):  
  ```python
  # Expectation suite can be integrated into ETL pipelines
  validator.expect_column_values_to_not_be_null(column="user_id")
  validator.expect_column_values_to_be_between(column="age", min_value=0, max_value=120)
  validator.expect_column_values_to_be_in_set(column="status", value_set=["active", "inactive"])
  ```

---

### **5. Analysis & Visualization**  
#### **Key Metrics**  
- **Temporal trends**:  
  - Rolling averages (3M/6M/yearly) using Pandas window functions.  
  - Year-over-year spending comparisons.  

- **Category insights**:  
  - Bio vs. regular food share (regular expression: `bio`).  
  - Meat vs. plant-based spending ratios.
- **Prices**  
   - Top 10 purchased products and evolutions of their prices
   - Evolutions of prices of main vegetables
   - Meat prices
   - 
- **Quantity**
   - How many kilograms of vegetables and fruits in average?
   - How many items in average, per month?
   - How many liquid detergent containers per year? How many liters?

#### **Streamlit App**  
- **Features**:  
  - Interactive filters (year/month/category).  
  - Drill-down charts (Altair/Vega-Lite for time series and bar charts).  
  - Caching (`@st.cache_data`) for large datasets.  

- **Deployment**:  
  - Dockerize the app for portability.  
  - Host on AWS EC2 or Streamlit Cloud.  

---

### **5. Risk Mitigation**  
- **Compliance**:  
  - Anonymize personal data (e.g., hash `order_id`).  
  - Adhere to Carrefour’s `robots.txt` and terms of service.  

- **Monitoring**:  
  - Log errors (e.g., failed scrapes, schema mismatches) with `structlog`.  
  - Data drift: either feature drift (inflation effect) or concept drift (Covid)
  - Alert on pipeline failures (e.g., Slack/Email notifications).  

---

### **6. Future Enhancements**  
- **Advanced NLP**: Use spaCy to categorize unstructured product names.  
- **Real-time dashboards**: Integrate Kafka for live data streaming.  
- **Cost optimization**: Migrate to AWS Glue/S3 for scalable storage if handling several loyalty cards.  

---


## Resources

### Scraping

- https://medium.com/@anisa.maharani/scraping-with-python-requests-aca585c17263
- https://www.zenrows.com/blog/bypass-cloudflare#how-cloudflare-detects-bots
- https://stackoverflow.com/questions/68289474/selenium-headless-how-to-bypass-cloudflare-detection-using-selenium

- https://www.zenrows.com/blog/bypass-cloudflare#fortified-headless-browsers
- https://scrapfly.io/blog/how-to-bypass-cloudflare-anti-scraping/
- https://www.zenrows.com/blog/curl-bypass-cloudflare#using-cookies

### Captcha

- https://deathbycaptcha.com/api/turnstile
- https://habr.com/en/articles/893086/
- https://medium.com/@data-surge/playwright-bypass-captcha-2478aa116583

### Hidden API

- https://scrapfly.io/blog/how-to-scrape-hidden-apis/
- https://github.com/ZFC-Digital/cf-clearance-scraper

### OAuth 2.0

- https://success.outsystems.com/documentation/11/integration_with_external_systems/rest/consume_rest_apis/

### Analytics

- https://blog.bruggen.com/2019/11/part-24-playing-with-carrefour-shopping.html
>>>>>>> c81defa (extraction pipeline receipts and pymongo)
