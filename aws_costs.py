import boto3
import json
import os
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

# ============================================================
# CONFIGURACION
# ============================================================
BASE_PATH = 'C:\\Users\\pablo\\aws-cost-lab'
SNAPSHOTS_PATH = os.path.join(BASE_PATH, 'daily-snapshots')
S3_BUCKET = 'tu-bucket-name'
S3_PREFIX = 'aws-cost-history'

os.makedirs(SNAPSHOTS_PATH, exist_ok=True)

# ============================================================
# FECHAS
# ============================================================
today = datetime.today()
yesterday = today - timedelta(days=1)

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
        GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}]
    )

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

    daily_costs.sort(key=lambda x: (x['date'], -x['cost']))
    return daily_costs

# ============================================================
# FUNCION PARA ARMAR EL JSON
# ============================================================
def build_output(daily_costs, start_date, end_date_display):
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

    # Resumen por mes
    monthly_summary = {}
    for item in daily_costs:
        month = item['date'][:7]
        if month not in monthly_summary:
            monthly_summary[month] = 0
        monthly_summary[month] += item['cost']

    monthly_summary_list = [
        {'month': k, 'total_cost': round(v, 6)}
        for k, v in sorted(monthly_summary.items())
    ]

    return {
        'snapshot_date': today.strftime('%Y-%m-%d'),
        'generated_at': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        'period': {
            'start': start_date,
            'end': end_date_display
        },
        'total_cost': total,
        'currency': 'USD',
        'monthly_summary': monthly_summary_list,
        'services_summary': services_summary_list,
        'daily_detail': daily_costs
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
first_day_current_month = today.replace(day=1)
first_day_last_month = (first_day_current_month - relativedelta(months=1))
last_month_str = first_day_last_month.strftime('%Y-%m')
current_month_str = today.strftime('%Y-%m')

print(f"📅 Hoy es: {today.strftime('%Y-%m-%d')} — Dia {today.day} del mes")

# ------------------------------------------------------------
# DIAS 1 AL 5: Traer mes anterior + mes actual
# Power BI lee los dos porque julio puede tener ajustes
# ------------------------------------------------------------
if today.day <= 5:
    print("📌 Modo: Mes anterior + Mes actual (posibles ajustes de AWS)")

    # Mes anterior
    start_last = first_day_last_month.strftime('%Y-%m-%d')
    end_last = first_day_current_month.strftime('%Y-%m-%d')
    costs_last = get_costs(start_last, end_last)
    output_last = build_output(
        costs_last,
        start_last,
        (first_day_current_month - timedelta(days=1)).strftime('%Y-%m-%d')
    )
    save_json(output_last, os.path.join(BASE_PATH, 'previous_month.json'))
    print(f"💾 previous_month.json guardado ({last_month_str}) — ${output_last['total_cost']} USD")

    # Mes actual
    start_current = first_day_current_month.strftime('%Y-%m-%d')
    end_current = today.strftime('%Y-%m-%d')
    costs_current = get_costs(start_current, end_current)
    output_current = build_output(
        costs_current,
        start_current,
        yesterday.strftime('%Y-%m-%d')
    )
    save_json(output_current, os.path.join(BASE_PATH, 'current_month.json'))
    print(f"💾 current_month.json guardado ({current_month_str}) — ${output_current['total_cost']} USD")

# ------------------------------------------------------------
# DIA 6 EN ADELANTE: Solo mes actual
# Julio ya cerrado, se mueve a S3 y se elimina previous_month.json
# ------------------------------------------------------------
else:
    print("📌 Modo: Solo mes actual (mes anterior ya cerrado)")

    # Solo mes actual
    start_current = first_day_current_month.strftime('%Y-%m-%d')
    end_current = today.strftime('%Y-%m-%d')
    costs_current = get_costs(start_current, end_current)
    output_current = build_output(
        costs_current,
        start_current,
        yesterday.strftime('%Y-%m-%d')
    )
    save_json(output_current, os.path.join(BASE_PATH, 'current_month.json'))
    print(f"💾 current_month.json guardado ({current_month_str}) — ${output_current['total_cost']} USD")

    # Eliminar previous_month.json si existe
    previous_path = os.path.join(BASE_PATH, 'previous_month.json')
    if os.path.exists(previous_path):
        os.remove(previous_path)
        print(f"🗑️  previous_month.json eliminado — mes anterior cerrado")

# ------------------------------------------------------------
# SNAPSHOT DEL DIA (siempre)
# ------------------------------------------------------------
if today.day <= 5:
    snapshot_data = output_last  # Snapshot incluye ambos meses
    snapshot_data['note'] = 'Incluye mes anterior por posibles ajustes AWS'
else:
    snapshot_data = output_current

snapshot_filename = f"{today.strftime('%Y-%m-%d')}.json"
snapshot_path = os.path.join(SNAPSHOTS_PATH, snapshot_filename)
save_json(snapshot_data, snapshot_path)
print(f"📸 Snapshot guardado: {snapshot_filename}")

# ------------------------------------------------------------
# DIA 6: Mover mes anterior a S3
# ------------------------------------------------------------
if today.day == 6:
    print(f"\n📦 Moviendo snapshots de {last_month_str} a S3...")

    s3_client = boto3.client('s3')
    last_month_folder = first_day_last_month.strftime('%Y/%m')
    moved = 0
    errors = 0

    for filename in os.listdir(SNAPSHOTS_PATH):
        if filename.startswith(last_month_str) and filename.endswith('.json'):
            local_path = os.path.join(SNAPSHOTS_PATH, filename)
            s3_key = f"{S3_PREFIX}/{last_month_folder}/{filename}"
            try:
                s3_client.upload_file(local_path, S3_BUCKET, s3_key)
                os.remove(local_path)
                print(f"  ✅ {filename} → s3://{S3_BUCKET}/{s3_key}")
                moved += 1
            except Exception as e:
                print(f"  ❌ Error con {filename}: {e}")
                errors += 1

    print(f"📊 Movidos: {moved} archivos | Errores: {errors}")

# ------------------------------------------------------------
# RESUMEN FINAL
# ------------------------------------------------------------
print(f"\n{'='*50}")
if today.day <= 5:
    print(f"💰 {last_month_str}: ${output_last['total_cost']} USD")
    print(f"💰 {current_month_str}: ${output_current['total_cost']} USD")
else:
    print(f"💰 {current_month_str}: ${output_current['total_cost']} USD")
print(f"{'='*50}")