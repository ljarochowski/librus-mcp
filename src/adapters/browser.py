"""Playwright browser adapter for Librus"""
from datetime import datetime
from typing import Optional
from pathlib import Path

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from ..ports import IBrowserPort
from ..domain.models import Child, ScrapeResult, Grade, Homework, CalendarEvent, Message, Remark
from .storage import FileStorageAdapter


class PlaywrightBrowserAdapter(IBrowserPort):
    """Playwright-based browser automation for Librus"""
    
    def __init__(self, storage: FileStorageAdapter, page_timeout: int = 30000):
        self.storage = storage
        self.page_timeout = page_timeout
    
    def _cookies_path(self, child: Child) -> Path:
        return self.storage.get_context_dir(child.name) / "cookies.json"
    
    async def is_session_valid(self, child: Child) -> bool:
        cookies_file = self._cookies_path(child)
        if not cookies_file.exists():
            return False
        
        async with async_playwright() as p:
            browser = await p.webkit.launch(headless=True)
            try:
                context = await browser.new_context(storage_state=str(cookies_file))
                page = await context.new_page()
                
                await page.goto(
                    'https://synergia.librus.pl/rodzic/index',
                    timeout=5000,
                    wait_until='domcontentloaded'
                )
                
                is_valid = '/loguj' not in page.url and '/login' not in page.url
                
                await page.close()
                await context.close()
                return is_valid
            except:
                return False
            finally:
                await browser.close()
    
    async def login(self, child: Child) -> bool:
        """Perform automated login"""
        cookies_file = self._cookies_path(child)
        if cookies_file.exists():
            cookies_file.unlink()
        
        async with async_playwright() as p:
            browser = await p.webkit.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()
            
            try:
                # Step 1: Go to portal and accept cookies
                await page.goto('https://portal.librus.pl/rodzina', timeout=30000)
                
                try:
                    cookie_btn = await page.wait_for_selector('button[data-modal-submit-all]', timeout=10000)
                    if cookie_btn:
                        await cookie_btn.click()
                        await page.wait_for_timeout(1000)
                except:
                    pass
                
                # Step 2: Click Synergia menu
                try:
                    menu = await page.wait_for_selector('a.btn-synergia-top.dropdown-toggle', timeout=10000)
                    await menu.click()
                    await page.wait_for_timeout(500)
                except:
                    pass
                
                # Step 3: Click Zaloguj
                try:
                    zaloguj = await page.wait_for_selector('a[href="/rodzina/synergia/loguj"]', timeout=10000)
                    await zaloguj.click()
                    await page.wait_for_timeout(2000)
                except:
                    pass
                
                # Step 4: Wait for iframe and fill form
                iframe_el = await page.wait_for_selector('iframe#caLoginIframe', timeout=30000)
                iframe = await iframe_el.content_frame()
                
                login_input = await iframe.wait_for_selector('input#Login', state='visible', timeout=30000)
                pass_input = await iframe.wait_for_selector('input#Pass', state='visible', timeout=30000)
                
                if child.username and child.password:
                    await login_input.fill(child.username)
                    await pass_input.fill(child.password)
                    await pass_input.press('Enter')
                    await page.wait_for_timeout(3000)
                
                # Wait for successful login
                await page.wait_for_url(lambda url: '/rodzic' in url, timeout=300000)
                
                # Save cookies
                await context.storage_state(path=str(cookies_file))
                return True
                
            except Exception as e:
                print(f"Login failed: {e}")
                return False
            finally:
                await context.close()
                await browser.close()
    
    async def scrape(self, child: Child, last_scrape: Optional[str]) -> ScrapeResult:
        """Scrape Librus data"""
        cookies_file = self._cookies_path(child)
        
        async with async_playwright() as p:
            browser = await p.webkit.launch(headless=True)
            context = await browser.new_context(storage_state=str(cookies_file))
            page = await context.new_page()
            
            try:
                result = ScrapeResult(
                    child_name=child.name,
                    timestamp=datetime.now()
                )
                
                # Scrape grades
                result.grades = await self._scrape_grades(page)
                
                # Scrape homework
                result.homework = await self._scrape_homework(page, last_scrape)
                
                # Scrape calendar
                result.calendar = await self._scrape_calendar(page)
                
                # Scrape messages
                result.messages = await self._scrape_messages(page)
                
                # Scrape remarks
                result.remarks = await self._scrape_remarks(page)
                
                # Save updated cookies
                await context.storage_state(path=str(cookies_file))
                
                return result
                
            finally:
                await context.close()
                await browser.close()
    
    async def _scrape_grades(self, page: Page) -> list[Grade]:
        """Scrape grades from Librus"""
        await page.goto('https://synergia.librus.pl/przegladaj_oceny/uczen', timeout=self.page_timeout)
        await page.wait_for_load_state('networkidle')
        
        grades = []
        
        # Use JavaScript to extract grades
        raw_grades = await page.evaluate('''() => {
            const grades = [];
            const rows = document.querySelectorAll('table.decorated.stretch tbody tr');
            
            rows.forEach(row => {
                const subjectCell = row.querySelector('td:first-child');
                if (!subjectCell) return;
                
                const subject = subjectCell.textContent.trim();
                const gradeCells = row.querySelectorAll('td.center a.ocena');
                
                gradeCells.forEach(cell => {
                    const grade = cell.textContent.trim();
                    const title = cell.getAttribute('title') || '';
                    
                    // Parse title for details
                    const categoryMatch = title.match(/Kategoria:\\s*([^\\n]+)/);
                    const dateMatch = title.match(/Data:\\s*([\\d-]+)/);
                    const teacherMatch = title.match(/Nauczyciel:\\s*([^\\n]+)/);
                    const weightMatch = title.match(/Waga:\\s*([^\\n]+)/);
                    
                    grades.push({
                        subject: subject,
                        grade: grade,
                        category: categoryMatch ? categoryMatch[1].trim() : '',
                        date: dateMatch ? dateMatch[1].trim() : '',
                        teacher: teacherMatch ? teacherMatch[1].trim() : '',
                        weight: weightMatch ? weightMatch[1].trim() : ''
                    });
                });
            });
            
            return grades;
        }''')
        
        for g in raw_grades:
            grades.append(Grade(
                subject=g['subject'],
                grade=g['grade'],
                date=g.get('date'),
                category=g.get('category', ''),
                weight=g.get('weight', ''),
                teacher=g.get('teacher', '')
            ))
        
        return grades
    
    async def _scrape_homework(self, page: Page, last_scrape: Optional[str]) -> list[Homework]:
        """Scrape homework assignments"""
        from datetime import timedelta
        from dateutil.relativedelta import relativedelta
        
        today = datetime.now()
        
        if last_scrape:
            start_date = datetime.fromisoformat(last_scrape.replace('Z', '+00:00'))
        else:
            school_year_start = datetime(today.year if today.month >= 9 else today.year - 1, 9, 1)
            start_date = school_year_start
        
        end_date = today + timedelta(days=30)
        homework = []
        current = start_date
        
        while current <= end_date:
            month_end = current + relativedelta(months=1) - timedelta(days=1)
            if month_end > end_date:
                month_end = end_date
            
            date_from = current.strftime('%Y-%m-%d')
            date_to = month_end.strftime('%Y-%m-%d')
            
            await page.goto('https://synergia.librus.pl/moje_zadania')
            
            try:
                await page.wait_for_selector('#dateFrom', timeout=5000)
                await page.fill('#dateFrom', date_from)
                await page.fill('#dateTo', date_to)
                await page.click('input[name="submitFiltr"]')
                await page.wait_for_load_state('networkidle')
                
                rows = await page.locator("table.decorated tbody tr").all()
                
                for row in rows:
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
                        homework.append(Homework(
                            subject=subject,
                            teacher=teacher,
                            title=title,
                            category=category,
                            date_added=date_added,
                            date_due=date_due
                        ))
            except:
                pass
            
            current = month_end + timedelta(days=1)
        
        return homework
    
    async def _scrape_calendar(self, page: Page) -> list[CalendarEvent]:
        """Scrape calendar events"""
        await page.goto('https://synergia.librus.pl/terminarz', timeout=self.page_timeout)
        await page.wait_for_load_state('networkidle')
        
        events = []
        
        raw_events = await page.evaluate('''() => {
            const events = [];
            const cells = document.querySelectorAll('td.active');
            
            cells.forEach(cell => {
                const dateAttr = cell.getAttribute('id');
                if (!dateAttr) return;
                
                const date = dateAttr.replace('kalendarz-dzien-', '');
                const items = cell.querySelectorAll('.kalendarz-dzien-szczegoly div');
                
                items.forEach(item => {
                    events.push({
                        date: date,
                        title: item.textContent.trim(),
                        category: item.className || ''
                    });
                });
            });
            
            return events;
        }''')
        
        for e in raw_events:
            events.append(CalendarEvent(
                date=e['date'],
                title=e['title'],
                category=e.get('category', '')
            ))
        
        return events
    
    async def _scrape_messages(self, page: Page) -> list[Message]:
        """Scrape messages"""
        await page.goto('https://synergia.librus.pl/wiadomosci', timeout=self.page_timeout)
        await page.wait_for_load_state('networkidle')
        
        messages = []
        
        raw_messages = await page.evaluate('''() => {
            const messages = [];
            const rows = document.querySelectorAll('table.decorated tbody tr');
            
            rows.forEach(row => {
                const cells = row.querySelectorAll('td');
                if (cells.length < 4) return;
                
                const isNew = row.classList.contains('bold') || row.querySelector('.new');
                
                messages.push({
                    sender: cells[1]?.textContent?.trim() || '',
                    subject: cells[2]?.textContent?.trim() || '',
                    date: cells[3]?.textContent?.trim() || '',
                    isNew: isNew
                });
            });
            
            return messages;
        }''')
        
        for m in raw_messages:
            messages.append(Message(
                date=m['date'],
                sender=m['sender'],
                subject=m['subject'],
                content='',  # Would need to click into each message
                is_new=m.get('isNew', False)
            ))
        
        return messages
    
    async def _scrape_remarks(self, page: Page) -> list[Remark]:
        """Scrape teacher remarks"""
        await page.goto('https://synergia.librus.pl/uwagi', timeout=self.page_timeout)
        await page.wait_for_load_state('networkidle')
        
        remarks = []
        
        raw_remarks = await page.evaluate('''() => {
            const remarks = [];
            const rows = document.querySelectorAll('table.decorated tbody tr');
            
            rows.forEach(row => {
                const cells = row.querySelectorAll('td');
                if (cells.length < 4) return;
                
                remarks.push({
                    date: cells[0]?.textContent?.trim() || '',
                    teacher: cells[1]?.textContent?.trim() || '',
                    content: cells[3]?.textContent?.trim() || ''
                });
            });
            
            return remarks;
        }''')
        
        for r in raw_remarks:
            content = r.get('content', '').lower()
            is_positive = any(w in content for w in ['dobr', 'świetn', 'wzorn', 'aktywn'])
            
            remarks.append(Remark(
                date=r['date'],
                teacher=r['teacher'],
                content=r['content'],
                is_positive=is_positive
            ))
        
        return remarks
