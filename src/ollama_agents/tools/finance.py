import yfinance as yf

def get_realtime_market_quote(ticker: str) -> dict:
    """Retrieves real-time or latest available financial market data for a given ticker symbol.

    Args:
        ticker: The stock ticker symbol (e.g., 'AAPL', 'NVDA', 'RELIANCE.NS', 'INFY.NS').
    """
    try:
        stock = yf.Ticker(ticker.strip().upper())
        info = stock.fast_info

        return {
            "symbol": ticker.upper(),
            "currency": info.currency,
            "last_price": round(float(info.last_price), 2),
            "day_high": round(float(info.day_high), 2),
            "day_low": round(float(info.day_low), 2),
            "previous_close": round(float(info.previous_close), 2),
            "market_cap": getattr(info, "market_cap", "N/A"),
        }
    except Exception as e:
        return {"error": f"Failed to fetch market data for {ticker}: {str(e)}"}