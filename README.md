# KKP Fireworks Catalogue — Railway deployment

Mobile-friendly Python/Flask catalogue based on the supplied KKP Diwali 2026 price list. It includes all 139 products across 12 categories, product search, category filters, quantity selection, estimated totals, customer details, and PDF order receipts.

The home page footer says **Created by Aditya Maganbhai Patel**.

## Deploy to Railway

1. Extract this ZIP on your computer.
2. Create a GitHub repository and upload the **contents** of this folder (do not upload only the ZIP file).
3. Open https://railway.app and create a new project from that GitHub repository.
4. Wait for Railway to deploy the app. The included `railway.json` uses Gunicorn and configures `/health` as a health check.
5. In Railway, open your app service → **Settings / Variables** and add:
   - `ORDER_DATA_DIR` = `/app/data`
6. Open the service's **Volumes** section and add a Volume mounted at exactly:
   - `/app/data`
7. Generate a public domain for the service from Railway's networking/domain settings.
8. Open the generated URL and test by submitting a sample order. Confirm that the PDF downloads and the order is stored.

**Important:** create and mount the Volume at `/app/data` before relying on live orders. Without a persistent Volume, local files can be lost when the container is replaced.

## What is saved

- Each submitted order PDF is saved to `/app/data/orders/<ORDER_ID>_order.pdf`.
- Order history and customer/order details are stored in `/app/data/orders.sqlite3` (SQLite).
- The customer also receives a PDF download in their browser.
- The app does **not** create `order.json` files.

The PDF is an order request, not proof of stock availability or a completed sale. Confirm stock and final prices with the customer.

## Local test

Python 3.12 is recommended.

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000. By default, local order files are stored in `./data`. To test the same path as Railway, set `ORDER_DATA_DIR=/app/data` before starting the app.

## Files

- `app.py` — Flask routes, PDF generation, persistent order storage
- `products.json` — product catalogue and prices
- `templates/index.html` — page template
- `public/style.css`, `public/app.js` — design and browser behavior
- `railway.json`, `Procfile` — Railway/Gunicorn startup configuration

## Data and security notes

The SQLite database and PDFs are stored on the mounted Volume. This is suitable for a single Railway app instance; avoid multiple replicas writing to the same SQLite database. Back up important order data periodically. This app does not include an admin/login screen to browse stored orders; the PDF files and database remain on the Volume.
