import time
import math
import uuid
import threading
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from enum import Enum


class DroneStatus(str, Enum):
    IDLE = "IDLE"
    DISPATCHED = "DISPATCHED"
    EN_ROUTE = "EN_ROUTE"
    ON_SITE = "ON_SITE"
    RETURNING = "RETURNING"
    CHARGING = "CHARGING"
    MALFUNCTION = "MALFUNCTION"


class DroneMode(str, Enum):
    SURVEILLANCE = "SURVEILLANCE"
    RESCUE = "RESCUE"
    SUPPLY_DROP = "SUPPLY_DROP"
    FIRE_SUPPRESSION = "FIRE_SUPPRESSION"
    FLOOD_RESCUE = "FLOOD_RESCUE"


@dataclass
class DroneState:
    drone_id: str
    name: str
    status: DroneStatus = DroneStatus.IDLE
    mode: DroneMode = DroneMode.SURVEILLANCE
    battery_level: float = 100.0
    current_lat: float = 19.0760   # Default: Mumbai
    current_lng: float = 72.8777
    target_lat: Optional[float] = None
    target_lng: Optional[float] = None
    altitude_m: float = 0.0
    speed_kmh: float = 0.0
    camera_active: bool = False
    payload: str = "None"
    mission_id: Optional[str] = None
    telemetry_log: List[Dict] = field(default_factory=list)
    eta_seconds: Optional[float] = None


