# Librus MCP Server

MCP server do automatycznego pobierania danych z Librusa (wiadomości, oceny, ogłoszenia, terminarz) dla wielu dzieci. Działa w trybie headless z automatycznym logowaniem.

## Funkcje

- 🔐 Automatyczne logowanie (sesje zapisywane lokalnie)
- 👨‍👩‍👧‍👦 Obsługa wielu dzieci
- 📧 Wiadomości (z załącznikami)
- 📊 Oceny (z trendami)
- 📢 Ogłoszenia
- 📅 Terminarz (sprawdziany, kartkówki, wywiadówki)
- 🧠 Pamięć kontekstowa (trendy, notatki)
- ⚡ Tryb delta (tylko nowe dane od ostatniego pobrania)

## Instalacja

```bash
# Klonuj repo
git clone <your-repo-url>
cd librus-mcp

# Utwórz venv i zainstaluj zależności
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Zainstaluj przeglądarki Playwright
playwright install webkit
```

## Konfiguracja

1. Skopiuj przykładowy plik credentials:
```bash
cp credentials.json.example credentials.json
```

2. Edytuj `credentials.json` i wpisz dane logowania dla każdego dziecka:
```json
{
  "children": [
    {
      "name": "Jan",
      "login": "jan_login",
      "password": "haslo123"
    }
  ]
}
```

**WAŻNE:** Plik `credentials.json` jest w `.gitignore` i NIE będzie commitowany do repo.

## Użycie z Kiro CLI

Dodaj do konfiguracji Kiro (`~/.kiro/config.json` lub lokalnie):

```json
{
  "mcpServers": {
    "librus": {
      "command": "/Users/twoja-sciezka/librus-mcp/venv/bin/python",
      "args": ["/Users/twoja-sciezka/librus-mcp/librus_mcp_server.py"]
    }
  }
}
```

Następnie w Kiro:
```
Pobierz dane z Librusa dla Jana
```

## Dostępne narzędzia MCP

- `scrape_librus` - Pobierz dane dla dziecka
- `get_memory` - Wyświetl zapamiętane trendy i notatki
- `save_analysis` - Zapisz notatkę/spostrzeżenie
- `list_children` - Lista wszystkich dzieci

## Struktura danych

Wszystkie dane przechowywane są w `~/.librus_scraper/`:
```
~/.librus_scraper/
├── jan/
│   ├── state.json          # Stan (ostatnie pobranie)
│   ├── memory.json         # Pamięć (trendy, notatki)
│   ├── latest.md           # Ostatnie dane
│   ├── history/            # Historia pobrań
│   └── browser_context/    # Sesja przeglądarki
```

## Bezpieczeństwo

- Credentials są poza repo (`.gitignore`)
- Dane dzieci są poza repo (`~/.librus_scraper/`)
- Sesje przeglądarki zapisywane lokalnie
- Pierwsze logowanie wymaga ręcznej autoryzacji (2FA/captcha)

## Licencja

MIT
