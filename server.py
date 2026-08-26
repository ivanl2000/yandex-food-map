#!/usr/bin/env python3
"""Yandex Food map - range queries for all indexed fields"""
import os, json, logging, sqlite3, re
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
log = logging.getLogger('yf')
DB = '/opt/yandex_food/orders.db'
PORT = int(os.environ.get('PORT', 8081))

SEL = "SELECT id,phone,name,created_at as date,city,street,house,place_name,lat,lon,amount_rub FROM orders"

def cap(s):
    """Capitalize first letter, keep rest"""
    if not s: return s
    if s[0].isalpha():
        return s[0].upper() + s[1:]
    return s

def range_query(cursor, field, prefix, limit):
    """Range query: field >= prefix AND field < prefix_next, uses index"""
    if not prefix: return []
    prefix = prefix[:50]
    nxt = prefix[:-1] + chr(ord(prefix[-1]) + 1) if prefix else '~'
    rows = []
    try:
        for r in cursor.execute(
            f"{SEL} WHERE {field} >= ? AND {field} < ? LIMIT ?",
            (prefix, nxt, limit)
        ):
            rows.append(dict(r))
    except Exception as e:
        log.error(f'range {field}={prefix}: {e}')
    return rows

def search(q, limit=200):
    if not q or len(q.strip()) < 2:
        return []
    qs = q.strip().lower()[:50]
    qd = re.sub(r'[^0-9]', '', qs)
    is_phone = len(qd) >= 7 and (len(qd) >= len(qs) * 0.5)
    
    conn = sqlite3.connect(DB, timeout=5)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    rows = []
    seen = set()
    
    def add(rs):
        for r in rs:
            if r['id'] not in seen:
                seen.add(r['id'])
                rows.append(r)
    
    try:
        # Phone range query
        if is_phone or len(qd) >= 3:
            add(range_query(c, 'phone', qd, limit))
            if is_phone or len(rows) >= limit:
                conn.close()
                return rows[:limit]
        
        # Name range: try lowercase, then capitalized
        if len(rows) < limit:
            add(range_query(c, 'name', qs, limit - len(rows)))
        if len(rows) < limit:
            add(range_query(c, 'name', cap(qs), limit - len(rows)))
        
        if len(rows) >= limit:
            conn.close()
            return rows[:limit]
        
        # City range: try lowercase, then capitalized
        add(range_query(c, 'city', qs, limit - len(rows)))
        if len(rows) < limit:
            add(range_query(c, 'city', cap(qs), limit - len(rows)))
        
        if len(rows) >= limit:
            conn.close()
            return rows[:limit]
        
        # Place name
        add(range_query(c, 'place_name', qs, limit - len(rows)))
        if len(rows) < limit:
            add(range_query(c, 'place_name', cap(qs), limit - len(rows)))
    
    except Exception as e:
        log.error(f'search: {e}')
    
    conn.close()
    return rows[:limit]

HTML = b'''<!DOCTYPE html>
<html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Yandex Food Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>
<style>*{margin:0;padding:0;box-sizing:border-box}html,body{height:100%}#map{height:100%}.p{position:fixed;top:10px;right:10px;z-index:1000;background:#fff;padding:10px;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,.2);max-width:260px;font:13px sans-serif}.p h3{color:#e74c3c;margin:0 0 3px}.i{width:100%;padding:5px;border:1px solid #ccc;border-radius:4px;margin-top:5px;font-size:13px}.i:focus{border-color:#e74c3c;outline:0}.st{font-size:11px;color:#999;margin-top:2px;min-height:14px}.rs{display:none;color:#e74c3c;cursor:pointer;font-size:12px;margin-top:2px}
</style></head><body>
<div id="map"></div><div class="p"><h3>Yandex Food</h3><span id="oc">23M</span>
<input class="i" id="s" placeholder="Name, phone, address..." autocomplete="off">
<div class="st" id="ss"></div><div class="rs" id="sr" onclick="rs()">Clear</div></div>
<script>
var m=L.map('map').setView([55.76,37.64],10);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18}).addTo(m);
var cl=L.markerClusterGroup({chunkedLoading:true,maxClusterRadius:50});m.addLayer(cl);
var ri=L.divIcon({className:'',html:'<div style="width:10px;height:10px;background:#e74c3c;border-radius:50%;border:2px solid #fff"></div>',iconSize:[14,14],iconAnchor:[7,7]});
function es(s){return s?s.replace(/&/g,'&amp;').replace(/</g,'&lt;'):''}
function ds(){var q=document.getElementById('s').value.trim();if(!q){rs();return}
document.getElementById('ss').textContent='...';document.getElementById('sr').style.display='block';
fetch('/search?q='+encodeURIComponent(q)).then(function(r){return r.json()}).then(function(d){
var r=(d.results||[]);cl.clearLayers();if(!r.length){document.getElementById('oc').textContent='0';document.getElementById('ss').textContent='0 found';return}
var mk=[];r.forEach(function(o){var la=parseFloat(o.lat),lo=parseFloat(o.lon);if(isNaN(la)||isNaN(lo))return;
var h=(o.name?'<b>'+es(o.name)+'</b><br>':'')+(o.date?es(o.date).slice(0,10)+'<br>':'')+([o.city,o.street,o.house].filter(function(x){return x}).join(', ')?es([o.city,o.street,o.house].filter(function(x){return x}).join(', '))+'<br>':'')+(o.phone?es(o.phone):'');
var mm=L.marker([la,lo],{icon:ri}).bindPopup(h);cl.addLayer(mm);mk.push(mm)});
document.getElementById('oc').textContent=r.length;document.getElementById('ss').textContent='Found '+r.length;
if(mk.length==1){m.setView(mk[0].getLatLng(),15);mk[0].openPopup()}else if(mk.length>1)m.fitBounds(L.featureGroup(mk).getBounds().pad(0.1))}).catch(function(){document.getElementById('ss').textContent='Error'})}
function rs(){document.getElementById('s').value='';document.getElementById('sr').style.display='none';document.getElementById('ss').textContent='';cl.clearLayers();document.getElementById('oc').textContent='23M';m.setView([55.76,37.64],10)}
document.getElementById('s').addEventListener('input',function(){clearTimeout(window._st);window._st=setTimeout(ds,400)});rs();
</script></body></html>
'''

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        try:
            if path == '/search':
                results = search(params.get('q', [''])[0], 200)
                body = json.dumps({'total': len(results), 'results': results}, ensure_ascii=False).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(HTML)))
                self.end_headers()
                self.wfile.write(HTML)
        except Exception as e:
            log.error(f'handler: {e}')
    def log_message(self, fmt, *args):
        log.info(f'{self.client_address[0]} {fmt % args}')

if __name__ == '__main__':
    log.info('Starting on port %d', PORT)
    HTTPServer(('0.0.0.0', PORT), Handler).serve_forever()