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

# ---- Demo subcommands (Typer basics) ----
@app.command()
def hello(name: str = "World"):
    """Say hello to someone."""
    print(f"Hello {name} 👋 from fossbox!")

@app.command()
def goodbye(name: str = "World"):
    """Say Goodbye to someone."""
    print(f"goodbye {name} 👋 from fossbox!")

# ---- Helpers ----
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

# ---- Core command ----
@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def run(
    ctx: typer.Context,  # gives access to everything after `--`

    # Resource limit options (stability)
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

    # Speed mode (fast tmp)
    tmpfs: str = typer.Option(
        "",
        help="Mount a RAM-backed /tmp of this SIZE inside the run (e.g., 500M, 1G). Speeds up temp-file-heavy tools."
    ),

    # Artifact options
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

      4) Speed mode (RAM-backed /tmp):
         python -m fossbox run --tmpfs 256M -- echo "hi fast tmp"
    """

    # 1) Collect the user's command (everything after `--`)
    if not ctx.args:
        typer.echo("Error: no command provided. Put your command after `--`.", err=True)
        raise typer.Exit(code=2)
    user_cmd = ctx.args[:]  # exact tokens the user typed

    # 2) Create an isolated workspace (unique temp folder)
    run_id = str(uuid.uuid4())[:8]  # short unique ID

    # ★ CHANGED: choose workspace root.
    # - Normal mode: keep using system temp (/tmp).
    # - Speed mode (--tmpfs): DO NOT use /tmp because PrivateTmp will hide it from the service.
    if tmpfs:
        runs_root = Path.home() / ".cache" / "fossbox" / "runs"
        runs_root.mkdir(parents=True, exist_ok=True)
        base_dir = Path(tempfile.mkdtemp(prefix=f"fossbox-{run_id}-", dir=str(runs_root))).resolve()
    else:
        base_dir = Path(tempfile.mkdtemp(prefix=f"fossbox-{run_id}-")).resolve()

    work_dir = (base_dir / "work")
    out.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    # 3) Hint many tools to use our workspace for temp files
    env = os.environ.copy()
    env["TMPDIR"] = str(work_dir)

    # 4) Translate --cpus into systemd CPUQuota string
    cpu_quota = _cpu_quota_from_cpus(cpus)

    # 5) Build the final command we will execute (systemd-run if available)
    use_systemd = _has_systemd_run()

    # Two launch modes:
    #   A) tmpfs requested -> transient SERVICE (TemporaryFileSystem)
    #   B) no tmpfs        -> transient SCOPE (previous behavior)
    if use_systemd and tmpfs:
        # Transient service to get a RAM-backed /tmp with a SIZE cap.
        sd_cmd = [
            "systemd-run",
            "--user",
            "--unit", f"fossbox-{run_id}",
            "--wait",
            "--collect",
            "-p", f"MemoryMax={ram}",
            "-p", f"CPUQuota={cpu_quota}",
            # Make /tmp private AND RAM-backed with size cap (the speed boost):
            "-p", "PrivateTmp=yes",
            f"-p", f"TemporaryFileSystem=/tmp:rw,size={tmpfs}",
            # Run inside our workspace and nudge tools to use /tmp:
            "-p", f"WorkingDirectory={work_dir}",
            "-p", "Environment=TMPDIR=/tmp",
        ]
        # ★ CHANGED: only add RuntimeMaxSec if a timeout was requested
        if timeout > 0:
            sd_cmd += ["-p", f"RuntimeMaxSec={timeout}"]

        full_cmd = sd_cmd + ["--"] + user_cmd
        launch_mode = f"systemd (service) with tmpfs /tmp={tmpfs}"
        use_cwd = None   # WorkingDirectory handled by systemd
        use_env = None   # Environment handled by systemd (TMPDIR=/tmp)
    elif use_systemd:
        # Previous behavior: transient scope (no tmpfs mount)
        sd_cmd = [
            "systemd-run",
            "--user",
            "--scope",
            "-p", f"MemoryMax={ram}",
            "-p", f"CPUQuota={cpu_quota}",
        ]
        if timeout and timeout > 0:
            sd_cmd += ["-p", f"RuntimeMaxSec={timeout}"]
        full_cmd = sd_cmd + ["--"] + user_cmd
        launch_mode = "systemd (scope)"
        use_cwd = work_dir  # change dir in our subprocess
        use_env = env       # TMPDIR points inside workspace
    else:
        # Fallback: no enforced limits, no tmpfs mount
        full_cmd = user_cmd
        launch_mode = "direct (no hard limits)"
        use_cwd = work_dir
        use_env = env

    try:
        # 6) Status
        typer.echo(f"[fossbox] workspace: {work_dir}")
        typer.echo(f"[fossbox] limits: cpus={cpus} (CPUQuota={cpu_quota}), ram={ram}, timeout={timeout or 'none'}")
        if tmpfs:
            typer.echo(f"[fossbox] speed mode: tmpfs /tmp with size={tmpfs}")
        typer.echo(f"[fossbox] launching via: {launch_mode} …")

        # 7) Run the command (blocking until it finishes)
        result = subprocess.run(full_cmd, cwd=use_cwd, env=use_env)
        rc = result.returncode

        if rc == 0:
            typer.echo("[fossbox] command completed successfully.")
        else:
            typer.echo(f"[fossbox] command exited with code {rc}", err=True)

        # 8) Copy artifacts matching --save
        patterns = [p.strip() for p in (save.split(",") if save else []) if p.strip()]
        copied = 0
        for pat in patterns:
            for match in glob.glob(str(work_dir / pat), recursive=True):
                src = Path(match)
                if src.is_file():
                    dest = out / src.name
                    if dest.exists():
                        dest = out / f"{src.stem}-{run_id}{src.suffix}"
                    shutil.copy2(src, dest)
                    copied += 1

        if patterns:
            typer.echo(f"[fossbox] saved {copied} file(s) to: {out}")
        else:
            typer.echo("[fossbox] no --save patterns provided; nothing copied out.")

        # Exit with the same code as the user's command
        raise typer.Exit(code=rc)

    finally:
        # 9) Cleanup sandbox (always)
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
