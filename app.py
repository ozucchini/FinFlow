import os, hmac
from flask import Flask, jsonify, request, render_template, abort
import core
core.init()
app = Flask(__name__)
KEY = os.getenv("API_KEY", "")
WH = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
CRON = os.getenv("CRON_SECRET", "")

def ok(esperado, recebido):   # segredo vazio = rota bloqueada (nunca aberta)
    return bool(esperado) and hmac.compare_digest(esperado.encode(), (recebido or "").encode())

@app.after_request
def seguranca(r):
    r.headers["Cache-Control"] = "no-store"
    r.headers["Referrer-Policy"] = "no-referrer"
    r.headers["X-Robots-Tag"] = "noindex"
    r.headers["X-Content-Type-Options"] = "nosniff"
    return r

@app.get("/d/<token>")
def painel(token): return render_template("dashboard.html", token=token)

@app.get("/api/resumo")
def resumo():
    r = core.resumo(request.headers.get("X-Token", ""))
    return jsonify(r) if r else abort(404)

# --- Telegram (webhook) ---
@app.post("/api/telegram")
def telegram():
    if not ok(WH, request.headers.get("X-Telegram-Bot-Api-Secret-Token")): abort(401)
    try:
        return jsonify(status=core.processar_update(request.get_json(force=True, silent=True) or {}))
    except Exception:
        app.logger.exception("falha ao processar update")
        return jsonify(status="erro"), 500   # o Telegram reenvia depois

# --- agendamento (Vercel Cron, 1x/dia 20h de Brasília): domingo = semana, último dia do mês = mês ---
@app.get("/api/cron")
def cron():
    if not ok(CRON, request.headers.get("Authorization", "").removeprefix("Bearer ")): abort(401)
    h = core.hoje(); feito = {}
    if h.weekday() == 6: feito["semana"] = core.relatorio_todos("semana", True, h)
    if h == core.fim_mes(h): feito["mes"] = core.relatorio_todos("mes", True, h)
    return jsonify({k: [{"chat_id": x["chat_id"], "enviada": x["enviada"]} for x in v] for k, v in feito.items()})

# --- ganchos para o n8n (protegidos por X-API-Key) ---
@app.post("/api/mensagem")
def mensagem():
    if not ok(KEY, request.headers.get("X-API-Key")): abort(401)
    b = request.get_json(force=True, silent=True) or {}
    try: cid = int(b["chat_id"]); txt = str(b["texto"])
    except (KeyError, ValueError, TypeError): abort(400)
    return jsonify({"resposta": core.registrar(cid, str(b.get("nome", "")), txt)})

@app.post("/api/relatorio/<kind>")   # ?enviar=false deixa o n8n enviar; ?forcar=true reenvia
def relatorio(kind):
    if not ok(KEY, request.headers.get("X-API-Key")): abort(401)
    if kind not in ("semana", "mes"): abort(404)
    return jsonify(core.relatorio_todos(kind, request.args.get("enviar", "true") == "true", forcar=request.args.get("forcar") == "true"))

@app.get("/health")
def health(): return "ok"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
