"""Librus scraping logic"""
from typing import Dict, Optional, List
from .scraper_js import get_scraper_js


async def scrape_homework(page, last_scrape: Optional[str] = None) -> List[Dict]:
    """Scrape homework using POST form submission, iterating by month"""
    from datetime import datetime, timedelta
    from dateutil.relativedelta import relativedelta
    
    today = datetime.now()
    
    if last_scrape:
        # Delta mode: from last scrape to +30 days
        start_date = datetime.fromisoformat(last_scrape.replace('Z', '+00:00'))
        end_date = today + timedelta(days=30)
    else:
        # Full mode: from Sept 1 of school year to today +30 days
        school_year_start = datetime(today.year if today.month >= 9 else today.year - 1, 9, 1)
        start_date = school_year_start
        end_date = today + timedelta(days=30)
    
    homework = []
    current = start_date
    
    # Iterate month by month
    while current <= end_date:
        month_end = current + relativedelta(months=1) - timedelta(days=1)
        if month_end > end_date:
            month_end = end_date
        
        date_from = current.strftime('%Y-%m-%d')
        date_to = month_end.strftime('%Y-%m-%d')
        
        await page.goto('https://synergia.librus.pl/moje_zadania')
        
        # Wait for form to load
        try:
            await page.wait_for_selector('#dateFrom', timeout=5000)
        except:
            # No homework form - skip this month
            current = month_end + timedelta(days=1)
            continue
        
        await page.fill('#dateFrom', date_from)
        await page.fill('#dateTo', date_to)
        await page.click('input[name="submitFiltr"]')
        await page.wait_for_load_state('networkidle')
        
        # Extract homework data
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
        
        current = month_end + timedelta(days=1)
    
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
    homework = await scrape_homework(page, None if is_first else last_scrape)
    result['homework'] = homework
    result['stats']['homework'] = len(homework)
    
    return result
