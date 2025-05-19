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

KPIs:
- monitor the true savings by engaging in the loyalty strategy
- reduce waste by controlling the purchase food quantity
- analyze food consumption to notice shifts over the years
- see the impact of Covid on our consumption
- analysis of how frequent we go to the mall
- what is my average basket?
- see the impact of Carrefour incentive to buy (using promotions discounts)
- have a share of spending by categories.
- monitor the frequencies of discounts.
- monitor pipelines efficiency in terms of query execution, and resilience in terms of ease of adjustment in case of update of the API.


---

### **1. Project Setup & Requirements**  
- **Define scope** (actionable goals):  
  - Extract receipts (orders, items, loyalty data) from Carrefour’s portal as documents.
  - Extract Drive orders from Carrefour's portal as documents.
  - Implement a consistent, sustainable extraction process in order to feed on a regular basis a MongoDB database consisting of JSON files with receipt or order details (not necessarily aligned using union operator and project operator).  
  - Analyze spending trends (rolling averages, top products), category shares (share of food spending), and temporal patterns (price evolutions of essential items) with advanced tools like Pandas.
  - Produce refined extracts with fine-grained queries in Pandas. 
  - Create a chain of Python or Bash scripts that automate the process of scraping and feeding the MongoDB database in a consistent way (appropriate error logging and caution on database-related transactions) 
  - Build a Streamlit dashboard for visualization and API endpoint then continuous integration with Dockerhub.  

- **Tech Stack**:  
  - Python 3.10+ but Python 3.8+ should be enough.  
  - JSON for storage by default (API endpoint), MongoDB for database and querying and Pandas for analysis. 
  - Matplotlib and maybe PowerBI for visualization, Streamlit for interactive display.  
- **Dependency management**
  The project does not need special packages for its main functionality that is based on curl commands, csv writing and formatting.
  - Create a new conda environment and install dependency (Selenium, playwright, requests, httpx, Pymongo) with Python 3.10 or Python 3.11.
  - Use Poetry otherwise for this pure Python project.
  - Use MongoDB Playground with Javascript to test queries on samples.
  - Use Pymongo for interfacing MongoDB querying and Pandas extended querying and refinement of data.
  - Use Docker for continuous integration.


---


### **2. Authentication**

Read https://medium.com/@rramgattie/samesite-and-subdomains-08870bbdd62c

Credentials give cookies, and clicks trigger api return.

The Carrefour website is protected by samesite parameters. Especially, when a cookie is set with `SameSite=LAX`, it means that the cookie will be sent with “safe” cross-origin requests initiated by third-party websites (such as when a user clicks on a link to your site from another site), but not with requests initiated by scripts on other sites. This is because requests originating from the same domain (or a subdomain) are generally considered same-site by browsers, even though they technically come from different subdomains.
See also https://portswigger.net/web-security/csrf/bypassing-samesite-restrictions. That prevents from using the library `requests` in order to send http requests. Hence, one needs to use more cumbersome tools.

