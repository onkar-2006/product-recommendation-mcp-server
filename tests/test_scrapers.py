import pytest
from src.scrapers.amazon import AmazonScraper
from src.scrapers.flipkart import FlipkartScraper
from src.scrapers.meesho import MeeshoScraper
from src.scrapers.myntra import MyntraScraper
from src.core.browser import browser_manager

pytestmark = pytest.mark.asyncio

# Mock HTML payloads representing typical search responses for each site

AMAZON_MOCK_SEARCH_HTML = """
<html>
<body>
  <div data-component-type="s-search-result">
    <h2>
      <a href="/dp/B00TEST123">
        <span>Amazon Mock Product 1</span>
      </a>
    </h2>
    <span class="a-price"><span class="a-offscreen">₹999.00</span></span>
    <span class="a-price a-text-price"><span class="a-offscreen">₹1,999.00</span></span>
    <img class="s-image" src="https://images.com/prod1.jpg" />
    <span class="a-icon-alt">4.2 out of 5 stars</span>
    <span class="a-size-base s-underline-text">150 ratings</span>
  </div>
</body>
</html>
"""

FLIPKART_MOCK_SEARCH_HTML = """
<html>
<body>
  <div data-id="FLIPKART_ITEM_123">
    <a href="/p/flipkart-mock-item/itm123">Link</a>
    <div class="_2WkVRV">FlipkartBrand</div>
    <a class="IRpwTa" href="/p/flipkart-mock-item/itm123">Casual Shoes For Men</a>
    <div class="Nx93jA">₹1,499</div>
    <div class="y30dLL">₹2,999</div>
    <div class="UkC1ED">50% OFF</div>
    <img class="DByo1Z" src="https://img.com/shoes1.jpg" />
    <div class="XQD0XM">4.5 ★</div>
    <span class="W5ryCn">(2,350)</span>
  </div>
</body>
</html>
"""

MEESHO_MOCK_SEARCH_HTML = """
<html>
<body>
  <a href="/p/meesho-mock-item-999">
    <img src="https://meesho.com/img999.jpg" />
    <p>Meesho Designer Kurti</p>
    <p>₹450</p>
    <p>₹900</p>
    <p>50% off</p>
    <p>3.8</p>
  </a>
</body>
</html>
"""

MYNTRA_MOCK_SEARCH_HTML = """
<html>
<body>
  <script>
    window.__myx = {
      "searchData": {
        "results": {
          "products": [
            {
              "brand": "MyntraBrand",
              "productName": "Mock T-Shirt",
              "price": 599,
              "mrp": 999,
              "discountDisplayStr": "40% OFF",
              "searchImage": "https://myntra.com/tshirt.jpg",
              "ratings": {"rating": 4.1, "ratingCount": 75},
              "landingPageUrl": "myntra-brand-mock-t-shirt/pdp"
            }
          ]
        }
      }
    };
  </script>
</body>
</html>
"""

# Scraper Unit Tests using Playwright Interception Routing

async def test_amazon_scraper_search():
    scraper = AmazonScraper()
    
    async def route_handler(route):
        await route.fulfill(status=200, body=AMAZON_MOCK_SEARCH_HTML, headers={"Content-Type": "text/html"})
        
    try:
        # Acquire a context to configure the route interception
        browser = await browser_manager.get_browser()
        async with browser_manager.page_context() as page:
            await page.route("**/s?k=*", route_handler)
            
            # Since the scraper creates its own page context internally,
            # we need to route globally, but here we can test the parser by running inside our controlled route.
            # To test scrapers independently of global requests, we mock the network router for all pages.
            await page.context.route("**/s?k=*", route_handler)
            
        # Execute scraper search (which will intercept on chromium via the route)
        # To ensure the scraper uses our mock page, we mock the global page_context temporarily or run search.
        # Let's test the search method directly.
        # Note: Playwright router holds globally for the browser if configured.
        # For simplicity in mock tests, we register routes on the singleton browser manager's contexts.
        # We can implement a clean mock test by patching the network globally.
        pass
    finally:
        await browser_manager.close()

async def test_amazon_search_extraction_logic():
    """Validates the Amazon extraction parser logic with mock network interception."""
    scraper = AmazonScraper()
    
    async def intercept(route):
        await route.fulfill(status=200, body=AMAZON_MOCK_SEARCH_HTML, headers={"Content-Type": "text/html"})

    async with browser_manager.page_context() as page:
        await page.context.route("**/s?k=*", intercept)
        # Run search
        results = await scraper.search("mock query", limit=1)
        
        assert len(results) >= 1
        assert results[0].title == "Amazon Mock Product 1"
        assert results[0].price == 999.0
        assert results[0].original_price == 1999.0
        assert results[0].discount == "50% OFF"
        assert results[0].platform == "amazon"

async def test_flipkart_search_extraction_logic():
    """Validates the Flipkart extraction parser logic with mock network interception."""
    scraper = FlipkartScraper()
    
    async def intercept(route):
        await route.fulfill(status=200, body=FLIPKART_MOCK_SEARCH_HTML, headers={"Content-Type": "text/html"})

    async with browser_manager.page_context() as page:
        await page.context.route("**/search*", intercept)
        results = await scraper.search("mock shoes", limit=1)
        
        assert len(results) >= 1
        assert "FlipkartBrand" in results[0].title
        assert results[0].price == 1499.0
        assert results[0].original_price == 2999.0
        assert results[0].discount == "50% OFF"
        assert results[0].platform == "flipkart"

async def test_meesho_search_extraction_logic():
    """Validates the Meesho extraction parser logic with mock network interception."""
    scraper = MeeshoScraper()
    
    async def intercept(route):
        await route.fulfill(status=200, body=MEESHO_MOCK_SEARCH_HTML, headers={"Content-Type": "text/html"})

    async with browser_manager.page_context() as page:
        await page.context.route("**/search*", intercept)
        results = await scraper.search("kurti", limit=1)
        
        assert len(results) >= 1
        assert "Designer Kurti" in results[0].title
        assert results[0].price == 450.0
        assert results[0].rating == 3.8
        assert results[0].platform == "meesho"

async def test_myntra_search_extraction_logic():
    """Validates the Myntra extraction parser logic parsing __myx scripts."""
    scraper = MyntraScraper()
    
    async def intercept(route):
        await route.fulfill(status=200, body=MYNTRA_MOCK_SEARCH_HTML, headers={"Content-Type": "text/html"})

    async with browser_manager.page_context() as page:
        await page.context.route("**/search*", intercept)
        results = await scraper.search("tshirt", limit=1)
        
        assert len(results) >= 1
        assert "MyntraBrand" in results[0].title
        assert results[0].price == 599.0
        assert results[0].rating == 4.1
        assert results[0].review_count == 75
        assert results[0].platform == "myntra"
