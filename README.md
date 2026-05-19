# chust-optom-1-regos-bot

Bu loyiha ishlayotgan `DCB` botga tegmagan holda, unga o'xshash alohida `Chust optom No 1` REGOS webhook botidir.

Hozirgi oqim:

- realizatsiya PDF holatda Telegram guruhga yuboriladi
- to'lov guruhga yuborilmaydi
- to'lov admin private chatiga yuboriladi
- mijoz telefoni Telegramda ulangan bo'lsa, private nusxa o'sha chatga ham boradi

Vaqtinchalik test sozlamalari:

- admin telefoni: `+998770575732`
- realizatsiya guruhi: `-1003482963610`

## Lokal ishga tushirish

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Windows uchun tez variant:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\start_local.ps1
```

Health check:

```text
GET /health
```

## Muhim envlar

Kamida quyidagilar to'ldiriladi:

- `APP_BRAND_NAME`
- `REGOS_BASE_URL`
- `WHOLESALE_BOT_TOKEN`
- `WHOLESALE_GROUP_CHAT_ID`
- `WHOLESALE_WEBHOOK_SECRET`
- `WHOLESALE_ADMIN_PHONE`

Muhim eslatma:

- `WHOLESALE_PAYMENT_GROUP_ENABLED=false` bo'lsa to'lov groupga chiqmaydi
- admin yoki mijoz botga private kirib `/start` yuboradi
- keyin o'z telefon raqamini share qiladi
- REGOS ichidagi telefon shu raqam bilan mos tushsa PDF private chatga keladi

Bu loyiha uchun `WHOLESALE_*` envlari asosiy hisoblanadi.

## Webhooklar

REGOS:

```text
POST https://your-domain/regos/webhook
```

Telegram wholesale bot:

```text
POST https://your-domain/telegram/webhook/wholesale/<WHOLESALE_WEBHOOK_SECRET>
```

Webhooklarni almashtirish faqat yangi servis shadow testdan o'tgandan keyin qilinadi.

## Coolify deploy

Repo Dockerfile bilan deploy bo'ladi. Qisqa tartib:

1. Coolify'da Git repo ulang.
2. o'zingizning domeningizni web service'ga bering.
3. Persistent volume'ni `/app/data` ga ulang.
4. Health check sifatida `/health` ishlating.
5. Ishlayotgan `DCB` webhooklariga tegmasdan shadow test qiling.

Batafsil qadamlar [docs/COOLIFY_DEPLOY.md](docs/COOLIFY_DEPLOY.md) va [docs/MIGRATION_CHECKLIST.md](docs/MIGRATION_CHECKLIST.md) ichida.

## Eslatma

- Event deduplikatsiya `event_id` bo'yicha SQLite ichida yuradi.
- Xatoda servis `500` qaytaradi va REGOS qayta yuborishi mumkin.
- Bu repo eski production serverga tegmaydi; yangi alohida deploy uchun tayyorlangan.
