"""Build the OBS-only Windows online installer and recipient ZIP from a clean checkout."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.request import urlopen
from zipfile import ZipFile, ZIP_DEFLATED

DOCS = Path(__file__).resolve().parent
REPO = DOCS.parents[1]
VERSION = "1.3.0"
BASE_NAME = "VoiceIsolatorRTX-OBS-" + VERSION
LOCK = json.loads((DOCS / "assets.lock.json").read_text(encoding="utf-8-sig"))


def digest(file):
    with file.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def compile_iss(iscc, file, definitions):
    subprocess.run([str(iscc), "/Q", *(f"/D{k}={v}" for k, v in definitions.items()),
                    str(file)], check=True)


def build(payload, out, nuget, iscc):
    out.mkdir(parents=True, exist_ok=True)
    if subprocess.check_output(["git", "-C", str(REPO), "status", "--porcelain", "--untracked-files=normal"]):
        raise ValueError("Build the source ZIP from a clean git checkout.")
    with tempfile.TemporaryDirectory(dir=out) as working:
        stage = Path(working)
        source = stage / "VoiceIsolatorRTX-OBS-source.zip"
        subprocess.run(["git", "-C", str(REPO), "archive", "--format=zip", "-o", str(source), "HEAD"], check=True)
        module = stage / "module"
        module.mkdir()
        compile_iss(iscc, REPO / "release/setup.iss", dict(ReleaseVersion=VERSION, Payload=payload,
                    SourceArchive=source, ReleaseDir=module))
        if not nuget:
            nuget = stage / "python.nupkg"
            with urlopen(LOCK["python"]["url"]) as response, nuget.open("wb") as f:
                shutil.copyfileobj(response, f)
        if digest(nuget) != LOCK["python"]["sha256"]:
            raise ValueError("Invalid CPython package checksum")
        bootstrap = stage / "bootstrap.zip"
        notices = {"OBS-GPL-2.0.txt": REPO / "LICENSE", "VoiceIsolator-MIT.txt": REPO / "shared-voice/LICENSE",
                   "Inworld-LICENSE.txt": REPO / "shared-voice/licenses/Inworld-LICENSE.txt",
                   "Inworld-NOTICE.txt": REPO / "shared-voice/licenses/Inworld-NOTICE.txt",
                   "Inno-Setup-LICENSE.txt": iscc.parent / "license.txt"}
        with ZipFile(nuget) as py, ZipFile(bootstrap, "w", ZIP_DEFLATED) as z:
            for name in py.namelist():
                if name.startswith("tools/") and not name.endswith("/"):
                    z.writestr("python/" + name.removeprefix("tools/"), py.read(name))
            z.writestr("python/python312._pth", ".\nLib\nDLLs\nLib/site-packages\nimport site\n")
            for file in sorted((REPO / "inference").rglob("*.py")):
                z.write(file, "inworld/" + file.relative_to(REPO / "inference").as_posix())
            for name in ("assets.lock.json", "prepare.py", "setup_assets.py"):
                z.write(DOCS / name, name)
            for name, path in notices.items():
                z.write(path, "licenses/" + name)
            py_license = py.read("tools/LICENSE.txt")
        queue = stage / "downloads.iss"
        queue.write_text("\n".join("      QueueAsset(" + ", ".join("'" + w[k].replace("'", "''") + "'"
                         for k in ("filename", "url", "sha256")) + ");"
                         for w in [*LOCK["wheels"], LOCK["model"]]), encoding="ascii")
        exe_name = BASE_NAME + "-Setup-x64.exe"
        compile_iss(iscc, DOCS / "obs-installer.iss", dict(Version=VERSION, Output=stage, Bootstrap=bootstrap,
                    ModuleSetup=module / exe_name, Docs=DOCS, DownloadsFile=queue))
        zip_name = BASE_NAME + "-Windows-x64.zip"
        files = {exe_name: stage / exe_name, "はじめに.txt": DOCS / "はじめに.txt",
                 "LICENSES.txt": DOCS / "LICENSES.txt", "source/" + source.name: source,
                 **{"licenses/" + k: v for k, v in notices.items()}}
        with ZipFile(stage / zip_name, "w", ZIP_DEFLATED) as z:
            for name, path in files.items():
                z.write(path, name)
            z.writestr("licenses/Python-LICENSE.txt", py_license)
        with ZipFile(stage / zip_name) as z:
            if z.testzip() or any(hashlib.sha256(z.read(n)).hexdigest() != digest(f) for n, f in files.items()):
                raise RuntimeError("Final archive content mismatch")
        (stage / zip_name).replace(out / zip_name)
        print(out / zip_name, (out / zip_name).stat().st_size, digest(out / zip_name))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", type=Path, required=True, help="Staged voice-isolator-rtx directory")
    parser.add_argument("--out", type=Path, default=REPO / "dist")
    parser.add_argument("--nuget", type=Path, help="Optional verified local Python 3.12.10 NuGet file")
    parser.add_argument("--iscc", type=Path, default=Path(os.environ["ProgramFiles(x86)"]) / "Inno Setup 6/ISCC.exe")
    options = parser.parse_args()
    build(options.payload.resolve(strict=True), options.out.resolve(), options.nuget, options.iscc)
