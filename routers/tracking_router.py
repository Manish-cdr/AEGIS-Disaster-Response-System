from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, List
import time
import uuid

router = APIRouter()

# In-memory store: device_id → latest location + trail
_devices: Dict[str, Dict] = {}
TRAIL_MAX = 100   # keep last N points per device
DEVICE_TIMEOUT = 300  # seconds before device considered offline

class LocationUpdate(BaseModel):
    device_id: Optional[str] = None   # omit to auto-generate
    label: str = "Field Unit"
    lat: float
    lng: float
    accuracy: Optional[float] = None
    heading: Optional[float] = None
    speed_kmh: Optional[float] = None
    battery: Optional[int] = None
    note: Optional[str] = None

@router.post("/update")
async def update_location(data: LocationUpdate):
    device_id = data.device_id or str(uuid.uuid4())[:8]
    now = time.time()
    if device_id not in _devices:
        _devices[device_id] = {
            "device_id": device_id,
            "label": data.label,
            "trail": [],
            "first_seen": now
        }
    dev = _devices[device_id]
    dev["label"] = data.label
    dev["lat"] = data.lat
    dev["lng"] = data.lng
    dev["accuracy"] = data.accuracy
    dev["heading"] = data.heading
    dev["speed_kmh"] = data.speed_kmh
    dev["battery"] = data.battery
    dev["note"] = data.note
    dev["last_seen"] = now
    dev["online"] = True
    dev["trail"].append({"lat": data.lat, "lng": data.lng, "ts": now})
    if len(dev["trail"]) > TRAIL_MAX:
        dev["trail"].pop(0)
    return {"device_id": device_id, "status": "ok", "timestamp": now}

@router.get("/devices")
async def get_all_devices():
    now = time.time()
    result = []
    for dev in _devices.values():
        last = dev.get("last_seen", 0)
        online = (now - last) < DEVICE_TIMEOUT
        result.append({**dev, "online": online, "trail": dev["trail"][-20:]})
    return {"devices": result, "count": len(result)}

@router.get("/device/{device_id}")
async def get_device(device_id: str):
    if device_id not in _devices:
        raise HTTPException(status_code=404, detail="Device not found")
    dev = _devices[device_id]
    online = (time.time() - dev.get("last_seen", 0)) < DEVICE_TIMEOUT
    return {**dev, "online": online}

@router.delete("/device/{device_id}")
async def remove_device(device_id: str):
    if device_id not in _devices:
        raise HTTPException(status_code=404, detail="Device not found")
    del _devices[device_id]
    return {"status": "removed"}

@router.post("/simulate")
async def simulate_devices():
    """Add 3 simulated field units for demo purposes."""
    import math, random
    base_lat, base_lng = 19.0760, 72.8777
    demos = [
        ("UNIT-01", "Field Officer A", 0.008,  0.004),
        ("UNIT-02", "Medic Team B",   -0.005,  0.010),
        ("UNIT-03", "Fire Brigade C",  0.012, -0.006),
    ]
    now = time.time()
    created = []
    for did, label, dlat, dlng in demos:
        _devices[did] = {
            "device_id": did, "label": label,
            "lat": base_lat + dlat, "lng": base_lng + dlng,
            "accuracy": 8.0, "heading": random.uniform(0,360),
            "speed_kmh": round(random.uniform(0,40),1),
            "battery": random.randint(30,95),
            "note": "Demo unit",
            "last_seen": now, "online": True,
            "first_seen": now,
            "trail": [
                {"lat": base_lat+dlat+math.sin(i)*0.001,
                 "lng": base_lng+dlng+math.cos(i)*0.001, "ts": now-i*10}
                for i in range(10, 0, -1)
            ]
        }
        created.append(did)
    return {"status": "ok", "simulated": created}