# Migration Checklist

## Phase 1. Repo tayyorlash

- `app/` ichida faqat REGOS botlar qoldirilgan
- support bot kodi chiqarilgan
- `.env.example` tozalangan
- Dockerfile qo'shilgan
- Coolify deploy hujjati yozilgan

## Phase 2. GitHub

- private repo nomi: `chust-optom-1-regos-bot`
- lokal fayllar shu repo ichiga yuklanadi
- branch protection keyinroq qo'yiladi

## Phase 3. Coolify

- repo Coolify'ga ulanadi
- `your-domain` biriktiriladi
- `/app/data` volume ulanadi
- envlar to'ldiriladi
- health check yashil holatga keladi

## Phase 4. Shadow test

- `/health` javob qaytaradi
- Telegram botlar test update qabul qiladi
- private phone mapping ishlaydi
- to'lov groupga chiqmaydi
- `+998770575732` admin private xabar oladi
- PDF render ishlaydi
- reminder joblar alohida yuradi
- REGOS test payloadlari qayta ishlanadi

## Phase 5. Cutover

Faqat alohida tasdiqdan keyin:

- Telegram webhooklar yangi domenga o'tkaziladi
- REGOS webhook yangi domenga o'tkaziladi
- trafik kuzatiladi
- eski production darhol o'chirilmaydi

## Phase 6. Post-cutover

- loglar tekshiriladi
- webhook archive tekshiriladi
- duplicate eventlar kuzatiladi
- reminder schedule real vaqtda tasdiqlanadi
