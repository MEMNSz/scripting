"""Servidor local de Trelby (editor HTML).

Liviano, solo librería estándar. Escucha únicamente en 127.0.0.1, sirve la
interfaz y lee/escribe guiones .fountain dentro de Documents\\Guiones.
Abre la app en su propia ventana (Edge/Chrome en modo --app) y se apaga solo
cuando la ventana lleva un rato cerrada.
"""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HOST = "127.0.0.1"
PORT = int(os.environ.get("SCRIPTING_PORT", "5170"))  # variable solo para pruebas
APP_DIR = Path(__file__).resolve().parent
SCRIPTS = Path.home() / "Documents" / "Guiones"
VERSIONS = SCRIPTS / ".versiones"
IDLE_EXIT = 90  # segundos sin noticias de la ventana -> se apaga
# imágenes de la Biblia/storyboard: por contenido (sha1), compartidas entre guiones y versiones
IMAGES = SCRIPTS / ".imagenes"
MIRRORS = SCRIPTS / ".salas"          # copia completa (Yjs) de cada sala online, para trabajar sin internet
ROOM_RE = re.compile(r"^[a-f0-9]{16}$")
UID_RE = re.compile(r"^[a-f0-9]{12}$")
IMG_RE = re.compile(r"^[0-9a-f]{40}[.](jpg|png|webp|gif)$")
IMG_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}
IMG_MIME = {v: k for k, v in IMG_EXT.items()}
NAME_RE = re.compile(r"^[^\\/:*?\"<>|]{1,120}\.fountain$")

last_ping = time.time()

# ---------------- actualizaciones (GitHub Releases) ----------------
UPDATE_REPO = "MEMNSz/scripting"
UPDATE_API = os.environ.get("SCRIPTING_UPDATE_API", "https://api.github.com")  # variable solo para pruebas
UPDATES_DIR = APP_DIR / ".actualizaciones"   # copias de lo que reemplaza cada actualización
UPDATE_SKIP = {".git", ".venv", "voces", ".actualizaciones", "__pycache__"}
_upd = {"t": 0.0, "data": None}


def app_version():
    try:
        return (APP_DIR / "VERSION").read_text(encoding="utf-8").strip() or "0.0.0"
    except OSError:
        return "0.0.0"


def vtuple(v):
    n = [int(x) for x in re.findall(r"\d+", v or "")[:3]]
    return tuple(n + [0] * (3 - len(n)))


def gh_get(path, accept="application/vnd.github+json"):
    import urllib.request
    req = urllib.request.Request(UPDATE_API + path, headers={"User-Agent": "Scripting-updater", "Accept": accept})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def update_check(force=False):
    if not force and _upd["data"] and time.time() - _upd["t"] < 1800:
        return _upd["data"]
    import urllib.error
    cur, dev = app_version(), (APP_DIR / ".git").exists()
    try:
        rel = json.loads(gh_get(f"/repos/{UPDATE_REPO}/releases/latest"))
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        rel = {}  # todavía no hay ninguna versión publicada
    tag = rel.get("tag_name", "")
    data = {"current": cur, "latest": tag.lstrip("vV"), "tag": tag, "newer": bool(tag) and vtuple(tag) > vtuple(cur),
            "name": rel.get("name") or tag, "notes": (rel.get("body") or "")[:4000], "url": rel.get("html_url", ""), "dev": dev}
    _upd.update(t=time.time(), data=data)
    return data


