import boto3
import json
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

# Fechas
today = datetime.today()
yesterday = today - timedelta(days=1)

# Inicio del mes anterior
start_date = (today.replace(day=1) - relativedelta(months=1)).strftime('%Y-%m-%d')

# Hasta ayer (end es exclusivo en AWS, ponemos today)
end_date = today.strftime('%Y-%m-%d')

print(f"📅 Consultando costos del {start_date} al {yesterday.strftime('%Y-%m-%d')}")

# Conectar a Cost Explorer
client = boto3.client('ce', region_name='us-east-1')

# Consultar costos por servicio agrupado por dia
response = client.get_cost_and_usage(
    TimePeriod={
        'Start': start_date,
        'End': end_date
    },
    Granularity='DAILY',
    Metrics=['UnblendedCost'],
    GroupBy=[
        {
            'Type': 'DIMENSION',
            'Key': 'SERVICE'
        }
    ]
)

# Procesar resultados dia por dia
daily_costs = []

for day in response['ResultsByTime']:
    day_date = day['TimePeriod']['Start']
    for group in day['Groups']:
        service = group['Keys'][0]
        cost = float(group['Metrics']['UnblendedCost']['Amount'])
        currency = group['Metrics']['UnblendedCost']['Unit']

        if cost > 0.0001:
            daily_costs.append({
                'date': day_date,
                'service': service,
                'cost': round(cost, 6),
                'currency': currency
            })

# Ordenar por fecha y luego por costo descendente
daily_costs.sort(key=lambda x: (x['date'], -x['cost']))

# Total general
total = round(sum(r['cost'] for r in daily_costs), 6)

# Resumen por servicio
services_summary = {}
for item in daily_costs:
    svc = item['service']
    if svc not in services_summary:
        services_summary[svc] = 0
    services_summary[svc] += item['cost']

services_summary_list = [
    {'service': k, 'total_cost': round(v, 6)}
    for k, v in sorted(services_summary.items(), key=lambda x: -x[1])
]

# Resumen por mes (util para Power BI)
monthly_summary = {}
for item in daily_costs:
    month = item['date'][:7]  # Ejemplo: "2026-07"
    if month not in monthly_summary:
        monthly_summary[month] = 0
    monthly_summary[month] += item['cost']

monthly_summary_list = [
    {'month': k, 'total_cost': round(v, 6)}
    for k, v in sorted(monthly_summary.items())
]

# Exportar a JSON
output = {
    'generated_at': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    'period': {
        'start': start_date,
        'end': yesterday.strftime('%Y-%m-%d')
    },
    'total_cost': total,
    'currency': 'USD',
    'monthly_summary': monthly_summary_list,   # Resumen por mes
    'services_summary': services_summary_list,  # Resumen por servicio
    'daily_detail': daily_costs                 # Detalle dia por dia
}

with open('C:\\Users\\pablo\\aws-cost-lab\\costs.json', 'w') as f:
    json.dump(output, f, indent=2)

print(f"✅ Costos exportados: {len(daily_costs)} registros")
print(f"💰 Total: ${total} USD")
print(f"📅 Meses cubiertos: {[m['month'] for m in monthly_summary_list]}")
print(f"📊 Servicios con costo: {len(services_summary_list)}")