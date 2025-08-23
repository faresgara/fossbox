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

@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def run(
    ctx: typer.Context,  # gives access to everything after `--`
    save: str = typer.Option(
        "",
        help='Comma-separated globs to copy out, e.g., "*.xml,*.gnmap"'
    ),
    out: Path = typer.Option(
        Path.cwd(),
        help="Folder where matched files (from --save) will be copied"
    ),
):
    """
    Run any command in a disposable workspace, copy selected outputs, then clean up.

    IMPORTANT: put your command AFTER `--` so Typer stops parsing.
    Example:
      python -m fossbox run --save '*.txt' -- bash -lc 'echo hi > note.txt'
    """
    # 1) Get the user's command (everything after `--`)
    if not ctx.args:
        # Friendly error if the user forgot to put a command after `--`
        typer.echo("Error: no command provided. Put your command after `--`.", err=True)
        raise typer.Exit(code=2)

    user_cmd = ctx.args[:]  # exact tokens, e.g., ["bash","-lc","echo hi > f.txt"]

    # 2) Create an isolated workspace
    run_id = str(uuid.uuid4())[:8]  # short unique ID to avoid name clashes
    base_dir = Path(tempfile.mkdtemp(prefix=f"fossbox-{run_id}-"))  # e.g., /tmp/fossbox-abc12345-xyz
    work_dir = base_dir / "work"
    out.mkdir(parents=True, exist_ok=True)     # ensure output folder exists
    work_dir.mkdir(parents=True, exist_ok=True)  # make the workspace

    # 3) Tell many tools to use our workspace for temp files
    env = os.environ.copy()
    env["TMPDIR"] = str(work_dir)  # many programs respect TMPDIR

    try:
        # 4) Show where we’re working (helpful for debugging)
        typer.echo(f"[fossbox] workspace: {work_dir}")

        # 5) Run the user's command INSIDE the workspace
        # - cwd=work_dir   → current directory is the workspace
        # - env=env        → apply TMPDIR so temp files go inside workspace
        result = subprocess.run(user_cmd, cwd=work_dir, env=env)
        rc = result.returncode  # process exit code (0 = success)

        if rc == 0:
            typer.echo("[fossbox] command completed successfully.")
        else:
            typer.echo(f"[fossbox] command exited with code {rc}", err=True)

        # 6) Copy artifacts matching --save patterns (if any)
        patterns = [p.strip() for p in (save.split(",") if save else []) if p.strip()]
        copied = 0
        for pat in patterns:
            # Search inside the workspace; supports wildcards like *.xml
            for match in glob.glob(str(work_dir / pat), recursive=True):
                src = Path(match)
                if src.is_file():
                    dest = out / src.name
                    # Avoid overwriting existing files in 'out'
                    if dest.exists():
                        dest = out / f"{src.stem}-{run_id}{src.suffix}"
                    shutil.copy2(src, dest)  # copy with metadata preserved
                    copied += 1

        if patterns:
            typer.echo(f"[fossbox] saved {copied} file(s) to: {out}")
        else:
            typer.echo("[fossbox] no --save patterns provided; nothing copied out.")

        # Bubble up the same exit code as the user's command
        raise typer.Exit(code=rc)

    finally:
        # 7) Always clean up the workspace (even if the command failed)
        try:
            shutil.rmtree(base_dir)
            typer.echo("[fossbox] cleaned up workspace.")
        except Exception as e:
            typer.echo(f"[fossbox] cleanup warning: {e}", err=True)


# Entry point: run the Typer app (so it can parse subcommands).
def main():
    app()

if __name__ == "__main__":
    main()
