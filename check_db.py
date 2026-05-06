import sqlite3

conn = sqlite3.connect("trades.db")
c = conn.cursor()

print("Összes sor:")
c.execute("SELECT COUNT(*) FROM trades")
print(c.fetchone())

print("\nNem szám értékek:")
c.execute("SELECT * FROM trades WHERE typeof(rsi) != 'real' OR typeof(macd) != 'real'")
rows = c.fetchall()
for r in rows:
    print(r)

if not rows:
    print("Nem találtam hibás sort – a probléma máshol van")

conn.close()