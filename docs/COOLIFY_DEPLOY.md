# Coolify Deploy

Bu hujjat `chust-optom-1-regos-bot`ni yangi domenga xavfsiz chiqarish uchun.

## 1. Maqsad

Yangi OVH serverda yangi servisni ishga tushirish, lekin eski Windows productionni o'chirmaslik.

## 2. Coolify web service

Coolify'da bitta web service yaratiladi:

- Domain: `your-domain`
- Build source: repo root
- Dockerfile: `Dockerfile`
- Exposed port: `8000`
- Health path: `/health`

## 3. Persistent storage

Quyidagi volume kerak:

- mount path: `/app/data`

Bu SQLite va webhook archive fayllari uchun kerak.

## 4. Kerakli envlar

Kamida:

- `APP_HOST=0.0.0.0`
- `APP_PORT=8000`
- `APP_TIMEZONE=Asia/Tashkent`
- `REGOS_BASE_URL`
- `APP_BRAND_NAME=Chust optom No 1`
- `REGOS_TIMEOUT_SECONDS`
- `STORAGE_PATH=./data/bot.db`
- `TEMP_DIR=./data/tmp`

Telegram uchun:

- `WHOLESALE_BOT_TOKEN`
- `WHOLESALE_GROUP_CHAT_ID`
- `WHOLESALE_WEBHOOK_SECRET`
- `WHOLESALE_ADMIN_PHONE=+998770575732`
- `WHOLESALE_PAYMENT_GROUP_ENABLED=false`

## 5. Reminder jobs

Reminder uchun Coolify scheduled jobs ochiladi:

1. Morning job
   Command: `python -m app.reminder_jobs --mode morning`

2. Debts job
   Command: `python -m app.reminder_jobs --mode debts`

Server timezone `Asia/Tashkent` ekanini tekshirish kerak.

## 6. Xavfsiz cutover tartibi

1. Repo deploy bo'ladi.
2. `https://your-domain/health` tekshiriladi.
3. Test `.env` bilan web service ichki tekshiriladi.
4. Telegram webhooklar hali o'zgartirilmaydi.
5. REGOS webhook hali o'zgartirilmaydi.
6. Shadow test reja bo'yicha tekshiruv o'tkaziladi.
7. Faqat tasdiqdan keyin webhooklar yangi domenga ko'chiriladi.

## 7. Hech qachon hozir qilinmaydigan ishlar

- eski production webhookni o'chirish
- eski Windows serverni to'xtatish
- DNS'ni eski production o'rniga almashtirish

Bular faqat alohida tasdiq bilan qilinadi.
