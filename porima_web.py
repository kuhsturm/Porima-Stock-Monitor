"""
Porima3D Stok Takip - Web Arayüzü
=================================
Flask + WebSocket tabanlı modern web arayüzü

Çalıştırmak için:
    python porima_web.py

Tarayıcıda açın:
    http://localhost:5000
"""

from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit
import requests
import json
import time
from datetime import datetime
import os
import threading
import sys
import io

# Windows konsol encoding düzeltmesi
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

app = Flask(__name__)
app.config['SECRET_KEY'] = 'porima-stock-monitor-secret'
socketio = SocketIO(app, cors_allowed_origins="*")


class StockMonitorAPI:
    """Porima3D Stok API İşlemleri"""
    
    BASE_URL = "https://porima3d.com"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Cache-Control': 'max-age=0',
        })
        self.previous_stock = {}
        self.data_file = "stock_data.json"
        self.load_previous_stock()
    
    def load_previous_stock(self):
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    self.previous_stock = json.load(f)
            except:
                self.previous_stock = {}
    
    def save_stock_data(self, data):
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except:
            pass
    
    def fetch_products(self):
        all_products = []
        page = 1
        
        while True:
            try:
                url = f"{self.BASE_URL}/products.json?limit=250&page={page}"
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                
                data = response.json()
                products = data.get('products', [])
                
                if not products:
                    break
                    
                all_products.extend(products)
                page += 1
                time.sleep(0.3)
                
            except Exception as e:
                print(f"Hata: {e}")
                break
                
        return all_products
    
    def filter_filaments(self, products):
        keywords = ['filament', 'pla', 'abs', 'petg', 'tpu', 'asa', 'flex', 'nylon', 'pa', 'silk', 'rainbow']
        
        filaments = []
        for product in products:
            title = product.get('title', '').lower()
            product_type = product.get('product_type', '').lower()
            
            if any(kw in title or kw in product_type for kw in keywords):
                filaments.append(product)
                
        return filaments
    
    def get_stock_data(self, products):
        stock_data = []
        
        for product in products:
            product_id = str(product.get('id'))
            title = product.get('title', '')
            handle = product.get('handle', '')
            url = f"{self.BASE_URL}/products/{handle}"
            
            for variant in product.get('variants', []):
                variant_title = variant.get('title', 'Varsayılan')
                available = variant.get('available', False)
                price = variant.get('price', '0')
                variant_id = str(variant.get('id'))
                
                stock_data.append({
                    'product_id': product_id,
                    'variant_id': variant_id,
                    'product': title,
                    'variant': variant_title,
                    'available': available,
                    'price': float(price) if price else 0,
                    'url': url,
                })
        
        return stock_data
    
    def check_changes(self, current_data):
        newly_available = []
        newly_out = []
        price_increased = []  # Zam yapılan ürünler
        price_decreased = []  # İndirim yapılan ürünler
        
        current_map = {f"{d['product_id']}_{d['variant_id']}": d for d in current_data}
        
        for key, current in current_map.items():
            if key in self.previous_stock:
                prev = self.previous_stock[key]
                
                # Stok değişiklikleri
                if current['available'] and not prev.get('available', False):
                    newly_available.append(current)
                elif not current['available'] and prev.get('available', True):
                    newly_out.append(current)
                
                # Fiyat değişiklikleri (minimum 0.01 TL fark)
                prev_price = prev.get('price', 0)
                curr_price = current.get('price', 0)
                
                if curr_price > prev_price + 0.01:  # Zam
                    current['old_price'] = prev_price
                    current['price_change'] = curr_price - prev_price
                    current['price_change_percent'] = ((curr_price - prev_price) / prev_price * 100) if prev_price > 0 else 0
                    price_increased.append(current)
                elif curr_price < prev_price - 0.01:  # İndirim
                    current['old_price'] = prev_price
                    current['price_change'] = prev_price - curr_price
                    current['price_change_percent'] = ((prev_price - curr_price) / prev_price * 100) if prev_price > 0 else 0
                    price_decreased.append(current)
        
        self.previous_stock = current_map
        self.save_stock_data(current_map)
        
        return newly_available, newly_out, price_increased, price_decreased


# Global değişkenler
api = StockMonitorAPI()
stock_data = []
change_log = []
is_monitoring = False
monitor_thread = None
check_interval = 300


def add_change_log(item, change_type):
    """Değişiklik geçmişine ekle"""
    global change_log
    
    entry = {
        'product': item['product'],
        'variant': item['variant'],
        'type': change_type,  # 'in', 'out', 'price_up', 'price_down'
        'time': datetime.now().strftime('%H:%M:%S'),
        'url': item.get('url', ''),
        'price': item.get('price', 0),
        'old_price': item.get('old_price', 0),
        'price_change': item.get('price_change', 0),
        'price_change_percent': item.get('price_change_percent', 0)
    }
    
    change_log.insert(0, entry)
    
    if len(change_log) > 50:
        change_log = change_log[:50]
    
    return entry


