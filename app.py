import os
import json
import threading
import requests
from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright

app = Flask(__name__)

# Environment Variables
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1538899048839258162/LQ79MbfFTVkI7vlFNbmdkoLu4u_puQRCqr8IVS-NYyoXMVZ3MnpALYjEdJjm2xTHmELN")
CHART_URL = os.environ.get("TV_CHART_URL", "https://tr.tradingview.com/chart/0pL1VjCl/?symbol=FX%3AEURUSD")


def process_alert_in_background(ticker, action, price, details, embed_color):
    """Background task to load TradingView, take a screenshot, and send to Discord."""
    screenshot_file = f"chart_{ticker}.png"

    try:
        # 1. Launch Playwright Headless Browser
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            context = browser.new_context(viewport={"width": 1920, "height": 1080})
            page = context.new_page()

            # 2. Go to the chart layout (using "load" to bypass WebSocket timeouts)
            print(f"Loading chart for {ticker}...")
            page.goto(CHART_URL, wait_until="load", timeout=60000)

            # Wait exactly 8 seconds for the candles and indicators to fully paint
            page.wait_for_timeout(8000)

            # Take the screenshot
            page.screenshot(path=screenshot_file)
            browser.close()
            print("Screenshot captured successfully!")

        # 3. Build the Discord Embed Payload
        payload = {
            "embeds": [{
                "title": f"🚨 {ticker} SCALPER BOT 🚨",
                "color": embed_color,
                "fields": [
                    {"name": "Event Type", "value": str(action).upper(), "inline": True},
                    {"name": "Price", "value": str(price), "inline": True},
                    {"name": "Trade Execution Details", "value": details, "inline": False}
                ],
                "image": {"url": f"attachment://{screenshot_file}"},
                "footer": {"text": "Powered by PyCharm & Playwright"}
            }]
        }

        # 4. Send to Discord
        with open(screenshot_file, "rb") as img:
            # 'files[0]' is the standard Discord API key for multipart form data uploads
            files = {"files[0]": (screenshot_file, img, "image/png")}

            response = requests.post(
                DISCORD_WEBHOOK_URL,
                data={"payload_json": json.dumps(payload)},
                files=files
            )
            response.raise_for_status()
            print("Successfully sent image to Discord.")

    except Exception as e:
        print(f"Screenshot Error: {e}")
        # Fallback: Send text only with the exact error message so we know what went wrong
        fallback_payload = {
            "embeds": [{
                "title": f"🚨 {ticker} SCALPER BOT 🚨",
                "color": embed_color,
                "description": f"*(Screenshot capture failed: {e})*",
                "fields": [
                    {"name": "Event Type", "value": str(action).upper(), "inline": True},
                    {"name": "Price", "value": str(price), "inline": True},
                    {"name": "Trade Execution Details", "value": details, "inline": False}
                ]
            }]
        }
        requests.post(DISCORD_WEBHOOK_URL, json=fallback_payload)

    finally:
        # 5. Clean up the image file from Railway's server memory
        if os.path.exists(screenshot_file):
            os.remove(screenshot_file)


@app.route('/webhook', methods=['POST'])
def tradingview_webhook():
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON payload received"}), 400

        # Extract data from TradingView
        ticker = data.get("ticker", "UNKNOWN")
        action = data.get("action", "ALERT UPDATE")
        price = data.get("price", "0.00")
        details = data.get("details", "No details")

        # Determine embed color: Red for Loss, Green for Profit/Entries
        embed_color = 3066993  # Green
        if "Loss" in details or "🛑" in details:
            embed_color = 15158332  # Red
        elif "Profit" in details or "✅" in details:
            embed_color = 3066993  # Green

        # Hand the heavy lifting to the background thread
        threading.Thread(
            target=process_alert_in_background,
            args=(ticker, action, price, details, embed_color)
        ).start()

        # Instantly return 200 OK so TradingView's 3-second timer doesn't sever the connection
        return jsonify({"status": "success", "message": "Webhook received. Screenshot processing in background."}), 200

    except Exception as e:
        print(f"Webhook Error: {e}")
        return jsonify({"error": str(e)}), 400


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)