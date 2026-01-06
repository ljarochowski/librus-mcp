# Testowanie School Assistant Agent

## ✅ Agent zainstalowany

Agent został zainstalowany w: `~/.kiro/agents/school-assistant.json`

## Jak przetestować

### 1. Uruchom Kiro CLI z agentem

```bash
kiro-cli --agent school-assistant
```

Powinieneś zobaczyć:
```
[school-assistant] >
```

### 2. Przetestuj podstawowe funkcje

#### Test 1: Lista dzieci
```
Jakie dzieci masz w systemie?
```

Agent powinien wywołać `list_children()` i pokazać listę.

#### Test 2: Sprawdź postępy dziecka
```
Jak Mateusz radzi sobie w szkole?
```

Agent powinien:
1. Wywołać `scrape_librus(child_name="Mateusz", force_full=false)`
2. Wywołać `get_memory(child_name="Mateusz")`
3. Przeanalizować dane
4. Pokazać podsumowanie z ocenami, zadaniami, uwagami

#### Test 3: Szczegóły przedmiotu
```
Pokaż mi oceny Mateusza z matematyki
```

Agent powinien wyfiltrować tylko oceny z matematyki.

#### Test 4: Zadania domowe
```
Czy Mateusz ma zaległe zadania?
```

Agent powinien sprawdzić dateDue < dzisiaj.

#### Test 5: Porównanie dzieci
```
Porównaj postępy Mateusza i Kuby
```

Agent powinien pobrać dane dla obu i porównać.

### 3. Sprawdź czy agent zapisuje analizy

Po znalezieniu problemów (np. spadające oceny), agent powinien automatycznie wywołać:
```
save_analysis(child_name="Mateusz", analysis_type="issue", content="...")
```

Sprawdź czy zapisało się w `~/.librus_scraper/mateusz/memory.json`

### 4. Zmiana agenta w trakcie sesji

Jeśli już masz otwartą sesję Kiro:
```
/agent swap
```

Wybierz `school-assistant` z listy.

### 5. Sprawdź dostęp do narzędzi MCP

Agent powinien mieć dostęp do:
- `@librus/scrape_librus`
- `@librus/get_memory`
- `@librus/save_analysis`
- `@librus/list_children`

Możesz to sprawdzić pytając:
```
Jakie narzędzia masz dostępne?
```

## Oczekiwane zachowanie

✅ Agent automatycznie pobiera dane z Librusa  
✅ Analizuje oceny, zadania, uwagi  
✅ Pokazuje trendy (wzrost/spadek)  
✅ Sugeruje konkretne działania  
✅ Zapisuje ważne spostrzeżenia do pamięci  
✅ Odpowiada po polsku o sprawach szkolnych  
✅ Używa emoji dla czytelności (📊 📝 ⚠️ 💡)  

## Troubleshooting

### Problem: "Agent not found"
```bash
ls ~/.kiro/agents/
# Powinien pokazać: school-assistant.json
```

### Problem: "MCP server failed to start"
Sprawdź czy server.py działa:
```bash
cd ~/librus-mcp
python3 server.py
```

### Problem: "No children found"
Sprawdź config.yaml:
```bash
cat ~/librus-mcp/config.yaml | grep -A 5 children
```

### Problem: Agent nie ma dostępu do danych
Sprawdź czy są scrape'y:
```bash
ls -la ~/.librus_scraper/
```

## Przykładowe pytania do agenta

- "Jak Mateusz radzi sobie w szkole?"
- "Czy Kuba ma zaległe zadania?"
- "Pokaż mi oceny z ostatniego miesiąca"
- "Jakie uwagi dostał Mateusz?"
- "Porównaj wyniki Mateusza i Kuby"
- "Które przedmioty wymagają uwagi?"
- "Czy są nieprzeczytane wiadomości od nauczycieli?"
- "Pokaż mi kalendarz wydarzeń szkolnych"