def refresh_stock():
    """Stok verilerini yenile"""
    global stock_data, change_log
    
    products = api.fetch_products()
    filaments = api.filter_filaments(products)
    stock_data = api.get_stock_data(filaments)
    
    newly_available, newly_out, price_increased, price_decreased = api.check_changes(stock_data)
    
    new_changes = []
    
    # Stok değişiklikleri
    for item in newly_available:
        entry = add_change_log(item, 'in')
        new_changes.append(entry)
    
    for item in newly_out:
        entry = add_change_log(item, 'out')
        new_changes.append(entry)
    
    # Fiyat değişiklikleri
    for item in price_increased:
        entry = add_change_log(item, 'price_up')
        new_changes.append(entry)
    
    for item in price_decreased:
        entry = add_change_log(item, 'price_down')
        new_changes.append(entry)
    
    return stock_data, new_changes


def monitor_loop():
    """Otomatik takip döngüsü"""
    global is_monitoring
    
    while is_monitoring:
        time.sleep(check_interval)
        if is_monitoring:
            try:
                data, changes = refresh_stock()
                
                # WebSocket ile tüm istemcilere güncelleme gönder
                socketio.emit('stock_update', {
                    'stock_data': data,
                    'changes': changes,
                    'stats': get_stats(data),
                    'time': datetime.now().strftime('%H:%M:%S')
                })
                
            except Exception as e:
                print(f"Monitor error: {e}")


def get_stats(data):
    """İstatistikleri hesapla"""
    in_stock = sum(1 for p in data if p['available'])
    out_stock = len(data) - in_stock
    return {
        'in_stock': in_stock,
        'out_stock': out_stock,
        'total': len(data)
    }


# Flask Routes
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/stock')
def get_stock():
    global stock_data
    
    if not stock_data:
        stock_data, _ = refresh_stock()
    
    return jsonify({
        'stock_data': stock_data,
        'stats': get_stats(stock_data),
        'change_log': change_log,
        'time': datetime.now().strftime('%H:%M:%S')
    })


@app.route('/api/refresh')
def api_refresh():
    data, changes = refresh_stock()
    
    return jsonify({
        'stock_data': data,
        'stats': get_stats(data),
        'changes': changes,
        'change_log': change_log,
        'time': datetime.now().strftime('%H:%M:%S')
    })


# WebSocket Events
@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('connected', {'status': 'ok'})


@socketio.on('start_monitoring')
def handle_start_monitoring(data):
    global is_monitoring, monitor_thread, check_interval
    
    check_interval = data.get('interval', 300)
    
    if not is_monitoring:
        is_monitoring = True
        monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        monitor_thread.start()
    
    emit('monitoring_status', {'active': True, 'interval': check_interval})


@socketio.on('stop_monitoring')
def handle_stop_monitoring():
    global is_monitoring
    
    is_monitoring = False
    emit('monitoring_status', {'active': False})


@socketio.on('clear_log')
def handle_clear_log():
    global change_log
    change_log = []
    emit('log_cleared', {'status': 'ok'})


@socketio.on('test_change')
def handle_test_change():
    """Test için sahte stok/fiyat değişikliği oluştur"""
    global change_log
    import random
    
    test_products = [
        ("Porima PLA Filament", "Beyaz / 1.75mm / 1kg", 636.00),
        ("Porima PETG Filament", "Siyah / 1.75mm / 1kg", 708.00),
        ("Porima Silk PLA", "Altın / 1.75mm / 1kg", 696.00),
        ("Porima ABS Filament", "Gri / 1.75mm / 1kg", 588.00),
        ("Porima Eco PLA", "Kırmızı / 1.75mm / 1kg", 576.00),
    ]
    
    product, variant, base_price = random.choice(test_products)
    change_type = random.choice(['in', 'out', 'price_up', 'price_down'])
    
    test_item = {
        'product': product,
        'variant': variant,
        'url': 'https://porima3d.com/products/test',
        'price': base_price
    }
    
    # Fiyat değişikliği için eski/yeni fiyat ekle
    if change_type == 'price_up':
        price_change = random.uniform(20, 100)
        test_item['old_price'] = base_price
        test_item['price'] = base_price + price_change
        test_item['price_change'] = price_change
        test_item['price_change_percent'] = (price_change / base_price) * 100
        message = f"TEST: {product} - ZAM! {base_price:.2f} TL → {test_item['price']:.2f} TL (+{price_change:.2f} TL)"
    elif change_type == 'price_down':
        price_change = random.uniform(20, 100)
        test_item['old_price'] = base_price
        test_item['price'] = base_price - price_change
        test_item['price_change'] = price_change
        test_item['price_change_percent'] = (price_change / base_price) * 100
        message = f"TEST: {product} - İNDİRİM! {base_price:.2f} TL → {test_item['price']:.2f} TL (-{price_change:.2f} TL)"
    else:
        message = f"TEST: {product} - {variant} {'stoğa girdi' if change_type == 'in' else 'stoktan çıktı'}!"
    
    entry = add_change_log(test_item, change_type)
    
    # Tüm istemcilere bildir
    socketio.emit('test_change_result', {
        'change': entry,
        'message': message
    })
    
    print(f"[TEST] {entry['time']} - {message}")


if __name__ == '__main__':
    # Templates klasörünü oluştur
    os.makedirs('templates', exist_ok=True)
    
    print("\n" + "="*50)
    print("🚀 Porima3D Stok Takip - Web Arayüzü")
    print("="*50)
    print("📡 Sunucu başlatılıyor...")
    print("🌐 Tarayıcıda açın: http://localhost:5000")
    print("⌨️  Durdurmak için Ctrl+C basın")
    print("="*50 + "\n")
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
