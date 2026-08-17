import os
import json
import threading
import requests
from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright

app = Flask(__name__)

# Environment Variables
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "YOUR_DISCORD_WEBHOOK_HERE")
CHART_URL = os.environ.get("TV_CHART_URL", "https://tr.tradingview.com/chart/0pL1VjCl/?symbol=FX%3AEURUSD")


def process_alert_in_background(ticker, action, price, details):
    """Takes a fullscreen screenshot and sends a highly copyable raw text message."""
    screenshot_file = f"chart_{ticker}.png"

    try:
        # 1. Launch Playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            context = browser.new_context(viewport={"width": 1920, "height": 1080})
            page = context.new_page()

            print(f"Loading chart for {ticker}...")
            page.goto(CHART_URL, wait_until="load", timeout=60000)

            # Wait exactly 8 seconds for the candles and strategy boxes to fully paint
            page.wait_for_timeout(8000)

            # TRICK: Press Shift+F to force TradingView into Fullscreen Mode
            # This instantly hides the watchlist, top menu, and drawing panels
            page.keyboard.press("Shift+F")
            page.wait_for_timeout(1500)  # Wait a brief moment for the zoom animation to finish

            # Take the cropped screenshot
            page.screenshot(path=screenshot_file)
            browser.close()
            print("Screenshot captured successfully!")

        # 2. Build the COPYABLE plain-text signal (No Embed Cards)
        signal_text = (
            f"**PAIR:** {ticker}\n"
            f"**ACTION:** {str(action).upper()}\n"
            f"**PRICE:** {price}\n"
            f"**DETAILS:** {details}"
        )

        payload = {
            "content": signal_text
        }

        # 3. Send text and image to Discord
        with open(screenshot_file, "rb") as img:
            files = {"files[0]": (screenshot_file, img, "image/png")}

            response = requests.post(
                DISCORD_WEBHOOK_URL,
                data={"payload_json": json.dumps(payload)},
                files=files
            )
            response.raise_for_status()
            print("Successfully sent signal to Discord.")

    except Exception as e:
        print(f"Screenshot Error: {e}")
        # Fallback text if the screenshot somehow fails
        fallback_text = (
            f"**PAIR:** {ticker}\n"
            f"**ACTION:** {str(action).upper()}\n"
            f"**PRICE:** {price}\n"
            f"**DETAILS:** {details}\n"
            f"*(Screenshot capture failed: {e})*"
        )
        requests.post(DISCORD_WEBHOOK_URL, json={"content": fallback_text})

    finally:
        # 4. Clean up local file
        if os.path.exists(screenshot_file):
            os.remove(screenshot_file)


@app.route('/webhook', methods=['POST'])
def tradingview_webhook():
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON payload received"}), 400

        ticker = data.get("ticker", "UNKNOWN")
        action = data.get("action", "ALERT UPDATE")
        price = data.get("price", "0.00")
        details = data.get("details", "No details")

        # Start the background screenshot thread
        threading.Thread(
            target=process_alert_in_background,
            args=(ticker, action, price, details)
        ).start()

        return jsonify({"status": "success", "message": "Signal processing"}), 200

    except Exception as e:
        print(f"Webhook Error: {e}")
        return jsonify({"error": str(e)}), 400


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)