#!/bin/bash
set -e

APP_DIR="/opt/bots/regos-tg-bot"
REPO_URL="https://github.com/nodirbekzarinasabina-2018/regos-tg-bot.git"

echo "🚀 Regos bot install started"

# 1. Asosiy paketlar
apt update -y
apt install -y python3 python3-venv git

# 2. Papka yaratish
mkdir -p /opt/bots

# 3. Repo'ni clone qilish yoki yangilash
if [ ! -d "$APP_DIR/.git" ]; then
    git clone "$REPO_URL" "$APP_DIR"
else
    cd "$APP_DIR"
    git pull
fi

cd "$APP_DIR"

# 4. Virtualenv
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate

# 5. Kutubxonalar
pip install --upgrade pip
pip install -r requirements.txt

# 6. Test run
echo "✅ Install finished"
echo "👉 Next step: systemd service qo‘shamiz"
