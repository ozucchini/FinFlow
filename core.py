import os, re, sqlite3, secrets, unicodedata, logging, requests
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")  # variáveis já definidas (Vercel, testes) têm prioridade

DBURL = os.getenv("DATABASE_URL", "")
PG = DBURL.startswith("postgres")          # produção: Postgres. Sem DATABASE_URL: SQLite local.
DB = os.getenv("DB_PATH", "finflow.db")
CDB = float(os.getenv("CDB_ANUAL", "0.145"))
TG = os.getenv("TELEGRAM_TOKEN", "")
DBURL = os.getenv("DATABASE_URL", "")
PG = DBURL.startswith("postgres")
DB = os.getenv("DB_PATH", "finflow.db")
TZ = ZoneInfo("America/Sao_Paulo")
log = logging.getLogger("finflow")

def hoje(): return datetime.now(TZ).date()   # a Vercel roda em UTC; o app usa o horário de Brasília

# ---------- banco (SQLite local ou Postgres, mesmas consultas com "?") ----------
def run(sql, params=()):
    if PG:
        import psycopg2, psycopg2.extras
        c = psycopg2.connect(DBURL, connect_timeout=10)
        try:
            with c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql.replace("?", "%s"), params)
                return [dict(r) for r in cur.fetchall()] if cur.description else []
        finally:
            c.close()
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    try:
        with c:
            cur = c.execute(sql, params)
            return [dict(r) for r in cur.fetchall()] if cur.description else []
    finally:
        c.close()

def init():
    pk = "bigserial primary key" if PG else "integer primary key autoincrement"
    ddl = [
        "create table if not exists users(chat_id bigint primary key, nome text, token text unique, lim_sem double precision default 150, meta_sem double precision default 100, lim_mes double precision default 600, meta_mes double precision default 400)",
        f"create table if not exists gastos(id {pk}, chat_id bigint, data text, nome text, valor double precision, categoria text, tipo text)",
        "create index if not exists gastos_idx on gastos(chat_id, data)",
        "create table if not exists mensagens(chat_id bigint, chave text, tom text, texto text, primary key(chat_id, chave))",
        "create table if not exists envios(chat_id bigint, chave text, primary key(chat_id, chave))",
        "create table if not exists updates(update_id bigint primary key)",
    ]
    if PG: run("; ".join(ddl))
    else:
        for s in ddl: run(s)

R = lambda v: "R$ " + f"{v:,.0f}".replace(",", ".")
Y = lambda v: v * (1 + CDB)

# ---------- classificação (edite à vontade) ----------
RULES = {
 "aluguel":("Moradia","e"),"condominio":("Moradia","e"),"mercado":("Alimentação","e"),"padaria":("Alimentação","e"),
 "luz":("Contas","e"),"energia":("Contas","e"),"agua":("Contas","e"),"internet":("Contas","e"),"farmacia":("Saúde","e"),
 "remedio":("Saúde","e"),"medico":("Saúde","e"),"onibus":("Transporte","e"),"gasolina":("Transporte","e"),
 "ifood":("Delivery","d"),"pizza":("Delivery","d"),"lanche":("Delivery","d"),"netflix":("Streaming","d"),
 "spotify":("Streaming","d"),"bar":("Bares e saídas","d"),"cerveja":("Bares e saídas","d"),"roupa":("Compras","d"),
 "tenis":("Compras","d"),"shopee":("Compras","d"),"jogo":("Jogos","d"),"steam":("Jogos","d"),"uber":("Transporte por app","d"),
 "cinema":("Lazer","d"),"invest":("Investimento","i"),"aporte":("Investimento","i"),"cdb":("Investimento","i"),"tesouro":("Investimento","i"),
}
def norm(s): return unicodedata.normalize("NFD", s.lower()).encode("ascii", "ignore").decode()

def parse(texto):
    m = re.search(r"(\d+(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:\.\d{1,2})?)", texto)
    if not m: return None
    s = m.group(1)
    v = float(s.replace(".", "").replace(",", ".")) if "," in s else float(s)
    if not (0 < v <= 1_000_000): return None
    nome = (texto[:m.start()] + texto[m.end():]).strip(" -:") or "Gasto"
    cat, tipo = "Outros", "d"
    for k, (c, t) in RULES.items():
        if k in norm(nome): cat, tipo = c, t
    return nome.capitalize(), v, cat, tipo

