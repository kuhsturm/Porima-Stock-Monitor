"""
Porima3D Filament Stok Takip - Modern GUI
==========================================
Şık ve modern arayüzlü stok takip uygulaması

Gereksinimler:
    pip install customtkinter pillow requests
"""

import customtkinter as ctk
from tkinter import messagebox
import threading
import requests
import json
import time
from datetime import datetime
import os
import sys

# Windows için encoding düzeltmesi
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Bildirim için
try:
    from plyer import notification
    NOTIFICATIONS_ENABLED = True
except ImportError:
    NOTIFICATIONS_ENABLED = False

# Ses için
try:
    import winsound
    SOUND_ENABLED = True
except ImportError:
    SOUND_ENABLED = False


# CustomTkinter tema ayarları
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class StockMonitorAPI:
    """Porima3D Stok API İşlemleri"""
    
    BASE_URL = "https://porima3d.com"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
        })
        self.previous_stock = {}
        self.data_file = "stock_data.json"
        self.load_previous_stock()
    
    def load_previous_stock(self):
        """Önceki stok verilerini yükle"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    self.previous_stock = json.load(f)
            except:
                self.previous_stock = {}
    
    def save_stock_data(self, data):
        """Stok verilerini kaydet"""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except:
            pass
    
    def fetch_products(self):
        """Tüm ürünleri çek"""
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
        """Filamentleri filtrele"""
        keywords = ['filament', 'pla', 'abs', 'petg', 'tpu', 'asa', 'flex', 'nylon', 'pa', 'silk', 'rainbow']
        
        filaments = []
        for product in products:
            title = product.get('title', '').lower()
            product_type = product.get('product_type', '').lower()
            
            if any(kw in title or kw in product_type for kw in keywords):
                filaments.append(product)
                
        return filaments
    
    def get_stock_data(self, products):
        """Stok verilerini hazırla"""
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
        """Stok değişikliklerini kontrol et"""
        newly_available = []
        newly_out = []
        
        current_map = {f"{d['product_id']}_{d['variant_id']}": d for d in current_data}
        
        for key, current in current_map.items():
            if key in self.previous_stock:
                prev = self.previous_stock[key]
                if current['available'] and not prev.get('available', False):
                    newly_available.append(current)
                elif not current['available'] and prev.get('available', True):
                    newly_out.append(current)
        
        # Önceki stoku güncelle
        self.previous_stock = current_map
        self.save_stock_data(current_map)
        
        return newly_available, newly_out


class ProductCard(ctk.CTkFrame):
    """Ürün kartı widget'ı"""
    
    def __init__(self, master, product_data, **kwargs):
        super().__init__(master, **kwargs)
        
        self.configure(
            corner_radius=12,
            fg_color=("#e8e8e8", "#2b2b2b"),
            border_width=1,
            border_color=("#d0d0d0", "#3d3d3d")
        )
        
        # Stok durumuna göre renk
        if product_data['available']:
            status_color = "#22c55e"  # Yeşil
            status_text = "STOKTA"
        else:
            status_color = "#ef4444"  # Kırmızı
            status_text = "STOKSUZ"
        
        # Ana container
        self.grid_columnconfigure(1, weight=1)
        
        # Stok göstergesi
        indicator = ctk.CTkFrame(self, width=6, corner_radius=3, fg_color=status_color)
        indicator.grid(row=0, column=0, rowspan=2, sticky="ns", padx=(8, 8), pady=8)
        
        # Ürün adı
        name_label = ctk.CTkLabel(
            self,
            text=product_data['product'],
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        )
        name_label.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=(10, 0))
        
        # Varyant ve fiyat
        variant_text = f"{product_data['variant']} • {product_data['price']:.2f} TL"
        variant_label = ctk.CTkLabel(
            self,
            text=variant_text,
            font=ctk.CTkFont(size=12),
            text_color=("#666666", "#a0a0a0"),
            anchor="w"
        )
        variant_label.grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=(0, 10))
        
        # Stok durumu badge
        status_badge = ctk.CTkLabel(
            self,
            text=status_text,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="white",
            fg_color=status_color,
            corner_radius=6,
            width=70,
            height=24
        )
        status_badge.grid(row=0, column=2, rowspan=2, padx=10, pady=10)


