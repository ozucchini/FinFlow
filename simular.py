import os, time, requests, core
URL = "http://127.0.0.1:5000"
SEG = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
MEU = 7179497575

def enviar(txt, cid=MEU, uid=None, seg=SEG):
    uid = uid or int(time.time() * 1000)
    r = requests.post(URL + "/api/telegram", headers={"X-Telegram-Bot-Api-Secret-Token": seg},
        json={"update_id": uid, "message": {"chat": {"id": cid, "type": "private"},
              "from": {"first_name": "Teste"}, "text": txt}})
    print(f"{txt!r:16} -> {r.status_code} {r.text.strip()}")
    return uid

enviar("ifood 50", seg="errado")   # segredo errado
enviar("/start")
enviar("mercado 300")
enviar("ifood 45,90")
u = enviar("invest 100")
enviar("invest 100", uid=u)        # mesmo update reenviado
enviar("oi")                       # mensagem inválida
enviar("ifood 10", cid=999)        # usuário não autorizado