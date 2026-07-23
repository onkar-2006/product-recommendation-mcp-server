import pytest
from src.core.db import init_db
from src.core.cache import (
    set_search_cache, get_search_cache,
    set_details_cache, get_details_cache,
    set_session_cache, get_session_cache
)

# Apply async markers to all tests in this file
pytestmark = pytest.mark.asyncio

@pytest.fixture(autouse=True)
async def setup_test_database():
    """Initializes the database schema before running module tests."""
    await init_db()

async def test_search_results_caching_lifecycle():
    """Tests saving search result payloads to SQLite cache and retrieving them."""
    platform = "flipkart"
    query = "cotton t-shirt"
    limit = 2
    mock_results = [
        {
            "title": "Cotton Brand Shirt Blue",
            "price": 499.0,
            "currency": "INR",
            "original_price": 999.0,
            "discount": "50% OFF",
            "rating": 4.1,
            "review_count": 89,
            "image_url": "https://img.com/1.jpg",
            "product_url": "https://flipkart.com/p/1",
            "platform": "flipkart",
            "in_stock": True,
            "specifications": None
        },
        {
            "title": "Slim Fit Cotton Tee Black",
            "price": 350.0,
            "currency": "INR",
            "original_price": 500.0,
            "discount": "30% OFF",
            "rating": 3.9,
            "review_count": 12,
            "image_url": "https://img.com/2.jpg",
            "product_url": "https://flipkart.com/p/2",
            "platform": "flipkart",
            "in_stock": True,
            "specifications": None
        }
    ]

    # Write mock data to cache
    await set_search_cache(platform, query, limit, mock_results)

    # Read data from cache
    cached_results = await get_search_cache(platform, query, limit)

    assert cached_results is not None
    assert len(cached_results) == 2
    assert cached_results[0]["title"] == "Cotton Brand Shirt Blue"
    assert cached_results[1]["price"] == 350.0
    assert cached_results[0]["platform"] == "flipkart"

async def test_product_details_caching_lifecycle():
    """Tests writing and reading expanded product details from cache."""
    url = "https://www.myntra.com/shoes/nike-run-swift/12345"
    mock_details = {
        "title": "Nike Run Swift Running Shoes",
        "price": 4500.0,
        "currency": "INR",
        "original_price": 6000.0,
        "discount": "25% OFF",
        "rating": 4.5,
        "review_count": 456,
        "image_url": "https://img.com/nike.jpg",
        "product_url": url,
        "platform": "myntra",
        "in_stock": True,
        "description": "Comfortable mesh design for road running.",
        "specifications": {"Sport": "Running", "Fastening": "Lace-ups"},
        "merchant": "Nike India"
    }

    await set_details_cache(url, mock_details)

    cached_details = await get_details_cache(url)

    assert cached_details is not None
    assert cached_details["title"] == "Nike Run Swift Running Shoes"
    assert cached_details["price"] == 4500.0
    assert cached_details["description"] == "Comfortable mesh design for road running."
    assert cached_details["specifications"]["Sport"] == "Running"

async def test_session_state_caching_lifecycle():
    """Tests saving and loading cookie profiles for anti-bot bypass validation."""
    platform = "meesho"
    mock_cookies = [
        {"name": "session_id", "value": "abcdef123456", "domain": ".meesho.com"},
        {"name": "user_pref", "value": "dark", "domain": ".meesho.com"}
    ]
    mock_headers = {
        "User-Agent": "SuperStealthAgent 1.0",
        "X-Custom-Auth": "SecretToken"
    }

    await set_session_cache(platform, mock_cookies, mock_headers)

    session = await get_session_cache(platform)

    assert session is not None
    cookies_res, headers_res = session
    assert len(cookies_res) == 2
    assert cookies_res[0]["name"] == "session_id"
    assert cookies_res[0]["value"] == "abcdef123456"
    assert headers_res is not None
    assert headers_res["X-Custom-Auth"] == "SecretToken"