class DroneService:
    """Manages drone fleet for disaster response."""

    DRONE_SPEED_KMH = 80.0
    CRUISE_ALTITUDE_M = 120.0
    BATTERY_DRAIN_PER_KM = 2.0  # % per km

    def __init__(self):
        self.fleet: Dict[str, DroneState] = {}
        self._init_fleet()
        self._simulation_threads: Dict[str, threading.Thread] = {}

    def _init_fleet(self):
        drones = [
            ("DRONE-001", "Alpha", DroneMode.SURVEILLANCE),
            ("DRONE-002", "Bravo", DroneMode.RESCUE),
            ("DRONE-003", "Charlie", DroneMode.FIRE_SUPPRESSION),
            ("DRONE-004", "Delta", DroneMode.FLOOD_RESCUE),
        ]
        for drone_id, name, mode in drones:
            self.fleet[drone_id] = DroneState(
                drone_id=drone_id,
                name=name,
                mode=mode,
                payload=self._default_payload(mode)
            )

    def _default_payload(self, mode: DroneMode) -> str:
        payloads = {
            DroneMode.SURVEILLANCE: "4K Camera + Thermal Imaging",
            DroneMode.RESCUE: "Life Vest + First Aid Kit",
            DroneMode.FIRE_SUPPRESSION: "Fire Retardant (5L)",
            DroneMode.FLOOD_RESCUE: "Flotation Device + Rope",
            DroneMode.SUPPLY_DROP: "Emergency Supplies Pack",
        }
        return payloads.get(mode, "Standard Equipment")

    def _haversine_km(self, lat1, lng1, lat2, lng2) -> float:
        R = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lng2 - lng1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    def dispatch(
        self,
        target_lat: float,
        target_lng: float,
        disaster_type: str = "general",
        preferred_drone_id: Optional[str] = None,
        mission_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Dispatch the best available drone to target location."""

        # Select drone
        drone = None
        if preferred_drone_id and preferred_drone_id in self.fleet:
            drone = self.fleet[preferred_drone_id]
        else:
            mode_map = {
                "fire": DroneMode.FIRE_SUPPRESSION,
                "flood": DroneMode.FLOOD_RESCUE,
                "accident": DroneMode.RESCUE,
                "general": DroneMode.SURVEILLANCE,
            }
            preferred_mode = mode_map.get(disaster_type, DroneMode.SURVEILLANCE)
            # Find idle drone with preferred mode first, then any idle drone
            for d in self.fleet.values():
                if d.status == DroneStatus.IDLE:
                    if d.mode == preferred_mode:
                        drone = d
                        break
            if drone is None:
                for d in self.fleet.values():
                    if d.status == DroneStatus.IDLE:
                        drone = d
                        break

        if drone is None:
            return {
                "success": False,
                "error": "No drones available. All units are deployed.",
                "fleet_status": self.get_fleet_status()
            }

        if drone.battery_level < 20:
            return {
                "success": False,
                "error": f"Drone {drone.name} battery too low ({drone.battery_level}%). Charging required.",
            }

        distance_km = self._haversine_km(
            drone.current_lat, drone.current_lng, target_lat, target_lng
        )
        eta_seconds = (distance_km / self.DRONE_SPEED_KMH) * 3600
        battery_needed = distance_km * self.BATTERY_DRAIN_PER_KM * 2  # round trip

        if battery_needed > drone.battery_level:
            return {
                "success": False,
                "error": f"Insufficient battery for round trip ({battery_needed:.1f}% needed, {drone.battery_level:.1f}% available).",
            }

        # Update drone state
        drone.status = DroneStatus.DISPATCHED
        drone.target_lat = target_lat
        drone.target_lng = target_lng
        drone.mission_id = mission_id or str(uuid.uuid4())
        drone.eta_seconds = eta_seconds
        drone.camera_active = True

        # Start simulation thread
        thread = threading.Thread(
            target=self._simulate_flight,
            args=(drone.drone_id, target_lat, target_lng, distance_km, eta_seconds),
            daemon=True
        )
        self._simulation_threads[drone.drone_id] = thread
        thread.start()

        return {
            "success": True,
            "drone_id": drone.drone_id,
            "drone_name": drone.name,
            "mode": drone.mode.value,
            "payload": drone.payload,
            "mission_id": drone.mission_id,
            "target": {"lat": target_lat, "lng": target_lng},
            "distance_km": round(distance_km, 2),
            "eta_seconds": round(eta_seconds, 0),
            "eta_minutes": round(eta_seconds / 60, 1),
            "battery_level": drone.battery_level,
            "status": drone.status.value
        }

    def _simulate_flight(self, drone_id: str, target_lat, target_lng, distance_km, eta_seconds):
        """Simulate drone flight in background thread."""
        drone = self.fleet[drone_id]
        steps = 20
        step_time = eta_seconds / steps

        start_lat, start_lng = drone.current_lat, drone.current_lng
        drone.status = DroneStatus.EN_ROUTE
        drone.altitude_m = self.CRUISE_ALTITUDE_M
        drone.speed_kmh = self.DRONE_SPEED_KMH

        for i in range(1, steps + 1):
            time.sleep(min(step_time, 2.0))  # Cap sim sleep for responsiveness
            fraction = i / steps
            drone.current_lat = start_lat + (target_lat - start_lat) * fraction
            drone.current_lng = start_lng + (target_lng - start_lng) * fraction
            drone.battery_level = max(0, drone.battery_level - (distance_km * self.BATTERY_DRAIN_PER_KM / steps))
            drone.eta_seconds = max(0, eta_seconds * (1 - fraction))
            drone.telemetry_log.append({
                "timestamp": time.time(),
                "lat": round(drone.current_lat, 6),
                "lng": round(drone.current_lng, 6),
                "battery": round(drone.battery_level, 1),
                "altitude": drone.altitude_m
            })

        # Arrived
        drone.status = DroneStatus.ON_SITE
        drone.current_lat = target_lat
        drone.current_lng = target_lng
        drone.speed_kmh = 0.0
        drone.eta_seconds = 0

    def recall_drone(self, drone_id: str) -> Dict[str, Any]:
        if drone_id not in self.fleet:
            return {"success": False, "error": "Drone not found"}
        drone = self.fleet[drone_id]
        drone.status = DroneStatus.RETURNING
        drone.target_lat = 19.0760
        drone.target_lng = 72.8777
        return {"success": True, "message": f"Drone {drone.name} is returning to base."}

    def get_fleet_status(self) -> List[Dict]:
        return [
            {
                **asdict(d),
                "status": d.status.value,
                "mode": d.mode.value,
                "telemetry_log": d.telemetry_log[-5:] if d.telemetry_log else []
            }
            for d in self.fleet.values()
        ]

    def get_drone_status(self, drone_id: str) -> Optional[Dict]:
        if drone_id not in self.fleet:
            return None
        d = self.fleet[drone_id]
        return {
            **asdict(d),
            "status": d.status.value,
            "mode": d.mode.value,
            "telemetry_log": d.telemetry_log[-10:] if d.telemetry_log else []
        }