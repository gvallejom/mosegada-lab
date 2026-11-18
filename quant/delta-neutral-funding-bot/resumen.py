import sqlite3, json

c = sqlite3.connect('data/bot.db')
rows = c.execute('SELECT data, status FROM positions ORDER BY opened_at').fetchall()

if not rows:
    print("No hay operaciones todavia.")
    exit()

all_pos = [json.loads(r[0]) for r in rows]
open_pos = [p for p in all_pos if p.get('status') == 'open']
closed_pos = [p for p in all_pos if p.get('status') == 'closed']

def fmt(p, i):
    sym     = p.get('long_leg',{}).get('symbol','?')
    size    = float(p.get('long_leg',{}).get('size',0))
    price   = float(p.get('long_leg',{}).get('entry_price',0))
    vol     = round(size * price * 2, 2)
    fees    = round(float(p.get('fees_paid',0)), 4)
    funding = round(float(p.get('accumulated_funding',0)), 4)
    lpnl    = float(p.get('long_leg',{}).get('unrealised_pnl',0))
    spnl    = float(p.get('short_leg',{}).get('unrealised_pnl',0))
    net     = round(funding + lpnl + spnl - fees, 4)
    opened  = p.get('opened_at','')[:19]
    closed  = p.get('closed_at') or '—'
    if closed != '—': closed = closed[:19]
    status  = '🟢 ABIERTA' if p.get('status') == 'open' else '🔴 CERRADA'
    print(f"  #{i:<3} {sym:<5} {status}")
    print(f"       Volumen:   ${vol:>12,.2f}")
    print(f"       Comis.:    ${fees:>12,.4f}")
    print(f"       Funding:   ${funding:>12,.4f}")
    print(f"       Net PnL:   ${net:>12,.4f}")
    print(f"       Abierta:   {opened}")
    print(f"       Cerrada:   {closed}")
    print()

print('='*50)
print(f"  ABIERTAS: {len(open_pos)}   CERRADAS: {len(closed_pos)}   TOTAL: {len(all_pos)}")
print('='*50)
for i, p in enumerate(all_pos, 1):
    fmt(p, i)

total_vol  = sum(float(p.get('long_leg',{}).get('size',0)) * float(p.get('long_leg',{}).get('entry_price',0)) * 2 for p in all_pos)
total_fees = sum(float(p.get('fees_paid',0)) for p in all_pos)
total_fund = sum(float(p.get('accumulated_funding',0)) for p in all_pos)
net_total  = total_fund - total_fees

print('='*50)
print("  RESUMEN GLOBAL")
print('='*50)
print(f"  Operaciones:        {len(all_pos)}")
print(f"  Volumen total:      ${total_vol:>12,.2f}")
print(f"  Comisiones totales: ${total_fees:>12,.4f}")
print(f"  Funding acumulado:  ${total_fund:>12,.4f}")
print(f"  Net PnL total:      ${net_total:>12,.4f}")
print('='*50)