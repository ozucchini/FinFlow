import os, tempfile, unittest, importlib
from datetime import date
d = tempfile.mkdtemp()
os.environ.update(DB_PATH=os.path.join(d, "t.db"), ALLOWED_IDS="1,2", API_KEY="k", TELEGRAM_WEBHOOK_SECRET="seg",
                  CRON_SECRET="cr", TELEGRAM_TOKEN="", BASE_URL="https://x.app", MAX_USERS="10")
os.environ.pop("DATABASE_URL", None)
import core, app as appmod
C = appmod.app.test_client()
WH = {"X-Telegram-Bot-Api-Secret-Token": "seg"}
def upd(i, cid, txt): return {"update_id": i, "message": {"chat": {"id": cid, "type": "private"}, "from": {"first_name": "T"}, "text": txt}}

class T(unittest.TestCase):
    def setUp(self):
        for t in ("users", "gastos", "mensagens", "envios", "updates"): core.run(f"delete from {t}")
        core.ALLOWED.clear(); core.ALLOWED.update({1, 2}); core.MAX_USERS = 10
        self.sent = []; core.tg_send = lambda c, t: (self.sent.append((c, t)) or True)
    def token(self, cid): return core.run("select token from users where chat_id=?", (cid,))[0]["token"]

    def test_despesa_e_investimento(self):
        self.assertIn("Anotado", core.registrar(1, "A", "mercado 300"))
        self.assertIn("Investimento registrado", core.registrar(1, "A", "invest 100"))
        r = core.resumo(self.token(1))["mes"]; self.assertEqual((r["e"], r["i"]), (300, 100))
    def test_dashboard(self):
        core.registrar(1, "A", "ifood 50"); t = self.token(1)
        self.assertEqual(C.get(f"/d/{t}").status_code, 200)
        self.assertEqual(C.get("/api/resumo", headers={"X-Token": t}).status_code, 200)
        self.assertEqual(C.get("/api/resumo", headers={"X-Token": "errado"}).status_code, 404)
        self.assertEqual(C.get("/api/resumo").status_code, 404)
        self.assertGreaterEqual(len(t), 30)
    def test_autorizacao(self):
        self.assertIn("Anotado", core.registrar(1, "A", "ifood 10"))
        r = core.registrar(99, "X", "ifood 10"); self.assertIn("não autorizado", r); self.assertIn("99", r)
        self.assertEqual(core.run("select count(*) n from users")[0]["n"], 1)
    def test_isolamento(self):
        core.registrar(1, "A", "mercado 100"); core.registrar(2, "B", "mercado 900")
        self.assertEqual(core.resumo(self.token(1))["mes"]["e"], 100)
        self.assertEqual(core.resumo(self.token(2))["mes"]["e"], 900)
        self.assertNotEqual(self.token(1), self.token(2))
    def test_persistencia(self):
        core.registrar(1, "A", "mercado 123"); t = self.token(1); importlib.reload(core)
        self.assertEqual(core.resumo(t)["mes"]["e"], 123)
    def test_mensagens_invalidas(self):
        for m in ("oi", "", "ifood 0", "ifood 99999999", "/novolink"): core.registrar(1, "A", m)
        self.assertEqual(core.run("select count(*) n from gastos")[0]["n"], 0)
    def test_novolink(self):
        core.registrar(1, "A", "/start"); antigo = self.token(1); core.registrar(1, "A", "/novolink")
        self.assertIsNone(core.resumo(antigo)); self.assertIsNotNone(core.resumo(self.token(1)))
    def test_limite_usuarios(self):
        core.MAX_USERS = 2; core.ALLOWED.add(3)
        core.registrar(1, "A", "/start"); core.registrar(2, "B", "/start")
        self.assertIn("Limite", core.registrar(3, "C", "ifood 5"))
    def test_webhook(self):
        self.assertEqual(C.post("/api/telegram", json=upd(1, 1, "ifood 5")).status_code, 401)
        self.assertEqual(C.post("/api/telegram", json=upd(1, 1, "ifood 5"), headers={"X-Telegram-Bot-Api-Secret-Token": "x"}).status_code, 401)
        self.assertEqual(C.post("/api/telegram", json=upd(1, 1, "ifood 5"), headers=WH).status_code, 200)
        C.post("/api/telegram", json=upd(1, 1, "ifood 5"), headers=WH)   # reenvio do mesmo update
        self.assertEqual(core.run("select count(*) n from gastos")[0]["n"], 1)
        self.assertEqual(len(self.sent), 1)
    def test_falha_temporaria_reenvio(self):
        orig = core.registrar
        core.registrar = lambda *a: (_ for _ in ()).throw(RuntimeError("banco fora"))
        self.assertEqual(C.post("/api/telegram", json=upd(7, 1, "ifood 5"), headers=WH).status_code, 500)
        core.registrar = orig   # Telegram reenvia o mesmo update e agora funciona
        self.assertEqual(C.post("/api/telegram", json=upd(7, 1, "ifood 5"), headers=WH).status_code, 200)
        self.assertEqual(core.run("select count(*) n from gastos")[0]["n"], 1)
    def test_cron_sem_duplicar(self):
        core.registrar(1, "A", "ifood 5")
        self.assertEqual(C.get("/api/cron").status_code, 401)
        H = {"Authorization": "Bearer cr"}
        core.hoje = lambda: date(2026, 11, 1)   # domingo
        self.assertEqual(C.get("/api/cron", headers=H).status_code, 200); C.get("/api/cron", headers=H)
        self.assertEqual(len(self.sent), 1)
        core.hoje = lambda: date(2026, 10, 28)  # quarta, fora do fim do mês
        self.assertEqual(C.get("/api/cron", headers=H).get_json(), {})
    def test_rotas_n8n(self):
        self.assertEqual(C.post("/api/mensagem", json={"chat_id": 1, "texto": "x 1"}).status_code, 401)
        H = {"X-API-Key": "k"}
        self.assertIn("Anotado", C.post("/api/mensagem", json={"chat_id": 1, "texto": "ifood 9"}, headers=H).get_json()["resposta"])
        self.assertEqual(C.post("/api/mensagem", json={"x": 1}, headers=H).status_code, 400)
        self.assertEqual(len(C.post("/api/relatorio/semana?enviar=false", headers=H).get_json()), 1)
        self.assertEqual(self.sent, [])
    def test_health(self): self.assertEqual(C.get("/health").data, b"ok")

if __name__ == "__main__": unittest.main(verbosity=2)
