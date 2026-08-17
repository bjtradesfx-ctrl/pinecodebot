import os
import json
import threading
import requests
from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright

app = Flask(__name__)

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1538899048839258162/LQ79MbfFTVkI7vlFNbmdkoLu4u_puQRCqr8IVS-NYyoXMVZ3MnpALYjEdJjm2xTHmELN")
CHART_URL = os.environ.get("TV_CHART_URL", "https://tr.tradingview.com/chart/0pL1VjCl/?symbol=FX%3AEURUSD")


def process_alert_in_background(ticker, action, price, details, embed_color):
    """Takes the screenshot in the background so TradingView doesn't time out."""
    screenshot_file = f"chart_{ticker}.png"

    try:
        # 1. Take Screenshot using Headless Chromium
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            context = browser.new_context(viewport={"width": 1920, "height": 1080})
            page = context.new_page()

            # Navigate to your layout and wait 5 seconds for indicators to render
            page.goto(CHART_URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(5000)

            page.screenshot(path=screenshot_file)
            browser.close()

        # 2. Build Discord Payload
        payload = {
            "embeds": [{
                "title": f"🚨 {ticker} SCALPER BOT 🚨",
                "color": embed_color,
                "fields": [
                    {"name": "Event Type", "value": str(action).upper(), "inline": True},
                    {"name": "Price", "value": str(price), "inline": True},
                    {"name": "Trade Execution Details", "value": details, "inline": False}
                ],
                "image": {"url": f"attachment://{screenshot_file}"}
            }]
        }

        # 3. Send to Discord with the Image attached
        with open(screenshot_file, "rb") as img:
            files = {"file": (screenshot_file, img, "image/png")}
            requests.post(
                DISCORD_WEBHOOK_URL,
                data={"payload_json": json.dumps(payload)},
                files=files
            )

    except Exception as e:
        print(f"Screenshot Error: {e}")
        # Fallback: Send text only if the browser somehow fails
        fallback_payload = {
            "embeds": [{
                "title": f"🚨 {ticker} SCALPER BOT 🚨",
                "color": embed_color,
                "description": "*(Screenshot capture failed, but trade logged)*",
                "fields": [
                    {"name": "Event Type", "value": str(action).upper(), "inline": True},
                    {"name": "Price", "value": str(price), "inline": True},
                    {"name": "Trade Execution Details", "value": details, "inline": False}
                ]
            }]
        }
        requests.post(DISCORD_WEBHOOK_URL, json=fallback_payload)

    finally:
        # Clean up the local image file
        if os.path.exists(screenshot_file):
            os.remove(screenshot_file)


@app.route('/webhook', methods=['POST'])
def tradingview_webhook():
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON payload"}), 400

        ticker = data.get("ticker", "UNKNOWN")
        action = data.get("action", "ALERT UPDATE")
        price = data.get("price", "0.00")
        details = data.get("details", "No details")

        embed_color = 3066993  # Green
        if "Loss" in details or "🛑" in details:
            embed_color = 15158332  # Red
        elif "Profit" in details or "✅" in details:
            embed_color = 3066993  # Green

        # START BACKGROUND THREAD (Instantly bypasses the 3-second limit)
        threading.Thread(
            target=process_alert_in_background,
            args=(ticker, action, price, details, embed_color)
        ).start()

        # Instantly reply to TradingView so it knows the webhook was successful
        return jsonify({"status": "success", "message": "Screenshot processing in background"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 400


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)