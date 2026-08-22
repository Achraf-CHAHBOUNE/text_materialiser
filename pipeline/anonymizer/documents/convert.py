"""Convert legacy/binary .doc to .docx via LibreOffice (headless).

python-docx can't read the old binary Word format (OLE), so we shell out to
LibreOffice's `soffice --convert-to docx`. Each call uses its own throwaway user
profile so conversions can run in parallel without profile-lock clashes.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

# Common Windows install locations (used when SOFFICE_PATH is not set).
_CANDIDATES = [
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/usr/bin/soffice",
    "/usr/bin/libreoffice",
]


def autodetect_soffice() -> str:
    for c in _CANDIDATES:
        if Path(c).exists():
            return c
    found = shutil.which("soffice") or shutil.which("libreoffice")
    return found or ""


def convert_to_docx(src: Path, soffice: str, out_dir: Path, timeout: int = 120) -> Path:
    """Convert `src` (.doc) to .docx inside `out_dir`; return the new path."""
    if not soffice:
        raise RuntimeError(
            "LibreOffice not found. Install it or set SOFFICE_PATH in .env "
            "to enable .doc conversion."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / (src.stem + ".docx")

    with tempfile.TemporaryDirectory() as profile:
        cmd = [
            soffice,
            f"-env:UserInstallation=file:///{Path(profile).as_posix()}",
            "--headless", "--norestore", "--convert-to", "docx",
            "--outdir", str(out_dir), str(src),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    if not target.exists():
        raise RuntimeError(
            f"LibreOffice failed to convert {src.name}: "
            f"{(proc.stderr or proc.stdout or 'no output').strip()[:200]}"
        )
    return target
