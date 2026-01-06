"""Credentials management"""
import json
from typing import Dict, List
from .config import config


class CredentialsError(Exception):
    """Raised when credentials are missing or invalid"""
    pass


def load_credentials() -> Dict:
    """Load credentials from config.yaml"""
    if 'children' not in config._config:
        raise CredentialsError(
            f"Missing children configuration in config.yaml!\n"
            f"Copy config.yaml.example and fill in your data"
        )
    
    return {"children": config._config['children']}


def resolve_child_name(name: str) -> str:
    """
    Resolve alias to canonical child name.
    
    Args:
        name: Child name or alias (case-insensitive)
        
    Returns:
        Canonical child name
        
    Example:
        >>> resolve_child_name("Kuba")
        "Jakub"
    """
    creds = load_credentials()
    name_lower = name.lower()
    
    for child in creds.get("children", []):
        if child["name"].lower() == name_lower:
            return child["name"]
        
        for alias in child.get("aliases", []):
            if alias.lower() == name_lower:
                return child["name"]
    
    return name


def list_children() -> List[Dict]:
    """
    List all configured children.
    
    Returns:
        List of dicts with 'name' and 'aliases'
    """
    creds = load_credentials()
    return [
        {
            "name": child["name"],
            "aliases": child.get("aliases", [])
        }
        for child in creds.get("children", [])
    ]
