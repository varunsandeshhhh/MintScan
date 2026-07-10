import asyncio
from typing import Dict, Optional, List
from rugcheck import fetch_risk_data
from birdeye import get_token_overview, get_token_trades, get_token_holders
from helius import get_token_metadata, get_parsed_transactions


async def analyze_security(token_address: str) -> Dict[str, Optional[object]]:
    """Perform layered security analysis for a token.

    Returns a dict with keys:
      - rugcheck_score, rugcheck_data
      - lp_locked (bool/None)
      - mint_authority_disabled (bool/None)
      - freeze_authority_disabled (bool/None)
      - owner_renounced (bool/None)
      - honeypot (bool/None)
      - tax_percent (float/None)
      - suspicious_wallets (list)
    """
    results: Dict[str, Optional[object]] = {
        'rugcheck_score': None,
        'rugcheck_data': None,
        'lp_locked': None,
        'mint_authority_disabled': None,
        'freeze_authority_disabled': None,
        'owner_renounced': None,
        'honeypot': None,
        'tax_percent': None,
        'suspicious_wallets': [],
    }

    # Run external checks concurrently where possible
    tasks = []
    tasks.append(asyncio.create_task(fetch_risk_data(token_address)))
    tasks.append(asyncio.create_task(get_token_overview(token_address)))
    tasks.append(asyncio.create_task(get_token_trades(token_address, limit=50)))
    tasks.append(asyncio.create_task(get_token_holders(token_address, limit=50)))

    # Helius metadata may be used for authorities
    tasks.append(asyncio.create_task(get_token_metadata(token_address)))

    done = await asyncio.gather(*tasks, return_exceptions=True)

    rugcheck_res = done[0] if len(done) > 0 else None
    birdeye_overview = done[1] if len(done) > 1 else None
    trades = done[2] if len(done) > 2 else None
    holders = done[3] if len(done) > 3 else None
    helius_meta = done[4] if len(done) > 4 else None

    # RugCheck
    try:
        if isinstance(rugcheck_res, dict):
            results['rugcheck_data'] = rugcheck_res
            results['rugcheck_score'] = rugcheck_res.get('risk_score') or rugcheck_res.get('score') or None
            # Owner renounced info
            results['owner_renounced'] = rugcheck_res.get('owner_is_renounced') if 'owner_is_renounced' in rugcheck_res else rugcheck_res.get('ownerRenounced')
            # LP locked info
            lp_locked = rugcheck_res.get('liquidityLocked') if 'liquidityLocked' in rugcheck_res else rugcheck_res.get('isLiquidityLocked')
            results['lp_locked'] = lp_locked
    except Exception:
        pass

    # Birdeye overview may have LP lock and tax flags
    try:
        if isinstance(birdeye_overview, dict):
            bi = birdeye_overview
            if results['lp_locked'] is None:
                results['lp_locked'] = bi.get('liquidityLocked') or bi.get('isLocked')
            # tax detection if provided
            if 'tax' in bi:
                results['tax_percent'] = bi.get('tax')
    except Exception:
        pass

    # Helius metadata for authorities
    try:
        if isinstance(helius_meta, dict):
            # Helius may provide mintAuthority / freezeAuthority fields
            mint = helius_meta.get('mintAuthority') if 'mintAuthority' in helius_meta else helius_meta.get('mint_authority')
            freeze = helius_meta.get('freezeAuthority') if 'freezeAuthority' in helius_meta else helius_meta.get('freeze_authority')
            results['mint_authority_disabled'] = (mint is None)
            results['freeze_authority_disabled'] = (freeze is None)
    except Exception:
        pass

    # Honeypot and tax heuristics using trades
    try:
        if isinstance(trades, list) and trades:
            # Simple honeypot heuristic: if buys generally fail or buyers receive much less
            failed_buys = 0
            buy_count = 0
            estimated_tax = []
            for t in trades:
                # Birdeye trade item structure may contain fields like 'type','inAmount','outAmount','fee'
                typ = t.get('type') if isinstance(t, dict) else None
                if typ and typ.lower() in ('buy', 'swap'):
                    buy_count += 1
                    in_amount = float(t.get('inAmount', 0) or 0)
                    out_amount = float(t.get('outAmount', 0) or 0)
                    # If out_amount is significantly lower than in_amount, estimate tax
                    if in_amount and out_amount:
                        tax_est = max(0.0, (in_amount - out_amount) / in_amount * 100)
                        estimated_tax.append(tax_est)
                    # Some APIs mark failed trades; check status
                    if t.get('status') in ('failed', 'reverted'):
                        failed_buys += 1

            if buy_count:
                avg_tax = sum(estimated_tax) / len(estimated_tax) if estimated_tax else None
                results['tax_percent'] = results.get('tax_percent') or avg_tax
                # Honeypot if many buys fail or tax > 50%
                results['honeypot'] = True if (failed_buys / buy_count) > 0.3 or (avg_tax and avg_tax > 50) else False
    except Exception:
        pass

    # Suspicious wallets: check holders for unusual concentration or blacklisted patterns
    try:
        suspicious = []
        if isinstance(holders, list):
            for h in holders[:20]:
                addr = h.get('address') or h.get('owner') or h.get('wallet')
                pct = float(h.get('percentage', 0) or 0)
                if pct > 10:
                    suspicious.append({'address': addr, 'percentage': pct, 'reason': 'Large holder'})
        results['suspicious_wallets'] = suspicious
    except Exception:
        pass

    return results
