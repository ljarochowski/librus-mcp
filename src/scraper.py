"""Librus scraping logic"""
from typing import Dict, Optional, List
from .scraper_js import get_scraper_js


async def scrape_homework(page) -> List[Dict]:
    """Scrape homework using POST form submission"""
    await page.goto('https://synergia.librus.pl/moje_zadania')
    
    # Set date range to full school year
    from datetime import datetime
    today = datetime.now()
    school_year_start = datetime(today.year if today.month >= 9 else today.year - 1, 9, 1)
    school_year_end = datetime(today.year + 1 if today.month >= 9 else today.year, 8, 31)
    
    date_from = school_year_start.strftime('%Y-%m-%d')
    date_to = school_year_end.strftime('%Y-%m-%d')
    
    await page.fill('#dateFrom', date_from)
    await page.fill('#dateTo', date_to)
    await page.click('input[name="submitFiltr"]')
    await page.wait_for_load_state('networkidle')
    
    # Extract homework data
    homework = []
    row_count = await page.locator("table.decorated tbody tr").count()
    
    for i in range(row_count):
        row = page.locator("table.decorated tbody tr").nth(i)
        cells = await row.locator("td").all()
        if len(cells) < 7:
            continue
        
        subject = (await cells[0].text_content() or "").strip()
        teacher = (await cells[1].text_content() or "").strip()
        title = (await cells[2].text_content() or "").strip()
        category = (await cells[3].text_content() or "").strip()
        date_added = (await cells[4].text_content() or "").strip()
        date_due = (await cells[6].text_content() or "").strip()
        
        if title and subject:
            homework.append({
                "subject": subject,
                "teacher": teacher,
                "title": title,
                "category": category,
                "dateAdded": date_added,
                "dateDue": date_due
            })
    
    return homework


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
    
    # Add homework scraped via Python (POST form)
    homework = await scrape_homework(page)
    result['homework'] = homework
    result['stats']['homework'] = len(homework)
    
    return result
