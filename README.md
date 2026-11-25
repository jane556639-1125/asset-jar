# Asset Jar V0.2 Test
測試版：示意行情、本機儲存，不可作為真實投資報表。請將所有檔案上傳至 asset-jar Repository 根目錄，Settings → Pages → Deploy from a branch → main → /(root)。iPhone Safari 開啟網站，分享 → 加入主畫面。尚未實作雲端、Google 登入、自動行情、歷史快照、完整匯入及交易編輯。測試版離線可能仍可寫入本機資料，不是正式版離線規則。

新版玻璃存錢罐圖示、手繪導覽、台股綠／美股藍、目標價追蹤移至個股庫存。保留原本本機資料鍵。若 iPhone 圖示未更新，可移除舊主畫面捷徑後重新加入（先備份資料）。

V0.3：透明首頁插畫、交易三分頁、表單響應式修正、買賣原因分流。代碼內建常用清單及既有庫存；GitHub Actions 可更新公開代碼及臺銀歷史匯率。請將 .github/workflows/market-data.yml 依路徑建立（網頁上傳可能不包含隱藏資料夾），Actions → Update reference data → Run workflow。資料來源尚未連線驗證，失敗時保留舊資料；無歷史匯率須手動輸入。未串接自動股價。若 Pages 不因機器人 commit 重新部署，請手動重新部署或由使用者提交一次更新。勿上傳個人交易資料。