def update_apply():
    import io
    import zipfile
    info = update_check(force=True)
    if info["dev"]:
        raise RuntimeError("Esta es la copia de desarrollo (tiene .git): se actualiza con git pull.")
    if not info["newer"]:
        raise RuntimeError("Ya tenés la última versión.")
    z = zipfile.ZipFile(io.BytesIO(gh_get(f"/repos/{UPDATE_REPO}/zipball/{info['tag']}", accept="*/*")))
    names = z.namelist()
    root = names[0].split("/")[0] + "/"
    base, files = APP_DIR.resolve(), {}
    for n in names:
        if n.endswith("/") or not n.startswith(root):
            continue
        rel = n[len(root):]
        parts = Path(rel).parts
        if not parts or ".." in parts or parts[0] in UPDATE_SKIP or Path(rel).is_absolute():
            continue
        dst = (APP_DIR / rel).resolve()
        if base not in dst.parents:
            continue
        files[rel] = (n, dst)
    for need in ("index.html", "server.py", "VERSION"):
        if need not in files:
            raise RuntimeError(f"El paquete no trae {need}.")
    newv = z.read(files["VERSION"][0]).decode("utf-8").strip()
    if vtuple(newv) != vtuple(info["tag"]):
        raise RuntimeError(f"El paquete dice versión {newv} y la publicada es {info['tag']}.")
    old = app_version()
    bdir = UPDATES_DIR / f"{old}-{datetime.now():%Y%m%d-%H%M%S}"
    for rel, (n, dst) in files.items():  # copia de lo que se va a pisar
        if dst.exists():
            b = bdir / rel
            b.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, b)
    for rel, (n, dst) in files.items():
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".upd-tmp")
        tmp.write_bytes(z.read(n))
        os.replace(tmp, dst)
    _upd["data"] = None
    return {"ok": True, "from": old, "to": newv, "files": len(files), "backup": str(bdir)}


def restart_soon():
    """Relanza el servidor (ya con el código nuevo) y cierra este."""
    def go():
        time.sleep(0.8)
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen([sys.executable, str(APP_DIR / "server.py"), "--no-window", "--wait-port"],
                         cwd=str(APP_DIR), creationflags=flags, close_fds=True)
        os._exit(0)
    threading.Thread(target=go, daemon=True).start()


# ---------------- lectura en voz alta (Piper local / voces de Edge en línea) ----------------
import asyncio
import hashlib
import io
import wave

VOICES_DIR = APP_DIR / "voces"
TTS_CACHE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Trelby-HTML" / "tts-cache"
PIPER_INFO = {  # nombre y género de las voces bajadas
    "es_AR-daniela-high": ("Daniela", "F"), "es_MX-ald-medium": ("Ald", "M"),
    "en_US-lessac-medium": ("Lessac", "F"), "en_US-ryan-medium": ("Ryan", "M"),
}
_piper, _piper_lock, _edge_list = {}, threading.Lock(), None


def piper_voices():
    out = []
    for f in sorted(VOICES_DIR.glob("*.onnx")):
        name, g = PIPER_INFO.get(f.stem, (f.stem.split("-")[1].title(), ""))
        out.append({"id": f.stem, "name": name, "lang": f.stem.split("-")[0].replace("_", "-"), "gender": g})
    return out


def edge_voices():
    global _edge_list
    if _edge_list is None:
        import edge_tts
        vs = asyncio.run(edge_tts.list_voices())
        _edge_list = [{"id": v["ShortName"], "name": v["ShortName"].split("-")[-1].replace("Neural", "").replace("Multilingual", " multi"),
                       "lang": v["Locale"], "gender": v["Gender"][0]}
                      for v in vs if v["Locale"].split("-")[0] in ("es", "en")]
    return _edge_list


def tts_audio(engine, voice, text, rate):
    """Devuelve (bytes, mime). Cachea en disco: releer una escena es instantáneo."""
    key = hashlib.sha1(f"{engine}|{voice}|{rate:.2f}|{text}".encode("utf-8")).hexdigest()
    ext, mime = ("wav", "audio/wav") if engine == "piper" else ("mp3", "audio/mpeg")
    f = TTS_CACHE / f"{key}.{ext}"
    if f.exists():
        return f.read_bytes(), mime
    TTS_CACHE.mkdir(parents=True, exist_ok=True)
    if engine == "piper":
        from piper import PiperVoice, SynthesisConfig
        onnx = VOICES_DIR / f"{voice}.onnx"
        if not re.fullmatch(r"[\w-]+", voice) or not onnx.exists():
            raise ValueError("voz de Piper desconocida")
        with _piper_lock:  # un modelo a la vez: liviano y seguro entre hilos
            v = _piper.get(voice) or _piper.setdefault(voice, PiperVoice.load(str(onnx)))
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                v.synthesize_wav(text, wf, syn_config=SynthesisConfig(length_scale=1 / max(0.5, min(2.0, rate))))
        data = buf.getvalue()
    else:
        import edge_tts
        if not re.fullmatch(r"[a-z]{2}-[A-Z]{2}-\w+", voice):
            raise ValueError("voz de Edge no válida")
        pct = round((rate - 1) * 100)
        async def go():
            out = b""
            async for ch in edge_tts.Communicate(text, voice, rate=f"{pct:+d}%").stream():
                if ch["type"] == "audio":
                    out += ch["data"]
            return out
        data = asyncio.run(go())
        if not data:
            raise RuntimeError("Edge no devolvió audio")
    f.write_bytes(data)
    return data, mime


