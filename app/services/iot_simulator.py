import random
from datetime import datetime, timezone
from app.database import supabase
import logging

logger = logging.getLogger(__name__)

def simulate_readings():
    """Δημιουργεί προσομοιωμένες μετρήσεις για όλες τις συσκευές"""
    
    devices = supabase.table("iot_devices")\
        .select("*")\
        .eq("status", "active")\
        .execute()
    
    if not devices.data:
        return []
    
    readings = []
    alerts = []
    
    for device in devices.data:
        device_id = device["id"]
        device_type = device["type"]
        
        if device_type == "waste_bin":
            fill_level = random.randint(20, 100)
            reading = {
                "device_id": device_id,
                "metric": "fill_level",
                "value": fill_level,
                "unit": "%",
                "alert": fill_level >= 80
            }
            readings.append(reading)
            if fill_level >= 80:
                alerts.append({
                    "device": device["name"],
                    "message": f"Κάδος {fill_level}% γεμάτος — χρειάζεται αποκομιδή!",
                    "level": "high" if fill_level >= 95 else "medium"
                })
        
        elif device_type == "street_light":
            is_on = random.choice([True, True, True, False])
            consumption = random.uniform(50, 150) if is_on else 0
            fault = random.random() < 0.1  # 10% πιθανότητα βλάβης
            reading = {
                "device_id": device_id,
                "metric": "consumption_watts",
                "value": round(consumption, 1),
                "unit": "W",
                "alert": fault
            }
            readings.append(reading)
            if fault:
                alerts.append({
                    "device": device["name"],
                    "message": f"Βλάβη φωτισμού — έλεγχος απαραίτητος!",
                    "level": "medium"
                })
        
        elif device_type == "environment":
            temp = round(random.uniform(18, 38), 1)
            air_quality = random.randint(30, 150)  # AQI
            noise = round(random.uniform(40, 90), 1)  # dB
            
            for metric, value, unit, threshold in [
                ("temperature", temp, "°C", 35),
                ("air_quality_aqi", air_quality, "AQI", 100),
                ("noise_db", noise, "dB", 80),
            ]:
                reading = {
                    "device_id": device_id,
                    "metric": metric,
                    "value": value,
                    "unit": unit,
                    "alert": value >= threshold
                }
                readings.append(reading)
            
            if air_quality >= 100:
                alerts.append({
                    "device": device["name"],
                    "message": f"Υψηλή ρύπανση αέρα — AQI: {air_quality}",
                    "level": "high"
                })
        
        elif device_type == "water_pressure":
            pressure = round(random.uniform(2.0, 6.0), 2)
            leak_detected = random.random() < 0.05  # 5% πιθανότητα διαρροής
            reading = {
                "device_id": device_id,
                "metric": "pressure_bar",
                "value": pressure,
                "unit": "bar",
                "alert": leak_detected or pressure < 2.5
            }
            readings.append(reading)
            if leak_detected:
                alerts.append({
                    "device": device["name"],
                    "message": "Πιθανή διαρροή νερού — άμεσος έλεγχος!",
                    "level": "high"
                })
        
        elif device_type == "traffic":
            congestion = random.randint(0, 100)
            reading = {
                "device_id": device_id,
                "metric": "congestion_level",
                "value": congestion,
                "unit": "%",
                "alert": congestion >= 80
            }
            readings.append(reading)
            if congestion >= 80:
                alerts.append({
                    "device": device["name"],
                    "message": f"Κυκλοφοριακή συμφόρηση {congestion}%",
                    "level": "medium"
                })
        
        # Update battery level
        battery = max(0, device.get("battery_level", 100) - random.randint(0, 1))
        supabase.table("iot_devices")\
            .update({
                "battery_level": battery,
                "last_seen": datetime.now(timezone.utc).isoformat()
            })\
            .eq("id", device_id)\
            .execute()
    
    # Αποθήκευσε readings
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
            .select("*")\
            .eq("device_id", device["id"])\
            .order("created_at", desc=True)\
            .limit(3)\
            .execute()
        
        result.append({
            **device,
            "latest_readings": readings.data or []
        })
    
    return result