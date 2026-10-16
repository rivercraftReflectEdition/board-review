# Setup in sandboxes and on Windows

SKILL.md (Setup) gives the normal install. This page covers agents that run commands in a
sandbox, and Windows. Installing needs network access and a writable Python; in a sandbox, ask
the user to run the install steps from a normal shell.

## Codex sandbox on Windows

The Codex sandbox on Windows runs commands as a separate, restricted user. On the machine where
this was found (Windows 11, October 2026), that user could not read per-user installs under
AppData: the per-user Python (`%LOCALAPPDATA%\Programs\Python`), Pythons that uv manages
(`%APPDATA%\uv\python`) and a per-user KiCad all failed to start. Other folders in the user
profile, such as Documents, could be read.

Python, once, from a normal shell:

1. Install a Python outside AppData, for example in `%USERPROFILE%\Tools\python`:
   `uv python install --install-dir <dir> 3.13`
2. uv marks its Pythons as externally managed, so make a venv from it and install the package
   there:
   ```
   <dir>\cpython-3.13.<patch>-windows-x86_64-none\python.exe -m venv <dir>\boardreview-venv
   <dir>\boardreview-venv\Scripts\python.exe -m pip install -e <board-review repo>
   ```
   Installing into the uv Python itself also works with `--break-system-packages`.
3. Tell the agent to call that `python.exe` for every `boardreview` command.

KiCad: a per-user install puts `kicad-cli.exe` under `%LOCALAPPDATA%\Programs\KiCad`, which the
sandbox cannot run. Install KiCad for all users (`%ProgramFiles%\KiCad`), or run the exports in
workflow/10_extract.md from a normal shell and give the review the files. Without either, the
review goes on with the open gate items that page lists.

Page rendering: the `boardreview` Python may have no PyMuPDF or poppler. Install `pymupdf` into
the same venv when that is allowed, or render pages with another Python the sandbox can read.
Rendering is the only job for that second Python.

## UTF-8 on Windows

When output goes to a pipe, as it does under an agent, Python on Windows writes it in the ANSI
code page (often cp1252). The ohm sign in calculator text, and other characters outside that
code page, then raise UnicodeEncodeError, and files opened without an encoding read wrong. Run every Python
command in UTF-8 mode, `python -X utf8 -m boardreview <command>`, or set `PYTHONUTF8=1` for the
session.
