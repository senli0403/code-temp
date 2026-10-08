# NQ K線分析(Databento + Claude)

那斯達克(CME NQ 期貨連續合約 `NQ.v.0`)K線分析桌面程式。資料直接來自你的 Databento 帳戶,右下角可與 Claude 討論圖表。

## 功能
- 日期範圍查詢、5/10/15/30 分K 下拉切換(以 1 分K 在本機聚合,切換不會再扣費)
- 主圖 SMA:MA10 / MA60 / MA72 / MA100(勾選顯示),成交量顯示在K線後方
- 台灣慣例:**紅K = 上漲、綠K = 下跌**
- 版面:上方K線圖;左下對話輸入框;右下對話紀錄
- AI 會收到你畫面上每根K棒的 OHLC、量、紅/綠K 標記與均線數值;你教它的規則(說「記住…」)會存成長期「AI 筆記」,之後每次分析都會自動套用
- 「預估費用」按鈕可在下載前查詢 Databento 費用;已下載的資料會快取在本機

## 使用
1. 執行 `NQ-KLine.exe`
2. 右上角「設定」填入 Databento API Key 與 Anthropic API Key(只存在 `%USERPROFILE%\.nq_kline\`)
3. 選日期 → 查詢。沒有金鑰也可勾「示範資料」先試用介面

## 取得 .exe
- **GitHub Actions**:到 Actions → *Build Windows exe* → 下載 artifact `NQ-KLine-windows`
- **自行在 Windows 打包**:雙擊 `build_windows.bat`,成品在 `dist\NQ-KLine.exe`
- 需要 Windows 10/11(使用內建的 Edge WebView2)

## 開發
```
pip install -r requirements-dev.txt
python run.py --browser    # 用瀏覽器開啟(免 pywebview)
python run.py              # 桌面視窗
pytest
```

## 注意
- 連續合約 `NQ.v.0`(成交量最大合約)換月時價格會有跳空,屬正常現象
- Databento 歷史資料按用量計費;結束日若超出可查範圍會回報錯誤,請提早一天
- AI 輸出僅為技術面解讀,非投資建議
