import boto3
import json
import os
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

# ============================================================
# CONFIGURACION
# ============================================================
import os
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
SNAPSHOTS_PATH = os.path.join(BASE_PATH, 'daily-snapshots')
HISTORICAL_PATH = os.path.join(BASE_PATH, 'historical')
S3_BUCKET = 'tu-bucket-name'
S3_PREFIX = 'aws-cost-history'

os.makedirs(SNAPSHOTS_PATH, exist_ok=True)
os.makedirs(HISTORICAL_PATH, exist_ok=True)

# ============================================================
# CONFIGURACION DE DIMENSIONES
# Aqui defines que campos quieres traer de AWS
# Para agregar mas en el futuro solo agrega al lista
# ============================================================
GROUP_BY_DIMENSIONS = [
    {'Type': 'DIMENSION', 'Key': 'SERVICE'},
    # {'Type': 'DIMENSION', 'Key': 'REGION'},           # Descomentar cuando se necesite
    # {'Type': 'DIMENSION', 'Key': 'LINKED_ACCOUNT'},   # Descomentar cuando se necesite
    # {'Type': 'TAG', 'Key': 'Environment'},             # Descomentar cuando se necesite
]

# ============================================================
# FECHAS
# ============================================================
today = datetime.today()
yesterday = today - timedelta(days=1)

first_day_current_month = today.replace(day=1)
first_day_last_month = first_day_current_month - relativedelta(months=1)
last_month_str = first_day_last_month.strftime('%Y-%m')
current_month_str = today.strftime('%Y-%m')

print(f"📅 Hoy es: {today.strftime('%Y-%m-%d')} — Dia {today.day} del mes")

# ============================================================
# FUNCION PARA GENERAR TODOS LOS DIAS DEL PERIODO
# ============================================================
def generate_all_days(start_date_str, end_date_str):
    start = datetime.strptime(start_date_str, '%Y-%m-%d')
    end = datetime.strptime(end_date_str, '%Y-%m-%d')
    days = []
    current = start
    while current <= end:
        days.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)
    return days

# ============================================================
# FUNCION PARA CONSULTAR AWS
# ============================================================
def get_costs(start_date, end_date):
    client = boto3.client('ce', region_name='us-east-1')
    response = client.get_cost_and_usage(
        TimePeriod={
            'Start': start_date,
            'End': end_date
        },
        Granularity='DAILY',
        Metrics=['UnblendedCost'],
        GroupBy=GROUP_BY_DIMENSIONS
    )

    costs_by_day = {}
    all_services = set()

    for day in response['ResultsByTime']:
        date = day['TimePeriod']['Start']
        costs_by_day[date] = {}
        for group in day['Groups']:
            # El primer key es siempre el servicio
            service = group['Keys'][0]
            cost = float(group['Metrics']['UnblendedCost']['Amount'])

            # Construir attributes dinamicamente con los demas keys
            attributes = {}
            keys = group['Keys']
            for i, dim in enumerate(GROUP_BY_DIMENSIONS):
                if i < len(keys):
                    field_name = dim['Key'].lower()
                    if i > 0:  # El primero es SERVICE, va en su propio campo
                        attributes[field_name] = keys[i]

            costs_by_day[date][service] = {
                'cost': round(cost, 6),
                'attributes': attributes
            }

            if cost > 0.0001:
                all_services.add(service)

    return costs_by_day, all_services

# ============================================================
# FUNCION PARA CONSTRUIR DAILY DETAIL CON TODOS LOS DIAS
# ============================================================
def build_daily_detail(costs_by_day, all_services, start_date, end_date_display):
    daily_detail = []
    all_days = generate_all_days(start_date, end_date_display)

    for day_date in all_days:
        day_costs = costs_by_day.get(day_date, {})

        if not all_services:
            daily_detail.append({
                "date": day_date,
                "service": "No cost",
                "cost": 0.0,
                "currency": "USD",
                "attributes": {}
            })
        else:
            for service in sorted(all_services):
                service_data = day_costs.get(service, {'cost': 0.0, 'attributes': {}})
                daily_detail.append({
                    "date": day_date,
                    "service": service,
                    "cost": service_data['cost'],
                    "currency": "USD",
                    "attributes": service_data['attributes']
                })

    return daily_detail