VER_RE = re.compile(r"^\d{8}-\d{6}(\d{3})?(__[^\\/:*?\"<>|]{1,60})?$")
LABEL_BAD = re.compile(r"[\\/:*?\"<>|\r\n]")


def snapshot(p, label=""):
    """Copia el guion actual a .versiones\\<guion>\\. Sin nombre, no duplica si no cambió."""
    vdir = VERSIONS / p.stem
    vdir.mkdir(parents=True, exist_ok=True)
    data = p.read_bytes()
    olds = sorted(vdir.glob("*.fountain"))
    if not label and olds and olds[-1].read_bytes() == data:
        return None
    label = LABEL_BAD.sub("-", label).strip()[:60]
    now = datetime.now()
    name = f"{now:%Y%m%d-%H%M%S}{now.microsecond // 1000:03d}" + (f"__{label}" if label else "") + ".fountain"
    (vdir / name).write_bytes(data)
    return name


def list_versions(p):
    vdir = VERSIONS / p.stem
    out = []
    for f in vdir.glob("*.fountain") if vdir.exists() else []:
        if not VER_RE.match(f.stem):
            continue
        ts, _, label = f.stem.partition("__")
        t = datetime.strptime(ts[:15], "%Y%m%d-%H%M%S").timestamp() + int(ts[15:] or 0) / 1000
        out.append({"id": f.stem, "label": label, "time": t, "size": f.stat().st_size})
    return sorted(out, key=lambda v: -v["time"])


def safe_path(name):
    """Devuelve la ruta del guion o None si el nombre no es válido."""
    if not name or not NAME_RE.match(name) or name.startswith("."):
        return None
    p = (SCRIPTS / name).resolve()
    return p if p.parent == SCRIPTS.resolve() else None



