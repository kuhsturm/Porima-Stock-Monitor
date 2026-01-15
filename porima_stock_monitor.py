"""
Porima3D Filament Stok Takip Programı
=====================================
Bu program Porima3D web sitesindeki filamentlerin stok durumunu takip eder.
Stokta olmayan ürünler tekrar stoğa girdiğinde bildirim verir.

Kullanım:
    python porima_stock_monitor.py

Gereksinimler:
    pip install requests beautifulsoup4 plyer
"""

import requests
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime
import os
import sys
import io

# Windows konsol encoding düzeltmesi
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Opsiyonel: Masaüstü bildirimi için
try:
    from plyer import notification
    NOTIFICATIONS_ENABLED = True
except ImportError:
    NOTIFICATIONS_ENABLED = False
    print("⚠️  Masaüstü bildirimleri için 'plyer' yükleyin: pip install plyer")

# Opsiyonel: Sesli uyarı için
try:
    import winsound
    SOUND_ENABLED = True
except ImportError:
    SOUND_ENABLED = False


class PorimaStockMonitor:
    """Porima3D Filament Stok Takip Sınıfı"""
    
    BASE_URL = "https://porima3d.com"
    FILAMENT_COLLECTIONS = [
        "/collections/3d-yazici-filament-cesitleri",
    ]
    
    # Shopify JSON endpoint'i
    PRODUCTS_JSON = "/products.json"
    
    def __init__(self, check_interval=300, data_file="stock_data.json"):
        """
        Args:
            check_interval: Kontrol aralığı (saniye), varsayılan 5 dakika
            data_file: Stok verilerinin kaydedileceği dosya
        """
        self.check_interval = check_interval
        self.data_file = data_file
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7',
        })
        self.previous_stock = self.load_stock_data()
        self.watched_products = []  # Takip edilen belirli ürünler
        
    def load_stock_data(self):
        """Önceki stok verilerini yükle"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️  Veri dosyası okunamadı: {e}")
        return {}
    
    def save_stock_data(self, data):
        """Stok verilerini kaydet"""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️  Veri dosyası kaydedilemedi: {e}")
    
    def get_all_products_json(self):
        """Shopify JSON API'den tüm ürünleri çek"""
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
                
                # Rate limiting için bekle
                time.sleep(0.5)
                
            except requests.exceptions.RequestException as e:
                print(f"❌ Ürünler alınamadı (sayfa {page}): {e}")
                break
            except json.JSONDecodeError as e:
                print(f"❌ JSON parse hatası: {e}")
                break
                
        return all_products
    
    def filter_filaments(self, products):
        """Sadece filament ürünlerini filtrele"""
        filament_keywords = [
            'filament', 'pla', 'abs', 'petg', 'tpu', 'asa', 
            'flex', 'nylon', 'pa', 'silk', 'rainbow'
        ]
        
        filaments = []
        for product in products:
            product_type = product.get('product_type', '').lower()
            title = product.get('title', '').lower()
            tags = ' '.join(product.get('tags', [])).lower()
            
            # Filament olup olmadığını kontrol et
            is_filament = any(kw in title or kw in product_type or kw in tags 
                            for kw in filament_keywords)
            
            if is_filament:
                filaments.append(product)
                
        return filaments
    
    def get_stock_status(self, products):
        """
        Ürünlerin stok durumunu analiz et
        
        Returns:
            dict: {product_id: {title, variants: [{variant_id, title, available, price}]}}
        """
        stock_status = {}
        
        for product in products:
            product_id = str(product.get('id'))
            product_title = product.get('title', 'Bilinmeyen Ürün')
            handle = product.get('handle', '')
            product_url = f"{self.BASE_URL}/products/{handle}"
            
            variants = []
            for variant in product.get('variants', []):
                variant_info = {
                    'id': str(variant.get('id')),
                    'title': variant.get('title', 'Varsayılan'),
                    'available': variant.get('available', False),
                    'price': variant.get('price', '0'),
                    'sku': variant.get('sku', ''),
                }
                variants.append(variant_info)
            
            stock_status[product_id] = {
                'title': product_title,
                'url': product_url,
                'handle': handle,
                'variants': variants,
                'last_checked': datetime.now().isoformat(),
            }
            
        return stock_status
    
    def compare_stock(self, current_stock):
        """
        Önceki ve şimdiki stok durumunu karşılaştır
        
        Returns:
            tuple: (newly_available, newly_out_of_stock)
        """
        newly_available = []
        newly_out_of_stock = []
        
        for product_id, current_data in current_stock.items():
            if product_id not in self.previous_stock:
                # Yeni ürün - ilk kez görüldü
                continue
                
            previous_data = self.previous_stock[product_id]
            current_variants = {v['id']: v for v in current_data['variants']}
            previous_variants = {v['id']: v for v in previous_data['variants']}
            
            for variant_id, current_variant in current_variants.items():
                if variant_id not in previous_variants:
                    continue
                    
                previous_variant = previous_variants[variant_id]
                
                # Stok durumu değişti mi?
                if current_variant['available'] and not previous_variant['available']:
                    # Stoksuzdan stoğa geçti
                    newly_available.append({
                        'product': current_data['title'],
                        'variant': current_variant['title'],
                        'url': current_data['url'],
                        'price': current_variant['price'],
                    })
                elif not current_variant['available'] and previous_variant['available']:
                    # Stoktan çıktı
                    newly_out_of_stock.append({
                        'product': current_data['title'],
                        'variant': current_variant['title'],
                        'url': current_data['url'],
                    })
                    
        return newly_available, newly_out_of_stock
    
    def notify(self, title, message):
        """Masaüstü bildirimi gönder"""
        print(f"\n🔔 {title}")
        print(f"   {message}")
        
        if NOTIFICATIONS_ENABLED:
            try:
                notification.notify(
                    title=title,
                    message=message[:256],  # Maksimum karakter sınırı
                    app_name="Porima Stok Takip",
                    timeout=10,
                )
            except Exception as e:
                print(f"⚠️  Bildirim gönderilemedi: {e}")
        
        if SOUND_ENABLED:
            try:
                # Windows sistem sesi çal
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except:
                pass
    
    def print_status_report(self, stock_status):
        """Mevcut stok durumunu ekrana yazdır"""
        out_of_stock_count = 0
        in_stock_count = 0
        
        for product_id, data in stock_status.items():
            for variant in data['variants']:
                if variant['available']:
                    in_stock_count += 1
                else:
                    out_of_stock_count += 1
        
        print(f"\n📊 Stok Özeti:")
        print(f"   ✅ Stokta: {in_stock_count} varyant")
        print(f"   ❌ Stoksuz: {out_of_stock_count} varyant")
        print(f"   📦 Toplam: {len(stock_status)} ürün")
    
    def list_out_of_stock(self, stock_status):
        """Stokta olmayan ürünleri listele"""
        print("\n" + "="*60)
        print("❌ STOKTA OLMAYAN FİLAMENTLER")
        print("="*60)
        
        count = 0
        for product_id, data in stock_status.items():
            out_of_stock_variants = [v for v in data['variants'] if not v['available']]
            
            if out_of_stock_variants:
                print(f"\n🔸 {data['title']}")
                for variant in out_of_stock_variants:
                    print(f"   - {variant['title']}")
                    count += 1
                    
        if count == 0:
            print("\n✅ Tüm filamentler stokta!")
        else:
            print(f"\n📌 Toplam {count} varyant stokta yok.")
        print("="*60)
    
    def list_in_stock(self, stock_status):
        """Stokta olan ürünleri listele"""
        print("\n" + "="*60)
        print("✅ STOKTA OLAN FİLAMENTLER")
        print("="*60)
        
        count = 0
        for product_id, data in stock_status.items():
            in_stock_variants = [v for v in data['variants'] if v['available']]
            
            if in_stock_variants:
                print(f"\n🔹 {data['title']}")
                for variant in in_stock_variants:
                    price_display = f"{float(variant['price']):.2f} TL" if variant['price'] else ""
                    print(f"   - {variant['title']} {price_display}")
                    count += 1
                    
        print(f"\n📌 Toplam {count} varyant stokta.")
        print("="*60)
    
    def watch_product(self, product_name):
        """Belirli bir ürünü takip listesine ekle"""
        self.watched_products.append(product_name.lower())
        print(f"👁️  '{product_name}' takip listesine eklendi.")
    
    def check_once(self):
        """Tek seferlik stok kontrolü yap"""
        print(f"\n⏳ [{datetime.now().strftime('%H:%M:%S')}] Stok kontrol ediliyor...")
        
        # Tüm ürünleri çek
        all_products = self.get_all_products_json()
        
        if not all_products:
            print("❌ Ürünler alınamadı!")
            return None
            
        print(f"   📦 {len(all_products)} ürün bulundu.")
        
        # Filamentleri filtrele
        filaments = self.filter_filaments(all_products)
        print(f"   🧵 {len(filaments)} filament ürünü tespit edildi.")
        
        # Stok durumunu al
        current_stock = self.get_stock_status(filaments)
        
        # Karşılaştır
        newly_available, newly_out_of_stock = self.compare_stock(current_stock)
        
        # Bildirimleri gönder
        for item in newly_available:
            self.notify(
                "🎉 Stokta!",
                f"{item['product']} - {item['variant']} stoğa girdi! {item['price']} TL"
            )
            
        for item in newly_out_of_stock:
            print(f"⚠️  Stoktan çıktı: {item['product']} - {item['variant']}")
        
        # Verileri kaydet
        self.previous_stock = current_stock
        self.save_stock_data(current_stock)
        
        # Durum raporu
        self.print_status_report(current_stock)
        
        return current_stock
    
    def run(self):
        """Sürekli stok takibi başlat"""
        print("\n" + "="*60)
        print("🚀 PORİMA3D FİLAMENT STOK TAKİP PROGRAMI")
        print("="*60)
        print(f"📡 Kontrol aralığı: {self.check_interval} saniye ({self.check_interval/60:.1f} dakika)")
        print(f"💾 Veri dosyası: {self.data_file}")
        print("⌨️  Durdurmak için Ctrl+C basın")
        print("="*60)
        
        try:
            while True:
                stock = self.check_once()
                
                if stock:
                    # İlk çalıştırmada stoksuz ürünleri göster
                    if not self.previous_stock or len(self.previous_stock) == 0:
                        self.list_out_of_stock(stock)
                
                print(f"\n⏰ Sonraki kontrol: {self.check_interval} saniye sonra...")
                time.sleep(self.check_interval)
                
        except KeyboardInterrupt:
            print("\n\n👋 Program durduruldu.")
            print("💾 Stok verileri kaydedildi.")


