"""Caller statistics and leaderboard tracking."""
from typing import Dict, List, Optional
from database import (
    log_caller_stat, update_caller_roi, get_caller_leaderboard, 
    get_caller_stats, get_call_history
)


async def track_caller_call(user_id: str, user_name: str, token_address: str, entry_price: float):
    """Track a user's token call."""
    try:
        log_caller_stat(user_id, user_name, token_address, entry_price)
        return True
    except Exception as e:
        print(f"Error tracking caller: {e}")
        return False


async def update_caller_returns(token_address: str, current_price: float):
    """Update all callers' ROI for a specific token."""
    try:
        from database import DB_PATH
        import sqlite3
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Get all callers who called this token
        cursor.execute('''
            SELECT caller_id FROM caller_stats 
            WHERE token_address = ?
        ''', (token_address,))
        
        callers = cursor.fetchall()
        conn.close()
        
        for (caller_id,) in callers:
            update_caller_roi(caller_id, token_address, current_price)
        
        return len(callers)
        
    except Exception as e:
        print(f"Error updating caller returns: {e}")
        return 0


def get_caller_leaderboard_embed_data(limit: int = 10) -> Dict:
    """Get leaderboard data formatted for Discord embed."""
    try:
        stats = get_caller_leaderboard(limit)
        
        if not stats:
            return {'error': 'No caller data available'}
        
        leaderboard = []
        for i, caller in enumerate(stats, 1):
            name = caller.get('caller_name') or caller.get('caller_id', '')[:12]
            avg_roi = caller.get('avg_roi') or 0
            total_calls = caller.get('total_calls') or 0
            wins = caller.get('wins') or 0
            
            emoji = ['🥇', '🥈', '🥉'] + ['#' + str(i) for _ in range(i - 3)]
            medal = emoji[min(i - 1, len(emoji) - 1)]
            
            leaderboard.append({
                'rank': f"{medal}",
                'name': name[:20],
                'roi': f"{avg_roi:.1f}%",
                'calls': total_calls,
                'wins': wins,
                'wr': f"{(wins/total_calls*100):.0f}%" if total_calls > 0 else "N/A",
            })
        
        return {'success': True, 'leaderboard': leaderboard}
        
    except Exception as e:
        print(f"Error getting leaderboard: {e}")
        return {'error': str(e)}


def get_caller_stats_embed_data(caller_id: str) -> Dict:
    """Get individual caller stats formatted for Discord embed."""
    try:
        stats = get_caller_stats(caller_id)
        
        if not stats:
            return {'error': 'No data for this caller'}
        
        return {
            'success': True,
            'caller_name': stats.get('caller_name') or stats.get('caller_id', '')[:16],
            'total_calls': stats.get('total_calls', 0),
            'avg_roi': f"{stats.get('avg_roi', 0):.1f}%",
            'wins': stats.get('wins', 0),
            'losses': stats.get('losses', 0),
            'best_roi': f"{stats.get('best_roi', 0):.1f}%",
            'worst_roi': f"{stats.get('worst_roi', 0):.1f}%",
            'win_rate': f"{(stats.get('wins', 0) / max(1, stats.get('total_calls', 1)) * 100):.0f}%",
        }
        
    except Exception as e:
        print(f"Error getting caller stats: {e}")
        return {'error': str(e)}


def format_call_with_return(token_address: str, symbol: str, entry_price: float, 
                           current_price: float) -> Dict:
    """Format a single call with return metrics."""
    try:
        if entry_price <= 0:
            roi = 0
            multiplier = 0
        else:
            roi = ((current_price - entry_price) / entry_price) * 100
            multiplier = current_price / entry_price
        
        return {
            'token': symbol or token_address[:8],
            'address': token_address,
            'entry': f"${entry_price:.8f}".rstrip('0').rstrip('.'),
            'current': f"${current_price:.8f}".rstrip('0').rstrip('.'),
            'roi': f"{roi:.1f}%",
            'return_multiple': f"{multiplier:.2f}x",
            'status': '🟢' if roi >= 0 else '🔴',
        }
        
    except Exception as e:
        print(f"Error formatting call: {e}")
        return {}


def get_top_calls(limit: int = 5) -> List[Dict]:
    """Get top performing calls by ROI."""
    try:
        from database import DB_PATH
        import sqlite3
        
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT token_address, current_price, entry_price, roi_pct
            FROM caller_stats
            WHERE roi_pct IS NOT NULL
            ORDER BY roi_pct DESC
            LIMIT ?
        ''', (limit,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'token': row['token_address'][:8],
                'address': row['token_address'],
                'current': f"${row['current_price']:.2f}",
                'entry': f"${row['entry_price']:.8f}",
                'roi': f"{row['roi_pct']:.1f}%",
            })
        
        conn.close()
        return results
        
    except Exception as e:
        print(f"Error getting top calls: {e}")
        return []


def get_worst_calls(limit: int = 5) -> List[Dict]:
    """Get worst performing calls by ROI."""
    try:
        from database import DB_PATH
        import sqlite3
        
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT token_address, current_price, entry_price, roi_pct
            FROM caller_stats
            WHERE roi_pct IS NOT NULL
            ORDER BY roi_pct ASC
            LIMIT ?
        ''', (limit,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'token': row['token_address'][:8],
                'address': row['token_address'],
                'current': f"${row['current_price']:.2f}",
                'entry': f"${row['entry_price']:.8f}",
                'roi': f"{row['roi_pct']:.1f}%",
            })
        
        conn.close()
        return results
        
    except Exception as e:
        print(f"Error getting worst calls: {e}")
        return []