# ---------- usuários e registro ----------
def get_user(chat_id, nome=""):
    r = run("select * from users where chat_id=?", (chat_id,))
    if r: return r[0]
    if run("select count(*) n from users")[0]["n"] >= MAX_USERS: return None
    run("insert into users(chat_id,nome,token) values(?,?,?) on conflict(chat_id) do nothing",
        (chat_id, nome[:60], secrets.token_urlsafe(24)))
    return run("select * from users where chat_id=?", (chat_id,))[0]

def registrar(chat_id, nome, texto):
    texto = (texto or "").strip()[:200]
    if chat_id not in ALLOWED:
        return f"Acesso não autorizado. Seu ID é {chat_id}. Envie esse número para quem administra o FinFlow."
    u = get_user(chat_id, nome or "")
    if u is None: return f"Limite de {MAX_USERS} usuários atingido."
    if texto.startswith(("/start", "/painel")):
        return f"Seu painel: {BASE}/d/{u['token']}\nMande gastos assim: ifood 45,90 ou invest 100.\nGuarde o link só para você. Se vazar, mande /novolink."
    if texto.startswith("/novolink"):
        t = secrets.token_urlsafe(24)
        run("update users set token=? where chat_id=?", (t, chat_id))
        return f"Link antigo desativado. Novo painel: {BASE}/d/{t}"
    p = parse(texto)
    if not p: return "Não entendi. Mande assim: ifood 45,90 ou invest 100."
    n, v, cat, t = p
    run("insert into gastos(chat_id,data,nome,valor,categoria,tipo) values(?,?,?,?,?,?)",
        (chat_id, hoje().isoformat(), n, v, cat, t))
    r = f"Anotado: {n}, {R(v)} ({cat})."
    if t == "d": r += f" Desnecessário. Investido por 1 ano no CDB, isso seria {R(Y(v))}."
    if t == "i": r += " Investimento registrado. Era isso que faltava."
    return r

