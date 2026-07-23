import pytest
import contextlib
import re
from src.core.browser import browser_manager

# Static Mock HTML definitions for scraper offline tests

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

@pytest.fixture(autouse=True)
def mock_scrapers_network(monkeypatch):
    """
    Globally patches browser_manager.page_context during test suites to automatically
    intercept and mock all outgoing network requests to Amazon, Flipkart, Meesho, and Myntra.
    Allows complete offline test validation.
    """
    original_page_context = browser_manager.page_context

    @contextlib.asynccontextmanager
    async def routed_page_context():
        async with original_page_context() as page:
            async def intercept_route(route):
                url = route.request.url.lower()
                if "amazon.in" in url:
                    await route.fulfill(status=200, body=AMAZON_MOCK_SEARCH_HTML, headers={"Content-Type": "text/html"})
                elif "flipkart.com" in url:
                    await route.fulfill(status=200, body=FLIPKART_MOCK_SEARCH_HTML, headers={"Content-Type": "text/html"})
                elif "meesho.com" in url:
                    await route.fulfill(status=200, body=MEESHO_MOCK_SEARCH_HTML, headers={"Content-Type": "text/html"})
                elif "myntra.com" in url:
                    await route.fulfill(status=200, body=MYNTRA_MOCK_SEARCH_HTML, headers={"Content-Type": "text/html"})
                else:
                    await route.continue_()

            # Set up routing filters using regular expressions to guarantee matching across all platforms
            await page.context.route(re.compile(r".*amazon\.in/s\?.*"), intercept_route)
            await page.context.route(re.compile(r".*flipkart\.com/search.*"), intercept_route)
            await page.context.route(re.compile(r".*meesho\.com/search.*"), intercept_route)
            await page.context.route(re.compile(r".*myntra\.com/search.*"), intercept_route)
            
            yield page

    monkeypatch.setattr(browser_manager, "page_context", routed_page_context)

@pytest.fixture(autouse=True)
async def cleanup_browser_session():
    """Closes the global browser manager singleton at the very end of the test session."""
    yield
    await browser_manager.close()
