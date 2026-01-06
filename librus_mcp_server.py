#!/usr/bin/env python3
"""
Librus MCP Server - Multi-child scraper with auto-login and memory
"""

import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import Dict

from playwright.async_api import async_playwright
from mcp.server import Server
from mcp.types import Tool, TextContent

# ============================================================================
# CONFIG
# ============================================================================

BASE_DIR = Path.home() / ".librus_scraper"
BASE_DIR.mkdir(exist_ok=True)

SCRIPT_DIR = Path(__file__).parent
CREDENTIALS_FILE = SCRIPT_DIR / "credentials.json"

CONFIG = {
    "HEADLESS": False,
    "LOGIN_TIMEOUT": 120000,
}

# ============================================================================
# CREDENTIALS
# ============================================================================

def load_credentials() -> Dict:
    if not CREDENTIALS_FILE.exists():
        raise FileNotFoundError(
            f"Brak pliku credentials.json!\n"
            f"Skopiuj credentials.json.example i wypełnij danymi:\n"
            f"cp {SCRIPT_DIR}/credentials.json.example {CREDENTIALS_FILE}"
        )
    
    with open(CREDENTIALS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_child_credentials(child_name: str) -> Dict:
    creds = load_credentials()
    for child in creds.get("children", []):
        if child["name"].lower() == child_name.lower():
            return child
    raise ValueError(f"Brak credentials dla dziecka: {child_name}")

# ============================================================================
# FILE MANAGEMENT
# ============================================================================

def get_child_dir(child_name: str) -> Path:
    safe_name = child_name.lower().replace(" ", "-")
    child_dir = BASE_DIR / safe_name
    child_dir.mkdir(parents=True, exist_ok=True)
    return child_dir

def get_context_dir(child_name: str) -> Path:
    context_dir = get_child_dir(child_name) / "browser_context"
    context_dir.mkdir(exist_ok=True)
    return context_dir

def load_state(child_name: str) -> Dict:
    state_file = get_child_dir(child_name) / "state.json"
    if state_file.exists():
        with open(state_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "child_name": child_name,
        "last_scrape_iso": None,
        "setup_completed": False
    }

def save_state(child_name: str, state: Dict):
    state_file = get_child_dir(child_name) / "state.json"
    with open(state_file, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def load_memory(child_name: str) -> Dict:
    memory_file = get_child_dir(child_name) / "memory.json"
    if memory_file.exists():
        with open(memory_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "child_name": child_name,
        "trends": {},
        "recurring_issues": [],
        "action_items": [],
        "parent_notes": [],
        "grade_history": {},
        "last_updated": None
    }

def save_memory(child_name: str, memory: Dict):
    memory_file = get_child_dir(child_name) / "memory.json"
    memory["last_updated"] = datetime.now().isoformat()
    with open(memory_file, 'w', encoding='utf-8') as f:
        json.dump(memory, f, indent=2, ensure_ascii=False)

def save_scrape_result(child_name: str, markdown: str):
    latest_file = get_child_dir(child_name) / "latest.md"
    with open(latest_file, 'w', encoding='utf-8') as f:
        f.write(markdown)
    
    history_dir = get_child_dir(child_name) / "history"
    history_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    history_file = history_dir / f"{timestamp}.md"
    with open(history_file, 'w', encoding='utf-8') as f:
        f.write(markdown)

# ============================================================================
# BROWSER & AUTO-LOGIN
# ============================================================================

async def get_browser_context(child_name: str, browser):
    context_dir = get_context_dir(child_name)
    state = load_state(child_name)
    
    cookies_file = context_dir / "cookies.json"
    
    if cookies_file.exists() and state.get("setup_completed"):
        print(f"🔐 [{child_name}] Auto-login (załadowano sesję)")
        context = await browser.new_context(storage_state=str(cookies_file))
    else:
        print(f"🔐 [{child_name}] PIERWSZA KONFIGURACJA - automatyczne logowanie...")
        creds = get_child_credentials(child_name)
        
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto('https://portal.librus.pl/rodzina/synergia/loguj')
        
        # Wypełnij formularz
        try:
            await page.fill('input[name="login"]', creds["login"])
            await page.fill('input[name="pass"]', creds["password"])
            await page.click('button[type="submit"]')
            
            print(f"⏳ Czekam na zalogowanie dla {child_name}...")
            await page.wait_for_url(lambda url: '/rodzic' in url, timeout=CONFIG["LOGIN_TIMEOUT"])
            print(f"✅ Zalogowano!")
        except Exception as e:
            print(f"⚠️ Automatyczne logowanie nie powiodło się: {e}")
            print(f"⏳ Zaloguj się ręcznie w przeglądarce...")
            await page.wait_for_url(lambda url: '/rodzic' in url, timeout=CONFIG["LOGIN_TIMEOUT"])
            print(f"✅ Zalogowano ręcznie!")
        
        await context.storage_state(path=str(cookies_file))
        print(f"💾 Sesja zapisana!")
        
        state["setup_completed"] = True
        save_state(child_name, state)
    
    return context

# ============================================================================
# SCRAPING
# ============================================================================

async def scrape_librus(child_name: str, force_full: bool = False) -> Dict:
    state = load_state(child_name)
    last_scrape = state.get("last_scrape_iso")
    is_first = last_scrape is None or force_full
    
    mode = "PEŁNY" if is_first else f"DELTA od {last_scrape}"
    
    print(f"\n{'='*60}")
    print(f"🚀 {child_name} - {mode}")
    print(f"{'='*60}\n")
    
    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=CONFIG["HEADLESS"])
        context = await get_browser_context(child_name, browser)
        page = await context.new_page()
        
        await page.goto('https://synergia.librus.pl/rodzic/index')
        
        js_code = await load_scraping_js()
        
        result = await page.evaluate(js_code, {
            "previousScanDate": last_scrape,
            "isFirstTime": is_first
        })
        
        now = datetime.now()
        state["last_scrape_iso"] = now.strftime("%Y-%m-%d %H:%M:%S")
        save_state(child_name, state)
        
        save_scrape_result(child_name, result["markdown"])
        await update_memory(child_name, result.get("rawData", {}))
        
        await context.close()
        await browser.close()
        
        return {
            "markdown": result["markdown"],
            "stats": result["stats"],
            "mode": mode,
            "child_name": child_name
        }

async def load_scraping_js() -> str:
    return """
    async (params) => {
        const CONFIG = {
            MAX_WIADOMOSCI_SAFETY: 200,
            MAX_OGLOSZENIA_SAFETY: 150,
            FETCH_DELAY_MS: 150,
            TERMINARZ_MIESIACE_NAPRZOD: 2
        };
        
        console.log("🚀 LIBRUS SCRAPER - Playwright Mode");
        
        const czyPierwszyRaz = params.isFirstTime;
        let dataOstatniegoPobierania = null;
        
        if (!czyPierwszyRaz && params.previousScanDate) {
            dataOstatniegoPobierania = new Date(params.previousScanDate);
            console.log(`✅ DELTA od ${params.previousScanDate}`);
        } else {
            console.log("📅 Tryb: PEŁNY KONTEKST");
        }
        
        // Helper functions
        function pobierzImieNazwisko() {
            const el = document.querySelector("#user-section > b");
            if (!el) return { pelne: "Nieznane", imie: "nieznane", nazwisko: "" };
            const text = el.textContent.trim().replace(/\\(rodzic.*?\\)/g, '').trim();
            const parts = text.split(/\\s+/);
            return { pelne: text, imie: parts[0] || "nieznane", nazwisko: parts[1] || "" };
        }
        
        async function fetchPage(url, method = 'GET', body = null) {
            const options = {
                method,
                credentials: 'same-origin',
                headers: { 'Accept': 'text/html' }
            };
            if (body) options.body = body;
            
            const response = await fetch(url, options);
            const html = await response.text();
            return new DOMParser().parseFromString(html, 'text/html');
        }
        
        function parsePolishDate(dateStr) {
            if (!dateStr) return null;
            dateStr = dateStr.trim().split(' ')[0];
            if (dateStr.match(/^\\d{4}-\\d{2}-\\d{2}$/)) return new Date(dateStr);
            if (dateStr.match(/^\\d{2}\\.\\d{2}\\.\\d{4}$/)) {
                const [d, m, r] = dateStr.split('.');
                return new Date(`${r}-${m}-${d}`);
            }
            return null;
        }
        
        function getPoczatekTygodnia() {
            const dzisiaj = new Date();
            const dzien = dzisiaj.getDay();
            const diff = dzien === 0 ? 6 : dzien - 1;
            const pon = new Date(dzisiaj);
            pon.setDate(dzisiaj.getDate() - diff);
            pon.setHours(0, 0, 0, 0);
            return pon;
        }
        
        const dziecko = pobierzImieNazwisko();
        const teraz = new Date();
        const poczatekTygodnia = getPoczatekTygodnia();
        
        const dane = {
            dziecko: dziecko.pelne,
            imie: dziecko.imie,
            nazwisko: dziecko.nazwisko,
            dataZbierania: teraz.toLocaleString('pl-PL'),
            czyPierwszyRaz,
            wiadomosci: [],
            ogloszenia: [],
            oceny: [],
            terminarz: []
        };
        
        // ====== 1. WIADOMOŚCI ======
        try {
            console.log("📧 Pobieram wiadomości...");
            const doc = await fetchPage('https://synergia.librus.pl/wiadomosci');
            const wiersze = doc.querySelectorAll("#formWiadomosci > div > div > table > tbody > tr > td:nth-child(2) > table.decorated.stretch > tbody > tr");
            
            let przetworzone = 0;
            
            for (let i = 0; i < Math.min(wiersze.length, CONFIG.MAX_WIADOMOSCI_SAFETY); i++) {
                const wiersz = wiersze[i];
                const linkElement = wiersz.querySelector("td:nth-child(4) > a");
                
                if (linkElement) {
                    const tytul = linkElement.textContent.trim();
                    const href = linkElement.getAttribute('href');
                    const nadawca = wiersz.querySelector("td:nth-child(3)")?.textContent.trim() || "";
                    const dataStr = wiersz.querySelector("td:nth-child(5)")?.textContent.trim() || "";
                    const statusImg = wiersz.querySelector("td:nth-child(1) img");
                    const czyPrzeczytana = statusImg?.getAttribute('alt')?.includes('przeczytana') || false;
                    
                    if (!czyPierwszyRaz && dataOstatniegoPobierania) {
                        const dataWiadomosci = parsePolishDate(dataStr);
                        if (!dataWiadomosci || dataWiadomosci < dataOstatniegoPobierania) {
                            continue;
                        }
                    }
                    
                    przetworzone++;
                    
                    let tresc = "", zalaczniki = [];
                    
                    try {
                        const docWiadomosc = await fetchPage(`https://synergia.librus.pl${href}`);
                        
                        const trescDiv = docWiadomosc.querySelector(".container-message-content");
                        if (trescDiv) {
                            tresc = trescDiv.innerHTML
                                .replace(/<br\\s*\\/?>/gi, '\\n')
                                .replace(/<a\\s+href="([^"]+)"[^>]*>([^<]+)<\\/a>/gi, '[$2]($1)')
                                .replace(/<[^>]+>/g, '')
                                .trim();
                        }
                        
                        const plikiRows = docWiadomosc.querySelectorAll("table tr");
                        let szukaj = false;
                        
                        for (const row of plikiRows) {
                            const td = row.querySelector("td");
                            if (td && td.textContent.includes("Pliki:")) {
                                szukaj = true;
                                continue;
                            }
                            if (szukaj && td) {
                                const img = td.querySelector("img[src*='filetype_icons']");
                                if (img) {
                                    const nazwa = td.textContent.trim();
                                    if (nazwa) zalaczniki.push(nazwa);
                                }
                            }
                        }
                    } catch (e) {
                        tresc = "[Błąd pobierania]";
                    }
                    
                    dane.wiadomosci.push({
                        tytul, nadawca, data: dataStr, przeczytana: czyPrzeczytana,
                        tresc, zalaczniki: zalaczniki.length > 0 ? zalaczniki : null,
                        link: `https://synergia.librus.pl${href}`
                    });
                    
                    await new Promise(r => setTimeout(r, CONFIG.FETCH_DELAY_MS));
                }
            }
            console.log(`✅ Wiadomości: ${dane.wiadomosci.length}`);
        } catch (e) {
            console.error("❌ Błąd wiadomości:", e.message);
        }
        
        // ====== 2. OGŁOSZENIA ======
        try {
            console.log("📢 Pobieram ogłoszenia...");
            const doc = await fetchPage('https://synergia.librus.pl/ogloszenia');
            const tabele = doc.querySelectorAll("table.decorated.big.center.printable");
            
            let wszystkie = 0;
            
            for (const tabela of tabele) {
                const thead = tabela.querySelector("thead > tr > td[colspan='2']");
                if (!thead) continue;
                
                wszystkie++;
                if (wszystkie > CONFIG.MAX_OGLOSZENIA_SAFETY) break;
                
                const tytul = thead.textContent.trim();
                const wiersze = tabela.querySelectorAll("tbody > tr");
                let autor = "", data = "", tresc = "";
                
                for (const wiersz of wiersze) {
                    const th = wiersz.querySelector("th");
                    const td = wiersz.querySelector("td");
                    
                    if (th && td) {
                        const label = th.textContent.trim();
                        const value = td.textContent.trim();
                        
                        if (label === "Dodał") autor = value;
                        else if (label === "Data publikacji") data = value;
                        else if (label === "Treść") tresc = value;
                    }
                }
                
                if (data) {
                    const dataOgl = parsePolishDate(data);
                    
                    if (czyPierwszyRaz || !dataOstatniegoPobierania || (dataOgl && dataOgl >= dataOstatniegoPobierania)) {
                        dane.ogloszenia.push({ tytul, tresc, autor, data });
                    }
                }
            }
            
            console.log(`✅ Ogłoszenia: ${dane.ogloszenia.length}`);
        } catch (e) {
            console.error("❌ Błąd ogłoszenia:", e.message);
        }
        
        // ====== 3. OCENY ======
        try {
            console.log("📊 Pobieram oceny...");
            const doc = await fetchPage('https://synergia.librus.pl/przegladaj_oceny/uczen');
            
            const wszystkieTabele = doc.querySelectorAll("table.decorated.stretch");
            let tabelaGlowna = null;
            
            for (const tabela of wszystkieTabele) {
                const style = tabela.getAttribute('style') || '';
                if (style.includes('display: none') || style.includes('display:none')) continue;
                
                const naglowki = tabela.querySelectorAll("thead td");
                const maPrzedmiot = Array.from(naglowki).some(n => n.textContent.trim() === "Przedmiot");
                
                if (maPrzedmiot) {
                    tabelaGlowna = tabela;
                    break;
                }
            }
            
            if (!tabelaGlowna) throw new Error("Brak tabeli");
            
            const wiersze = Array.from(tabelaGlowna.querySelectorAll("tbody > tr"));
            
            for (const wiersz of wiersze) {
                if (wiersz.getAttribute('name') === 'przedmioty_all') continue;
                
                const komorki = wiersz.querySelectorAll("td");
                if (komorki.length < 6) continue;
                
                const nazwaPrzedmiotu = komorki[1]?.textContent.trim();
                
                if (!nazwaPrzedmiotu || nazwaPrzedmiotu === "Przedmiot" || 
                    nazwaPrzedmiotu.includes("Zachowanie") || wiersz.classList.contains('bolded')) {
                    continue;
                }
                
                const ocenyOkres1 = komorki[2];
                const ocenyOkres2 = komorki[5];
                
                for (const { element, numer } of [{ element: ocenyOkres1, numer: 1 }, { element: ocenyOkres2, numer: 2 }]) {
                    if (!element) continue;
                    
                    const linkiOcen = element.querySelectorAll("a.ocena");
                    
                    for (const link of linkiOcen) {
                        const title = link.getAttribute('title');
                        if (!title) continue;
                        
                        const ocena = link.textContent.trim();
                        const dataMatch = title.match(/Data:\\s*(\\d{4}-\\d{2}-\\d{2})/);
                        if (!dataMatch) continue;
                        
                        const dataOceny = new Date(dataMatch[1]);
                        
                        if (czyPierwszyRaz || !dataOstatniegoPobierania || dataOceny >= dataOstatniegoPobierania) {
                            const kategoriaMatch = title.match(/Kategoria:\\s*([^<\\n]+)/);
                            const nauczycielMatch = title.match(/Nauczyciel:\\s*([^<\\n]+)/);
                            const komentarzMatch = title.match(/Komentarz:\\s*(.+?)$/s);
                            
                            dane.oceny.push({
                                przedmiot: nazwaPrzedmiotu,
                                okres: numer,
                                ocena,
                                data: dataMatch[1],
                                kategoria: kategoriaMatch?.[1]?.trim() || "",
                                nauczyciel: nauczycielMatch?.[1]?.trim() || "",
                                komentarz: komentarzMatch?.[1]?.trim().replace(/<br\\s*\\/?>/gi, ' ') || ""
                            });
                        }
                    }
                }
            }
            
            console.log(`✅ Oceny: ${dane.oceny.length}`);
        } catch (e) {
            console.error("❌ Błąd oceny:", e.message);
        }
        
        // ====== 4. TERMINARZ ======
        try {
            console.log("📅 Pobieram terminarz...");
            
            const dzisiaj = new Date();
            const miesiace = [];
            for (let i = 0; i <= CONFIG.TERMINARZ_MIESIACE_NAPRZOD; i++) {
                const data = new Date(dzisiaj.getFullYear(), dzisiaj.getMonth() + i, 1);
                miesiace.push({ rok: data.getFullYear(), miesiac: data.getMonth() + 1 });
            }
            
            for (const { rok, miesiac } of miesiace) {
                const formData = new FormData();
                formData.append('miesiac', miesiac);
                formData.append('rok', rok);
                
                const doc = await fetchPage('https://synergia.librus.pl/terminarz', 'POST', formData);
                
                const kalendarz = doc.querySelector("table.kalendarz.decorated.center");
                if (!kalendarz) continue;
                
                const komorki = kalendarz.querySelectorAll("tbody tr td");
                
                for (const komorka of komorki) {
                    const dzienDiv = komorka.querySelector("div.kalendarz-dzien");
                    if (!dzienDiv) continue;
                    
                    const numerDnia = dzienDiv.querySelector("div.kalendarz-numer-dnia")?.textContent.trim();
                    if (!numerDnia) continue;
                    
                    const dataStr = `${rok}-${String(miesiac).padStart(2,'0')}-${String(numerDnia).padStart(2,'0')}`;
                    
                    const wydarzeniaTabela = dzienDiv.querySelector("table");
                    if (!wydarzeniaTabela) continue;
                    
                    const wydarzeniaCells = wydarzeniaTabela.querySelectorAll("tbody tr td");
                    
                    for (const cell of wydarzeniaCells) {
                        const tresc = cell.textContent.trim();
                        const title = cell.getAttribute('title') || '';
                        
                        let rodzaj = "Inne";
                        if (tresc.includes("Sprawdzian")) rodzaj = "Sprawdzian";
                        else if (tresc.includes("Kartkówka")) rodzaj = "Kartkówka";
                        else if (tresc.includes("Wywiadówka")) rodzaj = "Wywiadówka";
                        
                        const przedmiotSpan = cell.querySelector("span.przedmiot");
                        const przedmiot = przedmiotSpan ? przedmiotSpan.textContent.trim() : "";
                        
                        const lekcjaMatch = tresc.match(/Nr lekcji:\\s*(\\d+)/);
                        const lekcja = lekcjaMatch ? lekcjaMatch[1] : "";
                        
                        const nauczycielMatch = title.match(/Nauczyciel:\\s*([^<\\n]+)/);
                        const nauczyciel = nauczycielMatch ? nauczycielMatch[1].trim() : "";
                        
                        const opisMatch = title.match(/Opis:\\s*(.+?)(?=<br>Data dodania|$)/s);
                        const opis = opisMatch ? opisMatch[1].trim().replace(/<br\\s*\\/?>/gi, '\\n') : tresc;
                        
                        dane.terminarz.push({
                            data: dataStr,
                            rodzaj,
                            przedmiot,
                            lekcja,
                            nauczyciel,
                            opis: opis || tresc
                        });
                    }
                }
                
                await new Promise(r => setTimeout(r, CONFIG.FETCH_DELAY_MS));
            }
            
            dane.terminarz = dane.terminarz.filter(t => {
                if (!t.data) return true;
                const dataWyd = new Date(t.data);
                return dataWyd >= poczatekTygodnia;
            });
            
            dane.terminarz.sort((a, b) => (a.data || '').localeCompare(b.data || ''));
            
            console.log(`✅ Wydarzenia: ${dane.terminarz.length}`);
        } catch (e) {
            console.error("❌ Błąd terminarz:", e.message);
        }
        
        // ====== MARKDOWN ======
        const terazISO = teraz.toISOString().replace('T', ' ').substring(0, 19);
        let markdown = `# Dane z Librusa - ${dane.dziecko}\\n**Data pobrania:** ${dane.dataZbierania}\\n\\n`;
        
        // Wiadomości
        markdown += `## 📧 Wiadomości (${dane.wiadomosci.length})\\n\\n`;
        if (dane.wiadomosci.length > 0) {
            dane.wiadomosci.forEach((w, i) => {
                const status = w.przeczytana ? '✅' : '🔴';
                markdown += `### ${status} ${i + 1}. ${w.tytul}\\n- **Od:** ${w.nadawca}\\n- **Data:** ${w.data}\\n`;
                if (w.zalaczniki) markdown += `- **Załączniki:** ${w.zalaczniki.join(', ')}\\n`;
                markdown += `\\n**Treść:**\\n\\n${w.tresc}\\n\\n---\\n\\n`;
            });
        } else {
            markdown += `*Brak wiadomości*\\n\\n`;
        }
        
        // Ogłoszenia
        markdown += `## 📢 Ogłoszenia (${dane.ogloszenia.length})\\n\\n`;
        if (dane.ogloszenia.length > 0) {
            dane.ogloszenia.forEach((o, i) => {
                markdown += `### ${i + 1}. ${o.tytul}\\n- **Autor:** ${o.autor}\\n- **Data:** ${o.data}\\n\\n${o.tresc}\\n\\n---\\n\\n`;
            });
        } else {
            markdown += `*Brak ogłoszeń*\\n\\n`;
        }
        
        // Oceny
        markdown += `## 📊 Oceny (${dane.oceny.length})\\n\\n`;
        if (dane.oceny.length > 0) {
            const grouped = {};
            dane.oceny.forEach(o => {
                if (!grouped[o.przedmiot]) grouped[o.przedmiot] = [];
                grouped[o.przedmiot].push(o);
            });
            
            for (const [przedmiot, oceny] of Object.entries(grouped)) {
                markdown += `### ${przedmiot}\\n\\n`;
                oceny.forEach(o => {
                    markdown += `- **${o.ocena}** (${o.kategoria}) - ${o.data}\\n  - Nauczyciel: ${o.nauczyciel}\\n`;
                    if (o.komentarz) markdown += `  - Komentarz: ${o.komentarz}\\n`;
                    markdown += `\\n`;
                });
            }
        } else {
            markdown += `*Brak ocen*\\n\\n`;
        }
        
        // Terminarz
        markdown += `## 📅 Terminarz (${dane.terminarz.length})\\n\\n`;
        if (dane.terminarz.length > 0) {
            dane.terminarz.forEach((t, i) => {
                markdown += `### ${i + 1}. ${t.rodzaj}\\n- **Data:** ${t.data}\\n`;
                if (t.lekcja) markdown += `- **Lekcja:** ${t.lekcja}\\n`;
                if (t.przedmiot) markdown += `- **Przedmiot:** ${t.przedmiot}\\n`;
                markdown += `- **Szczegóły:** ${t.opis}\\n\\n`;
            });
        } else {
            markdown += `*Brak wydarzeń*\\n\\n`;
        }
        
        // RETURN
        return {
            markdown: markdown,
            stats: {
                wiadomosci: dane.wiadomosci.length,
                ogloszenia: dane.ogloszenia.length,
                oceny: dane.oceny.length,
                terminarz: dane.terminarz.length
            },
            rawData: dane
        };
    }
    """

# ============================================================================
# MEMORY MANAGEMENT
# ============================================================================

async def update_memory(child_name: str, raw_data: Dict):
    memory = load_memory(child_name)
    
    for ocena in raw_data.get("oceny", []):
        przedmiot = ocena["przedmiot"]
        if przedmiot not in memory["grade_history"]:
            memory["grade_history"][przedmiot] = []
        
        memory["grade_history"][przedmiot].append({
            "ocena": ocena["ocena"],
            "data": ocena["data"],
            "kategoria": ocena.get("kategoria", "")
        })
        memory["grade_history"][przedmiot] = memory["grade_history"][przedmiot][-20:]
    
    for przedmiot, grades in memory["grade_history"].items():
        if len(grades) >= 3:
            recent = grades[-3:]
            vals = []
            for g in recent:
                try:
                    val = g["ocena"].replace("+", ".5").replace("-", ".0")
                    vals.append(float(val.split()[0]))
                except:
                    pass
            
            if len(vals) >= 3:
                if vals[-1] < vals[0] - 0.5:
                    trend = "SPADEK ⚠️"
                elif vals[-1] > vals[0] + 0.5:
                    trend = "WZROST ✅"
                else:
                    trend = "STABILNY"
                
                if przedmiot not in memory["trends"]:
                    memory["trends"][przedmiot] = {}
                memory["trends"][przedmiot]["kierunek"] = trend
                memory["trends"][przedmiot]["ostatnie"] = [g["ocena"] for g in recent]
    
    save_memory(child_name, memory)

def format_memory(memory: Dict) -> str:
    lines = []
    
    if memory.get("trends"):
        lines.append("### 📊 Trendy:\n")
        for przedmiot, trend in memory["trends"].items():
            lines.append(f"- **{przedmiot}**: {trend.get('kierunek', '')} (ostatnie: {', '.join(trend.get('ostatnie', []))})")
        lines.append("")
    
    if memory.get("recurring_issues"):
        lines.append("### ⚠️ Problemy:\n")
        for issue in memory["recurring_issues"]:
            lines.append(f"- {issue}")
        lines.append("")
    
    if memory.get("action_items"):
        lines.append("### ✅ TODO:\n")
        for item in memory["action_items"]:
            lines.append(f"- [ ] {item}")
        lines.append("")
    
    if memory.get("parent_notes"):
        lines.append("### 📝 Notatki:\n")
        for note in memory["parent_notes"][-5:]:
            lines.append(f"- **{note['date']}**: {note['note']}")
        lines.append("")
    
    return "\n".join(lines)

# ============================================================================
# MCP SERVER
# ============================================================================

server = Server("librus-scraper")

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="scrape_librus",
            description="Scrape Librus with auto-login for a child",
            inputSchema={
                "type": "object",
                "properties": {
                    "child_name": {
                        "type": "string",
                        "description": "Name of the child (e.g. 'Jan', 'Anna')"
                    },
                    "force_full": {
                        "type": "boolean",
                        "description": "Force full scan instead of delta (default: false)"
                    }
                },
                "required": ["child_name"]
            }
        ),
        Tool(
            name="get_memory",
            description="Get stored memory and trends for a child",
            inputSchema={
                "type": "object",
                "properties": {
                    "child_name": {
                        "type": "string",
                        "description": "Name of the child"
                    }
                },
                "required": ["child_name"]
            }
        ),
        Tool(
            name="save_analysis",
            description="Save an insight or note to child's memory",
            inputSchema={
                "type": "object",
                "properties": {
                    "child_name": {
                        "type": "string",
                        "description": "Name of the child"
                    },
                    "analysis_type": {
                        "type": "string",
                        "description": "Type of analysis to save",
                        "enum": ["issue", "action_item", "parent_note"]
                    },
                    "content": {
                        "type": "string",
                        "description": "Content of the note or analysis"
                    }
                },
                "required": ["child_name", "analysis_type", "content"]
            }
        ),
        Tool(
            name="list_children",
            description="List all children with their last scan dates",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "scrape_librus":
            child_name = arguments["child_name"]
            force_full = arguments.get("force_full", False)
            
            result = await scrape_librus(child_name, force_full)
            memory = load_memory(child_name)
            
            response = f"# 📚 {child_name} - {result['mode']}\n\n"
            response += f"## 🆕 Nowe dane:\n\n{result['markdown']}\n\n"
            response += f"---\n\n## 🧠 PAMIĘĆ:\n\n{format_memory(memory)}\n\n"
            response += f"**Stats:** 📧 {result['stats']['wiadomosci']} | "
            response += f"📢 {result['stats']['ogloszenia']} | "
            response += f"📊 {result['stats']['oceny']} | "
            response += f"📅 {result['stats']['terminarz']}"
            
            return [TextContent(type="text", text=response)]
        
        elif name == "get_memory":
            child_name = arguments["child_name"]
            memory = load_memory(child_name)
            response = f"# 🧠 {child_name}\n\n{format_memory(memory)}"
            return [TextContent(type="text", text=response)]
        
        elif name == "save_analysis":
            child_name = arguments["child_name"]
            atype = arguments["analysis_type"]
            content = arguments["content"]
            memory = load_memory(child_name)
            
            if atype == "issue":
                memory["recurring_issues"].append(content)
            elif atype == "action_item":
                memory["action_items"].append(content)
            elif atype == "parent_note":
                memory["parent_notes"].append({
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "note": content
                })
            
            save_memory(child_name, memory)
            return [TextContent(type="text", text=f"✅ Zapisano: {content}")]
        
        elif name == "list_children":
            children = [d.name for d in BASE_DIR.iterdir() if d.is_dir()]
            if not children:
                return [TextContent(type="text", text="Brak dzieci")]
            
            response = "# 👨‍👩‍👦 Dzieci:\n\n"
            for child in children:
                state = load_state(child)
                last = state.get("last_scrape_iso", "Nigdy")
                response += f"- **{child}** (ostatni: {last})\n"
            return [TextContent(type="text", text=response)]
    
    except Exception as e:
        return [TextContent(type="text", text=f"❌ Błąd: {str(e)}")]

# ============================================================================
# MAIN
# ============================================================================

async def main():
    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
