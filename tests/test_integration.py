import pytest
from src.tools.compare import compare_prices_logic
from src.core.browser import browser_manager

pytestmark = pytest.mark.asyncio

async def test_search_and_compare_prices_integration():
    """
    Integration test validating that compare_prices tool queries both platforms,
    correctly aggregates items, sorts them by price, and determines the cheapest option.
    """
    try:
        # Execute integration logic across amazon and flipkart
        compare_res = await compare_prices_logic(
            query="mock query", 
            platforms=["amazon", "flipkart"]
        )
        
        assert compare_res.query == "mock query"
        assert len(compare_res.results) >= 2
        
        # Verify results sorted ascending by price
        prices = [item.price for item in compare_res.results]
        assert prices == sorted(prices)
        
        # Verify cheapest item is identified
        assert compare_res.cheapest is not None
        assert compare_res.cheapest.price == min(prices)
        assert compare_res.cheapest.title in [r.title for r in compare_res.results]
    finally:
        await browser_manager.close()
