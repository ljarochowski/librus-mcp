"""Librus scraping logic"""
from typing import Dict, Optional
from .scraper_js import get_scraper_js


async def scrape_librus_data(page, last_scrape: Optional[str], is_first: bool) -> Dict:
    """
    Execute JavaScript scraper in browser context.
    
    Args:
        page: Playwright page object
        last_scrape: ISO datetime string of last scrape, or None
        is_first: True for full scrape, False for delta
        
    Returns:
        Dict with markdown, rawData, and stats
    """
    js_code = get_scraper_js()
    
    result = await page.evaluate(js_code, {
        "previousScanDate": last_scrape,
        "isFirstTime": is_first
    })
    
    return result
