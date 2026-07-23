import urllib.parse
from typing import List, Optional
from playwright.async_api import Page

from src.scrapers.base import BaseScraper
from src.schemas.product import Product, ProductDetails
from src.core.browser import browser_manager
from src.core.exceptions import ScrapingBlockedError, ProductNotFoundError
from src.core.logger import logger

class MeeshoScraper(BaseScraper):
    """Meesho.com scraper implementation."""

    async def search(self, query: str, limit: int = 5) -> List[Product]:
        async def _scrape() -> List[Product]:
            encoded_query = urllib.parse.quote(query)
            search_url = f"https://www.meesho.com/search?q={encoded_query}"

            logger.info(f"Navigating to Meesho search: {search_url}")
            async with browser_manager.page_context() as page:
                try:
                    await page.goto(search_url, wait_until="commit")
                    await self.random_delay(1500, 2500)

                    # 1. Bot check
                    html_content = await page.content()
                    if self.detect_bot_protection(html_content):
                        raise ScrapingBlockedError("Blocked by Meesho bot protection.")

                    # 2. Wait for product cards
                    # Meesho cards are typically anchors pointing to /p/ (product url)
                    card_selector = 'a[href*="/p/"]'
                    try:
                        await page.wait_for_selector(card_selector, timeout=8000)
                    except Exception:
                        if "no results found" in html_content.lower():
                            return []
                        raise ProductNotFoundError(f"Meesho search results not found for query: '{query}'")

                    await self.human_like_scroll(page, max_scrolls=2)

                    # 3. Extract items
                    items = await page.query_selector_all(card_selector)
                    logger.warning(f"Meesho Scraper: Found {len(items)} items matching selector '{card_selector}'")
                    products: List[Product] = []

                    for item in items:
                        if len(products) >= limit:
                            break

                        try:
                            # Product URL
                            href = await item.get_attribute("href")
                            if not href:
                                continue
                            product_url = urllib.parse.urljoin("https://www.meesho.com", href)

                            # Image
                            img_el = await item.query_selector("img")
                            image_url = None
                            if img_el:
                                image_url = await img_el.get_attribute("src")

                            # Text extraction (Meesho elements use dynamic styled-component classes, e.g. .sc-csuQGl)
                            # We can find them based on tags and text properties inside the card
                            title = ""
                            # The title is usually a paragraph/p tag with styling
                            p_tags = await item.query_selector_all("p")
                            logger.warning(f"Meesho Scraper: Found {len(p_tags)} p elements inside card")
                            
                            # Parse attributes from paragraph text elements
                            price = 0.0
                            original_price = None
                            discount = None
                            rating = None
                            review_count = None
                            
                            price_candidates = []

                            for p in p_tags:
                                text = (await p.inner_text()).strip()
                                logger.warning(f"Meesho Scraper: p text is '{text}'")
                                if not text:
                                    continue
                                
                                text_lower = text.lower()
                                
                                # 1. Discount check
                                if "% off" in text_lower or "off" in text_lower:
                                    discount = text
                                # 2. Rating check (e.g. '3.8')
                                elif len(text) == 3 and text[1] == "." and text[0].isdigit() and text[2].isdigit():
                                    try:
                                        rating = float(text)
                                    except ValueError:
                                        pass
                                # 3. Numeric price check
                                elif any(c.isdigit() for c in text):
                                    val = self.clean_price(text)
                                    if val > 0.0:
                                        price_candidates.append(val)
                                # 4. Title check (fallback to longest text)
                                elif len(text) > len(title) and "reviews" not in text_lower and "ratings" not in text_lower:
                                    title = text

                            # Self-correcting price logic (smaller of two is current price, larger is original/MRP)
                            if price_candidates:
                                if len(price_candidates) >= 2:
                                    price = min(price_candidates)
                                    original_price = max(price_candidates)
                                else:
                                    price = price_candidates[0]

                            # If title is still empty, fallback to inner text parsing
                            if not title:
                                title_el = await item.query_selector("span")
                                if title_el:
                                    title = (await title_el.inner_text()).strip()

                            # If no price was found, skip
                            if price == 0.0:
                                continue

                            products.append(Product(
                                title=title if title else f"Meesho Item ({query})",
                                price=price,
                                currency="INR",
                                original_price=original_price,
                                discount=discount,
                                rating=rating,
                                review_count=review_count,
                                image_url=image_url,
                                product_url=product_url,
                                platform="meesho",
                                in_stock=True
                            ))
                        except Exception as e:
                            logger.error(f"Skipping Meesho card parse: {e}", exc_info=True)
                            continue

                    return products
                except Exception as e:
                    if self.detect_bot_protection(await page.content()):
                        raise ScrapingBlockedError("Blocked by Meesho bot protection during search.")
                    raise e

        return await self.execute_with_retry(_scrape(), "meesho")

    async def get_details(self, url: str) -> ProductDetails:
        async def _scrape() -> ProductDetails:
            logger.info(f"Navigating to Meesho product details: {url}")
            async with browser_manager.page_context() as page:
                await page.goto(url, wait_until="commit")
                await self.random_delay(1500, 2500)

                html_content = await page.content()
                if self.detect_bot_protection(html_content):
                    raise ScrapingBlockedError("Blocked by Meesho bot protection on product detail page.")

                # 1. Extract Title (typically h3 or h1)
                title_el = await page.query_selector("h1, h3, span[class*='ProductTitle']")
                if not title_el:
                    raise ProductNotFoundError(f"Meesho details title not found at {url}")
                title = (await title_el.inner_text()).strip()

                # 2. Extract Price & Discount
                price = 0.0
                price_el = await page.query_selector("h3, h4, span[class*='Price']")
                # Find h3 or h4 that contains ₹
                headings = await page.query_selector_all("h3, h4, span")
                for h in headings:
                    text = (await h.inner_text()).strip()
                    if "₹" in text:
                        price = self.clean_price(text)
                        break

                original_price = None
                discount = None
                # Strikethrough text represents original price
                strike_el = await page.query_selector("p[style*='text-decoration: line-through'], span[style*='line-through']")
                if strike_el:
                    original_price = self.clean_price(await strike_el.inner_text())

                if original_price and original_price > price:
                    discount = f"{int(((original_price - price) / original_price) * 100)}% OFF"

                # 3. Rating & Reviews
                rating = None
                rating_el = await page.query_selector("span[class*='RatingPill'], div[class*='RatingPill']")
                if rating_el:
                    try:
                        rating_text = (await rating_el.inner_text()).strip()
                        rating = float(rating_text)
                    except Exception:
                        pass

                review_count = None
                review_el = await page.query_selector("span[class*='ReviewsCount'], span[class*='RatingsCount']")
                if review_el:
                    review_count = self.parse_review_count(await review_el.inner_text())

                # 4. Image
                img_el = await page.query_selector("img")
                image_url = None
                if img_el:
                    image_url = await img_el.get_attribute("src")

                # 5. In Stock
                in_stock = True
                stock_el = await page.query_selector("span[class*='OutOfStock'], p[class*='OutOfStock']")
                if stock_el:
                    in_stock = False

                # 6. Description & Specifications
                description = None
                desc_el = await page.query_selector("span[class*='Description'], div[class*='Description']")
                if desc_el:
                    description = (await desc_el.inner_text()).strip()

                specifications = {}
                # Meesho specifications list features as text blocks/paragraphs (e.g. "Fabric: Cotton", "Sleeve: Short")
                spec_tags = await page.query_selector_all("p, span")
                for tag in spec_tags:
                    text = (await tag.inner_text()).strip()
                    if text and ":" in text and len(text) < 100:
                        parts = text.split(":", 1)
                        key = parts[0].strip()
                        val = parts[1].strip()
                        if len(key) > 1 and len(val) > 1:
                            specifications[key] = val

                # 7. Merchant Seller info
                merchant = None
                merchant_el = await page.query_selector("span[class*='ShopName'], p[class*='ShopName']")
                if merchant_el:
                    merchant = (await merchant_el.inner_text()).strip()

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
                    platform="meesho",
                    in_stock=in_stock,
                    description=description,
                    specifications=specifications if specifications else None,
                    merchant=merchant
                )
        return await self.execute_with_retry(_scrape(), "meesho")