# ---------- períodos ----------
def semana_ini(d): return d - timedelta(days=d.weekday())
def fim_mes(d): return (d.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

def somas(chat_id, a, b):
    r = run("select tipo, sum(valor) s from gastos where chat_id=? and data between ? and ? group by tipo",
            (chat_id, a.isoformat(), b.isoformat()))
    r = {x["tipo"]: x["s"] for x in r}
    return r.get("e", 0), r.get("d", 0), r.get("i", 0)

# ---------- narrativas ----------
def story(d, i, lim, meta, per):
    x = max(0, d - lim); pouco = d <= lim; inv = i > 0; v = int(d + i) % 2
    T = {
     "good": [f"{per} no azul: só {R(d)} em supérfluos (limite {R(lim)}) e {R(i)} investidos. Não precisa de confete, é o mínimo que se espera de quem quer ficar tranquilo no futuro. Mas é um bom começo. Mantenha.",
              f"Olha só, alguém levando o dinheiro a sério. {R(d)} de supérfluo e {R(i)} para o futuro (em 1 ano no CDB: {R(Y(i))}). Agora faça disso hábito, não exceção."],
     "semInv": [f"Você segurou os gastos ({R(d)}), mas investiu R$ 0. Economizar e deixar o dinheiro parado é só adiar o gasto, e a inflação agradece. Separe {R(meta)} hoje.",
                f"Disciplina pela metade: gastou pouco ({R(d)}) e não investiu nada. Dinheiro parado não rende, só envelhece. Coloque pelo menos {R(meta)} no CDB."],
     "gastouInv": [f"Investiu {R(i)}, parabéns. Aí gastou {R(d)} em supérfluos, {R(x)} acima do limite, e desfez o esforço. Esse excesso no CDB viraria {R(Y(x))} em 1 ano. Escolha um lado.",
                   f"{R(i)} investidos e {R(d)} jogados em coisas que ninguém precisava. É encher balde furado. Corte {R(x)} e o furo fecha."],
     "bad": [f"{R(d)} em supérfluos, {R(x)} acima do limite, e R$ 0 investidos. No CDB isso seria {R(Y(d))} em 1 ano. Seu eu do futuro está olhando para você com aquela cara. Invista primeiro, gaste depois.",
             f"Vamos falar a real: {R(d)} sem necessidade e nenhum centavo guardado. Ninguém se aposenta de iFood e compra por impulso. Defina um teto e cumpra."]}
    k = "good" if pouco and inv else "semInv" if pouco else "gastouInv" if inv else "bad"
    return ("good" if k == "good" else "bad" if k == "bad" else "mid"), T[k][v]

def mensagem(u, kind, ref=None, salvar=False):
    ref = ref or hoje()
    if kind == "semana":
        a = semana_ini(ref); b = a + timedelta(days=6); lim, meta, per, chave = u["lim_sem"], u["meta_sem"], "Sua semana", f"S{a}"
    else:
        a = ref.replace(day=1); b = fim_mes(ref); lim, meta, per, chave = u["lim_mes"], u["meta_mes"], "Seu mês", f"M{a:%Y-%m}"
    e, d, i = somas(u["chat_id"], a, b)
    tom, texto = story(d, i, lim, meta, per)
    if salvar:
        run("insert into mensagens(chat_id,chave,tom,texto) values(?,?,?,?) on conflict(chat_id,chave) do update set tom=excluded.tom, texto=excluded.texto",
            (u["chat_id"], chave, tom, texto))
    return {"p": f"{a:%d/%m}–{b:%d/%m}", "e": e, "d": d, "i": i, "tom": tom, "texto": texto, "f": b < hoje(), "chave": chave}

def resumo(token):
    if not token: return None
    r = run("select * from users where token=?", (token,))
    if not r: return None
    u = r[0]; h = hoje(); a = semana_ini(h.replace(day=1)); semanas = []
    while a <= h:
        semanas.append(mensagem(u, "semana", a)); a += timedelta(days=7)
    m = mensagem(u, "mes", h); m["rend"] = Y(m["d"])
    return {"nome": u["nome"], "lim_sem": u["lim_sem"], "meta_sem": u["meta_sem"], "lim_mes": u["lim_mes"], "meta_mes": u["meta_mes"], "semanas": semanas, "mes": m}

# ---------- Telegram ----------
def tg_send(chat_id, texto):
    if not TG: log.warning("TELEGRAM_TOKEN vazio"); return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{TG}/sendMessage", json={"chat_id": chat_id, "text": texto}, timeout=8)
        if not r.ok: log.warning("Telegram recusou (%s): %s", r.status_code, r.text[:200])
        return r.ok
    except requests.RequestException as e:
        log.warning("Falha de rede ao enviar: %s", type(e).__name__); return False

def processar_update(u):
    """Webhook: cada update_id é processado uma vez. Se o banco falhar, libera o id para o Telegram reenviar."""
    m = u.get("message")
    if not (m and m.get("text")) or m["chat"].get("type") != "private": return "ignorado"
    uid = u["update_id"]
    if not run("insert into updates(update_id) values(?) on conflict(update_id) do nothing returning update_id", (uid,)):
        return "duplicado"
    try:
        cid = m["chat"]["id"]
        resp = registrar(cid, (m.get("from") or {}).get("first_name", ""), m["text"])
    except Exception:
        run("delete from updates where update_id=?", (uid,)); raise
    tg_send(cid, resp)
    return "ok"

def relatorio_todos(kind, enviar=True, ref=None, forcar=False):
    """enviar=True: envia e marca em 'envios' (sem duplicar). enviar=False: só devolve os textos (n8n envia)."""
    ref = ref or hoje(); out = []
    for u in run("select * from users"):
        m = mensagem(u, kind, ref, salvar=True)
        item = {"chat_id": u["chat_id"], "nome": u["nome"], "tom": m["tom"], "texto": m["texto"], "enviada": False}
        if enviar:
            if forcar: run("delete from envios where chat_id=? and chave=?", (u["chat_id"], m["chave"]))
            if run("insert into envios(chat_id,chave) values(?,?) on conflict(chat_id,chave) do nothing returning chat_id", (u["chat_id"], m["chave"])):
                item["enviada"] = tg_send(u["chat_id"], m["texto"])
                if not item["enviada"]: run("delete from envios where chat_id=? and chave=?", (u["chat_id"], m["chave"]))
        out.append(item)
    return out
