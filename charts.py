"""Chart generation for token analysis using matplotlib."""
import io
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
from typing import List, Dict, Optional
from database import get_price_volume_history, get_call_history


def generate_candlestick_chart(token_address: str, hours: int = 24) -> Optional[io.BytesIO]:
    """Generate candlestick chart for token price action."""
    try:
        history = get_price_volume_history(token_address, hours=hours)
        if not history or len(history) < 2:
            return None
        
        # Group by 4-hour candles
        candles = []
        current_candle = None
        
        for entry in history:
            ts = datetime.fromisoformat(entry['timestamp']) if isinstance(entry['timestamp'], str) else entry['timestamp']
            price = entry['price']
            
            # Start new candle every 4 hours
            candle_time = ts.replace(hour=(ts.hour // 4) * 4, minute=0, second=0)
            
            if not current_candle or current_candle['time'] != candle_time:
                if current_candle:
                    candles.append(current_candle)
                current_candle = {
                    'time': candle_time,
                    'open': price,
                    'high': price,
                    'low': price,
                    'close': price,
                }
            else:
                current_candle['high'] = max(current_candle['high'], price)
                current_candle['low'] = min(current_candle['low'], price)
                current_candle['close'] = price
        
        if current_candle:
            candles.append(current_candle)
        
        if len(candles) < 2:
            return None
        
        # Plot candlesticks
        fig, ax = plt.subplots(figsize=(12, 6))
        
        for i, candle in enumerate(candles):
            open_price = candle['open']
            close_price = candle['close']
            high = candle['high']
            low = candle['low']
            
            # Wick (high-low)
            ax.plot([i, i], [low, high], color='black', linewidth=1)
            
            # Body (open-close)
            body_color = 'green' if close_price >= open_price else 'red'
            body_height = abs(close_price - open_price)
            body_bottom = min(open_price, close_price)
            
            ax.bar(i, body_height, bottom=body_bottom, color=body_color, width=0.6, edgecolor='black', linewidth=1)
        
        ax.set_xlabel('Time')
        ax.set_ylabel('Price (USD)')
        ax.set_title(f'Token Price Action - {hours}h Candlestick Chart')
        ax.grid(True, alpha=0.3)
        
        # Save to bytes
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=80, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)
        
        return buf
        
    except Exception as e:
        print(f"Error generating candlestick chart: {e}")
        return None


def generate_price_chart(token_address: str, hours: int = 24) -> Optional[io.BytesIO]:
    """Generate price history line chart."""
    try:
        history = get_price_volume_history(token_address, hours=hours)
        if not history or len(history) < 2:
            return None
        
        timestamps = []
        prices = []
        
        for entry in history:
            ts = datetime.fromisoformat(entry['timestamp']) if isinstance(entry['timestamp'], str) else entry['timestamp']
            timestamps.append(ts)
            prices.append(entry['price'])
        
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(timestamps, prices, color='#9D4EDD', linewidth=2, label='Price')
        ax.fill_between(timestamps, prices, alpha=0.3, color='#9D4EDD')
        
        ax.set_xlabel('Time')
        ax.set_ylabel('Price (USD)')
        ax.set_title(f'Token Price History - {hours}h')
        ax.grid(True, alpha=0.3)
        ax.legend()
        
        # Format x-axis
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        plt.xticks(rotation=45)
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=80, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)
        
        return buf
        
    except Exception as e:
        print(f"Error generating price chart: {e}")
        return None


def generate_volume_chart(token_address: str, hours: int = 24) -> Optional[io.BytesIO]:
    """Generate trading volume chart."""
    try:
        history = get_price_volume_history(token_address, hours=hours)
        if not history or len(history) < 2:
            return None
        
        # Filter entries with volume data
        volumes = [(entry['timestamp'], entry['volume_24h']) for entry in history if entry.get('volume_24h')]
        
        if not volumes:
            return None
        
        timestamps = []
        volume_data = []
        
        for ts_str, vol in volumes:
            ts = datetime.fromisoformat(ts_str) if isinstance(ts_str, str) else ts_str
            timestamps.append(ts)
            volume_data.append(vol / 1_000_000)  # Convert to millions
        
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.bar(timestamps, volume_data, color='#00BFFF', edgecolor='black', linewidth=0.5)
        
        ax.set_xlabel('Time')
        ax.set_ylabel('Volume (M USD)')
        ax.set_title(f'Trading Volume - {hours}h')
        ax.grid(True, alpha=0.3, axis='y')
        
        # Format x-axis
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        plt.xticks(rotation=45)
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=80, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)
        
        return buf
        
    except Exception as e:
        print(f"Error generating volume chart: {e}")
        return None


