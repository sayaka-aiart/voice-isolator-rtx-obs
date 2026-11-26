"""Plan per-user engine installation and stage only the files that need repair."""
import base64
import contextlib
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import prepare

LOCK = json.loads((ROOT / "assets.lock.json").read_text(encoding="utf-8-sig"))
SITE = Path("python/Lib/site-packages")


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def key(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def distributions(root):
    if not (root / SITE).is_dir():
        return {}
    return {key(d.metadata["Name"]): d for d in metadata.distributions(path=[str(root / SITE)])
            if d.metadata.get("Name")}


def distribution_files(dist):
    for entry in dist.files or ():
        path = PurePosixPath(str(entry).replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or ":" in str(path) or path.suffix == ".pyc":
            continue
        yield entry


def intact(dist, wheel, site):
    if dist is None or dist.version != wheel["version"] or not dist.files:
        return False
    try:
        for entry in distribution_files(dist):
            path = site / entry
            stat = path.stat()
            if entry.size is not None and stat.st_size != entry.size:
                return False
            # RECORD hashes can be checked without the original wheel or an online index.
            if entry.hash and entry.hash.mode == "sha256":
                with path.open("rb") as f:
                    actual = hashlib.file_digest(f, "sha256").digest()
                if base64.urlsafe_b64encode(actual).rstrip(b"=").decode() != entry.hash.value:
                    return False
        return True
    except OSError:
        return False


def local_model(engine, setup_dir, selected):
    expected = LOCK["model"]
    name = expected["filename"]
    def matches(p):
        try:
            return p.is_file() and p.stat().st_size == expected["bytes"] and sha(p) == expected["sha256"]
        except OSError:
            return False
    if selected:
        p = Path(selected)
        if not matches(p):
            raise ValueError("The selected model does not match the required Inworld realtime model (SHA-256).")
        return p.resolve()
    default = Path(os.environ["LOCALAPPDATA"]) / "Programs/VoiceIsolatorRTX/engine-1.0.0"
    candidates = [engine / "inworld/models" / name, default / "inworld/models" / name,
                  setup_dir / name, setup_dir / "models" / name]
    home = Path(os.environ.get("HF_HOME", Path.home() / ".cache/huggingface"))
    hub = Path(os.environ.get("HF_HUB_CACHE", os.environ.get("HUGGINGFACE_HUB_CACHE", home / "hub")))
    cache = hub / "models--inworld--voice-isolator"
    candidates.append(cache / "blobs" / expected["sha256"])
    candidates.extend((cache / "snapshots").glob("*/" + name))
    return next((p.resolve() for p in dict.fromkeys(candidates) if matches(p)), None)


def plan(engine, setup_dir, selected):
    installed = distributions(engine)
    keep = []
    need = []
    for wheel in LOCK["wheels"]:
        if intact(installed.get(key(wheel["package"])), wheel, engine / SITE):
            keep.append(wheel["package"])
        else:
            need.append(wheel["filename"])
    model = local_model(engine, setup_dir, selected)
    if not model:
        need.append(LOCK["model"]["filename"])
    target = engine / "inworld/models" / LOCK["model"]["filename"]
    core = [p.relative_to(ROOT) for p in (ROOT / "inworld").rglob("*.py")]
    core.append(Path("assets.lock.json"))
    existing = (engine / "python/python.exe").is_file() and (engine / "prepare.py").is_file()
    complete = (existing and not need and target.is_file() and
                (model == target.resolve() or sha(target) == LOCK["model"]["sha256"]) and
                all((engine / p).is_file() and sha(engine / p) == sha(ROOT / p) for p in core))
    if complete:
        # Try the real private runtime before committing to offline reuse.
        args = [str(engine / "python/python.exe"), "-I", "-B", "-X", "utf8", str(engine / "prepare.py"),
                "diagnose", str(engine), str(LOG)]
        complete = subprocess.run(args, check=False).returncode == 0
    if not complete:
        prepare.precheck(engine)
    (ROOT.parent / "asset-plan.json").write_text(json.dumps(
        dict(keep=keep, need=need, model=str(model) if model else None, complete=complete)), encoding="utf-8")
    (ROOT.parent / "need.txt").write_text("\n".join(need), encoding="ascii")
    if complete:
        (ROOT.parent / "reuse.ok").touch()
    print(f"OBS asset plan: engine_reused={complete} local_wheels={len(keep)} "
          f"model={'local' if model else 'download'} downloads={len(need)}")
    if need:
        print("Required assets:", ", ".join(need))


def stage(engine):
    data = json.loads((ROOT.parent / "asset-plan.json").read_text(encoding="utf-8"))
    needed = set(data["need"])
    model = LOCK["model"]
    original = Path(data["model"]) if data["model"] else ROOT.parent / model["filename"]
    dest = ROOT / "inworld/models" / model["filename"]
    dest.parent.mkdir(exist_ok=True)
    shutil.copyfile(original, dest)
    if sha(dest) != model["sha256"]:
        raise ValueError("Model SHA-256 mismatch")
    def requirement(w):
        return f"{w['package']}=={w['version']} --hash=sha256:{w['sha256']}\n"
    (ROOT / "requirements.lock").write_text("".join(map(requirement, LOCK["wheels"])), encoding="ascii")
    missing = [w for w in LOCK["wheels"] if w["filename"] in needed]
    if missing:
        req = ROOT.parent / "missing.lock"
        req.write_text("".join(map(requirement, missing)), encoding="ascii")
        subprocess.run([sys.executable, "-I", "-B", "-m", "pip", "--isolated", "--disable-pip-version-check",
                        "install", "--no-index", "--no-deps", "--ignore-installed", "--no-cache-dir", "--no-compile",
                        "--no-warn-script-location", "--require-hashes", "--find-links", str(ROOT.parent),
                        "-r", str(req)], env=dict(os.environ, PIP_CONFIG_FILE=os.devnull), check=True,
                       stdout=sys.stdout, stderr=sys.stderr)
    installed = distributions(engine)
    linked = []
    for name in data["keep"]:
        for entry in distribution_files(installed[key(name)]):
            source = engine / SITE / entry
            copy = ROOT / SITE / entry
            if copy.exists():
                continue
            copy.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(source, copy)
            except OSError:
                shutil.copyfile(source, copy)
            linked.append(copy)
    prepare.smoke()
    # Existing libraries stay in their original location and keep their original installer ownership.
    for path in linked:
        path.unlink()


if __name__ == "__main__":
    action, target, directory, selected, logfile = sys.argv[1:]
    LOG = Path(logfile)
    with LOG.open("a", encoding="utf-8", buffering=1) as out:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            try:
                if action == "plan":
                    plan(Path(target), Path(directory), selected)
                elif action == "stage":
                    stage(Path(target))
                else:
                    raise ValueError(action)
            except Exception:
                traceback.print_exc()
                sys.exit(1)
