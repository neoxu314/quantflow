"""Pass macOS per-host HTTPS proxy settings to Yahoo's curl clients."""

import sys
from urllib.request import getproxies, getproxies_environment, proxy_bypass


def session_options():
    # curl already reads the explicit proxy environment, including NO_PROXY.
    if sys.platform != "darwin" or getproxies_environment():
        return {}
    proxy = getproxies().get("https")
    if not proxy:
        return {}
    hosts = (
        "finance.yahoo.com",
        "query1.finance.yahoo.com",
        "query2.finance.yahoo.com",
        "fc.yahoo.com",
        "guce.yahoo.com",
        "consent.yahoo.com",
    )
    routes = {f"https://{host}": proxy for host in hosts if not proxy_bypass(host)}
    return {"proxies": routes} if routes else {}