def generate_liquidity_chart(token_address: str, hours: int = 24) -> Optional[io.BytesIO]:
    """Generate liquidity history chart."""
    try:
        history = get_price_volume_history(token_address, hours=hours)
        if not history or len(history) < 2:
            return None
        
        # Filter entries with liquidity data
        liq_data = [(entry['timestamp'], entry['liquidity']) for entry in history if entry.get('liquidity')]
        
        if not liq_data:
            return None
        
        timestamps = []
        liquidity_values = []
        
        for ts_str, liq in liq_data:
            ts = datetime.fromisoformat(ts_str) if isinstance(ts_str, str) else ts_str
            timestamps.append(ts)
            liquidity_values.append(liq / 1_000_000)  # Convert to millions
        
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.plot(timestamps, liquidity_values, color='#00FF00', linewidth=2, marker='o', markersize=4, label='Liquidity')
        ax.fill_between(timestamps, liquidity_values, alpha=0.2, color='#00FF00')
        
        ax.set_xlabel('Time')
        ax.set_ylabel('Liquidity (M USD)')
        ax.set_title(f'LP Liquidity History - {hours}h')
        ax.grid(True, alpha=0.3)
        ax.legend()
        
        # Format x-axis
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        plt.xticks(rotation=45)
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=80, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)
        
        return buf
        
    except Exception as e:
        print(f"Error generating liquidity chart: {e}")
        return None


def generate_caller_performance_chart(limit: int = 10) -> Optional[io.BytesIO]:
    """Generate caller leaderboard bar chart."""
    try:
        from database import get_caller_leaderboard
        
        stats = get_caller_leaderboard(limit)
        if not stats:
            return None
        
        names = [s['caller_name'] or s['caller_id'][:8] for s in stats]
        rois = [s['avg_roi'] or 0 for s in stats]
        
        fig, ax = plt.subplots(figsize=(12, 6))
        colors = ['green' if roi >= 0 else 'red' for roi in rois]
        ax.barh(names, rois, color=colors, edgecolor='black', linewidth=1)
        
        ax.set_xlabel('Average ROI (%)')
        ax.set_title(f'Top {limit} Callers - Average ROI')
        ax.grid(True, alpha=0.3, axis='x')
        ax.axvline(x=0, color='black', linewidth=0.8)
        
        # Add value labels
        for i, (name, roi) in enumerate(zip(names, rois)):
            ax.text(roi + 1, i, f'{roi:.1f}%', va='center', fontsize=9)
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=80, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)
        
        return buf
        
    except Exception as e:
        print(f"Error generating caller chart: {e}")
        return None


def generate_holder_growth_chart(token_address: str) -> Optional[io.BytesIO]:
    """Generate holder count growth chart."""
    try:
        from database import get_top_holders
        
        holders = get_top_holders(token_address, limit=50)
        if not holders:
            return None
        
        # Sort by timestamp and group holder count growth
        sorted_holders = sorted(holders, key=lambda h: h.get('timestamp', ''))
        
        timestamps = [h['timestamp'] for h in sorted_holders]
        holder_counts = list(range(1, len(sorted_holders) + 1))
        
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(timestamps, holder_counts, color='#FFD700', linewidth=2, marker='o', markersize=4)
        ax.fill_between(range(len(holder_counts)), holder_counts, alpha=0.3, color='#FFD700')
        
        ax.set_xlabel('Time')
        ax.set_ylabel('Number of Tracked Holders')
        ax.set_title(f'Holder Growth - {token_address[:8]}...')
        ax.grid(True, alpha=0.3)
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=80, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)
        
        return buf
        
    except Exception as e:
        print(f"Error generating holder growth chart: {e}")
        return None
