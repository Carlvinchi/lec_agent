from pathlib import Path

"""Pre-downloads all SEC filings needed by the eval benchmark."""
_DOWNLOAD_DIR = Path("data/edgar")

# q1–q10: NVDA, AAPL, AMZN, GOOGL, TSLA, MSFT, META, F, GM, CRM
# q11–q20: WMT, NFLX, JPM, INTC, AMD, PFE, XOM, CVX, JNJ (SPY is price-history only)
TICKERS = [
    "NVDA", "AAPL", "AMZN", "GOOGL", "TSLA",
    "MSFT", "META", "F",    "GM",    "CRM",
    "WMT",  "NFLX", "JPM",  "INTC",  "AMD",
    "PFE",  "XOM",  "CVX",  "JNJ",
]
FILING_TYPE = "10-K"
YEARS = [2022, 2023, 2024]

if __name__ == "__main__":
    from sec_edgar_downloader import Downloader
    dl = Downloader(company_name="FinanceAgent", email_address="oc90699@yahoo.com", download_folder=_DOWNLOAD_DIR)
    for ticker in TICKERS:
        for year in YEARS:
            print(f"Fetching {ticker} {FILING_TYPE} {year}...")
            dl.get(FILING_TYPE, ticker, after=f"{year}-01-01", before=f"{year}-12-31")
    print("Prefetch complete.")
