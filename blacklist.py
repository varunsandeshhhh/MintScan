"""Simple blacklist of known malicious token or wallet addresses.

Add addresses here manually in lowercase to have the bot warn on those tokens.
"""
BLACKLIST = {
    # Example entries (lowercase)
    # 'badtokenaddress1': 'Known rugpull token',
}


def is_blacklisted(address: str):
    if not address:
        return None
    key = address.lower()
    reason = BLACKLIST.get(key)
    return reason
