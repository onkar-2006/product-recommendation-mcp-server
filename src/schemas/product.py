from pydantic import BaseModel, Field
from typing import Dict, List, Optional

class Product(BaseModel):
    """
    Standard model representing a single product search item.
    This structure is shared by all scraper targets.
    """
    title: str = Field(..., description="The name or title of the product")
    price: float = Field(..., description="The current selling price of the item")
    currency: str = Field(default="INR", description="Pricing currency symbol or abbreviation")
    original_price: Optional[float] = Field(default=None, description="Original list price (MRP) before discounts")
    discount: Optional[str] = Field(default=None, description="Applied discount percentage or text (e.g. '15% OFF')")
    rating: Optional[float] = Field(default=None, description="Average customer rating (e.g. 4.2 out of 5.0)")
    review_count: Optional[int] = Field(default=None, description="Total count of customer reviews/ratings submitted")
    image_url: Optional[str] = Field(default=None, description="URL of the product's primary showcase image")
    product_url: str = Field(..., description="Direct hyperlink to the product's detail page")
    platform: str = Field(..., description="The e-commerce source platform (amazon, flipkart, meesho, or myntra)")
    in_stock: bool = Field(default=True, description="True if the item is currently available for purchase")
    specifications: Optional[Dict[str, str]] = Field(
        default=None, 
        description="Key-value specifications or attributes extracted from the listing (brand, color, size, etc.)"
    )

class ProductDetails(Product):
    """
    Detailed product model including deep listing information
    like extended descriptions, merchant sellers, etc.
    """
    description: Optional[str] = Field(default=None, description="Extended descriptive text of the product")
    merchant: Optional[str] = Field(default=None, description="Merchant seller name")

class CompareResult(BaseModel):
    """
    Aggregated comparison payload across multiple platforms.
    """
    query: str = Field(..., description="The original query terms searched")
    cheapest: Optional[Product] = Field(default=None, description="The lowest priced matching product item found")
    results: List[Product] = Field(
        default=[], 
        description="Ranked list of all matching items sorted by price (ascending)"
    )
