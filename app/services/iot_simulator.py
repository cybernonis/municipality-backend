import random
from datetime import datetime, timezone
from app.database import supabase
import logging

logger = logging.getLogger(__name__)

def simulate_readings():
    """Δημιουργεί προσομοιωμένες μετρήσεις για όλες τις συσκευές"""
    
    devices = supabase.table("iot_devices")\
        .select("id, name, type")\
        .eq("status", "active")\
        .execute()
    
    if not devices.data:
        return {"readings": [], "alerts": []}
    
    readings = []
    alerts = []
    
    for device in devices.data:
        device_id = device["id"]
        device_type = device["type"]
        
        if device_type == "waste_bin":
            fill_level = random.randint(20, 100)
            readings.append({
                "device_id": device_id,
                "metric": "fill_level",
                "value": float(fill_level),
                "unit": "%",
                "alert": fill_level >= 80
            })
            if fill_level >= 80:
                alerts.append({
                    "device": device["name"],
                    "message": f"Κάδος {fill_level}% γεμάτος!",
                    "level": "high" if fill_level >= 95 else "medium"
                })
        
        elif device_type == "street_light":
            consumption = round(random.uniform(0, 150), 1)
            fault = random.random() < 0.1
            readings.append({
                "device_id": device_id,
                "metric": "consumption_watts",
                "value": consumption,
                "unit": "W",
                "alert": fault
            })
            if fault:
                alerts.append({
                    "device": device["name"],
                    "message": "Βλάβη φωτισμού!",
                    "level": "medium"
                })
        
        elif device_type == "environment":
            temp = round(random.uniform(18, 38), 1)
            aqi = float(random.randint(30, 150))
            readings.append({
                "device_id": device_id,
                "metric": "temperature",
                "value": temp,
                "unit": "°C",
                "alert": temp >= 35
            })
            readings.append({
                "device_id": device_id,
                "metric": "air_quality_aqi",
                "value": aqi,
                "unit": "AQI",
                "alert": aqi >= 100
            })
            if aqi >= 100:
                alerts.append({
                    "device": device["name"],
                    "message": f"Υψηλή ρύπανση — AQI: {aqi}",
                    "level": "high"
                })
        
        elif device_type == "water_pressure":
            pressure = round(random.uniform(2.0, 6.0), 2)
            leak = random.random() < 0.05
            readings.append({
                "device_id": device_id,
                "metric": "pressure_bar",
                "value": pressure,
                "unit": "bar",
                "alert": leak or pressure < 2.5
            })
            if leak:
                alerts.append({
                    "device": device["name"],
                    "message": "Πιθανή διαρροή νερού!",
                    "level": "high"
                })
        
        elif device_type == "traffic":
            congestion = float(random.randint(0, 100))
            readings.append({
                "device_id": device_id,
                "metric": "congestion_level",
                "value": congestion,
                "unit": "%",
                "alert": congestion >= 80
            })
            if congestion >= 80:
                alerts.append({
                    "device": device["name"],
                    "message": f"Κυκλοφοριακή συμφόρηση {congestion}%",
                    "level": "medium"
                })
    
    # Αποθήκευσε readings σε ένα batch
    if readings:
        supabase.table("iot_readings").insert(readings).execute()
    
    logger.info(f"✅ IoT: {len(readings)} readings, {len(alerts)} alerts")
    return {"readings": readings, "alerts": alerts}


def get_latest_readings():
    """Παίρνει τις τελευταίες μετρήσεις ανά device"""
    devices = supabase.table("iot_devices")\
        .select("*")\
        .execute()
    
    result = []
    for device in devices.data or []:
        readings = supabase.table("iot_readings")\
            .select("metric, value, unit, alert, created_at")\
            .eq("device_id", device["id"])\
            .order("created_at", desc=True)\
            .limit(3)\
            .execute()
        
        result.append({
            **device,
            "latest_readings": readings.data or []
        })
    
    return result