"""AI-powered token analysis synthesis and risk assessment."""
from typing import Dict, Optional, List


def _to_number(value, default: float = 0.0) -> float:
    """Safely convert values to a float, treating None/empty as default."""
    if value is None:
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def calculate_ai_confidence(security_data: Dict, holder_data: Dict, dev_data: Optional[Dict]) -> float:
    """Calculate overall confidence score (0-100) based on available data."""
    confidence = 50.0  # Base confidence

    # Security factors
    if security_data:
        risk_score = _to_number(security_data.get('rugcheck_score', 50), 50)
        if risk_score < 30:
            confidence += 15  # Good security = higher confidence
        elif risk_score > 70:
            confidence -= 20  # Poor security = lower confidence

    # Developer track record
    if dev_data:
        win_rate = _to_number(dev_data.get('win_rate', 0), 0)
        if win_rate > 60:
            confidence += 20
        elif win_rate < 20:
            confidence -= 15

    # Holder distribution
    if holder_data:
        top_10 = _to_number(holder_data.get('top_10_percentage', 0), 0)
        if top_10 > 60:
            confidence -= 15  # Concentrated ownership
        elif top_10 < 30:
            confidence += 10  # Well distributed

    return max(0, min(100, confidence))


def generate_risk_assessment(security_data: Dict, holder_data: Dict) -> str:
    """Generate a categorical risk assessment."""
    risk_score = _to_number(security_data.get('rugcheck_score', 50), 50) if security_data else 50

    if security_data and security_data.get('honeypot'):
        return "🔴 Critical - Honeypot Detected"
    elif risk_score >= 70:
        return "🔴 High - Multiple red flags"
    elif risk_score >= 50:
        return "🟠 Medium - Some concerns"
    elif risk_score >= 30:
        return "🟡 Low - Relatively safe"
    else:
        return "🟢 Very Low - Clean profile"


def generate_developer_summary(dev_data: Optional[Dict], token_count: int = 1) -> str:
    """Generate human-readable developer analysis."""
    if not dev_data:
        return "Developer history unavailable."
    
    win_rate = _to_number(dev_data.get('win_rate', 0), 0)
    total_value = _to_number(dev_data.get('total_value', 0), 0)
    avg_roi = _to_number(dev_data.get('avg_roi', 0), 0)
    token_count = int(_to_number(dev_data.get('token_count', 1), 1))
    
    summary_lines = []
    
    if token_count > 1:
        successful = max(1, int(token_count * (win_rate / 100)))
        summary_lines.append(f"Developer has launched {token_count} tokens.")
        
        if avg_roi > 0:
            summary_lines.append(f"{successful} reached profitability (Avg ROI: {avg_roi:.0f}%).")
        else:
            summary_lines.append(f"Limited profitability so far.")
    
    if total_value > 1_000_000:
        summary_lines.append(f"Portfolio value: ${total_value / 1_000_000:.1f}M (strong experience).")
    elif total_value > 100_000:
        summary_lines.append(f"Portfolio value: ${total_value / 1_000:.0f}K (moderate experience).")
    else:
        summary_lines.append(f"New developer with small track record.")
    
    return " ".join(summary_lines) if summary_lines else "Limited developer data."


def generate_holder_summary(holder_data: Optional[Dict], top_holders: List[Dict]) -> str:
    """Generate human-readable holder distribution analysis."""
    if not holder_data:
        return "Holder distribution unavailable."
    
    top_1 = _to_number(holder_data.get('top_1_percentage', 0), 0)
    top_10 = _to_number(holder_data.get('top_10_percentage', 0), 0)
    
    summary_lines = []
    
    if top_10 > 70:
        summary_lines.append("⚠️ Extremely concentrated - top 10 hold over 70%.")
        summary_lines.append("High dump risk from whale movements.")
    elif top_10 > 50:
        summary_lines.append("⚠️ Concentrated - top 10 hold over 50%.")
        summary_lines.append("Watch for insider activity.")
    elif top_10 > 30:
        summary_lines.append("✓ Moderate distribution - acceptable holder spread.")
    else:
        summary_lines.append("✓ Well distributed - low concentration risk.")
    
    if top_1 > 30:
        summary_lines.append(f"Single largest holder controls {top_1:.1f}% (high risk).")
    
    return " ".join(summary_lines) if summary_lines else "Holder distribution unclear."


