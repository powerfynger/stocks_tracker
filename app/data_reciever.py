from tradingview_screener import Query

def get_base_statistics():
    data=(Query()
            .select('name', 'Recommend.All', 'relative_volume_intraday|5', 'RSI|15', 'EMA10|5')
            .order_by('relative_volume_intraday|5', ascending=False)
            .set_markets('russia')
            .limit(10)
            .get_scanner_data())[1]

    return data.to_dict(orient="records")

def main():
    pass

if __name__ == "__main__":
    main()