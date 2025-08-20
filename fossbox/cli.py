# fossbox/cli.py
# --- ADD THESE IMPORTS AT THE TOP IF NOT ALREADY PRESENT ---
import os           # work with environment variables (we'll set TMPDIR)
import shutil       # copy files + delete directories
import subprocess   # run external commands (like nmap)
import tempfile     # create a unique temporary directory
import uuid         # generate a short unique run ID to tag files
import glob         # expand patterns like "*.xml"
from pathlib import Path  # safer path handling than plain strings
import typer


# Create the CLI app (container for subcommands)
app = typer.Typer(help="Fossbox CLI")

# Register a SUBCOMMAND named "hello"
@app.command()
def hello(name: str = "World"):
    """Say hello to someone."""
    print(f"Hello {name} 👋 from fossbox!")

@app.command()
def goodbye(name: str = "World"):
    """Say Goodbye to someone."""
    print(f"goodbye {name} 👋 from fossbox!")

# Entry point: run the Typer app (so it can parse subcommands).
# IMPORTANT: this should NOT call hello() directly.
def main():
    app()

if __name__ == "__main__":
    main()
