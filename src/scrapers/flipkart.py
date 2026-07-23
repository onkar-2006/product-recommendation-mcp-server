import urllib.parse
from typing import List, Optional
from playwright.async_api import Page

from src.scrapers.base import BaseScraper
from src.schemas.product import Product, ProductDetails
from src.core.browser import browser_manager
from src.core.exceptions import ScrapingBlockedError, ProductNotFoundError
from src.core.logger import logger

class FlipkartScraper(BaseScraper):
    """Flipkart.com scraper implementation."""

    async def search(self, query: str, limit: int = 5) -> List[Product]:
        async def _scrape() -> List[Product]:
            encoded_query = urllib.parse.quote(query)
            search_url = f"https://www.flipkart.com/search?q={encoded_query}"

            logger.info(f"Navigating to Flipkart search: {search_url}")
            async with browser_manager.page_context() as page:
                try:
                    await page.goto(search_url, wait_until="commit")
                    await self.random_delay(1000, 2000)

                    # 1. Bot Protection Check
                    html_content = await page.content()
                    if self.detect_bot_protection(html_content):
                        raise ScrapingBlockedError("Blocked by Flipkart bot protection.")

                    # 2. Wait for cards
                    # Flipkart uses [data-id] for product card grid elements
                    card_selector = "div[data-id]"
                    try:
                        await page.wait_for_selector(card_selector, timeout=8000)
                    except Exception:
                        if "no results found" in html_content.lower() or "did not match any products" in html_content.lower():
                            return []
                        raise ProductNotFoundError(f"Flipkart search results selector not found for query: '{query}'")

                    await self.human_like_scroll(page, max_scrolls=2)

                    # 3. Extract items
                    items = await page.query_selector_all(card_selector)
                    products: List[Product] = []

                    for item in items:
                        if len(products) >= limit:
                            break

                        try:
                            # 1. Product URL
                            url_el = await item.query_selector('a[href*="/p/"]')
                            if not url_el:
                                continue
                            href = await url_el.get_attribute("href")
                            if not href:
                                continue
                            product_url = urllib.parse.urljoin("https://www.flipkart.com", href)

                            # 2. Title & Brand
                            # Flipkart titles are sometimes split: Brand (e.g. div._2WkVRV) + short description (a.IRpwTa)
                            title = ""
                            brand_el = await item.query_selector("div._2WkVRV")
                            desc_el = await item.query_selector("a.IRpwTa")
                            
                            # Fallbacks
                            alt_title_el = await item.query_selector("a.wscy5P")
                            alt_title_el_2 = await item.query_selector("div.KzDPHZ")

                            if brand_el and desc_el:
                                brand = (await brand_el.inner_text()).strip()
                                desc = (await desc_el.inner_text()).strip()
                                title = f"{brand} - {desc}"
                            elif alt_title_el:
                                title = (await alt_title_el.inner_text()).strip()
                            elif alt_title_el_2:
                                title = (await alt_title_el_2.inner_text()).strip()
                            else:
                                # Get title attribute or inner text of any anchor
                                text_el = await item.query_selector("a")
                                if text_el:
                                    title = (await text_el.inner_text()).strip().split("\n")[0]
                            
                            if not title or len(title) < 3:
                                continue

                            # 3. Price & Discount
                            # Common pricing classes: div.Nx93jA, div._30jeq3
                            price_el = await item.query_selector("div.Nx93jA, div._30jeq3")
                            if not price_el:
                                continue
                            price = self.clean_price(await price_el.inner_text())

                            original_price = None
                            original_price_el = await item.query_selector("div.y30dLL, div._3I9_ca")
                            if original_price_el:
                                original_price = self.clean_price(await original_price_el.inner_text())

                            discount = None
                            discount_el = await item.query_selector("div.UkC1ED, div._3Ay6Sb")
                            if discount_el:
                                discount = (await discount_el.inner_text()).strip()

                            # 4. Image
                            img_el = await item.query_selector("img.DByo1Z, img._396cs4")
                            image_url = None
                            if img_el:
                                image_url = await img_el.get_attribute("src")

                            # 5. Rating & Reviews
                            rating = None
                            rating_el = await item.query_selector("div.XQD0XM, div._3LWZlK")
                            if rating_el:
                                try:
                                    rating_text = (await rating_el.inner_text()).strip()
                                    rating = float(rating_text.split()[0])
                                except Exception:
                                    pass

                            review_count = None
                            review_el = await item.query_selector("span.W5ryCn, span._2_R_DZ")
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
                                platform="flipkart",
                                in_stock=True
                            ))
                        except Exception as e:
                            logger.debug(f"Skipping Flipkart card parse: {e}")
                            continue

                    return products
                except Exception as e:
                    if self.detect_bot_protection(await page.content()):
                        raise ScrapingBlockedError("Blocked by Flipkart bot protection during search.")
                    raise e

        return await self.execute_with_retry(_scrape(), "flipkart")

    async def get_details(self, url: str) -> ProductDetails:
        async def _scrape() -> ProductDetails:
            logger.info(f"Navigating to Flipkart product details: {url}")
            async with browser_manager.page_context() as page:
                await page.goto(url, wait_until="commit")
                await self.random_delay(1500, 2500)

                html_content = await page.content()
                if self.detect_bot_protection(html_content):
                    raise ScrapingBlockedError("Blocked by Flipkart bot protection on product detail page.")

                # 1. Title
                title_el = await page.query_selector("span.VU-ZEg, span.B_NuCI")
                if not title_el:
                    raise ProductNotFoundError(f"Flipkart details title not found at {url}")
                title = (await title_el.inner_text()).strip()

                # 2. Price
                price = 0.0
                price_el = await page.query_selector("div.Nx93jA, div._30jeq3")
                if price_el:
                    price = self.clean_price(await price_el.inner_text())

                original_price = None
                original_price_el = await page.query_selector("div.y30dLL, div._3I9_ca")
                if original_price_el:
                    original_price = self.clean_price(await original_price_el.inner_text())

                discount = None
                discount_el = await page.query_selector("div.UkC1ED, div._3Ay6Sb")
                if discount_el:
                    discount = (await discount_el.inner_text()).strip()

                # 3. Rating & Reviews
                rating = None
                rating_el = await page.query_selector("div.XQD0XM, div._3LWZlK")
                if rating_el:
                    try:
                        rating_text = (await rating_el.inner_text()).strip()
                        rating = float(rating_text.split()[0])
                    except Exception:
                        pass

                review_count = None
                # Looks like "23,400 Ratings & 1,200 Reviews"
                review_el = await page.query_selector("span.W5ryCn, span._2_R_DZ")
                if review_el:
                    review_count = self.parse_review_count(await review_el.inner_text())

                # 4. Image
                img_el = await page.query_selector("img.DByo1Z, img._396cs4, img.j3ZgJK")
                image_url = None
                if img_el:
                    image_url = await img_el.get_attribute("src")

                # 5. In Stock
                in_stock = True
                stock_el = await page.query_selector("div._1SDm3c, div._16FRp0")
                if stock_el:
                    stock_text = (await stock_el.inner_text()).lower()
                    if "sold out" in stock_text or "out of stock" in stock_text:
                        in_stock = False

                # 6. Description & Specs
                description = None
                desc_el = await page.query_selector("div.yN-e2R, div._1mX1Zt")
                if desc_el:
                    description = (await desc_el.inner_text()).strip()

                specifications = {}
                # Flipkart lists specifications in key-value table rows under tables (.WbW1IL or ._3ENrCw)
                rows = await page.query_selector_all("tr.WbW1IL, tr._3ENrCw")
                for row in rows:
                    key_el = await row.query_selector("td.yf1gU8, td._1h3Z5e")
                    val_el = await row.query_selector("td.e2Y5HZ, td._2kl3hC")
                    if key_el and val_el:
                        key = (await key_el.inner_text()).strip()
                        val = (await val_el.inner_text()).strip()
                        specifications[key] = val

                # 7. Seller/Merchant
                merchant = None
                merchant_el = await page.query_selector("div.LO2-w8, div._1RL34t")
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
                    platform="flipkart",
                    in_stock=in_stock,
                    description=description,
                    specifications=specifications if specifications else None,
                    merchant=merchant
                )
        return await self.execute_with_retry(_scrape(), "flipkart")
