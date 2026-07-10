import sqlite3
import datetime
from typing import List, Dict, Optional
from pathlib import Path

DB_PATH = Path(__file__).parent / "scanner.db"


def init_database():
    """Initialize SQLite database with required tables."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Calls table - tracks token scans
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_address TEXT UNIQUE NOT NULL,
            token_name TEXT,
            symbol TEXT,
            initial_price REAL,
            entry_price REAL,
            current_price REAL,
            market_cap REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            called_by TEXT,
            accuracy_pct REAL DEFAULT 0
        )
    ''')
    
    # Holders table - tracks holder distribution
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS holders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_address TEXT NOT NULL,
            holder_address TEXT NOT NULL,
            percentage REAL,
            count REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(token_address, holder_address)
        )
    ''')
    
    # Developer wallets - tracks creator/dev wallets
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS developer_wallets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_address TEXT UNIQUE NOT NULL,
            wallet_name TEXT,
            token_count INTEGER,
            total_value REAL,
            win_rate REAL,
            avg_return REAL,
            discovery_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Alerts table - tracks custom alerts
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            token_address TEXT,
            alert_type TEXT,
            threshold_value REAL,
            is_active BOOLEAN DEFAULT 1,
            created_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Smart money tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS smart_money (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_address TEXT NOT NULL,
            wallet_label TEXT,
            profit_count INTEGER,
            loss_count INTEGER,
            win_rate REAL,
            avg_roi REAL,
            discovery_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Price history - stores periodic price snapshots for tokens
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_address TEXT NOT NULL,
            price REAL NOT NULL,
            market_cap REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Volume history - tracks 24h trading volume
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS volume_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_address TEXT NOT NULL,
            volume_24h REAL NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Liquidity history - tracks LP liquidity
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS liquidity_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_address TEXT NOT NULL,
            liquidity REAL NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Caller stats - tracks caller performance/leaderboard
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS caller_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            caller_id TEXT NOT NULL,
            caller_name TEXT,
            token_address TEXT NOT NULL,
            entry_price REAL,
            current_price REAL,
            call_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            roi_pct REAL,
            profit_loss REAL,
            UNIQUE(caller_id, token_address)
        )
    ''')
    
    # Portfolio wallets - user linked wallets
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS portfolio_wallets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            wallet_address TEXT NOT NULL,
            wallet_label TEXT,
            tracked_since DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, wallet_address)
        )
    ''')
    
    # Watchlists - user custom watch tokens
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS watchlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            token_address TEXT NOT NULL,
            alert_conditions TEXT,
            is_active BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, token_address)
        )
    ''')
    
    # Sniper wallets - early/bundled buyers
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sniper_wallets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_address TEXT NOT NULL,
            wallet_address TEXT NOT NULL,
            buy_timestamp DATETIME,
            amount REAL,
            value_usd REAL,
            is_bundled BOOLEAN DEFAULT 0,
            is_fresh_wallet BOOLEAN DEFAULT 0,
            detected_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()


def add_call(token_address: str, token_name: str, symbol: str, price: float, called_by: str = "Scanner"):
    """Add a new token call to the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO calls (token_address, token_name, symbol, initial_price, entry_price, current_price, called_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (token_address, token_name, symbol, price, price, price, called_by))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def log_price(token_address: str, price: float, market_cap: float = 0.0):
    """Log a price snapshot for a token."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO price_history (token_address, price, market_cap)
            VALUES (?, ?, ?)
        ''', (token_address, price, market_cap))
        conn.commit()
    finally:
        conn.close()


def get_price_changes(token_address: str):
    """Return percent changes for standard windows (1m,5m,1h,24h).

    Returns a dict: {'1m': pct, '5m': pct, '1h': pct, '24h': pct}
    If insufficient history, values may be None.
    """
    from datetime import datetime, timedelta

    windows = {
        '1m': 60,
        '5m': 300,
        '1h': 3600,
        '24h': 86400,
    }

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get latest price
    cursor.execute('''SELECT price, timestamp FROM price_history WHERE token_address = ? ORDER BY timestamp DESC LIMIT 1''', (token_address,))
    latest = cursor.fetchone()
    if not latest:
        conn.close()
        return {k: None for k in windows}

    latest_price = latest[0]
    latest_ts = datetime.fromisoformat(latest[1]) if isinstance(latest[1], str) else datetime.now()

    results = {}
    for label, secs in windows.items():
        target_time = latest_ts - timedelta(seconds=secs)

        # Find the newest price at or before the target_time
        cursor.execute('''
            SELECT price, timestamp FROM price_history
            WHERE token_address = ? AND timestamp <= ?
            ORDER BY timestamp DESC LIMIT 1
        ''', (token_address, target_time.isoformat()))
        row = cursor.fetchone()
        if row:
            old_price = row[0]
            try:
                pct = (latest_price - old_price) / old_price * 100 if old_price != 0 else None
            except Exception:
                pct = None
            results[label] = pct
        else:
            results[label] = None

    conn.close()
    return results


def get_call_history(limit: int = 10) -> List[Dict]:
    """Get recent call history."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM calls ORDER BY timestamp DESC LIMIT ?
    ''', (limit,))
    
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def add_holder(token_address: str, holder_address: str, percentage: float, count: float):
    """Add or update holder information."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO holders (token_address, holder_address, percentage, count)
            VALUES (?, ?, ?, ?)
        ''', (token_address, holder_address, percentage, count))
        conn.commit()
    finally:
        conn.close()


