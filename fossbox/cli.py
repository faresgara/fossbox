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

def _cpu_quota_from_cpus(cpus: float) -> str:
    """
    Convert --cpus (e.g., 2.0) into systemd CPUQuota percent string.
    Example: 2.0 CPUs -> '200%'.
    """
    return f"{int(cpus * 100)}%"

def _has_systemd_run() -> bool:
    """
    Check if 'systemd-run' exists for this user.
    If not, we still run the command (but without hard limits) and warn the user.
    """
    return shutil.which("systemd-run") is not None


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def run(
    ctx: typer.Context,  # gives access to everything after `--`

    # === NEW: resource limit options ===
    cpus: float = typer.Option(
        1.0,
        help="CPUs to allocate (e.g., --cpus 2 gives CPUQuota=200%)."
    ),
    ram: str = typer.Option(
        "1G",
        help="Hard RAM cap, systemd format (e.g., 512M, 1G, 2G)."
    ),
    timeout: int = typer.Option(
        0,
        help="Auto-kill after N seconds (0 = no timeout)."
    ),

    # === Existing artifact options ===
    save: str = typer.Option(
        "",
        help='Comma-separated globs to copy out from the sandbox, e.g., "*.xml,*.gnmap".'
    ),
    out: Path = typer.Option(
        Path.cwd(),
        help="Folder where matched files (from --save) will be copied."
    ),
):
    """
    Run any command in a disposable workspace, copy selected outputs, enforce limits, then clean up.

    IMPORTANT: put your command AFTER `--` so Typer stops parsing flags.
    Examples:
      1) Quick echo:
         python -m fossbox run -- echo "hello"

      2) Save a file:
         python -m fossbox run --save "report.txt" -- \
           bash -lc 'echo hi > report.txt'

      3) With limits + save nmap outputs:
         python -m fossbox run --cpus 2 --ram 1G --timeout 60 \
           --save "*.xml,*.gnmap" -- \
           nmap -T4 -sV -O 192.168.1.0/24 -oA scan
    """

    # 1) Collect the user's command (everything after `--`)
    # Example: if you ran:  python -m fossbox run -- echo "hi"
    # then ctx.args == ["echo", "hi"]
    if not ctx.args:
        typer.echo("Error: no command provided. Put your command after `--`.", err=True)
        raise typer.Exit(code=2)
    user_cmd = ctx.args[:]  # copy list of tokens exactly as the user typed them

    # 2) Create an isolated workspace (a unique temp folder for this run)
    #    Think of this like a clean desk for the job — no previous files here.
    run_id = str(uuid.uuid4())[:8]  # short unique ID (helps avoid name clashes)
    base_dir = Path(tempfile.mkdtemp(prefix=f"fossbox-{run_id}-"))  # e.g., /tmp/fossbox-1a2b3c4d-xxxx
    work_dir = base_dir / "work"
    out.mkdir(parents=True, exist_ok=True)        # make sure output folder exists
    work_dir.mkdir(parents=True, exist_ok=True)   # make the workspace folder

    # 3) Hint many tools to use our workspace for temp files by setting TMPDIR
    #    Not every tool uses TMPDIR, but many do, so this keeps temp junk inside our sandbox.
    env = os.environ.copy()
    env["TMPDIR"] = str(work_dir)

    # 4) Translate --cpus into systemd CPUQuota string (e.g., 2.0 -> "200%")
    cpu_quota = _cpu_quota_from_cpus(cpus)

    # 5) Build the final command we will execute.
    #    If 'systemd-run' exists, we wrap the user's command so systemd enforces:
    #       - MemoryMax (RAM cap)
    #       - CPUQuota (CPU limit)
    #       - RuntimeMaxSec (timeout)
    #    Otherwise we run directly and warn that hard limits are not enforced.
    use_systemd = _has_systemd_run()
    if use_systemd:
        sd_cmd = [
            "systemd-run",
            "--user",                    # run in your user session (no sudo)
            "--scope",                   # transient cgroup scope (auto-clean)
            "-p", f"MemoryMax={ram}",    # HARD RAM cap (e.g., 1G)
            "-p", f"CPUQuota={cpu_quota}",  # CPU limit as percent (e.g., "200%")
        ]
        if timeout and timeout > 0:
            sd_cmd += ["-p", f"RuntimeMaxSec={timeout}"]  # auto-kill after N seconds

        # IMPORTANT: The '--' here tells systemd: "the real command starts after this"
        full_cmd = sd_cmd + ["--"] + user_cmd
    else:
        full_cmd = user_cmd  # fallback path (no enforced limits)

    try:
        # 6) Friendly status messages so the user sees what's happening
        typer.echo(f"[fossbox] workspace: {work_dir}")
        typer.echo(f"[fossbox] limits: cpus={cpus} (CPUQuota={cpu_quota}), ram={ram}, timeout={timeout or 'none'}")
        if use_systemd:
            typer.echo("[fossbox] launching under systemd-run --user --scope …")
        else:
            typer.echo("[fossbox] WARNING: systemd-run not found; running without hard CPU/RAM caps.")

        # 7) Actually run the command.
        #    - cwd=work_dir → the command runs INSIDE our sandbox folder
        #    - env=env      → applies TMPDIR so many temp files land in the sandbox
        result = subprocess.run(full_cmd, cwd=work_dir, env=env)
        rc = result.returncode  # the command's exit code (0 = success, nonzero = error)

        if rc == 0:
            typer.echo("[fossbox] command completed successfully.")
        else:
            typer.echo(f"[fossbox] command exited with code {rc}", err=True)

        # 8) Copy artifacts matching --save patterns (if any)
        #    Example: --save "*.xml,*.gnmap" will copy those files from the sandbox to 'out'
        patterns = [p.strip() for p in (save.split(",") if save else []) if p.strip()]
        copied = 0
        for pat in patterns:
            # Search files inside the workspace; supports wildcards like *.xml
            for match in glob.glob(str(work_dir / pat), recursive=True):
                src = Path(match)
                if src.is_file():
                    dest = out / src.name
                    # Avoid overwriting existing files in the output folder.
                    # If 'dest' already exists, append the run_id to the filename.
                    if dest.exists():
                        dest = out / f"{src.stem}-{run_id}{src.suffix}"
                    shutil.copy2(src, dest)  # copy and preserve metadata (timestamps, perms)
                    copied += 1

        if patterns:
            typer.echo(f"[fossbox] saved {copied} file(s) to: {out}")
        else:
            typer.echo("[fossbox] no --save patterns provided; nothing copied out.")

        # 9) Exit with the same code as the user's command (important for scripting)
        raise typer.Exit(code=rc)

    finally:
        # 10) Always clean up the workspace (even if the command failed or crashed)
        try:
            shutil.rmtree(base_dir)
            typer.echo("[fossbox] cleaned up workspace.")
        except Exception as e:
            # If deletion fails (e.g., file still in use), warn but don't crash
            typer.echo(f"[fossbox] cleanup warning: {e}", err=True)

# Entry point: run the Typer app (so it can parse subcommands).
def main():
    app()

if __name__ == "__main__":
    main()
