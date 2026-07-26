import os
import re
import json
import math
from typing import Dict, Any, Optional, Tuple
import urllib.request
import urllib.parse


class LocationService:
    """Handles geolocation, geocoding, and mapping operations."""

    GEOAPIFY_API_KEY = os.getenv("GEOAPIFY_API_KEY", "YOUR_GEOAPIFY_API_KEY")

    # Disaster-prone sample locations for demo
    SAMPLE_LOCATIONS = [
        {"name": "Mumbai, Maharashtra", "lat": 19.0760, "lng": 72.8777},
        {"name": "Chennai, Tamil Nadu", "lat": 13.0827, "lng": 80.2707},
        {"name": "Kolkata, West Bengal", "lat": 22.5726, "lng": 88.3639},
        {"name": "Kerala Coast", "lat": 10.8505, "lng": 76.2711},
        {"name": "Uttarakhand Hills", "lat": 30.0668, "lng": 79.0193},
    ]

    def geocode_address(self, address: str) -> Dict[str, Any]:
        if self.GEOAPIFY_API_KEY == "YOUR_GEOAPIFY_API_KEY":
            return self._mock_geocode(address)

        try:
            encoded = urllib.parse.quote(address)

            url = (
            f"https://api.geoapify.com/v1/geocode/search"
            f"?text={encoded}"
            f"&apiKey={self.GEOAPIFY_API_KEY}"
        )

            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read())

            if data["features"]:
                props = data["features"][0]["properties"]
                return {
                "success": True,
                "lat": props["lat"],
                "lng": props["lon"],
                "formatted_address": props["formatted"],
                "place_id": props.get("place_id", "")
            }

        except Exception as e:
            print(f"[WARN] Geocoding failed: {e}")

        return self._mock_geocode(address)

    def _mock_geocode(self, address: str) -> Dict[str, Any]:
        """Mock geocoder for demo without real API key."""
        address_lower = address.lower()
        for loc in self.SAMPLE_LOCATIONS:
            if any(word in address_lower for word in loc["name"].lower().split(",")):
                return {
                    "success": True,
                    "lat": loc["lat"],
                    "lng": loc["lng"],
                    "formatted_address": loc["name"],
                    "place_id": "mock_place_id",
                    "note": "Mock geocoding result (no real API key configured)"
                }
        # Default fallback
        return {
            "success": True,
            "lat": 19.0760 + (hash(address) % 100) * 0.001,
            "lng": 72.8777 + (hash(address) % 100) * 0.001,
            "formatted_address": address,
            "place_id": "mock_place_id",
            "note": "Mock geocoding result"
        }

    def reverse_geocode(self, lat: float, lng: float) -> Dict[str, Any]:
        """Convert coordinates to address using Geoapify."""

        if self.GEOAPIFY_API_KEY == "YOUR_GEOAPIFY_API_KEY":
            return {
            "success": True,
            "formatted_address": f"Near ({lat:.4f}, {lng:.4f})",
            "note": "Mock reverse geocoding"
        }

        try:
            url = (
            f"https://api.geoapify.com/v1/geocode/reverse"
            f"?lat={lat}&lon={lng}"
            f"&apiKey={self.GEOAPIFY_API_KEY}"
        )

            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read())

            if data["features"]:
                props = data["features"][0]["properties"]
                return {
                "success": True,
                "formatted_address": props["formatted"],
                "place_id": props.get("place_id", "")
            }

        except Exception as e:
            print(f"[WARN] Reverse geocoding failed: {e}")

        return {
        "success": True,
        "formatted_address": f"Location ({lat:.4f}, {lng:.4f})",
    }

    def parse_iso6709(self, iso_string: str) -> Optional[Tuple[float, float]]:
        """Parse ISO 6709 GPS string from video metadata."""
        # e.g. "+19.0760+072.8777+10.000/"
        pattern = r'([+-]\d+\.\d+)([+-]\d+\.\d+)'
        match = re.search(pattern, iso_string)
        if match:
            lat = float(match.group(1))
            lng = float(match.group(2))
            return lat, lng
        return None

    def calculate_distance(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Haversine distance in km."""
        R = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lng2 - lng1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    def get_maps_embed_url(self, lat: float, lng: float, zoom: int = 14) -> str:
        """Generate map URL (OpenStreetMap)."""
        return f"https://www.openstreetmap.org/#map={zoom}/{lat}/{lng}"

    def get_static_map_url(self, lat: float, lng: float, zoom: int = 14) -> str:
        """Generate Geoapify Static Map URL with marker."""
    
        key = self.GEOAPIFY_API_KEY

        if key == "YOUR_GEOAPIFY_API_KEY":
            return ""

        return (
        f"https://maps.geoapify.com/v1/staticmap"
        f"?style=osm-bright"
        f"&width=600&height=400"
        f"&center=lonlat:{lng},{lat}"
        f"&zoom={zoom}"
        f"&marker=lonlat:{lng},{lat};color:%23ff0000;size:medium"
        f"&apiKey={key}"
    )