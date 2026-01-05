
from src.ibkr_data import IBKRData, IBKRConfig
from src.pricing import sigma_proxy_hv_vix

cfg = IBKRConfig(host="127.0.0.1", port=7497, client_id=28, use_market_data=False)
ibd = IBKRData(cfg)

try:
    ibd.connect()
    spy = ibd.stock("SPY")
    df_spy = ibd.historical_bars(spy, duration="5 Y", bar_size="1 day")[["datetime","close"]]
    df_vix = ibd.historical_vix(duration="5 Y", bar_size="1 day")

    df_sig = sigma_proxy_hv_vix(
        df_spy=df_spy,
        df_vix=df_vix,
        hv_window=20,
        hv_annualization=252,
        vix_weight=0.6
    )

    print(df_sig.tail(5))
    print("sigma_proxy last:", df_sig["sigma_proxy"].iloc[-1], "HV last:", df_sig["hv"].iloc[-1], "VIX last:", df_sig["vix"].iloc[-1])
finally:
    ibd.disconnect()