def generate_market_summary(token_data: Dict, risk_data: Optional[Dict]) -> str:
    """Generate market and buying pressure analysis."""
    summary_lines = []
    
    volume_24h = _to_number(token_data.get('volume_24h', 0), 0)
    market_cap = _to_number(token_data.get('market_cap', 0), 0)
    liquidity = _to_number(token_data.get('liquidity', 0), 0)
    
    # Buying pressure
    if volume_24h and market_cap:
        volume_ratio = volume_24h / market_cap if market_cap > 0 else 0
        if volume_ratio > 1.0:
            summary_lines.append("🟢 Strong buying pressure (high 24h volume).")
        elif volume_ratio > 0.5:
            summary_lines.append("📊 Moderate trading activity detected.")
        else:
            summary_lines.append("📉 Low trading volume - limited liquidity.")
    
    # Liquidity assessment
    if liquidity and market_cap:
        liq_ratio = liquidity / market_cap if market_cap > 0 else 0
        if liq_ratio > 0.3:
            summary_lines.append("✓ Good liquidity (easy to trade).")
        elif liq_ratio > 0.05:
            summary_lines.append("⚠️ Limited liquidity (slippage risk).")
        else:
            summary_lines.append("🔴 Very low liquidity (trap risk).")
    
    # Risk flags
    if risk_data:
        if risk_data.get('is_open_source'):
            summary_lines.append("✓ Open source code verified.")
        if risk_data.get('owner_is_renounced'):
            summary_lines.append("✓ Owner renounced (no rug pull risk).")
    
    return " ".join(summary_lines) if summary_lines else "Market data unavailable."


def generate_ai_summary(
    token_data: Dict,
    risk_data: Optional[Dict],
    security_data: Optional[Dict],
    holder_data: Optional[Dict],
    dev_data: Optional[Dict],
    top_holders: Optional[List[Dict]] = None,
) -> Dict:
    """Generate complete AI analysis summary."""
    
    if top_holders is None:
        top_holders = []

    token_data = token_data or {}
    security_data = security_data or {}
    holder_data = holder_data or {}
    dev_data = dev_data or {}
    
    # Calculate metrics
    confidence = calculate_ai_confidence(security_data or {}, holder_data or {}, dev_data)
    risk_assessment = generate_risk_assessment(security_data or {}, holder_data or {})
    
    # Generate narrative summaries
    dev_summary = generate_developer_summary(dev_data)
    holder_summary = generate_holder_summary(holder_data, top_holders)
    market_summary = generate_market_summary(token_data, risk_data)
    
    return {
        'risk_level': risk_assessment,
        'developer_analysis': dev_summary,
        'holder_analysis': holder_summary,
        'market_analysis': market_summary,
        'confidence_score': confidence,
        'recommendation': _get_recommendation(confidence, risk_assessment),
    }


def _get_recommendation(confidence: float, risk_level: str) -> str:
    """Provide investment recommendation based on metrics."""
    if 'Critical' in risk_level or 'Honeypot' in risk_level:
        return "❌ DO NOT INVEST - Critical risk detected."
    elif confidence >= 75 and 'High' not in risk_level:
        return "✓ STRONG BUY - High confidence, low risk."
    elif confidence >= 60 and 'High' not in risk_level:
        return "✓ BUY - Reasonable risk/reward profile."
    elif confidence >= 50 and 'Medium' not in risk_level:
        return "⚠️ HOLD - Mixed signals. Proceed with caution."
    elif confidence >= 40:
        return "⚠️ WAIT - High risk. Monitor for improvements."
    else:
        return "❌ AVOID - Too many red flags."
