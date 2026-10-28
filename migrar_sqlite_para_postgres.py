# Copia finflow.db (SQLite) para o Postgres definido em DATABASE_URL. NÃO apaga o arquivo original.
# Pode rodar mais de uma vez (não duplica). Uso: python migrar_sqlite_para_postgres.py
import sqlite3, core
assert core.PG, "Defina DATABASE_URL (Postgres) no .env antes de migrar."
core.init()
s = sqlite3.connect(core.DB); s.row_factory = sqlite3.Row
for u in s.execute("select * from users"):
    core.run("insert into users(chat_id,nome,token,lim_sem,meta_sem,lim_mes,meta_mes) values(?,?,?,?,?,?,?) on conflict(chat_id) do nothing",
             (u["chat_id"], u["nome"], u["token"], u["lim_sem"], u["meta_sem"], u["lim_mes"], u["meta_mes"]))
for g in s.execute("select * from gastos order by id"):
    core.run("insert into gastos(id,chat_id,data,nome,valor,categoria,tipo) values(?,?,?,?,?,?,?) on conflict(id) do nothing",
             (g["id"], g["chat_id"], g["data"], g["nome"], g["valor"], g["categoria"], g["tipo"]))
core.run("select setval(pg_get_serial_sequence('gastos','id'), greatest((select coalesce(max(id),1) from gastos),1))")
for t in ("users", "gastos"):
    a = s.execute(f"select count(*) from {t}").fetchone()[0]; b = core.run(f"select count(*) n from {t}")[0]["n"]
    print(f"{t}: SQLite={a} Postgres={b}", "OK" if b >= a else "CONFERIR")
