# Uso: python configurar_webhook.py            (liga o webhook em BASE_URL/api/telegram)
#      python configurar_webhook.py --remover  (desliga; só então o bot.py local pode rodar)
import os, sys, requests, core
API = f"https://api.telegram.org/bot{core.TG}"
if "--remover" in sys.argv:
    print(requests.post(f"{API}/deleteWebhook").json())
else:
    sec = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    if not core.BASE.startswith("https://") or not sec:
        raise SystemExit("Defina BASE_URL (https) e TELEGRAM_WEBHOOK_SECRET no .env")
    print(requests.post(f"{API}/setWebhook", json={"url": f"{core.BASE}/api/telegram", "secret_token": sec,
          "allowed_updates": ["message"], "max_connections": 10}).json())
    i = requests.get(f"{API}/getWebhookInfo").json()["result"]
    print("url:", i.get("url"), "| pendentes:", i.get("pending_update_count"), "| último erro:", i.get("last_error_message"))
