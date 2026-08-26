#!/usr/bin/env python3
"""Extract Yandex Food orders from saverudata 79_XX archives -> SQLite"""
import os, csv, json, tarfile, io, logging, sys, sqlite3

SRC = '/opt/saverudata/archives'
DB_PATH = '/opt/yandex_food/orders.db'
LOG_FILE = '/opt/yandex_food/extract.log'
BATCH_SIZE = 2000

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s',
                    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()])
log = logging.getLogger('extract')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT, name TEXT, created_at TEXT, place_id TEXT,
            city TEXT, street TEXT, house TEXT, office TEXT,
            lat REAL, lon REAL, amount_rub REAL, sum_orders INTEGER,
            floor TEXT, comment TEXT, entrance TEXT, doorcode TEXT,
            place_name TEXT, cdek_name TEXT,
            deliv_name TEXT, deliv_created TEXT, deliv_address TEXT,
            deliv_lat REAL, deliv_long REAL,
            deliv2_name TEXT, deliv2_order_id TEXT, deliv2_created TEXT,
            deliv2_products TEXT, deliv2_vendor TEXT,
            deliv2_lat REAL, deliv2_long REAL,
            deliv2_address TEXT, deliv2_city TEXT, deliv2_price REAL
        )
    ''')
    for col in ['name','city','place_name','lat','lon']:
        c.execute(f'CREATE INDEX IF NOT EXISTS idx_{col} ON orders({col})')
    conn.commit()
    conn.close()

INSERT_SQL = '''
    INSERT OR IGNORE INTO orders(
        phone,name,created_at,place_id,city,street,house,office,
        lat,lon,amount_rub,sum_orders,floor,comment,entrance,doorcode,
        place_name,cdek_name,deliv_name,deliv_created,deliv_address,
        deliv_lat,deliv_long,
        deliv2_name,deliv2_order_id,deliv2_created,deliv2_products,
        deliv2_vendor,deliv2_lat,deliv2_long,deliv2_address,deliv2_city,deliv2_price
    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
'''

def safe_float(v):
    try:
        f = float(v.strip()) if v and v.strip() else None
        return f if (f is None or (-90 < f < 180)) else None
    except: return None

def safe_int(v):
    try: return int(float(v.strip())) if v and v.strip() else None
    except: return None

def g(row, key, default=''):
    v = row.get(key)
    return (v or default).strip()

def make_row(row, header_fields):
    """Build a row tuple from CSV dict, only if it has valid yandex lat/lon/name"""
    lat = safe_float(row.get('yandex_latitude'))
    lon = safe_float(row.get('yandex_longitude'))
    name = g(row, 'yandex_name')
    if lat is None or lon is None or not name:
        return None
    
    return (
        g(row, 'phone_number'), name, g(row, 'yandex_created_at'),
        g(row, 'yandex_place_id'), g(row, 'yandex_address_city'),
        g(row, 'yandex_address_street'), g(row, 'yandex_address_house'),
        g(row, 'yandex_address_office'),
        lat, lon,
        safe_float(row.get('yandex_amount_rub')), safe_int(row.get('yandex_sum_orders')),
        g(row, 'yandex_address_floor'), g(row, 'yandex_address_comment'),
        g(row, 'yandex_address_entrance'), g(row, 'yandex_address_doorcode'),
        g(row, 'yandex_place_name'), g(row, 'cdek_full_name'),
        g(row, 'delivery_name'), g(row, 'delivery_created'),
        g(row, 'delivery_address'), safe_float(row.get('delivery_lat')), safe_float(row.get('delivery_long')),
        g(row, 'delivery2_name'), g(row, 'delivery2_order_id'),
        g(row, 'delivery2_created_at'), g(row, 'delivery2_products'),
        g(row, 'delivery2_vendor_name'), safe_float(row.get('delivery2_latitude')),
        safe_float(row.get('delivery2_longitude')), g(row, 'delivery2_address_full'),
        g(row, 'delivery2_address_city'), safe_float(row.get('delivery2_pricetotal_rub')),
    )

def process_archive(aname, conn):
    apath = os.path.join(SRC, aname)
    if not os.path.exists(apath):
        return 0, 0
    
    total = 0
    valid = 0
    batch = []
    
    try:
        with tarfile.open(apath, 'r:gz') as tar:
            for member in tar.getmembers():
                if not member.name.endswith('.csv'):
                    continue
                f = tar.extractfile(member)
                if not f:
                    continue
                content = f.read().decode('utf-8', errors='replace')
                reader = csv.DictReader(io.StringIO(content))
                for row in reader:
                    total += 1
                    tup = make_row(row, reader.fieldnames or [])
                    if tup is None:
                        continue
                    batch.append(tup)
                    valid += 1
                    
                    if len(batch) >= BATCH_SIZE:
                        conn.executemany(INSERT_SQL, batch)
                        conn.commit()
                        batch = []
        
        if batch:
            conn.executemany(INSERT_SQL, batch)
            conn.commit()
            batch = []
    
    except Exception as e:
        log.error(f'  {aname}: ERROR {e}')
    
    return total, valid

def extract_all():
    log.info('Starting extraction...')
    init_db()
    
    archives = sorted([f for f in os.listdir(SRC)
                      if f.startswith('79_') and f.endswith('.tar.gz')])
    log.info(f'Found {len(archives)} archives')
    
    conn = sqlite3.connect(DB_PATH)
    total_rows = 0
    total_valid = 0
    
    for i, aname in enumerate(archives):
        t, v = process_archive(aname, conn)
        total_rows += t
        total_valid += v
        log.info(f'[{i+1}/{len(archives)}] {aname}: {v} valid / {t} total (total: {total_valid})')
    
    conn.close()
    log.info(f'DONE! Total: {total_valid} valid orders from {total_rows} rows in {len(archives)} archives')
    print(f'\nRESULT: {total_valid} orders extracted')

if __name__ == '__main__':
    extract_all()