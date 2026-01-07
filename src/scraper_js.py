"""JavaScript scraper code for Librus"""


def get_scraper_js() -> str:
    """
    Get JavaScript code that runs in browser context to scrape Librus data.
    
    This code uses browser's fetch API and DOM parsing to extract:
    - Messages (with pagination)
    - Announcements
    - Grades
    - Calendar events
    """
    return """
    async (params) => {
        const CONFIG = {
            MAX_MESSAGES: 200,
            MAX_ANNOUNCEMENTS: 150,
            FETCH_DELAY_MS: 150,
            CALENDAR_MONTHS_AHEAD: 2
        };
        
        console.log("LIBRUS SCRAPER");
        
        const isFirstTime = params.isFirstTime;
        let lastScanDate = null;
        
        if (!isFirstTime && params.previousScanDate) {
            lastScanDate = new Date(params.previousScanDate);
            console.log(`DELTA since ${params.previousScanDate}`);
        } else {
            console.log("Mode: FULL CONTEXT");
        }
        
        const fetchPage = async (url) => {
            const response = await fetch(url);
            const html = await response.text();
            const parser = new DOMParser();
            return parser.parseFromString(html, 'text/html');
        };
        
        const parsePolishDate = (dateStr) => {
            const parts = dateStr.match(/(\\d{4})-(\\d{2})-(\\d{2}) (\\d{2}):(\\d{2}):(\\d{2})/);
            if (!parts) return null;
            return new Date(parts[1], parts[2] - 1, parts[3], parts[4], parts[5], parts[6]);
        };
        
        const now = new Date();
        const data = {
            collectionDate: now.toLocaleString('pl-PL'),
            isFirstTime,
            messages: [],
            announcements: [],
            grades: [],
            calendar: [],
            descriptiveGrade: null
        };
        
        // ====== 1. MESSAGES ======
        try {
            console.log("Fetching messages...");
            
            let allMessages = [];
            let currentPage = 0;
            let totalPages = 1;
            
            while (currentPage < totalPages && allMessages.length < CONFIG.MAX_MESSAGES) {
                const url = currentPage === 0 
                    ? 'https://synergia.librus.pl/wiadomosci'
                    : `https://synergia.librus.pl/wiadomosci?numer_strony105=${currentPage}&porcjowanie_pojemnik105=105`;
                
                console.log(`Page ${currentPage + 1}...`);
                const doc = await fetchPage(url);
                
                if (currentPage === 0) {
                    const paginationText = doc.querySelector('.pagination span')?.textContent || '';
                    const match = paginationText.match(/Strona\\s+\\d+\\s+z\\s+(\\d+)/);
                    if (match) {
                        totalPages = parseInt(match[1]);
                        console.log(`Total pages: ${totalPages}`);
                    }
                }
                
                const rows = doc.querySelectorAll("#formWiadomosci > div > div > table > tbody > tr > td:nth-child(2) > table.decorated.stretch > tbody > tr");
                console.log(`Found ${rows.length} messages on page`);
                
                for (let i = 0; i < rows.length; i++) {
                    if (allMessages.length >= CONFIG.MAX_MESSAGES) break;
                    
                    const row = rows[i];
                    const linkElement = row.querySelector("td:nth-child(4) > a");
                    
                    if (linkElement) {
                        const title = linkElement.textContent.trim();
                        const href = linkElement.getAttribute('href');
                        const sender = row.querySelector("td:nth-child(3)")?.textContent.trim() || "";
                        const dateStr = row.querySelector("td:nth-child(5)")?.textContent.trim() || "";
                        const statusImg = row.querySelector("td:nth-child(1) img");
                        const isRead = statusImg?.getAttribute('alt')?.includes('przeczytana') || false;
                        
                        if (!isFirstTime && lastScanDate) {
                            const messageDate = parsePolishDate(dateStr);
                            if (!messageDate || messageDate < lastScanDate) {
                                console.log(`Skipping old message: ${dateStr}`);
                                continue;
                            }
                        }
                        
                        let content = "", attachments = [];
                        
                        try {
                            const msgDoc = await fetchPage(`https://synergia.librus.pl${href}`);
                            
                            const contentDiv = msgDoc.querySelector(".container-message-content");
                            if (contentDiv) {
                                content = contentDiv.innerHTML
                                    .replace(/<br\\s*\\/?>/gi, '\\n')
                                    .replace(/<a\\s+href="([^"]+)"[^>]*>([^<]+)<\\/a>/gi, '[$2]($1)')
                                    .replace(/<[^>]+>/g, '')
                                    .trim();
                            }
                            
                            const fileRows = msgDoc.querySelectorAll("table tr");
                            let lookingForFiles = false;
                            
                            for (const fileRow of fileRows) {
                                const td = fileRow.querySelector("td");
                                if (td && td.textContent.includes("Pliki:")) {
                                    lookingForFiles = true;
                                    continue;
                                }
                                if (lookingForFiles && td) {
                                    const img = td.querySelector("img[src*='filetype_icons']");
                                    if (img) {
                                        const fileName = td.textContent.trim();
                                        if (fileName) attachments.push(fileName);
                                    }
                                }
                            }
                        } catch (e) {
                            content = "[Error fetching content]";
                        }
                        
                        allMessages.push({
                            title, sender, date: dateStr, isRead,
                            content, attachments: attachments.length > 0 ? attachments : null,
                            link: `https://synergia.librus.pl${href}`
                        });
                        
                        await new Promise(r => setTimeout(r, CONFIG.FETCH_DELAY_MS));
                    }
                }
                
                currentPage++;
            }
            
            data.messages = allMessages;
            console.log(`Messages: ${data.messages.length} total`);
        } catch (e) {
            console.error("Error fetching messages:", e.message);
        }
        
        // ====== 2. ANNOUNCEMENTS ======
        try {
            console.log("Fetching announcements...");
            const doc = await fetchPage('https://synergia.librus.pl/ogloszenia');
            const tables = doc.querySelectorAll("table.decorated.big.center.printable");
            
            let count = 0;
            
            for (const table of tables) {
                const thead = table.querySelector("thead > tr > td[colspan='2']");
                if (!thead) continue;
                
                count++;
                if (count > CONFIG.MAX_ANNOUNCEMENTS) break;
                
                const title = thead.textContent.trim();
                const rows = table.querySelectorAll("tbody > tr");
                let author = "", date = "", content = "";
                
                for (const row of rows) {
                    const th = row.querySelector("th");
                    const td = row.querySelector("td");
                    
                    if (th && td) {
                        const label = th.textContent.trim();
                        const value = td.textContent.trim();
                        
                        if (label === "Dodał") author = value;
                        else if (label === "Data publikacji") date = value;
                        else if (label === "Treść") content = value;
                    }
                }
                
                if (date) {
                    const announcementDate = parsePolishDate(date);
                    
                    if (isFirstTime || !lastScanDate || (announcementDate && announcementDate >= lastScanDate)) {
                        data.announcements.push({ title, content, author, date });
                    }
                }
            }
            
            console.log(`Announcements: ${data.announcements.length}`);
        } catch (e) {
            console.error("Error fetching announcements:", e.message);
        }
        
        // ====== 3. GRADES ======
        try {
            console.log("Fetching grades...");
            const doc = await fetchPage('https://synergia.librus.pl/przegladaj_oceny/uczen');
            
            // Parse ALL tables with grades
            const allTables = doc.querySelectorAll("table.decorated.stretch");
            
            for (const table of allTables) {
                const style = table.getAttribute('style') || '';
                if (style.includes('display: none') || style.includes('display:none')) continue;
                
                const rows = Array.from(table.querySelectorAll("tbody > tr"));
                
                for (const row of rows) {
                    if (row.getAttribute('name') === 'przedmioty_all') continue;
                    
                    const cells = row.querySelectorAll("td");
                    if (cells.length < 3) continue;
                    
                    const subject = cells[1]?.textContent.trim();
                    if (!subject) continue;
                    
                    // Check for nested table first (descriptive grades)
                    const nextRow = row.nextElementSibling;
                    let hasNestedGrades = false;
                    
                    if (nextRow && nextRow.getAttribute('name') === 'przedmioty_all') {
                        const nestedTable = nextRow.querySelector("table tbody");
                        if (nestedTable) {
                            const gradeRows = nestedTable.querySelectorAll("tr.detail-grades");
                            for (const gradeRow of gradeRows) {
                                const gradeCells = gradeRow.querySelectorAll("td");
                                if (gradeCells.length < 5) continue;
                                
                                const grade = gradeCells[0]?.textContent.trim();
                                const category = gradeCells[2]?.textContent.trim();
                                const date = gradeCells[4]?.textContent.trim();
                                
                                if (grade && grade !== 'Brak ocen' && category && (category.startsWith('Edukacja') || category.startsWith('Rozwój'))) {
                                    hasNestedGrades = true;
                                    data.grades.push({
                                        subject: category,
                                        grade,
                                        date: date || "",
                                        category: "",
                                        weight: "",
                                        teacher: ""
                                    });
                                }
                            }
                        }
                    }
                    
                    // Only parse span.grade-box if no nested grades found
                    if (!hasNestedGrades) {
                        const gradeCell = cells[2];
                        if (gradeCell) {
                            const gradeLinks = gradeCell.querySelectorAll('a.ocena');
                            for (const link of gradeLinks) {
                                const grade = link.textContent.trim();
                                if (grade) {
                                    data.grades.push({
                                        subject,
                                        grade,
                                        date: "",
                                        category: "",
                                        weight: "",
                                        teacher: ""
                                    });
                                }
                            }
                        }
                    }
                }
            }
            
            // Extract descriptive grade (ocena opisowa) - for primary school
            const descriptiveTables = doc.querySelectorAll("table.decorated.stretch");
            for (const table of descriptiveTables) {
                const header = table.querySelector("th strong");
                if (header && header.textContent.includes("Ocena śródroczna")) {
                    const rows = table.querySelectorAll("tbody tr");
                    for (const row of rows) {
                        const textCell = row.querySelector("td");
                        if (textCell) {
                            const paragraphs = textCell.querySelectorAll("p");
                            let descriptiveText = "";
                            for (const p of paragraphs) {
                                const text = p.textContent.trim();
                                if (text.length > 100) {
                                    descriptiveText += text + "\\n\\n";
                                }
                            }
                            if (descriptiveText) {
                                data.descriptiveGrade = descriptiveText.trim();
                                break;
                            }
                        }
                    }
                }
            }
        } catch (e) {
            console.error("Error fetching grades:", e.message);
        }
        
        // ====== 4. CALENDAR ======
        try {
            const today = new Date();
            
            for (let offset = 0; offset <= CONFIG.CALENDAR_MONTHS_AHEAD; offset++) {
                const date = new Date(today.getFullYear(), today.getMonth() + offset, 1);
                const year = date.getFullYear();
                const month = String(date.getMonth() + 1).padStart(2, '0');
                
                const doc = await fetchPage(`https://synergia.librus.pl/terminarz?rok=${year}&miesiac=${month}`);
                const events = doc.querySelectorAll(".line0, .line1");
                
                for (const event of events) {
                    const eventDate = event.querySelector("td:nth-child(1)")?.textContent.trim() || "";
                    const title = event.querySelector("td:nth-child(2)")?.textContent.trim() || "";
                    const category = event.querySelector("td:nth-child(3)")?.textContent.trim() || "";
                    
                    if (title) {
                        data.calendar.push({
                            date: eventDate,
                            title,
                            category
                        });
                    }
                }
                
                await new Promise(r => setTimeout(r, CONFIG.FETCH_DELAY_MS));
            }
        } catch (e) {
            console.error("Error fetching calendar:", e.message);
        }
        
        // ====== 5. HOMEWORK ======
        // NOTE: Homework is scraped via Python (POST form) - see scraper.py
        console.log("Homework will be scraped via Python");
        
        // ====== 6. REMARKS/NOTES ======
        try {
            console.log("Fetching remarks...");
            const doc = await fetchPage('https://synergia.librus.pl/uwagi');
            const rows = doc.querySelectorAll("table.decorated tbody tr");
            
            for (const row of rows) {
                const cells = row.querySelectorAll("td");
                if (cells.length < 4) continue;
                
                const content = cells[0]?.textContent.trim() || "";
                const date = cells[1]?.textContent.trim() || "";
                const teacher = cells[2]?.textContent.trim() || "";
                const category = cells[3]?.textContent.trim() || "";
                
                if (content) {
                    data.remarks = data.remarks || [];
                    data.remarks.push({
                        date,
                        teacher,
                        category,
                        content
                    });
                }
            }
            console.log(`Remarks: ${data.remarks?.length || 0}`);
        } catch (e) {
            console.error("Error fetching remarks:", e.message);
        }
        
        // ====== GENERATE MARKDOWN ======
        let md = `# Librus Data - ${data.messages[0]?.sender.split(' ')[0] || 'Student'}\\n`;
        md += `**Collection date:** ${data.collectionDate}\\n\\n`;
        
        md += `## Messages (${data.messages.length})\\n\\n`;
        data.messages.forEach((m, i) => {
            md += `### ${m.isRead ? '[READ]' : '[NEW]'} ${i + 1}. ${m.title}\\n`;
            md += `- **From:** ${m.sender}\\n`;
            md += `- **Date:** ${m.date}\\n`;
            if (m.attachments) md += `- **Attachments:** ${m.attachments.join(', ')}\\n`;
            md += `\\n**Content:**\\n${m.content}\\n\\n---\\n\\n`;
        });
        
        md += `## Announcements (${data.announcements.length})\\n\\n`;
        data.announcements.forEach((a, i) => {
            md += `### ${i + 1}. ${a.title}\\n`;
            md += `- **Date:** ${a.date}\\n`;
            md += `- **Author:** ${a.author}\\n\\n`;
            md += `${a.content}\\n\\n---\\n\\n`;
        });
        
        md += `## Grades (${data.grades.length})\\n\\n`;
        const gradesBySubject = {};
        data.grades.forEach(g => {
            if (!gradesBySubject[g.subject]) gradesBySubject[g.subject] = [];
            gradesBySubject[g.subject].push(g);
        });
        
        for (const [subject, grades] of Object.entries(gradesBySubject)) {
            md += `### ${subject}\\n\\n`;
            grades.forEach(g => {
                md += `- **${g.grade}** (${g.category}, weight: ${g.weight}) - ${g.date}\\n`;
            });
            md += `\\n`;
        }
        
        md += `## Calendar (${data.calendar.length})\\n\\n`;
        data.calendar.forEach(e => {
            md += `- **${e.date}** - ${e.title} (${e.category})\\n`;
        });
        
        md += `## Homework (${data.homework?.length || 0})\\n\\n`;
        (data.homework || []).forEach((h, i) => {
            md += `### ${i + 1}. ${h.subject} - ${h.title}\\n`;
            md += `- **Teacher:** ${h.teacher}\\n`;
            md += `- **Category:** ${h.category}\\n`;
            md += `- **Added:** ${h.dateAdded}\\n`;
            md += `- **Due:** ${h.dateDue}\\n\\n`;
        });
        
        md += `## Remarks/Notes (${data.remarks?.length || 0})\\n\\n`;
        (data.remarks || []).forEach((r, i) => {
            md += `### ${i + 1}. ${r.category}\\n`;
            md += `- **Date:** ${r.date}\\n`;
            md += `- **Teacher:** ${r.teacher}\\n`;
            md += `- **Content:** ${r.content}\\n\\n`;
        });
        
        return {
            markdown: md,
            rawData: data,
            stats: {
                messages: data.messages.length,
                announcements: data.announcements.length,
                grades: data.grades.length,
                calendar: data.calendar.length,
                homework: data.homework?.length || 0,
                remarks: data.remarks?.length || 0
            }
        };
    }
    """
