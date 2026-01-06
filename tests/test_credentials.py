"""Unit tests for credentials module"""
import pytest
import json
import tempfile
from pathlib import Path
from src.credentials import (
    load_credentials,
    resolve_child_name,
    list_children,
    CredentialsError
)


@pytest.fixture
def mock_credentials_file(monkeypatch):
    """Create temporary credentials in config"""
    import src.config
    
    test_children = [
        {
            "name": "Jakub",
            "aliases": ["Kuba"],
            "login": "test_login",
            "password": "test_pass"
        },
        {
            "name": "Anna",
            "aliases": [],
            "login": "anna_login",
            "password": "anna_pass"
        }
    ]
    
    # Override children in config
    original_children = src.config.config._config.get('children', [])
    src.config.config._config['children'] = test_children
    
    yield test_children
    
    # Restore
    src.config.config._config['children'] = original_children


def test_load_credentials_missing_file():
    """Test error when credentials are missing"""
    import src.config
    
    original_children = src.config.config._config.get('children')
    if 'children' in src.config.config._config:
        del src.config.config._config['children']
    
    with pytest.raises(CredentialsError, match="Missing children configuration"):
        load_credentials()
    
    # Restore
    if original_children is not None:
        src.config.config._config['children'] = original_children


def test_load_credentials_success(mock_credentials_file):
    """Test successful credentials loading"""
    creds = load_credentials()
    assert "children" in creds
    assert len(creds["children"]) == 2


def test_resolve_child_name_canonical(mock_credentials_file):
    """Test resolving canonical name"""
    assert resolve_child_name("Jakub") == "Jakub"
    assert resolve_child_name("jakub") == "Jakub"  # case-insensitive
    assert resolve_child_name("JAKUB") == "Jakub"


def test_resolve_child_name_alias(mock_credentials_file):
    """Test resolving alias to canonical name"""
    assert resolve_child_name("Kuba") == "Jakub"
    assert resolve_child_name("kuba") == "Jakub"


def test_resolve_child_name_not_found(mock_credentials_file):
    """Test resolving unknown name returns original"""
    assert resolve_child_name("Unknown") == "Unknown"


def test_list_children(mock_credentials_file):
    """Test listing all children"""
    children = list_children()
    assert len(children) == 2
    assert children[0]["name"] == "Jakub"
    assert children[0]["aliases"] == ["Kuba"]
    assert children[1]["name"] == "Anna"
    assert children[1]["aliases"] == []