# ---------- Hostear en mi Cloudflare: sube el servidor de salas a la cuenta del usuario ----------
# El token lo pega el usuario en la app; pasa solo por acá hacia api.cloudflare.com y no se guarda.
CF_NAME = "scripting-server"
def cf_deploy(token):
    import urllib.request, urllib.error, secrets
    def call(method, path, body=None, ctype="application/json"):
        data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
        req = urllib.request.Request("https://api.cloudflare.com/client/v4" + path, data=data, method=method,
                                     headers={"Authorization": "Bearer " + token, "Content-Type": ctype})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                j = json.loads(e.read())
                msg = "; ".join(x.get("message", "") for x in j.get("errors", [])) or str(e)
            except Exception:
                msg = str(e)
            raise RuntimeError(f"Cloudflare dijo: {msg} ({method} {path.split('/')[-1]})")
    accs = call("GET", "/accounts").get("result") or []
    if not accs:
        raise RuntimeError("El token no ve ninguna cuenta: creálo con la plantilla “Edit Cloudflare Workers”")
    acc = accs[0]["id"]
    scripts = call("GET", f"/accounts/{acc}/workers/scripts").get("result") or []
    exists = any(x.get("id") == CF_NAME for x in scripts)
    code = (Path(__file__).parent / "sync" / "src" / "index.js").read_text(encoding="utf-8")
    key = None
    meta = {"main_module": "index.js", "compatibility_date": "2026-11-01",
            "bindings": [{"type": "durable_object_namespace", "name": "ROOMS", "class_name": "Room"},
                         {"type": "durable_object_namespace", "name": "HUB", "class_name": "Hub"}]}
    if exists:
        meta["keep_bindings"] = ["secret_text"]      # conserva la clave de instalación de antes
    else:
        key = secrets.token_urlsafe(18)
        meta["bindings"].append({"type": "secret_text", "name": "SETUP_KEY", "text": key})
        meta["migrations"] = {"new_tag": "v1", "new_sqlite_classes": ["Room", "Hub"]}
    b = "----scripting" + secrets.token_hex(8)
    CRLF = "\r\n"
    head = (f"--{b}{CRLF}Content-Disposition: form-data; name=\"metadata\"{CRLF}Content-Type: application/json{CRLF}{CRLF}{json.dumps(meta)}{CRLF}"
            f"--{b}{CRLF}Content-Disposition: form-data; name=\"index.js\"; filename=\"index.js\"{CRLF}Content-Type: application/javascript+module{CRLF}{CRLF}")
    body = head.encode() + code.encode("utf-8") + f"{CRLF}--{b}--{CRLF}".encode()
    call("PUT", f"/accounts/{acc}/workers/scripts/{CF_NAME}", body, f"multipart/form-data; boundary={b}")
    try:
        sub = call("GET", f"/accounts/{acc}/workers/subdomain").get("result", {}).get("subdomain")
    except RuntimeError:
        sub = None
    if not sub:
        sub = "scripting-" + secrets.token_hex(3)
        call("PUT", f"/accounts/{acc}/workers/subdomain", {"subdomain": sub})
    call("POST", f"/accounts/{acc}/workers/scripts/{CF_NAME}/subdomain", {"enabled": True})
    return {"ok": True, "url": f"https://{CF_NAME}.{sub}.workers.dev", "key": key, "updated": exists}