class ChangeLogEntry(ctk.CTkFrame):
    """Değişiklik log girişi widget'ı"""
    
    def __init__(self, master, change_data, **kwargs):
        super().__init__(master, **kwargs)
        
        self.configure(
            corner_radius=8,
            fg_color=("#e8f5e9", "#1b3d1f") if change_data['type'] == 'in' else ("#ffebee", "#3d1b1b"),
            border_width=1,
            border_color=("#a5d6a7", "#2e5930") if change_data['type'] == 'in' else ("#ef9a9a", "#592323")
        )
        
        self.grid_columnconfigure(1, weight=1)
        
        # İkon
        icon = "✅" if change_data['type'] == 'in' else "❌"
        icon_label = ctk.CTkLabel(
            self,
            text=icon,
            font=ctk.CTkFont(size=18),
            width=30
        )
        icon_label.grid(row=0, column=0, rowspan=2, padx=(10, 5), pady=8)
        
        # Ürün bilgisi
        product_label = ctk.CTkLabel(
            self,
            text=change_data['product'],
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w"
        )
        product_label.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=(8, 0))
        
        # Varyant ve zaman
        info_text = f"{change_data['variant']} • {change_data['time']}"
        info_label = ctk.CTkLabel(
            self,
            text=info_text,
            font=ctk.CTkFont(size=11),
            text_color=("#555", "#aaa"),
            anchor="w"
        )
        info_label.grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=(0, 8))
        
        # Durum metni
        status_text = "Stoğa Girdi" if change_data['type'] == 'in' else "Stoktan Çıktı"
        status_color = "#16a34a" if change_data['type'] == 'in' else "#dc2626"
        status_label = ctk.CTkLabel(
            self,
            text=status_text,
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=status_color
        )
        status_label.grid(row=0, column=2, rowspan=2, padx=10, pady=8)


