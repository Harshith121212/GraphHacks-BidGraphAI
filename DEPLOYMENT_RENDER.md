# BidGraphAI — Render Deployment Guide

Deploy **BidGraphAI** to **Render** (https://render.com) with low-latency managed graph queries on **FalkorDB Cloud** and autonomous cognitive reasoning powered by **NVIDIA Nemotron 3.5**.

---

## Architecture Overview

```
                      Internet (HTTPS / SSL by Render)
                                     │
                                     ▼
                ┌──────────────────────────────────────────┐
                │ Render Web Service (https://*.onrender.com)│
                │ ───────────────────────────────────────  │
                │ • FastAPI REST API & Single-Port Server  │
                │ • Static Frontend Command Center         │
                │ • FastMCP stdio Subsystem                │
                │ • NVIDIA Nemotron 3.5 (OpenRouter)       │
                └────────────────────┬─────────────────────┘
                                     │ (Encrypted TLS / Port 6379)
                                     ▼
                ┌──────────────────────────────────────────┐
                │ FalkorDB Cloud (https://app.falkordb.cloud)│
                │ ───────────────────────────────────────  │
                │ • Managed Graph Database                 │
                │ • Indian Tender & Client Multi-Hop Graph │
                │ • Low-Latency Managed In-Memory Graph    │
                └──────────────────────────────────────────┘
```

---

## Step 1: Create a Free FalkorDB Cloud Database

1. Sign up or log in at **[FalkorDB Cloud Console](https://app.falkordb.cloud)**.
2. Click **Create Database** and select the free tier instance.
3. Under **Connection Details**, copy:
   * **Host**: e.g. `instance-xxx.falkordb.cloud`
   * **Port**: `6379` (or specified port)
   * **Password**: Your database password
   * **SSL**: `true` (enabled by default on cloud)

---

## Step 2: Deploy with Render Blueprint (1-Click Recommended)

BidGraphAI includes a native `render.yaml` blueprint for automatic configuration.

1. **Push your repository** to your GitHub account:
   ```bash
   git add .
   git commit -m "Configure BidGraphAI for Render deployment"
   git push origin main
   ```

2. Go to **[Render Dashboard](https://dashboard.render.com/)**.
3. Click **New +** (top right) and select **Blueprint**.
4. Connect your **BidGraphAI** repository.
5. Render detects `render.yaml` and displays the service definition.
6. Provide your environment parameters when prompted:
   * `FALKORDB_HOST`: Your FalkorDB Cloud host endpoint
   * `FALKORDB_PORT`: `6379`
   * `FALKORDB_PASSWORD`: Your FalkorDB Cloud password
   * `FALKORDB_SSL`: `true`
   * `AUTO_SEED`: `true`
   * `OPENROUTER_API_KEY_ALPHA`: Your OpenRouter API Key (NVIDIA Nemotron 3.5)
   * `OPENROUTER_API_KEY_BETA`: Your OpenRouter API Key
7. Click **Apply**.
8. Render will build the container, verify database connectivity, auto-seed the benchmark graph, and deploy your live dashboard!

---

## Step 3: Manual Deployment (Alternative to Blueprint)

If you prefer setting up manually via the Render UI:

1. In the Render Dashboard, click **New +** -> **Web Service**.
2. Select your GitHub repository.
3. Configure the service settings:
   * **Name**: `bidgraph-ai`
   * **Region**: Choose closest to your database (e.g. `Oregon (US West)` or `Frankfurt (EU Central)`)
   * **Branch**: `main`
   * **Runtime**: `Docker`
   * **Dockerfile Path**: `./Dockerfile`
   * **Instance Type**: `Free` or `Starter`
4. Add the following **Environment Variables**:

| Variable | Value | Description |
| :--- | :--- | :--- |
| `PORT` | `10000` | Port for web traffic (Render sets this automatically) |
| `AUTO_SEED` | `true` | Seeds benchmark tenders & 12 contractors on boot |
| `FALKORDB_HOST` | `your-db.falkordb.cloud` | FalkorDB Cloud host |
| `FALKORDB_PORT` | `6379` | FalkorDB port |
| `FALKORDB_PASSWORD` | `your_password` | FalkorDB password |
| `FALKORDB_SSL` | `true` | Enable TLS for cloud connections |
| `FALKORDB_GRAPH_NAME` | `tender_intel_graph` | Graph name |
| `OPENROUTER_MODEL` | `nvidia/nemotron-3.5-super-vl:free` | Free Nemotron model |
| `OPENROUTER_API_KEY_ALPHA` | `your_key` | Primary reasoning key |
| `OPENROUTER_API_KEY_BETA` | `your_key` | Secondary reasoning key |
| `DEFAULT_ALERT_EMAIL` | `hackathon-demo@outlook.com` | Alert recipient address |

5. Under **Health Check Path**, enter: `/api/health`.
6. Click **Create Web Service**.

---

## Step 4: Verify Deployment

Once the deployment finishes (typically 2-3 minutes):

1. **Inspect Logs**: In the Render dashboard, open the **Logs** tab. You should see:
   ```text
   =================================================================
      BidGraphAI: FalkorDB + MCP Tender Intelligence Engine        
   =================================================================
   [1/3] Verifying FalkorDB connectivity...
   >> FalkorDB connected successfully.
   [2/3] AUTO_SEED=true: Initializing benchmark graph & Indian tender data...
   >> Seeding benchmark graph completed.
   [3/3] Launching FastAPI server & Frontend Dashboard on 0.0.0.0:10000...
   INFO: Uvicorn running on http://0.0.0.0:10000
   ```
2. **Access Dashboard**: Click your live URL (e.g. `https://bidgraph-ai.onrender.com`).
3. **Test Autonomous Actions**:
   * Click **Run AI Tender Matching** to trigger the dual-agent matching loop.
   * View the **JV Consortium Hub** tab to review syndicate pairings and the 5-stage decision tree.
   * Open the **Interactive Graph Explorer** on the right pane to navigate live nodes and relationships.

---

## Optional: Custom Domain & Free SSL

Render provides automatic SSL certificates for custom domains:
1. In Render, navigate to **Settings** -> **Custom Domains**.
2. Click **Add Custom Domain** and enter your domain (e.g., `tenders.yourcompany.com`).
3. Add the `CNAME` record provided by Render to your DNS provider (Cloudflare, GoDaddy, Namecheap, etc.).
4. Render will automatically issue a Let's Encrypt SSL certificate within a few minutes.
