"""Tests for adapters"""
import pytest
import pickle
from pathlib import Path
from datetime import datetime
from src.adapters.config import YamlConfigAdapter
from src.adapters.storage import FileStorageAdapter
from src.domain.models import ScrapeResult, Grade, Homework


class TestYamlConfigAdapter:
    def test_get_children(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
browser:
  login_timeout_ms: 120000
  page_timeout_ms: 30000
storage:
  data_dir: ".test_data"
children:
  - name: "Test"
    aliases: ["T"]
    username: "user"
    password: "pass"
""")
        config = YamlConfigAdapter(config_file)
        children = config.get_children()
        
        assert len(children) == 1
        assert children[0].name == "Test"
        assert children[0].aliases == ["T"]
        assert children[0].username == "user"
    
    def test_get_child_by_alias(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
browser:
  login_timeout_ms: 120000
  page_timeout_ms: 30000
storage:
  data_dir: ".test_data"
children:
  - name: "Jakub"
    aliases: ["Kuba"]
""")
        config = YamlConfigAdapter(config_file)
        
        assert config.get_child("Jakub").name == "Jakub"
        assert config.get_child("Kuba").name == "Jakub"
        assert config.get_child("Unknown") is None
    
    def test_get_timeouts(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
browser:
  login_timeout_ms: 60000
  page_timeout_ms: 15000
storage:
  data_dir: ".test"
children: []
""")
        config = YamlConfigAdapter(config_file)
        
        assert config.get_browser_timeout() == 60000
        assert config.get_page_timeout() == 15000
    
    def test_missing_config_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            YamlConfigAdapter(tmp_path / "nonexistent.yaml")


class TestFileStorageAdapter:
    def test_load_save_state(self, tmp_path):
        storage = FileStorageAdapter(tmp_path)
        
        storage.save_state("test", {"last_scrape_iso": "2024-01-01"})
        state = storage.load_state("test")
        
        assert state["last_scrape_iso"] == "2024-01-01"
    
    def test_load_state_default(self, tmp_path):
        storage = FileStorageAdapter(tmp_path)
        state = storage.load_state("nonexistent")
        
        assert state["child_name"] == "nonexistent"
        assert state["last_scrape_iso"] is None
    
    def test_save_load_memory(self, tmp_path):
        storage = FileStorageAdapter(tmp_path)
        
        storage.save_memory("test", {"grade_history": {"Math": []}})
        memory = storage.load_memory("test")
        
        assert "grade_history" in memory
    
    def test_load_memory_default(self, tmp_path):
        storage = FileStorageAdapter(tmp_path)
        memory = storage.load_memory("nonexistent")
        
        assert memory["child_name"] == "nonexistent"
        assert "grade_history" in memory
    
    def test_get_child_dir_creates_directory(self, tmp_path):
        storage = FileStorageAdapter(tmp_path)
        child_dir = storage.get_child_dir("Test Child")
        
        assert child_dir.exists()
        assert child_dir.name == "test-child"
    
    def test_get_context_dir(self, tmp_path):
        storage = FileStorageAdapter(tmp_path)
        context_dir = storage.get_context_dir("test")
        
        assert context_dir.exists()
        assert context_dir.name == "browser_context"
    
    def test_save_result_creates_markdown(self, tmp_path):
        storage = FileStorageAdapter(tmp_path)
        result = ScrapeResult(
            child_name="Test",
            timestamp=datetime.now(),
            grades=[Grade("Math", "5", "2024-01-01", "test")],
        )
        
        storage.save_result("test", result)
        
        md_file = storage.get_child_dir("test") / "latest.md"
        assert md_file.exists()
        content = md_file.read_text()
        assert "Test" in content
        assert "Math" in content
    
    def test_save_result_creates_pickle(self, tmp_path):
        storage = FileStorageAdapter(tmp_path)
        now = datetime.now()
        result = ScrapeResult(
            child_name="Test",
            timestamp=now,
            grades=[Grade("Math", "5", "2024-01-01", "test")],
        )
        
        storage.save_result("test", result)
        
        pkl_file = storage.get_child_dir("test") / f"{now.year}-{now.month:02d}.pkl"
        assert pkl_file.exists()
    
    def test_get_recent_data(self, tmp_path):
        storage = FileStorageAdapter(tmp_path)
        now = datetime.now()
        
        # Create pickle file
        child_dir = storage.get_child_dir("test")
        data = {'timestamp': now.isoformat(), 'data': {'rawData': {'grades': []}}}
        pkl_file = child_dir / f"{now.year}-{now.month:02d}.pkl"
        with open(pkl_file, 'wb') as f:
            pickle.dump(data, f)
        
        recent = storage.get_recent_data("test", months=2)
        
        assert len(recent) == 1
        assert f"{now.year}-{now.month:02d}" in recent
    
    def test_merge_monthly_data_deduplicates(self, tmp_path):
        storage = FileStorageAdapter(tmp_path)
        now = datetime.now()
        
        # First save
        result1 = ScrapeResult(
            child_name="Test",
            timestamp=now,
            grades=[Grade("Math", "5", "2024-01-01", "test")],
        )
        storage.save_result("test", result1)
        
        # Second save with same grade
        result2 = ScrapeResult(
            child_name="Test",
            timestamp=now,
            grades=[
                Grade("Math", "5", "2024-01-01", "test"),  # duplicate
                Grade("Math", "4", "2024-01-02", "test"),  # new
            ],
        )
        storage.save_result("test", result2)
        
        # Load and check
        data = storage.get_recent_data("test", months=1)
        month_key = f"{now.year}-{now.month:02d}"
        grades = data[month_key]['data']['rawData']['grades']
        
        assert len(grades) == 2  # deduplicated