class PorimaStockMonitorApp(ctk.CTk):
    """Ana Uygulama Penceresi"""
    
    def __init__(self):
        super().__init__()
        
        # Pencere ayarları
        self.title("🧵 Porima3D Stok Takip")
        self.geometry("1400x800")
        self.minsize(1100, 650)
        
        # API
        self.api = StockMonitorAPI()
        
        # Veriler
        self.all_products = []
        self.filtered_products = []
        self.change_log = []  # Değişiklik geçmişi
        self.is_monitoring = False
        self.monitor_thread = None
        self.check_interval = 300  # 5 dakika
        
        # UI oluştur
        self.create_ui()
        
        # İlk veriyi yükle
        self.after(500, self.initial_load)
    
    def create_ui(self):
        """Arayüzü oluştur"""
        
        # Ana grid yapılandırması
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # ===== SOL PANEL (Kontroller) =====
        self.create_sidebar()
        
        # ===== ÜST BAR =====
        self.create_topbar()
        
        # ===== ANA İÇERİK =====
        self.create_main_content()
        
        # ===== ALT BAR (Durum) =====
        self.create_statusbar()
    
    def create_sidebar(self):
        """Sol panel"""
        sidebar = ctk.CTkFrame(self, width=280, corner_radius=0, fg_color=("#f0f0f0", "#1a1a1a"))
        sidebar.grid(row=0, column=0, rowspan=3, sticky="nsew")
        sidebar.grid_propagate(False)
        
        # Logo/Başlık
        logo_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        logo_frame.pack(fill="x", padx=20, pady=(25, 20))
        
        title = ctk.CTkLabel(
            logo_frame,
            text="🧵 Porima3D",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title.pack(anchor="w")
        
        subtitle = ctk.CTkLabel(
            logo_frame,
            text="Filament Stok Takip",
            font=ctk.CTkFont(size=14),
            text_color=("#666", "#888")
        )
        subtitle.pack(anchor="w")
        
        # Ayırıcı
        ctk.CTkFrame(sidebar, height=2, fg_color=("#d0d0d0", "#333")).pack(fill="x", padx=20, pady=10)
        
        # ===== İSTATİSTİKLER =====
        stats_label = ctk.CTkLabel(
            sidebar,
            text="📊 İstatistikler",
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w"
        )
        stats_label.pack(fill="x", padx=20, pady=(15, 10))
        
        # Stok sayıları
        stats_frame = ctk.CTkFrame(sidebar, fg_color=("#e0e0e0", "#252525"), corner_radius=10)
        stats_frame.pack(fill="x", padx=20, pady=5)
        
        self.in_stock_label = ctk.CTkLabel(
            stats_frame,
            text="✅ Stokta: --",
            font=ctk.CTkFont(size=14),
            anchor="w"
        )
        self.in_stock_label.pack(fill="x", padx=15, pady=(12, 4))
        
        self.out_stock_label = ctk.CTkLabel(
            stats_frame,
            text="❌ Stoksuz: --",
            font=ctk.CTkFont(size=14),
            anchor="w"
        )
        self.out_stock_label.pack(fill="x", padx=15, pady=(4, 4))
        
        self.total_label = ctk.CTkLabel(
            stats_frame,
            text="📦 Toplam: --",
            font=ctk.CTkFont(size=14),
            anchor="w"
        )
        self.total_label.pack(fill="x", padx=15, pady=(4, 12))
        
        # ===== KONTROLLER =====
        controls_label = ctk.CTkLabel(
            sidebar,
            text="⚙️ Kontroller",
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w"
        )
        controls_label.pack(fill="x", padx=20, pady=(25, 10))
        
        # Kontrol aralığı
        interval_frame = ctk.CTkFrame(sidebar, fg_color="transparent")
        interval_frame.pack(fill="x", padx=20, pady=5)
        
        ctk.CTkLabel(
            interval_frame,
            text="Kontrol Aralığı:",
            font=ctk.CTkFont(size=13)
        ).pack(anchor="w")
        
        self.interval_var = ctk.StringVar(value="5 dakika")
        interval_menu = ctk.CTkOptionMenu(
            interval_frame,
            values=["1 dakika", "2 dakika", "5 dakika", "10 dakika", "30 dakika"],
            variable=self.interval_var,
            command=self.on_interval_change,
            width=200
        )
        interval_menu.pack(fill="x", pady=(5, 0))
        
        # Yenile butonu
        self.refresh_btn = ctk.CTkButton(
            sidebar,
            text="🔄 Şimdi Kontrol Et",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=45,
            command=self.refresh_data
        )
        self.refresh_btn.pack(fill="x", padx=20, pady=(20, 10))
        
        # Otomatik takip butonu
        self.monitor_btn = ctk.CTkButton(
            sidebar,
            text="▶️ Otomatik Takip Başlat",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=45,
            fg_color=("#22c55e", "#16a34a"),
            hover_color=("#16a34a", "#15803d"),
            command=self.toggle_monitoring
        )
        self.monitor_btn.pack(fill="x", padx=20, pady=5)
        
        # Ayırıcı
        ctk.CTkFrame(sidebar, height=2, fg_color=("#d0d0d0", "#333")).pack(fill="x", padx=20, pady=20)
        
        # Bildirim ayarları
        notif_label = ctk.CTkLabel(
            sidebar,
            text="🔔 Bildirimler",
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w"
        )
        notif_label.pack(fill="x", padx=20, pady=(5, 10))
        
        self.notif_sound = ctk.CTkSwitch(
            sidebar,
            text="Sesli Uyarı",
            font=ctk.CTkFont(size=13)
        )
        self.notif_sound.pack(fill="x", padx=20, pady=3)
        if SOUND_ENABLED:
            self.notif_sound.select()
        
        self.notif_desktop = ctk.CTkSwitch(
            sidebar,
            text="Masaüstü Bildirimi",
            font=ctk.CTkFont(size=13)
        )
        self.notif_desktop.pack(fill="x", padx=20, pady=3)
        if NOTIFICATIONS_ENABLED:
            self.notif_desktop.select()
        
        # Alt bilgi
        footer = ctk.CTkLabel(
            sidebar,
            text="v1.0 • porima3d.com",
            font=ctk.CTkFont(size=11),
            text_color=("#999", "#666")
        )
        footer.pack(side="bottom", pady=15)
    
    def create_topbar(self):
        """Üst bar"""
        topbar = ctk.CTkFrame(self, height=70, corner_radius=0, fg_color=("#ffffff", "#1e1e1e"))
        topbar.grid(row=0, column=1, sticky="ew")
        topbar.grid_propagate(False)
        
        # Arama
        search_frame = ctk.CTkFrame(topbar, fg_color="transparent")
        search_frame.pack(side="left", fill="y", padx=20, pady=15)
        
        self.search_entry = ctk.CTkEntry(
            search_frame,
            placeholder_text="🔍 Ürün ara...",
            width=300,
            height=40,
            font=ctk.CTkFont(size=14)
        )
        self.search_entry.pack(side="left", padx=(0, 10))
        self.search_entry.bind("<KeyRelease>", self.on_search)
        
        # Filtreler
        filter_frame = ctk.CTkFrame(topbar, fg_color="transparent")
        filter_frame.pack(side="left", fill="y", pady=15)
        
        self.filter_var = ctk.StringVar(value="Tümü")
        filter_menu = ctk.CTkSegmentedButton(
            filter_frame,
            values=["Tümü", "Stokta", "Stoksuz"],
            variable=self.filter_var,
            command=self.on_filter_change,
            font=ctk.CTkFont(size=13)
        )
        filter_menu.pack(side="left")
        
        # Son güncelleme
        self.last_update_label = ctk.CTkLabel(
            topbar,
            text="Son güncelleme: --",
            font=ctk.CTkFont(size=12),
            text_color=("#666", "#888")
        )
        self.last_update_label.pack(side="right", padx=20)
    
    def create_main_content(self):
        """Ana içerik alanı"""
        content_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=("#f5f5f5", "#121212"))
        content_frame.grid(row=1, column=1, sticky="nsew")
        content_frame.grid_columnconfigure(0, weight=3)  # Ürün listesi
        content_frame.grid_columnconfigure(1, weight=1)  # Değişiklik paneli
        content_frame.grid_rowconfigure(0, weight=1)
        
        # ===== SOL: Ürün Listesi =====
        product_frame = ctk.CTkFrame(content_frame, corner_radius=0, fg_color="transparent")
        product_frame.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        product_frame.grid_columnconfigure(0, weight=1)
        product_frame.grid_rowconfigure(0, weight=1)
        
        self.product_list = ctk.CTkScrollableFrame(
            product_frame,
            corner_radius=10,
            fg_color=("#ffffff", "#1e1e1e")
        )
        self.product_list.grid(row=0, column=0, sticky="nsew")
        self.product_list.grid_columnconfigure(0, weight=1)
        
        # Yükleniyor mesajı
        self.loading_label = ctk.CTkLabel(
            self.product_list,
            text="⏳ Ürünler yükleniyor...",
            font=ctk.CTkFont(size=16)
        )
        self.loading_label.grid(row=0, column=0, pady=50)
        
        # ===== SAĞ: Değişiklik Geçmişi =====
        history_frame = ctk.CTkFrame(content_frame, corner_radius=10, fg_color=("#ffffff", "#1e1e1e"))
        history_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)
        history_frame.grid_columnconfigure(0, weight=1)
        history_frame.grid_rowconfigure(1, weight=1)
        
        # Başlık
        history_header = ctk.CTkFrame(history_frame, fg_color="transparent")
        history_header.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 10))
        history_header.grid_columnconfigure(0, weight=1)
        
        history_title = ctk.CTkLabel(
            history_header,
            text="📋 Değişiklik Geçmişi",
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w"
        )
        history_title.grid(row=0, column=0, sticky="w")
        
        # Temizle butonu
        clear_btn = ctk.CTkButton(
            history_header,
            text="Temizle",
            font=ctk.CTkFont(size=11),
            width=60,
            height=25,
            fg_color=("#d0d0d0", "#333"),
            hover_color=("#bbb", "#444"),
            text_color=("#333", "#ccc"),
            command=self.clear_change_log
        )
        clear_btn.grid(row=0, column=1, sticky="e")
        
        # Değişiklik listesi
        self.change_list = ctk.CTkScrollableFrame(
            history_frame,
            corner_radius=0,
            fg_color="transparent"
        )
        self.change_list.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.change_list.grid_columnconfigure(0, weight=1)
        
        # Boş mesaj
        self.empty_history_label = ctk.CTkLabel(
            self.change_list,
            text="Henüz değişiklik yok\n\nStok durumu değiştiğinde\nburada görünecek",
            font=ctk.CTkFont(size=12),
            text_color=("#888", "#666"),
            justify="center"
        )
        self.empty_history_label.grid(row=0, column=0, pady=30)
    
    def create_statusbar(self):
        """Alt durum çubuğu"""
        statusbar = ctk.CTkFrame(self, height=35, corner_radius=0, fg_color=("#e0e0e0", "#1a1a1a"))
        statusbar.grid(row=2, column=1, sticky="ew")
        statusbar.grid_propagate(False)
        
        self.status_label = ctk.CTkLabel(
            statusbar,
            text="🟢 Hazır",
            font=ctk.CTkFont(size=12),
            anchor="w"
        )
        self.status_label.pack(side="left", padx=15, pady=5)
        
        self.monitor_status = ctk.CTkLabel(
            statusbar,
            text="",
            font=ctk.CTkFont(size=12),
            anchor="e"
        )
        self.monitor_status.pack(side="right", padx=15, pady=5)
    
    def initial_load(self):
        """İlk yükleme"""
        self.refresh_data()
    
    def refresh_data(self):
        """Verileri yenile"""
        self.status_label.configure(text="⏳ Veriler alınıyor...")
        self.refresh_btn.configure(state="disabled")
        
        # Arka planda veri çek
        thread = threading.Thread(target=self._fetch_data_thread, daemon=True)
        thread.start()
    
    def _fetch_data_thread(self):
        """Veri çekme thread'i"""
        try:
            products = self.api.fetch_products()
            filaments = self.api.filter_filaments(products)
            stock_data = self.api.get_stock_data(filaments)
            
            # Değişiklikleri kontrol et
            newly_available, newly_out = self.api.check_changes(stock_data)
            
            # UI güncelle (ana thread'de)
            self.after(0, lambda: self._update_ui(stock_data, newly_available, newly_out))
            
        except Exception as e:
            self.after(0, lambda: self._show_error(str(e)))
    
    def _update_ui(self, stock_data, newly_available, newly_out=None):
        """UI'ı güncelle"""
        if newly_out is None:
            newly_out = []
            
        self.all_products = stock_data
        self.apply_filters()
        
        # İstatistikleri güncelle
        in_stock = sum(1 for p in stock_data if p['available'])
        out_stock = len(stock_data) - in_stock
        
        self.in_stock_label.configure(text=f"✅ Stokta: {in_stock}")
        self.out_stock_label.configure(text=f"❌ Stoksuz: {out_stock}")
        self.total_label.configure(text=f"📦 Toplam: {len(stock_data)}")
        
        # Son güncelleme
        current_time = datetime.now().strftime('%H:%M:%S')
        self.last_update_label.configure(text=f"Son güncelleme: {current_time}")
        self.status_label.configure(text="🟢 Veriler güncellendi")
        self.refresh_btn.configure(state="normal")
        
        # Değişiklikleri kaydet ve göster
        for item in newly_available:
            self.add_change_log(item, 'in')
            self.send_notification(item)
        
        for item in newly_out:
            self.add_change_log(item, 'out')
    
    def _show_error(self, message):
        """Hata göster"""
        self.status_label.configure(text=f"🔴 Hata: {message}")
        self.refresh_btn.configure(state="normal")
    
    def apply_filters(self):
        """Filtreleri uygula"""
        search_term = self.search_entry.get().lower()
        filter_type = self.filter_var.get()
        
        filtered = []
        for p in self.all_products:
            # Arama filtresi
            if search_term:
                if search_term not in p['product'].lower() and search_term not in p['variant'].lower():
                    continue
            
            # Stok filtresi
            if filter_type == "Stokta" and not p['available']:
                continue
            if filter_type == "Stoksuz" and p['available']:
                continue
            
            filtered.append(p)
        
        self.filtered_products = filtered
        self.render_products()
    
    def render_products(self):
        """Ürünleri göster"""
        # Mevcut widget'ları temizle
        for widget in self.product_list.winfo_children():
            widget.destroy()
        
        if not self.filtered_products:
            empty_label = ctk.CTkLabel(
                self.product_list,
                text="📭 Sonuç bulunamadı",
                font=ctk.CTkFont(size=16)
            )
            empty_label.grid(row=0, column=0, pady=50)
            return
        
        # Ürün kartlarını oluştur
        for i, product in enumerate(self.filtered_products[:200]):  # İlk 200
            card = ProductCard(self.product_list, product)
            card.grid(row=i, column=0, sticky="ew", pady=3, padx=5)
    
    def on_search(self, event=None):
        """Arama değiştiğinde"""
        self.apply_filters()
    
    def on_filter_change(self, value):
        """Filtre değiştiğinde"""
        self.apply_filters()
    
    def on_interval_change(self, value):
        """Kontrol aralığı değiştiğinde"""
        intervals = {
            "1 dakika": 60,
            "2 dakika": 120,
            "5 dakika": 300,
            "10 dakika": 600,
            "30 dakika": 1800
        }
        self.check_interval = intervals.get(value, 300)
    
    def toggle_monitoring(self):
        """Otomatik takibi aç/kapat"""
        if self.is_monitoring:
            self.stop_monitoring()
        else:
            self.start_monitoring()
    
    def start_monitoring(self):
        """Otomatik takibi başlat"""
        self.is_monitoring = True
        self.monitor_btn.configure(
            text="⏹️ Takibi Durdur",
            fg_color=("#ef4444", "#dc2626"),
            hover_color=("#dc2626", "#b91c1c")
        )
        self.monitor_status.configure(text=f"🔴 Otomatik takip aktif ({self.interval_var.get()})")
        
        # Takip thread'ini başlat
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def stop_monitoring(self):
        """Otomatik takibi durdur"""
        self.is_monitoring = False
        self.monitor_btn.configure(
            text="▶️ Otomatik Takip Başlat",
            fg_color=("#22c55e", "#16a34a"),
            hover_color=("#16a34a", "#15803d")
        )
        self.monitor_status.configure(text="")
    
    def _monitor_loop(self):
        """Otomatik takip döngüsü"""
        while self.is_monitoring:
            time.sleep(self.check_interval)
            if self.is_monitoring:
                self.after(0, self.refresh_data)
    
    def add_change_log(self, item, change_type):
        """Değişiklik geçmişine ekle"""
        current_time = datetime.now().strftime('%H:%M:%S')
        
        change_data = {
            'product': item['product'],
            'variant': item['variant'],
            'type': change_type,  # 'in' veya 'out'
            'time': current_time,
            'url': item.get('url', '')
        }
        
        # Listeye ekle (en yenisi en üstte)
        self.change_log.insert(0, change_data)
        
        # Maksimum 50 kayıt tut
        if len(self.change_log) > 50:
            self.change_log = self.change_log[:50]
        
        # UI'ı güncelle
        self.render_change_log()
    
    def render_change_log(self):
        """Değişiklik geçmişini göster"""
        # Mevcut widget'ları temizle
        for widget in self.change_list.winfo_children():
            widget.destroy()
        
        if not self.change_log:
            # Boş mesaj
            self.empty_history_label = ctk.CTkLabel(
                self.change_list,
                text="Henüz değişiklik yok\n\nStok durumu değiştiğinde\nburada görünecek",
                font=ctk.CTkFont(size=12),
                text_color=("#888", "#666"),
                justify="center"
            )
            self.empty_history_label.grid(row=0, column=0, pady=30)
            return
        
        # Değişiklik kartlarını oluştur
        for i, change in enumerate(self.change_log):
            entry = ChangeLogEntry(self.change_list, change)
            entry.grid(row=i, column=0, sticky="ew", pady=3, padx=2)
    
    def clear_change_log(self):
        """Değişiklik geçmişini temizle"""
        self.change_log = []
        self.render_change_log()
    
    def send_notification(self, item):
        """Bildirim gönder"""
        message = f"{item['product']} - {item['variant']} stoğa girdi!"
        
        # Masaüstü bildirimi
        if self.notif_desktop.get() and NOTIFICATIONS_ENABLED:
            try:
                notification.notify(
                    title="🎉 Stokta!",
                    message=message[:256],
                    app_name="Porima Stok Takip",
                    timeout=10
                )
            except:
                pass
        
        # Sesli uyarı
        if self.notif_sound.get() and SOUND_ENABLED:
            try:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except:
                pass


def main():
    """Ana fonksiyon"""
    app = PorimaStockMonitorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