# ============================================================
# FUNCION PARA ARMAR EL JSON v1.0
# ============================================================
def build_output(costs_by_day, all_services, start_date, end_date_display, month_str):
    daily_detail = build_daily_detail(costs_by_day, all_services, start_date, end_date_display)
    total = round(sum(r['cost'] for r in daily_detail), 6)

    return {
        "schema_version": "1.0",
        "month": month_str,
        "generated_at": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        "total_cost": total,
        "currency": "USD",
        "daily_detail": daily_detail
    }

# ============================================================
# FUNCION PARA GUARDAR JSON
# ============================================================
def save_json(data, filepath):
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

# ============================================================
# LOGICA PRINCIPAL
# ============================================================
if today.day <= 5:
    print("📌 Modo: Mes anterior + Mes actual (posibles ajustes de AWS)")

    # Mes anterior completo
    start_last = first_day_last_month.strftime('%Y-%m-%d')
    end_last = first_day_current_month.strftime('%Y-%m-%d')
    last_day_last_month = (first_day_current_month - timedelta(days=1)).strftime('%Y-%m-%d')

    costs_last, services_last = get_costs(start_last, end_last)
    output_last = build_output(costs_last, services_last, start_last, last_day_last_month, last_month_str)
    save_json(output_last, os.path.join(BASE_PATH, 'previous_month.json'))
    print(f"💾 previous_month.json ({last_month_str}) — ${output_last['total_cost']} USD")

    # Mes actual hasta ayer
    start_current = first_day_current_month.strftime('%Y-%m-%d')
    end_current = today.strftime('%Y-%m-%d')
    costs_current, services_current = get_costs(start_current, end_current)
    output_current = build_output(costs_current, services_current, start_current, yesterday.strftime('%Y-%m-%d'), current_month_str)
    save_json(output_current, os.path.join(BASE_PATH, 'current_month.json'))
    print(f"💾 current_month.json ({current_month_str}) — ${output_current['total_cost']} USD")

    snapshot_data = output_last

else:
    print("📌 Modo: Solo mes actual (mes anterior ya cerrado)")

    start_current = first_day_current_month.strftime('%Y-%m-%d')
    end_current = today.strftime('%Y-%m-%d')
    costs_current, services_current = get_costs(start_current, end_current)
    output_current = build_output(costs_current, services_current, start_current, yesterday.strftime('%Y-%m-%d'), current_month_str)
    save_json(output_current, os.path.join(BASE_PATH, 'current_month.json'))
    print(f"💾 current_month.json ({current_month_str}) — ${output_current['total_cost']} USD")

    # El dia 6 mover mes anterior a historical/ y luego a S3
    if today.day == 6:
        print(f"\n📦 Cerrando mes {last_month_str}...")

        # Guardar mes anterior en historical/
        start_last = first_day_last_month.strftime('%Y-%m-%d')
        end_last = first_day_current_month.strftime('%Y-%m-%d')
        last_day_last_month = (first_day_current_month - timedelta(days=1)).strftime('%Y-%m-%d')
        costs_last, services_last = get_costs(start_last, end_last)
        output_last = build_output(costs_last, services_last, start_last, last_day_last_month, last_month_str)
        historical_file = os.path.join(HISTORICAL_PATH, f"{last_month_str}.json")
        save_json(output_last, historical_file)
        print(f"💾 historical/{last_month_str}.json guardado")

        # Eliminar previous_month.json
        previous_path = os.path.join(BASE_PATH, 'previous_month.json')
        if os.path.exists(previous_path):
            os.remove(previous_path)
            print(f"🗑️  previous_month.json eliminado")

    snapshot_data = output_current

# ============================================================
# SNAPSHOT DEL DIA
# ============================================================
snapshot_filename = f"{today.strftime('%Y-%m-%d')}.json"
snapshot_path = os.path.join(SNAPSHOTS_PATH, snapshot_filename)
save_json(snapshot_data, snapshot_path)
print(f"📸 Snapshot: {snapshot_filename}")

# ============================================================
# RESUMEN FINAL
# ============================================================
print(f"\n{'='*50}")
if today.day <= 5:
    print(f"💰 {last_month_str}: ${output_last['total_cost']} USD")
    print(f"💰 {current_month_str}: ${output_current['total_cost']} USD")
else:
    print(f"💰 {current_month_str}: ${output_current['total_cost']} USD")
print(f"{'='*50}")