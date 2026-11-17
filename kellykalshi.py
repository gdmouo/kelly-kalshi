import requests
import datetime
import base64
from cryptography.hazmat.primitives import serialization, hashes
import tkinter as tk
import threading
from tkinter import ttk, messagebox
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.backends import default_backend
from urllib.parse import urlparse

DEMO_URL = 'https://external-api.demo.kalshi.co/trade-api/v2'

PRODUCTION_URL = 'https://external-api.kalshi.com/trade-api/v2'

KALSHI_FEES = 0.02

class KalshiAPI:
    def __init__(self, key_id, private_key_path, environment):
        if not key_id or not private_key_path:
            messagebox.showinfo(
                "API credentials needed",
                "Enter your Kalshi API Key ID and private key."
            )
            return

        self.key_id = key_id
        self.private_key = self.load_private_key(private_key_path)

        if environment == "Demo":
            self.base_url = DEMO_URL
        else:
            self.base_url = PRODUCTION_URL

    def load_private_key(self, key_path):
        try:
            with open(key_path, "rb") as f:
                return serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())
        except Exception as error:
            messagebox.showerror(
                "Connection failed",
                f"{type(error).__name__}: {error}"
            )

    def create_signature(self, private_key, timestamp, method, path):
            """Create the request signature with the key's algorithm."""
            # Strip query parameters before signing
            path_without_query = path.split('?')[0]
            message = f"{timestamp}{method}{path_without_query}".encode('utf-8')
            if isinstance(private_key, Ed25519PrivateKey):
                signature = private_key.sign(message)
            else:
                signature = private_key.sign(
                    message,
                    padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                    hashes.SHA256()
                )
            return base64.b64encode(signature).decode('utf-8')
    
    def get(self, path):
        if not self.key_id or not self.private_key:
            messagebox.showinfo(
                "API credentials needed",
                "Enter your Kalshi API Key ID and private key."
            )
            return
        
        timestamp = str(int(datetime.datetime.now().timestamp() * 1000))
        # Signing requires the full URL path from root (e.g. /trade-api/v2/portfolio/balance)
        sign_path = urlparse(self.base_url + path).path
        signature = self.create_signature(self.private_key, timestamp, "GET", sign_path)

        headers = {
            'KALSHI-ACCESS-KEY': self.key_id,
            'KALSHI-ACCESS-SIGNATURE': signature,
            'KALSHI-ACCESS-TIMESTAMP': timestamp
        }

        return requests.get(self.base_url + path, headers=headers)

    def markets(self, ticker):
        markets_url = f"{self.base_url}/markets?series_ticker={ticker}&status=open"
        print(f"{markets_url}")
        markets_response = requests.get(markets_url)
        markets_data = markets_response.json()

        return markets_data

def market_price_cents(market, side):
    side = side.lower()
    # Prefer newer dollar-denominated fields if present.
    dollar_key = f"{side}_ask_dollars"
    cent_key = f"{side}_ask"
    if market.get(dollar_key) not in (None, ""):
        return float(market[dollar_key]) * 100
    value = market.get(cent_key)
    if value not in (None, ""):
        return float(value)
    # Fallback for older market payloads.
    last = market.get(f"last_price")
    if last not in (None, ""):
        return float(last)
    return None

