"""Unit tests for storage module"""
import pytest
import json
import tempfile
from pathlib import Path
from src.storage import (
    get_child_dir,
    get_context_dir,
    load_state,
    save_state,
    save_scrape_result,
    load_memory,
    save_memory,
    get_last_scan_date
)


@pytest.fixture
def temp_data_dir(monkeypatch):
    """Create temporary data directory"""
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_path = Path(tmpdir)
        import src.config
        src.config.config.set_test_override('data_dir', temp_path)
        yield temp_path
        src.config.config.clear_test_overrides()


@pytest.fixture
def mock_credentials(monkeypatch):
    """Mock credentials to avoid file dependency"""
    def mock_resolve(name):
        return name.capitalize()
    
    import src.storage
    monkeypatch.setattr(src.storage, 'resolve_child_name', mock_resolve)


def test_get_child_dir_creates_directory(temp_data_dir, mock_credentials):
    """Test that child directory is created"""
    child_dir = get_child_dir("Jakub")
    assert child_dir.exists()
    assert child_dir.is_dir()
    assert child_dir.name == "jakub"


def test_get_context_dir_creates_subdirectory(temp_data_dir, mock_credentials):
    """Test that browser context subdirectory is created"""
    context_dir = get_context_dir("Jakub")
    assert context_dir.exists()
    assert context_dir.name == "browser_context"


def test_load_state_new_child(temp_data_dir, mock_credentials):
    """Test loading state for new child returns defaults"""
    state = load_state("Jakub")
    assert state["child_name"] == "Jakub"
    assert state["last_scrape_iso"] is None
    assert state["setup_completed"] is False


def test_save_and_load_state(temp_data_dir, mock_credentials):
    """Test saving and loading state"""
    test_state = {
        "child_name": "Jakub",
        "last_scrape_iso": "2026-01-06 20:00:00",
        "setup_completed": True
    }
    
    save_state("Jakub", test_state)
    loaded_state = load_state("Jakub")
    
    assert loaded_state == test_state


def test_save_scrape_result(temp_data_dir, mock_credentials):
    """Test saving markdown result"""
    markdown = "# Test Data\n\nSome content"
    save_scrape_result("Jakub", markdown)
    
    output_file = get_child_dir("Jakub") / "latest.md"
    assert output_file.exists()
    assert output_file.read_text() == markdown


def test_load_memory_new_child(temp_data_dir, mock_credentials):
    """Test loading memory for new child returns defaults"""
    memory = load_memory("Jakub")
    assert memory["child_name"] == "Jakub"
    assert memory["issues"] == []
    assert memory["action_items"] == []
    assert memory["parent_notes"] == []
    assert memory["trends"] == {}


def test_save_and_load_memory(temp_data_dir, mock_credentials):
    """Test saving and loading memory"""
    test_memory = {
        "child_name": "Jakub",
        "issues": ["Issue 1"],
        "action_items": ["Action 1"],
        "parent_notes": ["Note 1"],
        "trends": {"grades": "improving"}
    }
    
    save_memory("Jakub", test_memory)
    loaded_memory = load_memory("Jakub")
    
    assert loaded_memory == test_memory


def test_get_last_scan_date_none(temp_data_dir, mock_credentials):
    """Test getting last scan date when none exists"""
    assert get_last_scan_date("Jakub") is None


def test_get_last_scan_date_exists(temp_data_dir, mock_credentials):
    """Test getting last scan date when it exists"""
    state = {
        "child_name": "Jakub",
        "last_scrape_iso": "2026-01-06 20:00:00",
        "setup_completed": True
    }
    save_state("Jakub", state)
    
    assert get_last_scan_date("Jakub") == "2026-01-06 20:00:00"
