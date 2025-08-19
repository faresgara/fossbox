# fossbox/cli.py
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
