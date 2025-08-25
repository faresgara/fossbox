# fossbox-run

**Run security tools fast, safely, and cleanly — with one command.**

`fossbox` is a beginner-friendly CLI that launches your commands in a **temporary, isolated workspace**, with **CPU/RAM limits** for stability, optional **tmpfs** (RAM-backed `/tmp`) for speed, and **automatic cleanup**. Artifacts you care about are copied out; everything else disappears.

## Why?

Security tools can be heavy. They create lots of temp files, spike CPU/RAM, and leave junk behind. `fossbox` gives you a safe “sandbox per run”:

- **Stability**: cap CPU (`--cpus`) and memory (`--ram`) to keep your VM responsive.  
- **Speed**: `--tmpfs SIZE` mounts a RAM disk at `/tmp` (inside the run) for faster temp I/O.  
- **Cleanliness**: outputs you select with `--save` are copied to your folder; the workspace is deleted.

---

## Install

> Requires Python 3.10+ and systemd user sessions (Kali/Debian/Ubuntu work fine).
...