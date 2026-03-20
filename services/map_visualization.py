"""
Advanced India Logistics Map — Leaflet.js
Features:
  - Pan-India view (zoom 5, center ~22°N 79°E)
  - Multi-shipment animated markers with status colors
  - Route polylines per shipment
  - Rich popup: Tracking ID, Route, Status, ETA, Carrier
  - Filter buttons: All | In Transit | Delayed | Delivered
  - Search box: highlight + zoom to a specific TKT ID
  - City hub markers (all 24 nodes)
  - Dark tile layer
"""

import json
from typing import List, Dict, Optional, Any


# ── Status → color ────────────────────────────────────────────────────────────
STATUS_COLOR = {
    # Lifecycle stages
    "Created":           "#818CF8",
    "Picked Up":         "#F59E0B",
    "In Transit":        "#00D1FF",
    "Out for Delivery":  "#FB923C",
    "Delivered":         "#22C55E",
    "Delayed":           "#EF4444",
    # Legacy
    "Pending":           "#94A3B8",
    "Booked":            "#818CF8",
}


def _fmt_eta(eta_iso: str) -> str:
    try:
        import datetime
        eta_dt = datetime.datetime.fromisoformat(eta_iso)
        hrs    = max(0.0, (eta_dt - datetime.datetime.now()).total_seconds() / 3600)
        return f"{hrs:.1f} h ({eta_dt.strftime('%d %b %H:%M')})"
    except Exception:
        return "TBD"


