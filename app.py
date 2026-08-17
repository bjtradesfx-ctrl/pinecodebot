import os
import requests
from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright

app = Flask(__name__)

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1538899048839258162/LQ79MbfFTVkI7vlFNbmdkoLu4u_puQRCqr8IVS-NYyoXMVZ3MnpALYjEdJjm2xTHmELN")
# Replace with your shared TradingView chart layout URL
CHART_URL = os.environ.get("TV_CHART_URL", "https://tr.tradingview.com/chart/0pL1VjCl/?symbol=FX%3AEURUSD")


def take_chart_screenshot(output_path="chart.png"):
    """Launches a headless browser to capture the live TradingView chart."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Create a browser context with high resolution
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        # Load your chart URL
        page.goto(CHART_URL, wait_until="networkidle")
        # Allow extra time for indicators and candles to render
        page.wait_for_timeout(3000)

        # Save screenshot
        page.screenshot(path=output_path)
        browser.close()
    return output_path


@app.route('/webhook', methods=['POST'])
def tradingview_webhook():
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No JSON payload received"}), 400

        ticker = data.get("ticker", "XAUUSD")
        action = data.get("action", "ALERT UPDATE")
        price = data.get("price", "0.00")
        details = data.get("details", "No details provided")

        # Set embed color: Red for Loss, Green for Profit/Entries
        embed_color = 3066993  # Green
        if "Loss" in details or "🛑" in details:
            embed_color = 15158332  # Red
        elif "Profit" in details or "✅" in details:
            embed_color = 3066993  # Green

        # Take screenshot of the chart
        screenshot_file = "chart.png"
        take_chart_screenshot(screenshot_file)

        # Build Discord payload referencing the uploaded image
        payload = {
            "embeds": [{
                "title": f"🚨 {ticker} SCALPER BOT 🚨",
                "color": embed_color,
                "fields": [
                    {"name": "Event Type", "value": str(action).upper(), "inline": True},
                    {"name": "Price", "value": str(price), "inline": True},
                    {"name": "Trade Execution Details", "value": details, "inline": False}
                ],
                "image": {"url": "attachment://chart.png"},
                "footer": {"text": "Powered by PyCharm & Playwright"}
            }]
        }

        # Send multipart request with the image file attached
        with open(screenshot_file, "rb") as img:
            files = {
                "file": ("chart.png", img, "image/png")
            }
            response = requests.post(
                DISCORD_WEBHOOK_URL,
                data={"payload_json": requests.compat.json.dumps(payload)},
                files=files
            )
            response.raise_for_status()

        # Clean up local screenshot file
        if os.path.exists(screenshot_file):
            os.remove(screenshot_file)

        return jsonify({"status": "success", "message": "Signal + Screenshot sent to Discord!"}), 200

    except Exception as e:
        print(f"Error processing webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)