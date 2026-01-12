"""Tests for application layer use cases"""
import pytest
from pathlib import Path
from datetime import datetime
from src.application import (
    GetGradesSummaryUseCase,
    GetCalendarEventsUseCase,
    AnalyzeGradesUseCase
)
from src.adapters.storage import FileStorageAdapter
from src.adapters.config import YamlConfigAdapter


@pytest.fixture
def config_file(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("""
browser:
  login_timeout_ms: 120000
  page_timeout_ms: 30000
storage:
  data_dir: ".test_data"
children:
  - name: "TestChild"
    aliases: ["TC"]
""")
    return config


@pytest.fixture
def storage(tmp_path):
    return FileStorageAdapter(tmp_path)


@pytest.fixture
def config(config_file):
    return YamlConfigAdapter(config_file)


@pytest.fixture
def storage_with_data(storage):
    """Storage with sample grade data"""
    import pickle
    from datetime import datetime
    
    child_dir = storage.get_child_dir("TestChild")
    now = datetime.now()
    
    data = {
        'timestamp': now.isoformat(),
        'data': {
            'rawData': {
                'grades': [
                    {'subject': 'Math', 'grade': '5', 'date': '2024-01-01', 'category': 'test', 'weight': '1'},
                    {'subject': 'Math', 'grade': '4', 'date': '2024-01-02', 'category': 'test', 'weight': '1'},
                    {'subject': 'Math', 'grade': '3', 'date': '2024-01-03', 'category': 'test', 'weight': '1'},
                    {'subject': 'Physics', 'grade': '2', 'date': '2024-01-01', 'category': 'test', 'weight': '1'},
                    {'subject': 'Physics', 'grade': '2', 'date': '2024-01-02', 'category': 'test', 'weight': '1'},
                    {'subject': 'Math', 'grade': '4', 'date': None, 'category': 'ocena śródroczna', 'weight': ''},
                ],
                'calendar': [
                    {'date': (now.replace(day=1)).strftime('%Y-%m-%d'), 'title': 'Past event', 'category': ''},
                    {'date': '2099-01-15', 'title': 'Sprawdzian z matematyki', 'category': ''},
                    {'date': '2099-01-16', 'title': 'Wycieczka', 'category': ''},
                ],
                'homework': [],
                'messages': [],
                'remarks': [],
            }
        }
    }
    
    monthly_file = child_dir / f"{now.year}-{now.month:02d}.pkl"
    with open(monthly_file, 'wb') as f:
        pickle.dump(data, f)
    
    return storage


class TestGetGradesSummaryUseCase:
    def test_child_not_found(self, storage, config):
        use_case = GetGradesSummaryUseCase(storage, config)
        result = use_case.execute("Unknown")
        assert "error" in result
    
    def test_no_data(self, storage, config):
        use_case = GetGradesSummaryUseCase(storage, config)
        result = use_case.execute("TestChild")
        assert "error" in result
    
    def test_returns_grades_summary(self, storage_with_data, config):
        use_case = GetGradesSummaryUseCase(storage_with_data, config)
        result = use_case.execute("TestChild")
        
        assert result["total_current_grades"] == 5  # excludes semester grade
        assert "Math" in result["by_subject"]
        assert "Physics" in result["by_subject"]
        assert "Math" in result["semester_grades"]
    
    def test_resolves_alias(self, storage_with_data, config):
        use_case = GetGradesSummaryUseCase(storage_with_data, config)
        result = use_case.execute("TC")  # alias
        
        assert "error" not in result
        assert result["total_current_grades"] == 5


class TestGetCalendarEventsUseCase:
    def test_child_not_found(self, storage, config):
        use_case = GetCalendarEventsUseCase(storage, config)
        result = use_case.execute("Unknown")
        assert "error" in result
    
    def test_returns_upcoming_events(self, storage_with_data, config):
        use_case = GetCalendarEventsUseCase(storage_with_data, config)
        result = use_case.execute("TestChild", days_ahead=36500)  # ~100 years
        
        assert result["total_events"] == 3
        assert len(result["upcoming"]) == 2  # future events only
        assert len(result["upcoming_tests"]) == 1


class TestAnalyzeGradesUseCase:
    def test_child_not_found(self, storage, config):
        use_case = AnalyzeGradesUseCase(storage, config)
        result = use_case.execute("Unknown")
        assert "error" in result
    
    def test_analyzes_grades(self, storage_with_data, config):
        use_case = AnalyzeGradesUseCase(storage_with_data, config)
        result = use_case.execute("TestChild")
        
        assert result["total_grades"] == 6
        assert result["overall_average"] is not None
        assert "Physics" in result["at_risk"]  # avg 2.0
        assert "Math" in result["by_subject"]
        assert result["by_subject"]["Math"]["average"] == 4.0
    
    def test_no_data(self, storage, config):
        use_case = AnalyzeGradesUseCase(storage, config)
        result = use_case.execute("TestChild")
        assert "error" in result
    
    def test_trend_calculation(self, storage_with_data, config):
        use_case = AnalyzeGradesUseCase(storage_with_data, config)
        result = use_case.execute("TestChild")
        
        # Math has 3 grades, should have trend
        assert "trend" in result["by_subject"]["Math"]


class TestLoginChildUseCase:
    @pytest.mark.asyncio
    async def test_child_not_found(self, config):
        from src.application import LoginChildUseCase
        from unittest.mock import AsyncMock
        
        mock_browser = AsyncMock()
        use_case = LoginChildUseCase(mock_browser, config)
        result = await use_case.execute("Unknown")
        
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()
    
    @pytest.mark.asyncio
    async def test_no_credentials(self, tmp_path):
        from src.application import LoginChildUseCase
        from src.adapters.config import YamlConfigAdapter
        from unittest.mock import AsyncMock
        
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
browser:
  login_timeout_ms: 120000
  page_timeout_ms: 30000
storage:
  data_dir: ".test"
children:
  - name: "NoCreds"
    aliases: []
""")
        config = YamlConfigAdapter(config_file)
        mock_browser = AsyncMock()
        use_case = LoginChildUseCase(mock_browser, config)
        
        result = await use_case.execute("NoCreds")
        
        assert result["status"] == "error"
        assert "credentials" in result["message"].lower()


class TestScrapeChildUseCase:
    @pytest.mark.asyncio
    async def test_child_not_found(self, storage, config):
        from src.application import ScrapeChildUseCase
        from unittest.mock import AsyncMock
        
        mock_browser = AsyncMock()
        use_case = ScrapeChildUseCase(mock_browser, storage, config)
        result = await use_case.execute("Unknown")
        
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()
    
    @pytest.mark.asyncio
    async def test_session_expired(self, storage, config):
        from src.application import ScrapeChildUseCase
        from unittest.mock import AsyncMock
        
        mock_browser = AsyncMock()
        mock_browser.is_session_valid.return_value = False
        
        use_case = ScrapeChildUseCase(mock_browser, storage, config)
        result = await use_case.execute("TestChild")
        
        assert result["status"] == "session_expired"