def build_india_map(
    shipments: List[Dict],
    city_nodes: Optional[Dict] = None,
    height: int = 600,
    highlight_tid: Optional[str] = None,
) -> str:
    """
    Build and return a self-contained Leaflet.js HTML map of India
    showing all provided shipments with popups, route lines, and filters.

    Args:
        shipments:    list of shipment dicts from simulation engine
        city_nodes:   INDIA_CITIES dict (auto-imported if None)
        height:       map height in pixels
        highlight_tid: tracking ID to zoom/highlight on load
    """
    if city_nodes is None:
        try:
            from services.india_network import INDIA_CITIES
            city_nodes = INDIA_CITIES
        except Exception:
            city_nodes = {}

    # ── City hub GeoJSON ──────────────────────────────────────────────────────
    city_json = json.dumps([
        {"name": c, "lat": v["lat"], "lon": v["lon"], "zone": v.get("zone", "")}
        for c, v in city_nodes.items()
    ])

    # ── Shipment data for JS ──────────────────────────────────────────────────
    ship_data = []
    for s in shipments:
        route = s.get("route", [s.get("source", ""), s.get("destination", "")])
        route_coords = []
        for city in route:
            c = city_nodes.get(city, {})
            if c:
                route_coords.append({"lat": c["lat"], "lon": c["lon"], "city": city})
        eta_str = _fmt_eta(s.get("eta", ""))
        ship_data.append({
            "tracking_id": s.get("tracking_id", ""),
            "source":      s.get("source", s.get("origin_city", "")),
            "destination": s.get("destination", s.get("destination_city", "")),
            "current_city":s.get("current_city", ""),
            "lat":         s.get("lat", 0),
            "lon":         s.get("lon", 0),
            "status":      s.get("status", "In Transit"),
            "carrier":     s.get("carrier", ""),
            "weight":      s.get("weight", ""),
            "priority":    s.get("priority", ""),
            "eta":         eta_str,
            "color":       STATUS_COLOR.get(s.get("status", ""), "#94A3B8"),
            "route_coords":route_coords,
            "speed":       round(s.get("speed_kmph", 0)),
        })

    ship_json     = json.dumps(ship_data)
    highlight_js  = json.dumps(highlight_tid or "")

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>eShipz India Logistics Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  *   {{ margin:0; padding:0; box-sizing:border-box; }}
  body{{ background:#0B0E14; font-family:'Inter',sans-serif; }}
  #map{{ width:100%; height:{height}px; }}

  /* Filter bar */
  #filter-bar {{
    position:absolute; top:10px; left:50%; transform:translateX(-50%);
    z-index:1000; display:flex; gap:8px; flex-wrap:wrap; justify-content:center;
  }}
  .filter-btn {{
    background:rgba(11,14,20,0.85); color:#D1D5DB;
    border:1px solid #374151; border-radius:20px;
    padding:5px 14px; font-size:12px; cursor:pointer;
    backdrop-filter:blur(4px); transition:all .2s;
  }}
  .filter-btn:hover  {{ border-color:#625DF5; color:#fff; }}
  .filter-btn.active {{ background:#625DF5; border-color:#625DF5; color:#fff; }}

  /* Search box */
  #search-bar {{
    position:absolute; top:52px; left:50%; transform:translateX(-50%);
    z-index:1000; display:flex; gap:6px;
  }}
  #search-input {{
    background:rgba(11,14,20,0.9); color:#D1D5DB;
    border:1px solid #374151; border-radius:8px;
    padding:5px 12px; font-size:12px; width:200px;
    outline:none;
  }}
  #search-input::placeholder {{ color:#6B7280; }}
  #search-btn {{
    background:#625DF5; color:#fff; border:none;
    border-radius:8px; padding:5px 12px; font-size:12px;
    cursor:pointer;
  }}

  /* Legend */
  #legend {{
    position:absolute; bottom:20px; right:10px; z-index:1000;
    background:rgba(11,14,20,0.88); border:1px solid #374151;
    border-radius:10px; padding:10px 14px; font-size:11px; color:#D1D5DB;
  }}
  .leg-row {{ display:flex; align-items:center; gap:6px; margin:3px 0; }}
  .leg-dot {{ width:10px; height:10px; border-radius:50%; }}

  /* Popup */
  .lf-popup-custom {{ font-family:'Inter',sans-serif; font-size:12px; }}
  .popup-header {{
    background:#625DF5; color:#fff; padding:6px 10px;
    border-radius:6px 6px 0 0; font-weight:700; font-size:13px;
  }}
  .popup-body {{ padding:8px 10px; }}
  .popup-row {{ margin:3px 0; color:#334155; }}
  .popup-row b {{ color:#111827; }}
  .status-badge {{
    display:inline-block; padding:2px 8px; border-radius:10px;
    font-size:11px; font-weight:600; color:#fff;
  }}

  /* Stats strip */
  #stats-strip {{
    position:absolute; bottom:20px; left:10px; z-index:1000;
    background:rgba(11,14,20,0.88); border:1px solid #374151;
    border-radius:10px; padding:8px 14px; font-size:11px; color:#94A3B8;
  }}
  #stats-strip span {{ color:#D1D5DB; font-weight:600; }}
</style>
</head>
<body>
<div id="map"></div>

<!-- Filter Bar -->
<div id="filter-bar">
  <button class="filter-btn active" onclick="applyFilter('All')">🌐 All</button>
  <button class="filter-btn" onclick="applyFilter('Picked Up')">📦 Picked Up</button>
  <button class="filter-btn" onclick="applyFilter('In Transit')">🚚 In Transit</button>
  <button class="filter-btn" onclick="applyFilter('Out for Delivery')">🏠 Out for Delivery</button>
  <button class="filter-btn" onclick="applyFilter('Delayed')">⚠️ Delayed</button>
  <button class="filter-btn" onclick="applyFilter('Delivered')">✅ Delivered</button>
</div>

<!-- Search Bar -->
<div id="search-bar">
  <input id="search-input" type="text" placeholder="Search TKT000001..." />
  <button id="search-btn" onclick="searchShipment()">🔍</button>
</div>

<!-- Stats Strip -->
<div id="stats-strip" id="stats-bar"></div>

<!-- Legend -->
<div id="legend">
  <div style="font-weight:700;margin-bottom:6px;color:#fff;">Legend</div>
  <div class="leg-row"><div class="leg-dot" style="background:#818CF8"></div> Created</div>
  <div class="leg-row"><div class="leg-dot" style="background:#F59E0B"></div> Picked Up</div>
  <div class="leg-row"><div class="leg-dot" style="background:#00D1FF"></div> In Transit</div>
  <div class="leg-row"><div class="leg-dot" style="background:#FB923C"></div> Out for Delivery</div>
  <div class="leg-row"><div class="leg-dot" style="background:#22C55E"></div> Delivered</div>
  <div class="leg-row"><div class="leg-dot" style="background:#EF4444"></div> Delayed</div>
  <div class="leg-row"><div class="leg-dot" style="background:#4B5563"></div> City Hub</div>
</div>

<script>
// ── Data ──────────────────────────────────────────────────────────────────────
const CITIES    = {city_json};
const SHIPMENTS = {ship_json};
const HIGHLIGHT = {highlight_js};

// ── Map init ──────────────────────────────────────────────────────────────────
const map = L.map('map', {{
  center: [22.5, 82.0],
  zoom: 5,
  zoomControl: true,
}});

// Primary: Stadia dark (reliable in iframes)
const tileLayer = L.tileLayer(
  'https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{{z}}/{{x}}/{{y}}{{r}}.png',
  {{attribution: '©Stadia Maps ©OpenMapTiles ©OpenStreetMap', maxZoom: 20}}
);
tileLayer.on('tileerror', function() {{
  // Fallback to CartoDB if Stadia fails
  L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_matter/{{z}}/{{x}}/{{y}}.png',
    {{attribution:'©CartoDB', subdomains:'abcd', maxZoom:19}}).addTo(map);
}});
tileLayer.addTo(map);

// ── State ─────────────────────────────────────────────────────────────────────
let currentFilter = 'All';
let shipMarkers   = {{}};  // tracking_id → marker
let routeLines    = {{}};  // tracking_id → polyline
let cityMarkers   = [];

// ── City hub markers ──────────────────────────────────────────────────────────
function addCityHubs() {{
  CITIES.forEach(c => {{
    const icon = L.divIcon({{
      className:'',
      html:`<div style="width:8px;height:8px;background:#4B5563;border:1px solid #6B7280;
                border-radius:50%;"></div>`,
      iconAnchor:[4,4]
    }});
    const m = L.marker([c.lat, c.lon], {{icon}})
      .bindTooltip(`<b>${{c.name}}</b><br><small>${{c.zone}} Hub</small>`, {{
        permanent:false, direction:'top', className:'lf-tooltip'
      }}).addTo(map);
    cityMarkers.push(m);
  }});
}}
addCityHubs();

// ── Popup HTML ────────────────────────────────────────────────────────────────
function makePopup(s) {{
  const statusBg = s.color;
  return `<div class="lf-popup-custom" style="min-width:200px">
    <div class="popup-header">📦 ${{s.tracking_id}}</div>
    <div class="popup-body">
      <div class="popup-row">🚀 <b>Route:</b> ${{s.source}} → ${{s.destination}}</div>
      <div class="popup-row">📍 <b>Now:</b> ${{s.current_city}}</div>
      <div class="popup-row">🚛 <b>Carrier:</b> ${{s.carrier}}</div>
      <div class="popup-row">⚖️ <b>Weight:</b> ${{s.weight}} kg | ${{s.priority}} priority</div>
      <div class="popup-row">⏱ <b>ETA:</b> ${{s.eta}}</div>
      <div class="popup-row">🏎 <b>Speed:</b> ${{s.speed}} km/h</div>
      <div class="popup-row" style="margin-top:6px">
        <span class="status-badge" style="background:${{statusBg}}">${{s.status}}</span>
      </div>
    </div>
  </div>`;
}}

// ── Shipment markers + routes ─────────────────────────────────────────────────
function makeTruckIcon(color) {{
  return L.divIcon({{
    className: '',
    html: `<div style="
      width:28px; height:28px; border-radius:50%;
      background:${{color}}22; border:2px solid ${{color}};
      display:flex; align-items:center; justify-content:center;
      box-shadow:0 0 12px ${{color}}66;
      animation:pulse 2s infinite;">🚚</div>`,
    iconAnchor: [14, 14]
  }});
}}

function renderShipments(filter) {{
  // Remove old
  Object.values(shipMarkers).forEach(m => map.removeLayer(m));
  Object.values(routeLines).forEach(l => map.removeLayer(l));
  shipMarkers = {{}};
  routeLines  = {{}};

  let visible = 0;
  SHIPMENTS.forEach(s => {{
    if (filter !== 'All' && s.status !== filter) return;
    visible++;

    // Route polyline
    if (s.route_coords && s.route_coords.length > 1) {{
      const latlngs = s.route_coords.map(r => [r.lat, r.lon]);
      routeLines[s.tracking_id] = L.polyline(latlngs, {{
        color: s.color, weight: 2, opacity: 0.4, dashArray: '5 5'
      }}).addTo(map);
    }}

    // Truck marker
    const icon = makeTruckIcon(s.color);
    const m = L.marker([s.lat || 20, s.lon || 78], {{icon}})
      .bindPopup(makePopup(s), {{maxWidth:260, className:''}})
      .addTo(map);
    shipMarkers[s.tracking_id] = m;
  }});

  // Update stats
  document.getElementById('stats-strip').innerHTML =
    `Showing <span>${{visible}}</span> shipments · Filter: <span>${{filter}}</span>`;
}}

// ── Filter logic ──────────────────────────────────────────────────────────────
function applyFilter(filter) {{
  currentFilter = filter;
  document.querySelectorAll('.filter-btn').forEach(b => {{
    b.classList.toggle('active', b.textContent.trim().includes(filter) ||
      (filter === 'All' && b.textContent.includes('All')));
  }});
  renderShipments(filter);
}}

// ── Search logic ──────────────────────────────────────────────────────────────
function searchShipment() {{
  const q = document.getElementById('search-input').value.trim().toUpperCase();
  if (!q) return;
  const s = SHIPMENTS.find(x => x.tracking_id.toUpperCase() === q);
  if (!s) {{
    alert(`Shipment ${{q}} not found on map.`);
    return;
  }}
  // Show all filter so marker is visible
  applyFilter('All');
  const m = shipMarkers[s.tracking_id];
  if (m) {{
    map.flyTo([s.lat || 20, s.lon || 78], 8, {{animate:true, duration:1.5}});
    setTimeout(() => m.openPopup(), 1600);
  }}
}}

// Allow Enter key in search
document.getElementById('search-input').addEventListener('keydown', e => {{
  if (e.key === 'Enter') searchShipment();
}});

// ── CSS pulse animation ───────────────────────────────────────────────────────
const style = document.createElement('style');
style.textContent = `
  @keyframes pulse {{
    0%   {{ box-shadow: 0 0 0 0 rgba(255,255,255,0.4); }}
    70%  {{ box-shadow: 0 0 0 8px rgba(255,255,255,0); }}
    100% {{ box-shadow: 0 0 0 0 rgba(255,255,255,0); }}
  }}
`;
document.head.appendChild(style);

// ── Initial render ────────────────────────────────────────────────────────────
renderShipments('All');

// ── Auto-highlight on load ────────────────────────────────────────────────────
if (HIGHLIGHT) {{
  setTimeout(() => {{
    document.getElementById('search-input').value = HIGHLIGHT;
    searchShipment();
  }}, 800);
}}
</script>
</body>
</html>"""
    return html


# ── Single-shipment map (for User Dashboard) ───────────────────────────────────
def build_shipment_map(
    route_coords: List[Dict],
    current_lat:  Optional[float] = None,
    current_lon:  Optional[float] = None,
    all_shipments:Optional[List[Dict]] = None,
    show_all:     bool = False,
    height:       int  = 400,
    highlight_tid:Optional[str] = None,
) -> str:
    """
    Compatibility wrapper.
    If show_all=True or all_shipments provided → delegates to build_india_map.
    Otherwise builds a focused single-route map.
    """
    if show_all or (all_shipments and len(all_shipments) > 1):
        return build_india_map(
            shipments=all_shipments or [],
            height=height,
            highlight_tid=highlight_tid,
        )

    # ── Single shipment focused map ────────────────────────────────────────────
    if not route_coords:
        centre_lat, centre_lon = (current_lat or 22.0), (current_lon or 79.0)
    else:
        centre_lat = sum(r["lat"] for r in route_coords) / len(route_coords)
        centre_lon = sum(r["lon"] for r in route_coords) / len(route_coords)

    route_js = json.dumps([[r["lat"], r["lon"]] for r in route_coords])
    cities_js= json.dumps([{"name": r.get("city",""), "lat": r["lat"], "lon": r["lon"]}
                           for r in route_coords])
    cur_lat  = current_lat or (route_coords[-1]["lat"] if route_coords else 20)
    cur_lon  = current_lon or (route_coords[-1]["lon"] if route_coords else 78)

    return f"""<!DOCTYPE html><html><head>
<meta charset="utf-8">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  *{{margin:0;padding:0;box-sizing:border-box;}}
  #map{{width:100%;height:{height}px;}}
</style>
</head><body>
<div id="map"></div>
<script>
const map = L.map('map',{{center:[{centre_lat},{centre_lon}],zoom:6}});
const tl = L.tileLayer(
  'https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{{z}}/{{x}}/{{y}}{{r}}.png',
  {{attribution:'©Stadia Maps ©OpenStreetMap', maxZoom:20}}
);
tl.on('tileerror', function(){{
  L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_matter/{{z}}/{{x}}/{{y}}.png',
    {{attribution:'©CartoDB',subdomains:'abcd',maxZoom:19}}).addTo(map);
}});
tl.addTo(map);

const route={route_js};
const cities={cities_js};
if(route.length>1)
  L.polyline(route,{{color:'#00D1FF',weight:3,opacity:0.7}}).addTo(map);

cities.forEach((c,i)=>{{
  const icon=L.divIcon({{className:'',
    html:`<div style="width:10px;height:10px;background:${{i===0?'#22C55E':i===cities.length-1?'#F59E0B':'#625DF5'}};
          border-radius:50%;border:2px solid #fff;"></div>`,iconAnchor:[5,5]}});
  L.marker([c.lat,c.lon],{{icon}}).bindTooltip(c.name,{{permanent:false}}).addTo(map);
}});

const truckIcon=L.divIcon({{className:'',
  html:`<div style="font-size:22px;filter:drop-shadow(0 0 6px #00D1FF);">🚚</div>`,
  iconAnchor:[11,11]}});
L.marker([{cur_lat},{cur_lon}],{{icon:truckIcon}})
  .bindPopup('<b>Current Position</b>')
  .addTo(map);
</script></body></html>"""
