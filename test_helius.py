from helius import get_helius_api_key


def test_get_helius_api_key_reads_current_settings(monkeypatch):
    import helius

    monkeypatch.setattr(helius, 'settings', {'HELIUS_API_KEY': 'demo-key'})

    assert get_helius_api_key() == 'demo-key'
