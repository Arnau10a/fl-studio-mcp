"""Backward-compatible launcher shim for fl-studio-mcp."""

from fl_studio_mcp.server import main, mcp

__all__ = ["main", "mcp"]

if __name__ == "__main__":
    main()