class Handler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".webmanifest": "application/manifest+json",
        ".svg": "image/svg+xml",
        ".js": "text/javascript",
    }

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(APP_DIR), **kw)

    def log_message(self, *a):  # silencioso
        pass

    # Solo se acepta lo que viene de esta misma app (evita que otra página
    # del navegador lea o escriba guiones).
    def _trusted(self):
        host = self.headers.get("Host", "")
        if host not in (f"{HOST}:{PORT}", f"localhost:{PORT}"):
            return False
        if self.command == "POST" and self.headers.get("X-Trelby") != "1":
            return False
        return True

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        if not self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def do_GET(self):
        global last_ping
        if not self._trusted():
            return self._json({"error": "origen no permitido"}, 403)
        url = urlparse(self.path)
        q = parse_qs(url.query)
        if url.path == "/api/update/check":
            try:
                return self._json(update_check(q.get("force", ["0"])[0] == "1"))
            except Exception as e:
                return self._json({"error": f"No pude consultar GitHub: {e}", "current": app_version()}, 502)
        if url.path == "/api/update/version":
            return self._json({"version": app_version()})
        if url.path == "/api/mirror":
            room = q.get("room", [""])[0]
            if not room:
                items = []
                for m in sorted(MIRRORS.glob("*.json"), key=lambda p: -p.stat().st_mtime) if MIRRORS.exists() else []:
                    try:
                        items.append({**json.loads(m.read_text(encoding="utf-8")), "id": m.stem.split(".")[0], "mtime": m.stat().st_mtime})
                    except Exception:
                        pass
                return self._json({"rooms": items})
            uid = q.get("u", [""])[0]
            p = MIRRORS / f"{room}.{uid}.yjs"
            if not ROOM_RE.match(room) or not UID_RE.match(uid) or not p.exists():
                return self._json({"error": "sin copia local"}, 404)
            data = p.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if url.path == "/api/ping":
            last_ping = time.time()
            return self._json({"ok": True, "dir": str(SCRIPTS)})
        if url.path == "/api/list":
            last_ping = time.time()
            items = [
                {"name": p.name, "mtime": p.stat().st_mtime, "size": p.stat().st_size}
                for p in SCRIPTS.glob("*.fountain")
            ]
            items.sort(key=lambda x: -x["mtime"])
            return self._json({"dir": str(SCRIPTS), "items": items})
        if url.path == "/api/open":
            p = safe_path(q.get("name", [""])[0])
            if not p or not p.exists():
                return self._json({"error": "no existe"}, 404)
            return self._json({"name": p.name, "text": p.read_text(encoding="utf-8")})
        if url.path == "/api/voices":
            res = {"piper": piper_voices(), "edge": [], "edgeError": None}
            try:
                res["edge"] = edge_voices()
            except Exception as e:  # sin internet o servicio caído: queda Piper
                res["edgeError"] = f"{type(e).__name__}: {e}"[:200]
            return self._json(res)
        if url.path == "/api/versions":
            p = safe_path(q.get("name", [""])[0])
            if not p:
                return self._json({"error": "nombre no válido"}, 400)
            return self._json({"items": list_versions(p)})
        if url.path == "/api/version":
            p = safe_path(q.get("name", [""])[0])
            vid = q.get("id", [""])[0]
            if not p or not VER_RE.match(vid):
                return self._json({"error": "pedido no válido"}, 400)
            f = VERSIONS / p.stem / (vid + ".fountain")
            if not f.exists():
                return self._json({"error": "no existe"}, 404)
            return self._json({"id": vid, "text": f.read_text(encoding="utf-8")})
        if url.path == "/api/img":
            name = q.get("f", [""])[0]
            f = IMAGES / name
            if not IMG_RE.match(name) or not f.exists():
                return self._json({"error": "no existe"}, 404)
            data = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", IMG_MIME[name.rsplit(".", 1)[1]])
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "max-age=31536000, immutable")
            self.end_headers()
            self.wfile.write(data)
            return
        if url.path.startswith("/api/"):
            return self._json({"error": "ruta desconocida"}, 404)
        if url.path.endswith((".py", ".bat")) or "/." in url.path or ".bak" in url.path or url.path.startswith(("/voces/", "/ventana/")):
            return self._json({"error": "no"}, 404)
        return super().do_GET()

    def do_POST(self):
        if not self._trusted():
            return self._json({"error": "origen no permitido"}, 403)
        url = urlparse(self.path)
        q = parse_qs(url.query)
        if url.path == "/api/update/apply":
            try:
                res = update_apply()
            except Exception as e:
                return self._json({"error": str(e)}, 400)
            self._json(res)
            restart_soon()
            return
        if url.path == "/api/tts":
            n = int(self.headers.get("Content-Length", "0"))
            try:
                req = json.loads(self.rfile.read(min(n, 20000)).decode("utf-8"))
                text = str(req.get("text", "")).strip()[:3000]
                if not text:
                    return self._json({"error": "sin texto"}, 400)
                data, mime = tts_audio(req.get("engine", "piper"), str(req.get("voice", "")), text, float(req.get("rate", 1)))
            except Exception as e:
                return self._json({"error": f"{type(e).__name__}: {e}"[:300]}, 502)
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if url.path == "/api/mirror":
            room = q.get("room", [""])[0]
            n = int(self.headers.get("Content-Length", "0"))
            uid = q.get("u", [""])[0]
            if not ROOM_RE.match(room) or not UID_RE.match(uid) or not 0 < n <= 50_000_000:
                return self._json({"error": "sala o tamaño no válido"}, 400)
            data = self.rfile.read(n)
            MIRRORS.mkdir(parents=True, exist_ok=True)
            if q.get("kind", [""])[0] == "fountain":
                # copia legible del guion de la sala, para abrirla con cualquier programa
                name = re.sub(r'[\\/:*?"<>|.]+', "-", q.get("name", ["sala"])[0])[:80].strip() or "sala"
                out = SCRIPTS / "Salas online"
                out.mkdir(parents=True, exist_ok=True)
                (out / f"{name}.fountain").write_bytes(data)
                return self._json({"ok": True})
            tmp = MIRRORS / f"{room}.{uid}.yjs.tmp"
            tmp.write_bytes(data)
            os.replace(tmp, MIRRORS / f"{room}.{uid}.yjs")
            (MIRRORS / f"{room}.{uid}.json").write_text(json.dumps({"name": q.get("name", [""])[0][:80], "srv": q.get("srv", [""])[0][:200], "u": uid}, ensure_ascii=False), encoding="utf-8")
            return self._json({"ok": True})
        if url.path == "/api/reveal":
            # abre el Explorador con el archivo exportado marcado (solo dentro de Guiones)
            try:
                p = Path(q.get("path", [""])[0]).resolve()
                p.relative_to(SCRIPTS.resolve())
            except Exception:
                return self._json({"error": "ruta no válida"}, 400)
            if p.exists():
                subprocess.Popen(f'explorer.exe /select,"{p}"')
            return self._json({"ok": p.exists()})
        if url.path == "/api/pdf":
            # PDF de novela: Edge en segundo plano imprime el HTML que arma la app (sin cuadro de impresión ni encabezados del navegador)
            name = re.sub(r'[\\/:*?"<>|]+', "-", q.get("name", [""])[0]).strip().lstrip(".")[:120]
            n = int(self.headers.get("Content-Length", "0"))
            if not name.lower().endswith(".pdf") or not 0 < n <= 20_000_000:
                return self._json({"error": "nombre o tamaño no válido"}, 400)
            edge = next((p for p in (os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"), os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe")) if os.path.exists(p)), None)
            if not edge:
                return self._json({"error": "no encontré Microsoft Edge para armar el PDF"}, 500)
            import tempfile
            tmp = Path(tempfile.mkdtemp(prefix="scripting-pdf-"))
            src = tmp / "libro.html"
            src.write_bytes(self.rfile.read(n))
            raw = q.get("raw", [""])[0] == "1"   # raw: devuelve el PDF para que la app lo guarde donde elija el usuario
            if raw:
                dst = Path(tempfile.gettempdir()) / f"scripting-{time.time_ns()}.pdf"
            else:
                out = SCRIPTS / "Exportados"
                out.mkdir(parents=True, exist_ok=True)
                dst = out / name
            try:
                subprocess.run([edge, "--headless", "--disable-gpu", "--no-pdf-header-footer", "--no-first-run",
                                f"--user-data-dir={tmp / 'perfil'}", f"--print-to-pdf={dst}", src.as_uri()],
                               timeout=90, capture_output=True)
            except Exception as e:
                return self._json({"error": f"Edge no pudo armar el PDF: {e}"}, 500)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            if not dst.exists() or dst.stat().st_size < 500:
                return self._json({"error": "Edge no generó el PDF"}, 500)
            if raw:
                data = dst.read_bytes()
                dst.unlink(missing_ok=True)
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if q.get("open", [""])[0] == "1":
                try:
                    subprocess.Popen(f'explorer.exe /select,"{dst}"')
                except Exception:
                    pass
            return self._json({"ok": True, "path": str(dst)})
        if url.path == "/api/export":
            # archivos exportados (Word, EPUB) en Documents\Guiones\Exportados
            name = re.sub(r'[\\/:*?"<>|]+', "-", q.get("name", [""])[0]).strip().lstrip(".")[:120]
            n = int(self.headers.get("Content-Length", "0"))
            if not re.search(r"\.(docx|epub|fdx|fountain|doc)$", name, re.I) or not 0 < n <= 50_000_000:
                return self._json({"error": "nombre o tamaño no válido"}, 400)
            out = SCRIPTS / "Exportados"
            out.mkdir(parents=True, exist_ok=True)
            p = out / name
            p.write_bytes(self.rfile.read(n))
            if q.get("open", [""])[0] == "1":
                try:
                    subprocess.Popen(f'explorer.exe /select,"{p}"')
                except Exception:
                    pass
            return self._json({"ok": True, "path": str(p)})
        if url.path == "/api/cf-deploy":
            n = int(self.headers.get("Content-Length", "0"))
            try:
                token = str(json.loads(self.rfile.read(min(n, 5000)).decode("utf-8")).get("token", "")).strip()
                if not re.fullmatch(r"[A-Za-z0-9_-]{20,200}", token):
                    return self._json({"error": "ese token no tiene pinta de token de Cloudflare"}, 400)
                return self._json(cf_deploy(token))
            except Exception as e:
                return self._json({"error": str(e)[:400]}, 502)
        if url.path == "/api/img":
            ext = IMG_EXT.get(self.headers.get("Content-Type", "").split(";")[0].strip())
            n = int(self.headers.get("Content-Length", "0"))
            if not ext or not 0 < n <= 15_000_000:
                return self._json({"error": "imagen no válida (jpg, png, webp o gif de hasta 15 MB)"}, 400)
            data = self.rfile.read(n)
            name = f"{hashlib.sha1(data).hexdigest()}.{ext}"
            IMAGES.mkdir(parents=True, exist_ok=True)
            if not (IMAGES / name).exists():
                tmp = IMAGES / (name + ".tmp")
                tmp.write_bytes(data)
                os.replace(tmp, IMAGES / name)
            return self._json({"ok": True, "name": name})
        if url.path not in ("/api/save", "/api/snapshot"):
            return self._json({"error": "ruta desconocida"}, 404)
        p = safe_path(q.get("name", [""])[0])
        if not p:
            return self._json({"error": "nombre no válido"}, 400)
        n = int(self.headers.get("Content-Length", "0"))
        if n > 20_000_000:
            return self._json({"error": "demasiado grande"}, 413)
        text = self.rfile.read(n).decode("utf-8")
        # copia de la versión anterior antes de pisarla (solo si de verdad cambia)
        if (p.exists() and (q.get("version", ["0"])[0] == "1" or url.path == "/api/snapshot")
                and p.read_text(encoding="utf-8") != text):
            snapshot(p)
        tmp = p.with_suffix(".fountain.tmp")
        tmp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(tmp, p)
        made = None
        mode = q.get("version", ["0"])[0]
        if url.path == "/api/snapshot":  # versión con nombre del contenido nuevo
            made = snapshot(p, q.get("label", [""])[0] or "Versión manual")
        elif mode == "1":  # Ctrl+S: punto del historial con lo que hay ahora (no duplica)
            made = snapshot(p)
        elif mode == "auto":  # autoguardado: una versión automática cada 10 min si cambió
            vdir = VERSIONS / p.stem
            olds = sorted(vdir.glob("*.fountain")) if vdir.exists() else []
            if not olds or (time.time() - olds[-1].stat().st_mtime > 600 and olds[-1].read_bytes() != p.read_bytes()):
                made = snapshot(p, "Autoguardado")
        return self._json({"ok": True, "name": p.name, "path": str(p), "version": made})


