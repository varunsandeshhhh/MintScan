from ai_summary import generate_ai_summary


def test_generate_ai_summary_handles_none_metrics():
    token_data = {
        'price': 0.1,
        'market_cap': 100000,
        'liquidity': 20000,
        'volume_24h': 5000,
    }
    security_data = {
        'rugcheck_score': None,
        'honeypot': None,
    }
    holder_data = {
        'top_1_percentage': None,
        'top_10_percentage': None,
    }
    dev_data = {
        'win_rate': None,
        'avg_roi': None,
        'total_value': None,
        'token_count': None,
    }

    summary = generate_ai_summary(token_data, None, security_data, holder_data, dev_data)

    assert 'risk_level' in summary
    assert 'recommendation' in summary
    assert 'developer_analysis' in summary
    assert 'holder_analysis' in summary
    assert 'market_analysis' in summary
    assert 'confidence_score' in summary
