import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, abort, jsonify, request, Response
from pymongo import MongoClient, ASCENDING
from pymongo.errors import PyMongoError
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_TRANSCRIPT_BYTES", str(8 * 1024 * 1024)))

MONGODB_URI = os.getenv("TRANSCRIPT_MONGODB_URI", "").strip()
DB_NAME = os.getenv("TRANSCRIPT_DB_NAME", "orbit_transcripts").strip() or "orbit_transcripts"
UPLOAD_TOKEN = os.getenv("TRANSCRIPT_UPLOAD_TOKEN", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
_client = None
_collection = None


def collection():
    global _client, _collection
    if not MONGODB_URI:
        raise RuntimeError("TRANSCRIPT_MONGODB_URI não configurada")
    if _collection is None:
        _client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000, tz_aware=True)
        _collection = _client[DB_NAME]["transcripts"]
        _collection.create_index([("token", ASCENDING)], unique=True)
        _collection.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)
    return _collection


def require_upload_token():
    if not UPLOAD_TOKEN:
        return jsonify(success=False, error="O servidor não configurou TRANSCRIPT_UPLOAD_TOKEN."), 503
    supplied = request.headers.get("Authorization", "")
    expected = f"Bearer {UPLOAD_TOKEN}"
    if not hmac.compare_digest(supplied, expected):
        return jsonify(success=False, error="Token de upload inválido."), 401
    return None


@app.get("/")
def home():
    return Response("""<!doctype html><html lang='pt-BR'><meta charset='utf-8'>
    <meta name='viewport' content='width=device-width,initial-scale=1'>
    <title>Orbit Apps | Transcrições</title>
    <style>body{margin:0;background:#111118;color:#eee;font:16px system-ui;display:grid;min-height:100vh;place-items:center}.box{max-width:620px;padding:32px;border:1px solid #343443;border-radius:18px;background:#191922}h1{color:#b6a0ff;margin-top:0}p{line-height:1.6;color:#c9c9d4}</style>
    <main class='box'><h1>Orbit Apps Transcripts</h1><p>Serviço de hospedagem de transcrições de tickets.</p><p>O serviço está online. Os links são privados por identificador e podem expirar automaticamente.</p></main></html>""", mimetype="text/html")


@app.get("/health")
def health():
    return jsonify(status="ok", service="orbit-apps-transcripts")


@app.post("/api/v1/transcript/upload")
def upload_transcript():
    denied = require_upload_token()
    if denied:
        return denied

    uploaded = request.files.get("file")
    if uploaded is None:
        return jsonify(success=False, error="Campo 'file' ausente."), 400
    raw = uploaded.read(app.config["MAX_CONTENT_LENGTH"] + 1)
    if not raw:
        return jsonify(success=False, error="O arquivo está vazio."), 400
    if len(raw) > app.config["MAX_CONTENT_LENGTH"]:
        return jsonify(success=False, error="Transcrição muito grande."), 413
    try:
        html = raw.decode("utf-8")
    except UnicodeDecodeError:
        return jsonify(success=False, error="O arquivo precisa estar em UTF-8."), 400
    if "<html" not in html.lower():
        return jsonify(success=False, error="O conteúdo não parece ser um HTML."), 400

    token = secrets.token_urlsafe(16)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=int(os.getenv("TRANSCRIPT_TTL_DAYS", "3")))
    record = {
        "token": token,
        "html": html,
        "channel_name": (request.form.get("channel_name") or "ticket")[:100],
        "filename": (request.form.get("filename") or uploaded.filename or "transcript.html")[:150],
        "created_at": now,
        "expires_at": expires,
    }
    try:
        collection().insert_one(record)
    except RuntimeError as e:
        return jsonify(success=False, error=str(e)), 503
    except PyMongoError as e:
        app.logger.error("Erro no MongoDB ao salvar transcrição: %s", e)
        return jsonify(success=False, error="Não foi possível salvar a transcrição no banco."), 503

    base = PUBLIC_BASE_URL or request.url_root.rstrip("/")
    url = f"{base}/transcript/{token}"
    return jsonify(success=True, url=url, fullUrl=url, expiresAt=expires.isoformat()), 201


@app.get("/transcript/<token>")
def view_transcript(token):
    try:
        record = collection().find_one({"token": token}, {"_id": 0, "html": 1, "expires_at": 1})
    except (RuntimeError, PyMongoError) as e:
        app.logger.error("Erro ao consultar transcrição: %s", e)
        return Response("Serviço de transcrições temporariamente indisponível.", status=503, mimetype="text/plain")
    if not record:
        abort(404, description="Esta transcrição não existe ou expirou.")
    expires = record.get("expires_at")
    if expires and expires < datetime.now(timezone.utc):
        try:
            collection().delete_one({"token": token})
        except Exception:
            pass
        abort(404, description="Esta transcrição expirou.")

    response = Response(record["html"], mimetype="text/html; charset=utf-8")
    # Transcript content comes from Discord messages; disable scripts and active embeds.
    response.headers["Content-Security-Policy"] = "default-src https: data: blob:; script-src 'none'; style-src 'unsafe-inline' https:; img-src https: data: blob:; font-src https: data:; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "private, no-store"
    return response


@app.errorhandler(404)
def not_found(error):
    return Response("""<!doctype html><html lang='pt-BR'><meta charset='utf-8'><title>Transcrição não encontrada</title><body style='background:#111118;color:#eee;font:16px system-ui;padding:40px'><h1>Transcrição não encontrada</h1><p>O link pode estar incorreto ou a transcrição pode ter expirado.</p></body></html>""", status=404, mimetype="text/html")


@app.errorhandler(413)
def too_large(error):
    return jsonify(success=False, error="Arquivo excede o tamanho máximo permitido."), 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
