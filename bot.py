# SOMENTE para testar no seu PC (polling). Em produção o Telegram usa o webhook (api/telegram).
import sys, time, traceback, requests, core
URL = f"https://api.telegram.org/bot{core.TG}"
def api(m, **p): return requests.get(f"{URL}/{m}", params=p, timeout=45).json()

core.init()
me = api("getMe")
if not me.get("ok"): print("TOKEN INVÁLIDO:", me); raise SystemExit(1)
if api("getWebhookInfo")["result"].get("url"):
    if "--forcar" not in sys.argv:
        print("Há um webhook ativo (produção). Rodar o bot local o REMOVERIA.\nSe for isso mesmo, use: python bot.py --forcar"); raise SystemExit(1)
    api("deleteWebhook")
print("Bot local @" + me["result"]["username"], "| IDs liberados:", core.ALLOWED, "| Ctrl+C para parar")
off = 0
while True:
    try:
        r = api("getUpdates", offset=off, timeout=30)
        if not r.get("ok"): print("Telegram disse:", r); time.sleep(5); continue
        for u in r["result"]:
            off = u["update_id"] + 1
            try: print("update:", core.processar_update(u))
            except Exception: traceback.print_exc()
    except Exception as e:
        print("erro de rede:", type(e).__name__); time.sleep(5)