#### Attempt 1: Bypass Cloudflare & Login
- **Anti-bot measures**:  
  - Find a way around Cloudfare (especially Turnstile).
  - Use `undetected_chromedriver` with Selenium to mask `navigator.webdriver` flags.  Deploy headless browsers with patched TLS fingerprints (e.g., using `selenium-stealth`). See for example https://scrapfly.io/blog/how-to-avoid-web-scraping-blocking-tls/#what-is-tls for TLS fingerprints explanation.
  - Rotate user-agents and mimic human behavior (randomized delays, mouse movements).  
  - Beware HTTP Details Most users browse the internet web pages through a few popular browsers, such as Chrome, Firefox, or Edge. These browsers intercept their configuration. Reproduce: `Accept` (`application/json` when scraping hidden APIs or `text/xml` for sitemaps), `accept-language`, `user-agent` and `cookie`.
  - Leverage Javascript for fingerprinting work (see https://scrapfly.io/blog/how-to-avoid-web-scraping-blocking-javascript/#how-does-browser-fingerprinting-work).
  - Beware connection with VPN might not work due to IP ban.


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
  - The only viable option is to get the API response by `curl` command (no need to pause once logged in as one can run in chain several curl get commands). 
  
- **Data structure**:  
  - Parse JSON responses into three tables:  
    1. **Orders**: `order_id, datetime, total_amount, payment_method, discounts`.
    2. **Receipts:** `id, dateKey`, `total_amount_`  
    3. **Items**: `order_id, product_name, quantity, price, category` (enrich via NLP if raw data is unstructured, for example predict the category with feature VAT).  
    4. **Loyalty**: `order_id, points_earned, rewards_used`.  
  - Expose an endpoint (FastAPI) that accesses to that database, and use it to feed a Streamlit app.

---

### **4. Data Storage & Pipelines**

#### **Database Design**  
- **Storage strategy**:
  - Build a MongoDB database since the API response is in JSON format and can constitute a document database easy to query from with MongoDB. Use of NoSQL in the context of local data (collected from a mobile app or a laptop on a daily or weekly basis).
  - Keep the stdout as it is (JSON file containing the receipt or order details) so that analysis by NoSQL querying is not constrained. 
  - Given a sample of 3 years, we have around 300 receipts / orders equivalent to $\approx 300 \times 30 = 9000$ rows (with overhead 10K rows max) and few columns (count on single hand). This can be handled with Pandas. The data scaling may become an issue if one consider receipts / orders from various sources. Still when restraining to an individual, it is likely not an issue if the consumption is "normal".
  - Use PySpark for distributed processing if data scales beyond 1M+ rows (only plausible for purchased items). Only about a thousand rows or less for order receipts (use Pandas). 
- **Schema enforcement**:  
  - Validate data types (e.g., `decimal` for amounts, `datetime` for timestamps in Pandas).  
  - Handle missing values (e.g., default `0` for discounts, payment info). This is done in MongoDB in aggregation pipeline.  

#### Database connection

On macOS, for the first time, use Homebrew to install `mongodb-community`.
Then, run:

```bash
brew services start mongodb-community
```
This starts the connection to the database. For sake of simplicity, we employ a local database (e.g. `localhost:27017` as connection string). Most script close the connection but it is recommended to check.

When done, do not forget to run:
```bash
brew services stop mongodb-community
```

   
#### Querying

We use MQL (MongoDB Query Language) with the help of either MongoDB Atlas SQL Interface or Copilot for query statement based on prompt of query specifications. We have several approaches:
- general querying: all the records with payment infos, and maybe summary of purchased products (for pie charts)
- summary by month and year: total amount, total amount with VAT 5,5%
- queries focused on products (different time granularity) with keywords `$unwind` and `$group` on the `products` key.

The more complex operations such as joining and pivoting table should be deferred to **Pandas**, for example joining loyalty history and receipt details on a dateKey in a non-obvious way (several receipts with the same dateKey).

The next step is to perform fuzzy join using the libraries `rapidfuzz` and `pandas` on the product labels in order to merge receipt, order and loyalty data.


#### **Automation & CI/CD**  
- **Pipeline orchestration**:  
  - Script extraction → transformation → storage as a Python module.  
  - Use GitHub Actions to schedule monthly runs (Cron jobs).
  - The cron job may need to force the opening of a new tab for login in Carrefour account which is a bit harsh for a consumer.

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
  - How much a year spending on non-food commodities? Filtering with VAT 20% (small amount not higher than 15-20 euros by unit).
  - Month with the most immediate discount? Reaction from year-to-year?  
- **Behavioral trends**:
  - Periods of the year with higher spending on a sample of three-four years
  - Drive vs in-store: what one buys
  - Average price per product for Drive orders and in-store receipts
- **Category insights**:  
  - Bio vs. regular food share (regular expression: `bio`).  
  - Meat vs. plant-based spending ratios.
- **Prices**  
   - Top 10 purchased products and evolutions of their prices
   - Evolutions of prices of main vegetables
   - Evolutions of meat prices
   - 
- **Quantity**
   - How many kilograms of vegetables and fruits in average?
   - How many items in average, per month?
   - Inventory for hygiene and beauty (total quantity based on number of purchases of a selection of products by month or year): use rolling aggregation to get a better grasp of the evolution of number of items and then the actual consumption patterns.
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
  - Adhere to Carrefour’s `robots.txt` and terms of service.
  - Do not version-control `secrets.yml` that contain some critical piece of information relative to user.
  - WISH: Anonymize personal data (e.g. hash some critical id number if necessary).  
   

- **Monitoring**:  
  - Log errors (e.g., failed scrapes, schema mismatches) with `structlog` thanks to `logging` library.
  - Data drift: either feature drift (inflation effect) or concept drift (Covid)
  - Alert on pipeline failures (e.g., Slack/Email notifications).  

---

### **6. Future Enhancements**  
- **Advanced NLP**: Use spaCy to categorize unstructured product names based on a sample of already categorized items from the Drive orders.
- **Modification of schema**: Find a better representation of the documents so that querying does not rely on dynamic fields.  
- **Real-time dashboards**: Integrate Kafka for live data streaming.  
- **Optimization of database accesses**: Find a better calendar for database access and work on how many updates one want to accurately monitor the KPIs.
- **Creation of a complete MongoDB pipeline** that is actionable right off the shelf. Use the full power of MongoDB.
- Use of command-line for quick command without switching to separate application. Use of Git, etc.
- Continuous deployment of database (Streamlit access to database).
- **Cost optimization**: Migrate to AWS Glue/S3 for scalable storage if handling several loyalty cards (user accounts). Think of paying for efficient scraping (automation of login without the resort to browsers).
- **OOP or imperative coding**: Understand the true purpose of coding with OOP in several use cases surrounding this project.  
- Find other API endpoints that can enrich the database, especially product-related information such as `ean` and their categories (food, hygiene, or others).
- Talk with Carrefour shareholders about possibility to integrate this work as a microservice or a feature in the new iteration of the app.

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

### Continuous integration

- https://hub.docker.com/r/aminehy/docker-streamlit-app
- https://www.liquibase.com/resources/guides/database-continuous-integration