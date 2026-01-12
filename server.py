#!/usr/bin/env python3
"""
Librus MCP Server - Clean Architecture Entry Point

This is the new entry point using Ports & Adapters / DDD architecture.
The old server.py is kept for backward compatibility during transition.
"""
from src.infrastructure import main

if __name__ == "__main__":
    main()
