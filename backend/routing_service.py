"""OSRM routing service with caching and fallback handling."""
import json
import time
import sqlite3
from typing import Optional, Dict, Any
from dataclasses import dataclass
from backend.config import get_settings
from backend.database import get_db_path, get_db_connection


@dataclass
class RouteResult:
    duration_seconds: Optional[int]
    distance_meters: Optional[int]
    geometry: Optional[Dict[str, Any]]
    source: str


_route_cache: Dict[str, RouteResult] = {}
_cache_timestamps: Dict[str, float] = {}


def get_cache_key(origin_lng: float, origin_lat: float, dest_lng: float, dest_lat: float) -> str:
    return f"{origin_lng:.6f},{origin_lat:.6f}->{dest_lng:.6f},{dest_lat:.6f}"


def load_route_cache() -> None:
    settings = get_settings()
    try:
        with open(settings.route_cache_path, 'r') as f:
            data = json.load(f)
        for entry in data.get("routes", []):
            key = entry["key"]
            _route_cache[key] = RouteResult(
                duration_seconds=entry.get("duration_seconds"),
                distance_meters=entry.get("distance_meters"),
                geometry=entry.get("geometry"),
                source=entry.get("source", "osrm_cached")
            )
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass


def save_route_cache() -> None:
    settings = get_settings()
    data = {"routes": []}
    for key, result in _route_cache.items():
        data["routes"].append({
            "key": key,
            "duration_seconds": result.duration_seconds,
            "distance_meters": result.distance_meters,
            "geometry": result.geometry,
            "source": result.source
        })
    try:
        with open(settings.route_cache_path, 'w') as f:
            json.dump(data, f)
    except Exception:
        pass


def get_cached_route(key: str) -> Optional[RouteResult]:
    settings = get_settings()
    if key in _route_cache:
        if time.time() - _cache_timestamps.get(key, 0) < settings.route_cache_ttl_seconds:
            return _route_cache[key]
        else:
            del _route_cache[key]
            _cache_timestamps.pop(key, None)
    return None


def set_cached_route(key: str, result: RouteResult) -> None:
    _route_cache[key] = result
    _cache_timestamps[key] = time.time()


def get_db_cached_route(origin_lng: float, origin_lat: float, dest_lng: float, dest_lat: float) -> Optional[RouteResult]:
    try:
        with get_db_connection() as conn:
            row = conn.execute(
                """SELECT route_json, source FROM route_cache
                   WHERE origin_lat = ? AND origin_lng = ? AND dest_lat = ? AND dest_lng = ?
                   AND datetime(expires_at) > datetime('now')""",
                (origin_lat, origin_lng, dest_lat, dest_lng)
            ).fetchone()
            if row:
                route_data = json.loads(row["route_json"])
                return RouteResult(
                    duration_seconds=route_data.get("duration_seconds"),
                    distance_meters=route_data.get("distance_meters"),
                    geometry=route_data.get("geometry"),
                    source=row["source"]
                )
    except Exception:
        pass
    return None


def set_db_cached_route(
    origin_lng: float, origin_lat: float,
    dest_lng: float, dest_lat: float,
    result: RouteResult, ttl_seconds: int = 300
) -> None:
    try:
        import datetime
        expires = datetime.datetime.utcnow() + datetime.timedelta(seconds=ttl_seconds)
        key = get_cache_key(origin_lng, origin_lat, dest_lng, dest_lat)
        with get_db_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO route_cache
                   (id, origin_lat, origin_lng, dest_lat, dest_lng, route_json, source, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (key, origin_lat, origin_lng, dest_lat, dest_lng,
                 json.dumps({
                     "duration_seconds": result.duration_seconds,
                     "distance_meters": result.distance_meters,
                     "geometry": result.geometry
                 }),
                 result.source,
                 datetime.datetime.utcnow().isoformat(),
                 expires.isoformat())
            )
            conn.commit()
    except Exception:
        pass


def fetch_osrm_route(origin_lng: float, origin_lat: float, dest_lng: float, dest_lat: float) -> Optional[RouteResult]:
    settings = get_settings()
    import urllib.request
    import urllib.error
    
    url = f"{settings.routing_base_url}/route/v1/driving/{origin_lng},{origin_lat};{dest_lng},{dest_lat}"
    params = "?overview=full&geometries=geojson&steps=false"
    
    try:
        req = urllib.request.Request(url + params, headers={'User-Agent': 'SahayakDispatch/1.0'})
        with urllib.request.urlopen(req, timeout=settings.routing_timeout) as response:
            data = json.loads(response.read().decode())
        
        if data.get("code") == "Ok" and data.get("routes"):
            route = data["routes"][0]
            return RouteResult(
                duration_seconds=int(route.get("duration", 0)),
                distance_meters=int(route.get("distance", 0)),
                geometry=route.get("geometry"),
                source="osrm_live"
            )
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, KeyError, TimeoutError):
        pass
    
    return None


def get_route(
    origin_lng: float, origin_lat: float,
    dest_lng: float, dest_lat: float,
    use_cache: bool = True
) -> RouteResult:
    key = get_cache_key(origin_lng, origin_lat, dest_lng, dest_lat)
    
    if use_cache:
        cached = get_cached_route(key)
        if cached:
            return RouteResult(
                duration_seconds=cached.duration_seconds,
                distance_meters=cached.distance_meters,
                geometry=cached.geometry,
                source="osrm_cached"
            )
        
        db_cached = get_db_cached_route(origin_lng, origin_lat, dest_lng, dest_lat)
        if db_cached:
            set_cached_route(key, db_cached)
            return RouteResult(
                duration_seconds=db_cached.duration_seconds,
                distance_meters=db_cached.distance_meters,
                geometry=db_cached.geometry,
                source="osrm_cached"
            )
    
    result = fetch_osrm_route(origin_lng, origin_lat, dest_lng, dest_lat)
    
    if result:
        if use_cache:
            set_cached_route(key, result)
            set_db_cached_route(origin_lng, origin_lat, dest_lng, dest_lat, result)
        return result
    
    from backend.responder_matcher import haversine_distance
    distance = haversine_distance(origin_lat, origin_lng, dest_lat, dest_lng)
    duration = int(distance / (30 * 1000 / 3600))
    
    fallback_result = RouteResult(
        duration_seconds=duration,
        distance_meters=int(distance),
        geometry=None,
        source="approximate_straight_line"
    )
    
    if use_cache:
        set_cached_route(key, fallback_result)
    
    return fallback_result


load_route_cache()