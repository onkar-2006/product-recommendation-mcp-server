import urllib.parse
from typing import List, Optional
from playwright.async_api import Page

from src.scrapers.base import BaseScraper
from src.schemas.product import Product, ProductDetails
from src.core.browser import browser_manager
from src.core.exceptions import ScrapingBlockedError, ProductNotFoundError
from src.core.logger import logger

class AmazonScraper(BaseScraper):
    """Amazon.in scraper implementation."""
    
    async def search(self, query: str, limit: int = 5) -> List[Product]:
        async def _scrape() -> List[Product]:
            encoded_query = urllib.parse.quote(query)
            search_url = f"https://www.amazon.in/s?k={encoded_query}"
            
            logger.info(f"Navigating to Amazon search: {search_url}")
            async with browser_manager.page_context() as page:
                try:
                    # Navigate with wait_until to make sure initial layout loaded
                    await page.goto(search_url, wait_until="commit")
                    await self.random_delay(1000, 2000)
                    
                    # 1. Bot Protection Check
                    html_content = await page.content()
                    if self.detect_bot_protection(html_content) or "captcha" in page.url.lower():
                        raise ScrapingBlockedError("Amazon bot detection triggered (CAPTCHA / Robot Check page).")
                    
                    # 2. Wait for items or no results flag
                    try:
                        await page.wait_for_selector('[data-component-type="s-search-result"]', timeout=8000)
                    except Exception:
                        # Check if it was blocked or if there really are 0 results
                        if "no results for" in html_content.lower() or "did not match any products" in html_content.lower():
                            return []
                        raise ProductNotFoundError(f"Amazon search results selector not found for: '{query}'")
                    
                    # Ensure lazy-loaded cards render
                    await self.human_like_scroll(page, max_scrolls=2)
                    
                    # 3. Extract items
                    items = await page.query_selector_all('[data-component-type="s-search-result"]')
                    products: List[Product] = []
                    
                    for item in items:
                        if len(products) >= limit:
                            break
                        
                        try:
                            # Skip sponsored ads (they contain sponsored label or class)
                            sponsored_el = await item.query_selector(".puis-sponsored-label-text")
                            if sponsored_el:
                                continue
                                
                            # Title
                            title_el = await item.query_selector("h2 a span")
                            if not title_el:
                                continue
                            title = (await title_el.inner_text()).strip()
                            
                            # Product URL
                            url_el = await item.query_selector("h2 a")
                            if not url_el:
                                continue
                            href = await url_el.get_attribute("href")
                            if not href:
                                continue
                            product_url = urllib.parse.urljoin("https://www.amazon.in", href)
                            
                            # Price & Original Price
                            price_el = await item.query_selector(".a-price .a-offscreen")
                            if not price_el:
                                continue # Skip items without pricing
                            price_text = await price_el.inner_text()
                            price = self.clean_price(price_text)
                            
                            # MRP (Original Price)
                            original_price = None
                            discount = None
                            original_price_el = await item.query_selector(".a-price.a-text-price span.a-offscreen")
                            if original_price_el:
                                original_price_text = await original_price_el.inner_text()
                                original_price = self.clean_price(original_price_text)
                                if original_price > price:
                                    discount_pct = int(((original_price - price) / original_price) * 100)
                                    discount = f"{discount_pct}% OFF"
                            
                            # Image
                            img_el = await item.query_selector("img.s-image")
                            image_url = await img_el.get_attribute("src") if img_el else None
                            
                            # Ratings
                            rating = None
                            rating_el = await item.query_selector("span.a-icon-alt")
                            if rating_el:
                                rating_text = await rating_el.inner_text()
                                # Extracts e.g. "4.2 out of 5 stars" -> 4.2
                                match = re.search(r"([\d.]+)\s*out", rating_text)
                                if match:
                                    rating = float(match.group(1))
                                    
                            # Review Count
                            review_count = None
                            review_el = await item.query_selector("span.a-size-base.s-underline-text")
                            if review_el:
                                review_text = await review_el.inner_text()
                                review_count = self.parse_review_count(review_text)
                                
                            products.append(Product(
                                title=title,
                                price=price,
                                currency="INR",
                                original_price=original_price,
                                discount=discount,
                                rating=rating,
                                review_count=review_count,
                                image_url=image_url,
                                product_url=product_url,
                                platform="amazon",
                                in_stock=True
                            ))
                        except Exception as card_err:
                            logger.debug(f"Skipping Amazon card due to parsing exception: {card_err}")
                            continue
                            
                    return products
                except Exception as e:
                    if self.detect_bot_protection(await page.content()):
                        raise ScrapingBlockedError("Blocked by Amazon bot protection during search.")
                    raise e
                    
        return await self.execute_with_retry(_scrape(), "amazon")

    async def get_details(self, url: str) -> ProductDetails:
        async def _scrape() -> ProductDetails:
            logger.info(f"Navigating to Amazon product details: {url}")
            async with browser_manager.page_context() as page:
                await page.goto(url, wait_until="commit")
                await self.random_delay(1500, 2500)
                
                # Check for blocks
                html_content = await page.content()
                if self.detect_bot_protection(html_content):
                    raise ScrapingBlockedError("Amazon bot detection triggered on product detail page.")
                
                # Verify product exists
                title_el = await page.query_selector("#productTitle")
                if not title_el:
                    raise ProductNotFoundError(f"Amazon product details title element not found at {url}")
                title = (await title_el.inner_text()).strip()
                
                # Extract image
                img_el = await page.query_selector("#landingImage")
                image_url = await img_el.get_attribute("src") if img_el else None
                
                # Extract price
                price = 0.0
                price_el = await page.query_selector(".a-price-whole")
                if price_el:
                    price = self.clean_price(await price_el.inner_text())
                else:
                    # Fallback for books or alternate pages
                    price_fallback = await page.query_selector("#price")
                    if price_fallback:
                        price = self.clean_price(await price_fallback.inner_text())
                
                original_price = None
                original_price_el = await page.query_selector(".basis-price .a-price.a-text-price span.a-offscreen")
                if original_price_el:
                    original_price = self.clean_price(await original_price_el.inner_text())
                
                discount = None
                discount_el = await page.query_selector(".savingPriceOverride")
                if discount_el:
                    discount = (await discount_el.inner_text()).strip()
                elif original_price and original_price > price:
                    discount = f"{int(((original_price - price) / original_price) * 100)}% OFF"
                
                # Ratings
                rating = None
                rating_el = await page.query_selector("#acrPopover span.a-icon-alt")
                if rating_el:
                    rating_text = await rating_el.inner_text()
                    match = re.search(r"([\d.]+)\s*out", rating_text)
                    if match:
                        rating = float(match.group(1))
                        
                review_count = None
                review_el = await page.query_selector("#acrCustomerReviewText")
                if review_el:
                    review_count = self.parse_review_count(await review_el.inner_text())
                
                # In stock status
                in_stock = True
                stock_el = await page.query_selector("#availability")
                if stock_el:
                    stock_text = (await stock_el.inner_text()).lower()
                    if "currently unavailable" in stock_text or "out of stock" in stock_text:
                        in_stock = False
                        
                # Description
                description = None
                desc_el = await page.query_selector("#productDescription")
                if desc_el:
                    description = (await desc_el.inner_text()).strip()
                else:
                    # Fallback to feature bullets
                    bullets_el = await page.query_selector("#feature-bullets")
                    if bullets_el:
                        description = (await bullets_el.inner_text()).strip()
                        
                # Technical Specifications
                specifications = {}
                # Check standard table
                rows = await page.query_selector_all(".prodDetTable tr")
                for row in rows:
                    th = await row.query_selector("th")
                    td = await row.query_selector("td")
                    if th and td:
                        key = (await th.inner_text()).strip()
                        val = (await td.inner_text()).strip()
                        specifications[key] = val
                        
                # Check alternative spec sheets
                if not specifications:
                    rows = await page.query_selector_all("#technicalSpecifications_feature_div tr")
                    for row in rows:
                        label = await row.query_selector(".label")
                        value = await row.query_selector(".value")
                        if label and value:
                            key = (await label.inner_text()).strip()
                            val = (await value.inner_text()).strip()
                            specifications[key] = val
                
                # Merchant
                merchant = None
                merchant_el = await page.query_selector("#merchantInfoOfficiallySoldByCustomerText")
                if merchant_el:
                    merchant = (await merchant_el.inner_text()).strip()
                else:
                    seller_el = await page.query_selector("#sellerProfileTriggerId")
                    if seller_el:
                        merchant = (await seller_el.inner_text()).strip()
                        
                return ProductDetails(
                    title=title,
                    price=price,
                    currency="INR",
                    original_price=original_price,
                    discount=discount,
                    rating=rating,
                    review_count=review_count,
                    image_url=image_url,
                    product_url=url,
                    platform="amazon",
                    in_stock=in_stock,
                    description=description,
                    specifications=specifications if specifications else None,
                    merchant=merchant
                )
        return await self.execute_with_retry(_scrape(), "amazon")
import re