def get_top_holders(token_address: str, limit: int = 10) -> List[Dict]:
    """Get top holders for a token."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM holders 
        WHERE token_address = ? 
        ORDER BY percentage DESC 
        LIMIT ?
    ''', (token_address, limit))
    
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def track_developer_wallet(wallet_address: str, wallet_name: str, token_count: int, total_value: float):
    """Track a developer wallet."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO developer_wallets 
            (wallet_address, wallet_name, token_count, total_value)
            VALUES (?, ?, ?, ?)
        ''', (wallet_address, wallet_name, token_count, total_value))
        conn.commit()
    finally:
        conn.close()


def get_developer_wallets() -> List[Dict]:
    """Get all tracked developer wallets."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM developer_wallets ORDER BY total_value DESC')
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


# ============ CALLER STATS FUNCTIONS ============

def log_caller_stat(caller_id: str, caller_name: str, token_address: str, entry_price: float):
    """Log a caller's token call."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO caller_stats 
            (caller_id, caller_name, token_address, entry_price, current_price)
            VALUES (?, ?, ?, ?, ?)
        ''', (caller_id, caller_name, token_address, entry_price, entry_price))
        conn.commit()
    finally:
        conn.close()


def update_caller_roi(caller_id: str, token_address: str, current_price: float):
    """Update caller's ROI for a token."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        # Get entry price
        cursor.execute('''
            SELECT entry_price FROM caller_stats 
            WHERE caller_id = ? AND token_address = ?
        ''', (caller_id, token_address))
        row = cursor.fetchone()
        
        if row:
            entry_price = row[0]
            roi = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
            
            cursor.execute('''
                UPDATE caller_stats 
                SET current_price = ?, roi_pct = ?
                WHERE caller_id = ? AND token_address = ?
            ''', (current_price, roi, caller_id, token_address))
            conn.commit()
    finally:
        conn.close()


def get_caller_leaderboard(limit: int = 10) -> List[Dict]:
    """Get top callers by average ROI."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT caller_id, caller_name, 
               COUNT(*) as total_calls,
               AVG(roi_pct) as avg_roi,
               SUM(CASE WHEN roi_pct > 0 THEN 1 ELSE 0 END) as wins
        FROM caller_stats
        GROUP BY caller_id
        ORDER BY avg_roi DESC
        LIMIT ?
    ''', (limit,))
    
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def get_caller_stats(caller_id: str) -> Dict:
    """Get detailed stats for a specific caller."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT 
            caller_id, caller_name,
            COUNT(*) as total_calls,
            AVG(roi_pct) as avg_roi,
            SUM(CASE WHEN roi_pct > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN roi_pct <= 0 THEN 1 ELSE 0 END) as losses,
            MAX(roi_pct) as best_roi,
            MIN(roi_pct) as worst_roi
        FROM caller_stats
        WHERE caller_id = ?
        GROUP BY caller_id
    ''', (caller_id,))
    
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}


# ============ VOLUME & LIQUIDITY HISTORY ============

