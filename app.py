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
    """Takes a fullscreen, zoomed-out screenshot and sends a formatted plain-text signal."""
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

            # Wait for indicators to paint
            page.wait_for_timeout(8000)

            # TRICK 1: Press Shift+F to force TradingView into Fullscreen Mode
            page.keyboard.press("Shift+F")
            page.wait_for_timeout(1500)

            # TRICK 2: Zoom out the chart by pressing Ctrl+Down Arrow 5 times
            for _ in range(5):
                page.keyboard.press("Control+ArrowDown")
                page.wait_for_timeout(200)  # Brief pause so TradingView registers each zoom step

            # Take the cropped and zoomed-out screenshot
            page.screenshot(path=screenshot_file)
            browser.close()
            print("Screenshot captured successfully!")

        # 2. Build the COPYABLE plain-text signal
        # This replaces "SL:" with "**SL:**" and "TP:" with "**TP:**" so they appear bold in Discord
        formatted_details = details.replace("SL:", "**SL:**").replace("TP:", "**TP:**")

        signal_text = (
            f"**PAIR:** {ticker}\n"
            f"**ACTION:** {str(action).upper()}\n"
            f"**ENTRY:** {formatted_details}"
        )

        payload = {
            "content": signal_text
        }

        # 3. Send text and image to Discord
        with open(screenshot_file, "rb") as img:
            files = {"files[0]": (screenshot_file, img, "image/png")}
            requests.post(
                DISCORD_WEBHOOK_URL,
                data={"payload_json": json.dumps(payload)},
                files=files
            )
            print("Successfully sent signal to Discord.")

    except Exception as e:
        print(f"Screenshot Error: {e}")
        # Fallback text format
        formatted_details = details.replace("SL:", "**SL:**").replace("TP:", "**TP:**")
        fallback_text = (
            f"**PAIR:** {ticker}\n"
            f"**ACTION:** {str(action).upper()}\n"
            f"**ENTRY:** {formatted_details}\n"
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