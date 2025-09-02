
---

# fossbox-run

**Run security tools safely, predictably, and cleanly — with one command.**

`fossbox` is a beginner-friendly CLI that launches your commands in a **temporary, isolated workspace**, with **CPU/RAM limits** for stability, optional **tmpfs** (RAM-backed `/tmp`) to *optimize speed when possible*, and **automatic cleanup**.
Artifacts you care about are copied out; everything else disappears. The runtime overhead added by `fossbox` is **negligible** — your tools run at native speed or even faster with tmpfs.

---

## Why?

Security tools can be heavy. They create lots of temp files, spike CPU/RAM, and leave junk behind. `fossbox` gives you a safe “sandbox per run”:

* **Stability** → cap CPU (`--cpus`) and memory (`--ram`) so your VM never freezes.
* **Performance-aware** → `--tmpfs SIZE` can mount a RAM disk for `/tmp` to optimize speed *when the tool benefits from fast temporary storage*.
* **Cleanliness** → keep only what you ask for with `--save`; everything else is deleted on exit.
* **Low overhead** → `fossbox` itself adds almost no cost; it just sets up limits, runs your command, and cleans up.

---

## Install

> Requires **Python 3.10+** and **systemd user sessions** (works fine on Kali, Debian, Ubuntu).

Clone and install locally:

```bash
git clone https://github.com/faresgara/fossbox.git
cd fossbox-run
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Now you can run:

```bash
python -m fossbox --help
```

---

## Usage

### Hello world

```bash
python -m fossbox hello --name Fares
```

Output:

```
Hello Fares 👋 from fossbox!
```

### Run a simple command

```bash
python -m fossbox run -- echo "hi from sandbox"
```

### Save files from the sandbox

```bash
python -m fossbox run --save "*.txt" -- \
  bash -lc 'echo report > report.txt'
```

Saved files appear in your current directory.

---

## Examples

### Run nmap with limits

```bash
sudo python -m fossbox run --as-root --cpus 2 --ram 2G --timeout 60 \
  --save "*.xml,*.gnmap,*.nmap" -- \
  nmap -T4 -sV -O 192.168.1.0/24 -oA scan
```

* 2 CPUs (200% quota)
* 2 GB RAM
* Timeout after 60s
* Saves `scan.xml`, `scan.gnmap`, `scan.nmap`

---

### Optimize speed when possible (tmpfs)

```bash
python -m fossbox run --tmpfs 512M --save "results.txt" -- \
  wfuzz -c -z file,wordlist.txt http://target/FUZZ > results.txt
```

* Mounts a 512 MB RAM disk at `/tmp` inside workspace
* Improve performance for tools that create lots of temporary files

---

### Run as root

```bash
sudo python -m fossbox run --as-root ...
```

---

## Exit codes

* **0** → command ran successfully
* **1** → invalid privilege usage (e.g., `--as-root` without root)
* **2** → user error (e.g., forgot to add command after `--`)
* **N** → any other code is bubbled up from the tool itself

---

## License

MIT — free for personal and commercial use.

---