def main():
    """Ana fonksiyon"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Porima3D Filament Stok Takip Programı',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Kullanım Örnekleri:
  python porima_stock_monitor.py                    # Varsayılan ayarlarla başlat (5 dk aralık)
  python porima_stock_monitor.py -i 60              # 1 dakika aralıkla kontrol et
  python porima_stock_monitor.py --once             # Tek seferlik kontrol yap
  python porima_stock_monitor.py --list-out         # Stoksuz ürünleri listele
  python porima_stock_monitor.py --list-in          # Stoktaki ürünleri listele
        """
    )
    
    parser.add_argument('-i', '--interval', type=int, default=300,
                        help='Kontrol aralığı (saniye), varsayılan: 300 (5 dakika)')
    parser.add_argument('--once', action='store_true',
                        help='Tek seferlik kontrol yap ve çık')
    parser.add_argument('--list-out', action='store_true',
                        help='Stokta olmayan ürünleri listele')
    parser.add_argument('--list-in', action='store_true',
                        help='Stokta olan ürünleri listele')
    parser.add_argument('--data-file', type=str, default='stock_data.json',
                        help='Stok verilerinin kaydedileceği dosya')
    
    args = parser.parse_args()
    
    # Monitor oluştur
    monitor = PorimaStockMonitor(
        check_interval=args.interval,
        data_file=args.data_file
    )
    
    if args.once or args.list_out or args.list_in:
        # Tek seferlik işlemler
        stock = monitor.check_once()
        
        if stock:
            if args.list_out:
                monitor.list_out_of_stock(stock)
            if args.list_in:
                monitor.list_in_stock(stock)
    else:
        # Sürekli takip
        monitor.run()


if __name__ == "__main__":
    main()