class KellyKalshiApp:
    def __init__(self, root):
        self.root = root
        self.root.title("KellyKalshi")
        self.root.geometry("760x720")
        self.root.minsize(680, 800)
        self.api = None
        self.markets_by_label = {}
        self.selected_market = None
        self.selected_contract_price = 0
        self.balance = 0
        self.decimal_odds = 0
        self.build_ui()


    def build_ui(self):
        self.outer = ttk.Frame(self.root, padding=14)
        self.outer.pack(fill="both", expand=True)

        self.build_auth()
        self.build_search()
        self.build_market_view()
        self.build_account_view()
        self.build_kelly_calculator()

        #self.market_combo.bind("<<ComboboxSelected>>", self.on_market_selected)

    def build_auth(self):
        auth = ttk.LabelFrame(self.outer, text="Kalshi API connection", padding=10)
        auth.pack(fill="x", pady=5)

        row = ttk.Frame(auth)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text="Environment:", width=14).pack(side="left")
        self.environment = tk.StringVar(value="Production")
        ttk.Combobox(
            row, textvariable=self.environment, values=["Production","Demo"],
            state="readonly", width=15
        ).pack(side="left")

        row = ttk.Frame(auth)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text="API Key ID:", width=14).pack(side="left")
        self.key_entry = ttk.Entry(row)
        self.key_entry.pack(side="left", fill="x", expand=True)
        self.key_entry.insert(0, 'str-str-str-str-str')

        row = ttk.Frame(auth)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text="PEM Path:", width=14).pack(side="left")
        self.private_key_path_entry = ttk.Entry(row)
        self.private_key_path_entry.pack(side="left", fill="x", expand=True)
        self.private_key_path_entry.insert(0, '.../_.pem')

        row = ttk.Frame(auth)
        row.pack(fill="x", pady=(6, 2))
        ttk.Button(row, text="Connect", command=self.connect).pack(
            side="left"
        )

        self.api_connection_label = ttk.Label(row, text="Not connected")
        self.api_connection_label.pack(side="left", padx=12)

    def build_search(self):
        market_frame = ttk.LabelFrame(self.outer, text="Select contract", padding=10)
        market_frame.pack(fill="x", pady=7)
        row = ttk.Frame(market_frame)
        row.pack(fill="x")
        ttk.Label(row, text="Search series ticker:").pack(side="left")
        self.series_ticker_entry = ttk.Entry(row)
        self.series_ticker_entry.pack(side="left", fill="x", expand=True, padx=7)
        ttk.Button(row, text="Load markets", command=self.load_markets).pack(
            side="left"
        )
        self.series_ticker_entry.insert(0, 'KXBTC15M')

        self.market_combo = ttk.Combobox(market_frame, state="readonly")
        self.market_combo.pack(fill="x", pady=7)
        self.market_combo.bind("<<ComboboxSelected>>", self.on_market_selected)

        self.market_connection_label = ttk.Label(row, text="Not connected")
        self.market_connection_label.pack(side="left", padx=12)

    def build_market_view(self):
        market_view_frame = ttk.LabelFrame(self.outer, text="View market data", padding=10)
        market_view_frame.pack(fill="x", pady=10)
        
        row = ttk.Frame(market_view_frame)
        row.pack(fill="x")
        ttk.Label(row, text="Side:").pack(side="left")
        self.side = tk.StringVar(value="yes")
        ttk.Radiobutton(
            row, text="YES", variable=self.side, value="yes",
            command=self.update_market_view
        ).pack(side="left", padx=5)
        ttk.Radiobutton(
            row, text="NO", variable=self.side, value="no",
            command=self.update_market_view
        ).pack(side="left", padx=5)
        self.price_label = ttk.Label(row, text="Contract price: —")
        self.price_label.pack(side="left", padx=18)

        self.decimal_odds_label = ttk.Label(row, text="Decimal odds: —")
        self.decimal_odds_label.pack(side="left", padx=18)

        #ttk.Button(row, text="Refresh", command=self.update_market_view).pack(
        #    side="left"
        #)

    def build_account_view(self):
        account = ttk.LabelFrame(self.outer, text="Account", padding=10)
        account.pack(fill="x", pady=7)

        self.balance_label = ttk.Label(
            account, text="Available balance: —",
            font=("Segoe UI", 14, "bold")
        )
        self.balance_label.pack(anchor="w")

        row = ttk.Frame(account)
        row.pack(fill="x", pady=(6, 2))

        ttk.Button(row, text="Refresh", command=self.refresh).pack(
            side="left"
        )

    def build_kelly_calculator(self):
        kellycalc = ttk.LabelFrame(self.outer, text="Kelly Criterion", padding=10)
        kellycalc.pack(fill="x", pady=9)

        row = ttk.Frame(kellycalc)
        row.pack(fill="x", pady=(6, 2))
        self.wager_label = ttk.Label(
            row, text="Recommended Wager: —",
            font=("Segoe UI", 14, "bold")
        )
        self.wager_label.pack(anchor="w")

        row = ttk.Frame(kellycalc)
        row.pack(fill="x", pady=(6, 2))
        ttk.Label(row, text="Win Estimate (%):", width=14).pack(side="left")
        self.winning_chance_estimate = ttk.Entry(row)
        self.winning_chance_estimate.pack(side="left", fill="x", expand=True)
        self.winning_chance_estimate.insert(0, "70")

        row = ttk.Frame(kellycalc)
        row.pack(fill="x", pady=(6, 2))
        ttk.Button(row, text="Calculate", command=self.calculate).pack(
            side="left"
        )

    def calculate(self):
        kelly_wager = 0

        if not self.api:
            messagebox.showinfo("Not connected", "Connect to Kalshi first.")
            return

        if not self.selected_market:
            messagebox.showinfo("Not connected", "Select market first.")
            return

        try:
            decimal_odds_entry = float(self.decimal_odds)
            win_prob_estimate_entry = float(self.winning_chance_estimate.get())/100
            bankroll_entry = float(self.balance)

            if decimal_odds_entry <= 1:
                raise ValueError("Decimal odds must be greater than 1.")

            if not 0 <= win_prob_estimate_entry <= 1:
                raise ValueError("Winning chance must be between 0 and 100.")

            if bankroll_entry < 0:
                raise ValueError("Bankroll cannot be negative. Loser")
            
            kelly_frac = (((decimal_odds_entry - 1) * win_prob_estimate_entry) - (1 - win_prob_estimate_entry))/ (decimal_odds_entry - 1)
            kelly_wager = kelly_frac * bankroll_entry
            kelly_wager = max(0, kelly_wager - KALSHI_FEES)

            self.wager_label.config(
                text=f"Recommended Wager: ${kelly_wager:.2f}"
            )

        except ValueError as e:
            messagebox.showerror("Invalid input", str(e))
        

    def connect(self):
        key_id = self.key_entry.get().strip()
        private_key_path = self.private_key_path_entry.get().strip()
        environment = self.environment.get()

        self.api_connection_label.config(text="Connecting…")

        threading.Thread(
            target=self._connect_worker, args=(key_id, private_key_path, environment), daemon=True
        ).start()
    
    def _connect_worker(self, key_id, private_key_path, environment):
        self.api = KalshiAPI(
            key_id=key_id,
            private_key_path=private_key_path,
            environment=environment
        )  

        try:
            response = self.api.get("/portfolio/balance")
            self.balance = response.json()['balance'] / 100
            self.balance_label.config(
                text=f"Available balance: ${self.balance:.2f}"
            ) 
            self.root.after(0, lambda: self.on_connected())
        except Exception as error:
            self.root.after(0, lambda err=str(error): self.on_connection_error(err))

    def on_connected(self):
        self.api_connection_label.config(text="Connected")

    def on_connection_error(self, error):
        messagebox.showerror(
            "Connection failed",
            f"{type(error).__name__}: {error}"
        )

    def refresh(self):
        if not self.api:
            messagebox.showinfo("Not connected", "Connect to Kalshi first.")
            return

        try:
            response = self.api.get("/portfolio/balance")
            self.balance = response.json()['balance'] / 100
            self.balance_label.config(
                text=f"Available balance: ${self.balance:.2f}"
            ) 
        except Exception as error:
            self.on_connection_error(str(error))

    def load_markets(self):
        if not self.api:
            messagebox.showinfo("Not connected", "Connect to Kalshi first.")
            return
            
        ticker = self.series_ticker_entry.get().strip()
        markets_data = self.api.markets(ticker)
        self.show_markets(markets_data)

    def show_markets(self, markets_data):
        self.markets_by_label.clear()

        labels = []
        for market in markets_data['markets']:
            title = market['title']
            ticker = market['ticker']
            label = f"{title}  [{ticker}]"
            self.markets_by_label[label] = market
            labels.append(label)

        self.market_combo["values"] = labels
        self.market_connection_label.config(text=f"Loaded {len(labels)} open markets")

        if labels:
            self.market_combo.current(0)
            self.on_market_selected()

    def on_market_selected(self, _event=None):
        label = self.market_combo.get()
        market = self.markets_by_label.get(label)
        if not market:
            return
        self.selected_market = market
        self.update_market_view()
    
    def update_market_view(self):
        if not self.selected_market:
            return
        side = self.side.get()

        price = market_price_cents(self.selected_market, side)

        if price is None or not 0 < price < 100:
            self.price_label.config(text="Contract price: unavailable")
            self.decimal_odds_label.config(text="Decimal odds: —")
        else:
            self.price_label.config(text=f"Contract price: {price:.1f}¢")
            cost = price / 100
            self.decimal_odds = 1 / cost
            self.decimal_odds_label.config(text=f"Decimal odds: {self.decimal_odds:.1f}x")

root = tk.Tk()
app = KellyKalshiApp(root)
root.mainloop()