def find_browser():
    cands = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    return next((c for c in cands if os.path.exists(c)), None)


def open_window():
    url = f"http://{HOST}:{PORT}/index.html"
    exe = find_browser()
    if exe:
        subprocess.Popen([exe, f"--app={url}", "--window-size=1600,950"])
    else:
        webbrowser.open(url)


def port_busy():
    with socket.socket() as s:
        return s.connect_ex((HOST, PORT)) == 0


def watchdog(server):
    while True:
        time.sleep(10)
        if time.time() - last_ping > IDLE_EXIT:
            server.shutdown()
            return


def main():
    # si existe el entorno de la app (voces), correr con ese Python
    venv = APP_DIR / ".venv" / "Scripts" / ("pythonw.exe" if Path(sys.executable).name.lower() == "pythonw.exe" else "python.exe")
    if venv.exists() and Path(sys.executable).resolve() != venv.resolve() and not os.environ.get("TRELBY_NO_VENV"):
        os.environ["TRELBY_NO_VENV"] = "1"
        sys.exit(subprocess.call([str(venv), str(Path(__file__).resolve()), *sys.argv[1:]]))
    if "--wait-port" in sys.argv:  # relanzado tras actualizar: esperar a que se libere el puerto
        for _ in range(60):
            if not port_busy():
                break
            time.sleep(0.2)
        else:
            return
    if port_busy():  # ya está abierto: solo otra ventana
        open_window()
        return
    SCRIPTS.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    threading.Thread(target=watchdog, args=(server,), daemon=True).start()
    if "--no-window" not in sys.argv:
        open_window()
    server.serve_forever()


if __name__ == "__main__":
    main()