def log_volume(token_address: str, volume_24h: float):
    """Log volume snapshot."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO volume_history (token_address, volume_24h)
            VALUES (?, ?)
        ''', (token_address, volume_24h))
        conn.commit()
    finally:
        conn.close()


def log_liquidity(token_address: str, liquidity: float):
    """Log liquidity snapshot."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO liquidity_history (token_address, liquidity)
            VALUES (?, ?)
        ''', (token_address, liquidity))
        conn.commit()
    finally:
        conn.close()


def get_price_volume_history(token_address: str, hours: int = 24) -> List[Dict]:
    """Get price and volume history for charting."""
    from datetime import datetime, timedelta
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cutoff = datetime.now() - timedelta(hours=hours)
    
    cursor.execute('''
        SELECT 
            p.timestamp, p.price, p.market_cap,
            v.volume_24h, l.liquidity
        FROM price_history p
        LEFT JOIN volume_history v ON p.token_address = v.token_address 
            AND DATE(p.timestamp) = DATE(v.timestamp)
        LEFT JOIN liquidity_history l ON p.token_address = l.token_address 
            AND DATE(p.timestamp) = DATE(l.timestamp)
        WHERE p.token_address = ? AND p.timestamp >= ?
        ORDER BY p.timestamp ASC
    ''', (token_address, cutoff.isoformat()))
    
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


# ============ PORTFOLIO WALLET FUNCTIONS ============

def add_portfolio_wallet(user_id: str, wallet_address: str, wallet_label: str = None):
    """Link a wallet to a user."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO portfolio_wallets 
            (user_id, wallet_address, wallet_label)
            VALUES (?, ?, ?)
        ''', (user_id, wallet_address, wallet_label))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error adding portfolio wallet: {e}")
        return False
    finally:
        conn.close()


def get_portfolio_wallets(user_id: str) -> List[Dict]:
    """Get all wallets linked to a user."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM portfolio_wallets 
        WHERE user_id = ?
        ORDER BY tracked_since DESC
    ''', (user_id,))
    
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def remove_portfolio_wallet(user_id: str, wallet_address: str) -> bool:
    """Unlink a wallet from a user."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            DELETE FROM portfolio_wallets 
            WHERE user_id = ? AND wallet_address = ?
        ''', (user_id, wallet_address))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


# ============ WATCHLIST FUNCTIONS ============

def add_watchlist(user_id: str, token_address: str, alert_conditions: str = None):
    """Add token to user's watchlist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO watchlists 
            (user_id, token_address, alert_conditions)
            VALUES (?, ?, ?)
        ''', (user_id, token_address, alert_conditions or ''))
        conn.commit()
        return True
    finally:
        conn.close()


def get_watchlist(user_id: str) -> List[Dict]:
    """Get all tokens in user's watchlist."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM watchlists 
        WHERE user_id = ? AND is_active = 1
        ORDER BY created_at DESC
    ''', (user_id,))
    
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def remove_watchlist(user_id: str, token_address: str) -> bool:
    """Remove token from watchlist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE watchlists SET is_active = 0
            WHERE user_id = ? AND token_address = ?
        ''', (user_id, token_address))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


# ============ SNIPER WALLET FUNCTIONS ============

def log_sniper_wallet(token_address: str, wallet_address: str, amount: float, value_usd: float, 
                     is_bundled: bool = False, is_fresh: bool = False):
    """Log a sniper/early buyer wallet."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO sniper_wallets 
            (token_address, wallet_address, amount, value_usd, is_bundled, is_fresh_wallet)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (token_address, wallet_address, amount, value_usd, is_bundled, is_fresh))
        conn.commit()
    finally:
        conn.close()


def get_snipers_for_token(token_address: str, limit: int = 10) -> List[Dict]:
    """Get sniper wallets for a token."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM sniper_wallets 
        WHERE token_address = ?
        ORDER BY buy_timestamp ASC
        LIMIT ?
    ''', (token_address, limit))
    
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results


def create_alert(user_id: str, token_address: str, alert_type: str, threshold_value: float):
    """Create a new alert."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO alerts (user_id, token_address, alert_type, threshold_value)
        VALUES (?, ?, ?, ?)
    ''', (user_id, token_address, alert_type, threshold_value))
    
    conn.commit()
    conn.close()
    return True


def get_active_alerts() -> List[Dict]:
    """Get all active alerts."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM alerts WHERE is_active = 1')
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results
