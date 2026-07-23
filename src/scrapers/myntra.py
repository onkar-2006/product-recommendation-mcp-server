import json
import re
import urllib.parse
from typing import List, Optional, Dict, Any
from playwright.async_api import Page

from src.scrapers.base import BaseScraper
from src.schemas.product import Product, ProductDetails
from src.core.browser import browser_manager
from src.core.exceptions import ScrapingBlockedError, ProductNotFoundError
from src.core.logger import logger

class MyntraScraper(BaseScraper):
    """Myntra.com scraper implementation."""

    async def search(self, query: str, limit: int = 5) -> List[Product]:
        async def _scrape() -> List[Product]:
            encoded_query = urllib.parse.quote(query)
            search_url = f"https://www.myntra.com/search?rawQuery={encoded_query}"

            logger.info(f"Navigating to Myntra search: {search_url}")
            async with browser_manager.page_context() as page:
                try:
                    await page.goto(search_url, wait_until="commit")
                    await self.random_delay(1500, 2500)

                    # 1. Bot check
                    html_content = await page.content()
                    if self.detect_bot_protection(html_content):
                        raise ScrapingBlockedError("Blocked by Myntra bot protection.")

                    # 2. Try JSON Extraction from window.__myx script first
                    products = await self._parse_myx_search_data(page, limit)
                    if products:
                        logger.info(f"Successfully extracted {len(products)} search items from Myntra JSON state.")
                        return products

                    # 3. Fallback: DOM Extraction
                    logger.info("Myntra JSON state extraction failed. Falling back to DOM parsing...")
                    card_selector = "li.product-base"
                    try:
                        await page.wait_for_selector(card_selector, timeout=8000)
                    except Exception:
                        if "no results found" in html_content.lower() or "we could not find any matches" in html_content.lower():
                            return []
                        raise ProductNotFoundError(f"Myntra search results not found for query: '{query}'")

                    await self.human_like_scroll(page, max_scrolls=2)

                    items = await page.query_selector_all(card_selector)
                    products = []

                    for item in items:
                        if len(products) >= limit:
                            break

                        try:
                            # Product URL
                            url_el = await item.query_selector("a")
                            if not url_el:
                                continue
                            href = await url_el.get_attribute("href")
                            if not href:
                                continue
                            product_url = urllib.parse.urljoin("https://www.myntra.com", href)

                            # Title & Brand
                            brand_el = await item.query_selector("h3.product-brand")
                            name_el = await item.query_selector("h4.product-product")
                            brand = (await brand_el.inner_text()).strip() if brand_el else ""
                            name = (await name_el.inner_text()).strip() if name_el else ""
                            title = f"{brand} - {name}" if brand and name else (brand or name)
                            
                            if not title:
                                continue

                            # Price details
                            price_el = await item.query_selector("span.product-discountedPrice")
                            # Fallback if no discount
                            if not price_el:
                                price_el = await item.query_selector("div.product-price")
                            
                            if not price_el:
                                continue
                            price = self.clean_price(await price_el.inner_text())

                            original_price = None
                            original_price_el = await item.query_selector("span.product-strike")
                            if original_price_el:
                                original_price = self.clean_price(await original_price_el.inner_text())

                            discount = None
                            discount_el = await item.query_selector("span.product-discountPercentage")
                            if discount_el:
                                discount = (await discount_el.inner_text()).strip()

                            # Image
                            img_el = await item.query_selector("img.product-thumb, picture img")
                            image_url = None
                            if img_el:
                                # Myntra dynamic pages lazy-load images and put URL in src or class src-specific loader
                                image_url = await img_el.get_attribute("src")

                            # Rating
                            rating = None
                            rating_el = await item.query_selector("div.product-ratingsContainer")
                            if rating_el:
                                rating_text = (await rating_el.inner_text()).strip()
                                match = re.search(r"([\d.]+)\s*★", rating_text)
                                if match:
                                    rating = float(match.group(1))

                            products.append(Product(
                                title=title,
                                price=price,
                                currency="INR",
                                original_price=original_price,
                                discount=discount,
                                rating=rating,
                                review_count=None,
                                image_url=image_url,
                                product_url=product_url,
                                platform="myntra",
                                in_stock=True
                            ))
                        except Exception as e:
                            logger.debug(f"Skipping Myntra card parse: {e}")
                            continue

                    return products
                except Exception as e:
                    if self.detect_bot_protection(await page.content()):
                        raise ScrapingBlockedError("Blocked by Myntra bot protection during search.")
                    raise e

        return await self.execute_with_retry(_scrape(), "myntra")

    async def get_details(self, url: str) -> ProductDetails:
        async def _scrape() -> ProductDetails:
            logger.info(f"Navigating to Myntra product details: {url}")
            async with browser_manager.page_context() as page:
                await page.goto(url, wait_until="commit")
                await self.random_delay(1500, 2500)

                html_content = await page.content()
                if self.detect_bot_protection(html_content):
                    raise ScrapingBlockedError("Blocked by Myntra bot protection on product detail page.")

                # 1. Try JSON state parsing first
                pdp_data = await self._parse_myx_pdp_data(page)
                if pdp_data:
                    logger.info("Successfully extracted product details from Myntra JSON state.")
                    return pdp_data

                # 2. Fallback: DOM parsing
                logger.info("Myntra JSON details extraction failed. Falling back to DOM parsing...")
                
                title_brand_el = await page.query_selector("h1.pdp-title")
                title_name_el = await page.query_selector("h1.pdp-name")
                if not title_brand_el:
                    raise ProductNotFoundError(f"Myntra details title element not found at {url}")
                
                brand = (await title_brand_el.inner_text()).strip()
                name = (await title_name_el.inner_text()).strip() if title_name_el else ""
                title = f"{brand} - {name}" if name else brand

                price = 0.0
                price_el = await page.query_selector("span.pdp-price strong, span.pdp-price")
                if price_el:
                    price = self.clean_price(await price_el.inner_text())

                original_price = None
                original_price_el = await page.query_selector("span.pdp-mrp")
                if original_price_el:
                    original_price = self.clean_price(await original_price_el.inner_text())

                discount = None
                discount_el = await page.query_selector("span.pdp-discount")
                if discount_el:
                    discount = (await discount_el.inner_text()).strip()

                rating = None
                rating_el = await page.query_selector("div.index-overallRating div")
                if rating_el:
                    try:
                        rating = float((await rating_el.inner_text()).split()[0])
                    except Exception:
                        pass

                review_count = None
                review_el = await page.query_selector("div.index-ratingsCount")
                if review_el:
                    review_count = self.parse_review_count(await review_el.inner_text())

                # Image
                img_el = await page.query_selector("div.image-grid-image, img.pdp-image")
                image_url = None
                if img_el:
                    # In Myntra detail pages, images are often styled as backgrounds or standard img
                    style = await img_el.get_attribute("style")
                    if style and "url(" in style:
                        match = re.search(r'url\("?([^"\)]+)"?\)', style)
                        if match:
                            image_url = match.group(1)
                    else:
                        image_url = await img_el.get_attribute("src")

                in_stock = True
                stock_el = await page.query_selector("div.pdp-outOfStock")
                if stock_el:
                    in_stock = False

                description = None
                desc_el = await page.query_selector("p.pdp-product-description-content")
                if desc_el:
                    description = (await desc_el.inner_text()).strip()

                specifications = {}
                spec_rows = await page.query_selector_all("div.index-row")
                for row in spec_rows:
                    key_el = await row.query_selector("div.index-rowKey")
                    val_el = await row.query_selector("div.index-rowValue")
                    if key_el and val_el:
                        key = (await key_el.inner_text()).strip()
                        val = (await val_el.inner_text()).strip()
                        specifications[key] = val

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
                    platform="myntra",
                    in_stock=in_stock,
                    description=description,
                    specifications=specifications if specifications else None,
                    merchant=None
                )
        return await self.execute_with_retry(_scrape(), "myntra")

    # Helper JSON Script Parsers

    async def _parse_myx_search_data(self, page: Page, limit: int) -> Optional[List[Product]]:
        """Parses Search Data from window.__myx script if available."""
        try:
            scripts = await page.query_selector_all("script")
            for script in scripts:
                text = (await script.text_content()) or ""
                if "window.__myx" in text:
                    # Find JSON starting block
                    match = re.search(r"window\.__myx\s*=\s*(\{.*\})", text, re.DOTALL)
                    if match:
                        data = json.loads(match.group(1))
                        
                        # Navigate nested structure: searchData -> results -> products
                        search_data = data.get("searchData", {})
                        results = search_data.get("results", {})
                        products_raw = results.get("products", [])
                        
                        products: List[Product] = []
                        for p in products_raw:
                            if len(products) >= limit:
                                break
                            
                            try:
                                brand = p.get("brand", "")
                                name = p.get("additionalInfo", p.get("productName", ""))
                                title = f"{brand} - {name}" if brand and name else (brand or name)
                                
                                price = float(p.get("price", 0.0))
                                original_price = float(p.get("mrp", 0.0))
                                discount = p.get("discountDisplayStr")
                                
                                # Image
                                image_url = p.get("searchImage")
                                
                                # Ratings
                                rating = None
                                ratings_data = p.get("ratings", {})
                                if ratings_data:
                                    rating = float(ratings_data.get("rating", 0.0))
                                
                                review_count = None
                                if ratings_data:
                                    review_count = int(ratings_data.get("ratingCount", 0))

                                landing_page = p.get("landingPageUrl", "")
                                product_url = urllib.parse.urljoin("https://www.myntra.com/", landing_page)

                                products.append(Product(
                                    title=title,
                                    price=price,
                                    currency="INR",
                                    original_price=original_price if original_price > price else None,
                                    discount=discount,
                                    rating=rating if rating else None,
                                    review_count=review_count if review_count else None,
                                    image_url=image_url,
                                    product_url=product_url,
                                    platform="myntra",
                                    in_stock=True
                                ))
                            except Exception as parse_err:
                                logger.debug(f"JSON item parsing error: {parse_err}")
                                continue
                        return products
            return None
        except Exception as e:
            logger.warning(f"Failed parsing Myntra __myx script data: {e}")
            return None

    async def _parse_myx_pdp_data(self, page: Page) -> Optional[ProductDetails]:
        """Parses Product Details Data from window.__myx script if available."""
        try:
            scripts = await page.query_selector_all("script")
            for script in scripts:
                text = (await script.text_content()) or ""
                if "window.__myx" in text:
                    match = re.search(r"window\.__myx\s*=\s*(\{.*\})", text, re.DOTALL)
                    if match:
                        data = json.loads(match.group(1))
                        pdp_data = data.get("pdpData", {})
                        if not pdp_data:
                            continue
                        
                        brand = pdp_data.get("brand", {}).get("name", "")
                        name = pdp_data.get("name", "")
                        title = f"{brand} - {name}" if brand and name else (brand or name)
                        
                        # Price Details
                        price_data = pdp_data.get("price", {})
                        price = float(price_data.get("discounted", 0.0))
                        original_price = float(price_data.get("mrp", 0.0))
                        
                        discount = None
                        if original_price > price:
                            discount = f"{int(((original_price - price) / original_price) * 100)}% OFF"
                            
                        # Ratings
                        rating = None
                        review_count = None
                        ratings_data = pdp_data.get("ratings", {})
                        if ratings_data:
                            rating = float(ratings_data.get("averageRating", 0.0))
                            review_count = int(ratings_data.get("totalCount", 0))

                        # Image
                        media = pdp_data.get("media", {}).get("albums", [])
                        image_url = None
                        if media:
                            images = media[0].get("images", [])
                            if images:
                                image_url = images[0].get("src")

                        # Description
                        description = pdp_data.get("description", "")
                        
                        # Specifications
                        specifications = {}
                        spec_raw = pdp_data.get("specifications", {})
                        # Specifications are often dictionary clusters or lists under pdpData
                        if isinstance(spec_raw, dict):
                            for k, v in spec_raw.items():
                                if isinstance(v, dict):
                                    specifications.update(v)
                                elif isinstance(v, list):
                                    for item in v:
                                        if isinstance(item, dict) and "name" in item and "value" in item:
                                            specifications[item["name"]] = item["value"]
                        
                        # Standard product details fallback into specs
                        details_list = pdp_data.get("productDetails", [])
                        for detail in details_list:
                            title_lbl = detail.get("title", "")
                            desc_val = detail.get("description", "")
                            if title_lbl and desc_val:
                                specifications[title_lbl] = desc_val

                        # Merchant
                        merchant = None
                        sellers = pdp_data.get("sellers", [])
                        if sellers:
                            merchant = sellers[0].get("sellerName")

                        # Stock Check
                        in_stock = True
                        sizes = pdp_data.get("sizes", [])
                        # If all sizes have 0 inventory
                        available_sizes = [s for s in sizes if s.get("available", False)]
                        if not available_sizes and sizes:
                            in_stock = False

                        return ProductDetails(
                            title=title,
                            price=price,
                            currency="INR",
                            original_price=original_price if original_price > price else None,
                            discount=discount,
                            rating=rating if rating else None,
                            review_count=review_count if review_count else None,
                            image_url=image_url,
                            product_url=page.url,
                            platform="myntra",
                            in_stock=in_stock,
                            description=description if description else None,
                            specifications=specifications if specifications else None,
                            merchant=merchant
                        )
            return None
        except Exception as e:
            logger.warning(f"Failed parsing Myntra PDP window.__myx script: {e}")
            return None
