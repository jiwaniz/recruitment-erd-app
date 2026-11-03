# Deployment guide: GitHub, free MySQL and Streamlit Community Cloud

Last checked against the providers' documentation on 30 October 2026. Free tiers change, so confirm the limits
on the pages linked at the end before you rely on them.

**What was tested and what was not.** The application and the sample-data loader were tested on a local database.
Nothing could be deployed to GitHub, Aiven or Streamlit from where this project was written, so steps 4 to 7 below
(accounts, cloud database, cloud app) have not been run by the author. Follow the checklist in step 7 to verify.

## Overview

```
Your laptop (local MySQL)  --->  same code  <---  GitHub repo  --->  Streamlit Community Cloud (public URL)
                                                                           |
                                                                           v
                                                              Aiven for MySQL (free tier, separate database)
```
Your local database is never exposed to the internet. The cloud app talks only to the cloud database.

## 0. Do you need a cloud database at all?

Only if you want a **public URL**. Streamlit Community Cloud runs your app on Streamlit's own servers. Those servers cannot
reach `localhost` on your laptop, and you should never open your laptop's MySQL port to the internet. So a public version
needs a database that is also online. Your options:

| Goal | What to use | Needs a cloud database? |
|---|---|---|
| Show the supervisor in person or on a screen-share | Run the app locally (`streamlit run app.py`) | No |
| Supervisor opens a link while your laptop is on | A tunnel such as Cloudflare Tunnel or ngrok pointing at the local app (your DB stays on your laptop) | No |
| A link that works any time, without your laptop | Streamlit Community Cloud + a cloud MySQL (this guide) | **Yes** |

The project brief asks for Streamlit Community Cloud, so the rest of this guide covers that route. If you do not need an
always-available link, the local option is simpler and has nothing to expire.

## 1a. Aiven: "30-day trial" is not the same as the free plan

Aiven has two separate things, and sign-up pages mostly advertise the first:

* **Free trial:** 30 days of credits for *paid* services. It ends after 30 days.
* **Free tier (what this guide uses):** a small MySQL service with **no time limit and no credit card**.
  Per Aiven's pricing page (updated 27 Oct 2026) it can be used "indefinitely free of charge" and keeps running after the
  trial ends. Aiven reserves the right to power it off when idle (with a notice; you can turn it back on), and to change its
  region or configuration. "No time limit" is therefore not a permanent guarantee.

When you create the service, choose the **Free** plan, not a plan paid with trial credits. If a plan asks you to add a
payment card, you are on the wrong plan. If Aiven's free plan is not available to you, use the fallback in section 1 or the
local / tunnel options above. Always keep a local copy of the SQL scripts so you can recreate the database anywhere.

## 1. Free MySQL hosting: recommendation

**Recommended: Aiven for MySQL, free plan** (real MySQL, no credit card).

| Item | Facts from Aiven's documentation |
|---|---|
| Resources | 1 node, 1 CPU, 1 GB RAM, 1 GB storage, backups included |
| Cost / card | Free, no credit card, no time limit |
| Connections | `max_connections` limited to 76 (the app uses at most 10 per running instance) |
| Inactivity | **Aiven may power the service off after a period of no activity** (you get a notice). You power it on again in the console. |
| Network | Public endpoint, TLS required, **no static IPs** (so you cannot restrict access to the app's IP; leave the allowed-IP list at its default) |
| Limits | One free MySQL service per organization, no support, no SLA, Aiven may change region or configuration |
| Source | https://aiven.io/docs/products/mysql/concepts/mysql-free-tier (page updated 5 Aug 2026) |

**Fallback: TiDB Cloud Starter** (no credit card, free monthly quota). It speaks the MySQL protocol and works with
PyMySQL and this code, but it is **MySQL-compatible, not MySQL**. Use it only if Aiven is not available to you.
Its free allowance is published as 5 GiB row storage per cluster for the first five clusters (https://docs.pingcap.com/tidbcloud/select-cluster-tier);
third-party sites quote different numbers, so check the page.
Do not use PostgreSQL: the application and the SQL are written for MySQL.

## 2. Run the app locally first
Follow the README ("Run it on your computer"). Do not continue until the local app works.

## 3. Put the project on GitHub

1. Create an account at https://github.com and click **New repository**. Name: `recruitment-erd-app`.
   Choose **Public** if you will use a free Streamlit account (Community Cloud can also deploy private repos after you authorise it).
   Do not add a README (the project already has one).
2. Install Git for Windows (https://git-scm.com). In the project folder:
   ```
   git init
   git add .
   git status
   ```
   **Check `git status`**: `.env` and `.streamlit/secrets.toml` must NOT be listed. If they are, stop and check `.gitignore`.
   ```
   git commit -m "Recruitment ERD application"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/recruitment-erd-app.git
   git push -u origin main
   ```
   Git asks you to sign in to GitHub in a browser window the first time.
3. If you ever commit a password by mistake, change the password immediately. Deleting the file later does not remove it from history.

## 4. Create the free cloud MySQL database (Aiven)

1. Sign up at https://console.aiven.io (no credit card).
2. **Create service** > **MySQL** > choose the **Free** plan and a region > create. Wait until the status is *Running*.
3. On the service overview page note: **Host**, **Port**, **User** (`avnadmin`), **Password**, **Database name** (`defaultdb`), and download the **CA certificate** (`ca.pem`).
4. Load the sample database from your laptop (this uses the admin account once). In PowerShell, in the project folder, with the virtual environment active:
   ```
   $env:DB_HOST="your-host.aivencloud.com"
   $env:DB_PORT="12345"
   $env:DB_NAME="defaultdb"
   $env:DB_USER="avnadmin"
   $env:DB_PASSWORD="the-admin-password"
   $env:DB_SSL_CA="C:\path\to\ca.pem"
   python scripts/load_sample_database.py
   ```
   Expected output: `29 statements`, `63 statements`, then `Sample database loaded.`
   (Environment variables set this way last only for that PowerShell window and are not saved in any file.)
5. Create the limited account the web app will use. Connect with any MySQL client as `avnadmin`
   (for example `mysql --ssl-ca=ca.pem -h HOST -P PORT -u avnadmin -p defaultdb`) and run the two statements in
   `scripts/create_app_user.sql`, using `defaultdb` as the database name and a new strong password.
6. Prove the cloud database is reachable by the app account: run `python scripts/inspect_db.py` with the same
   variables but `DB_USER=rms_app` and its password. You should see 29 tables and no integrity violations.

## 5. Prepare the Streamlit secrets
Create the text below (do not save it inside the repository). Generate each `password_hash` with `python scripts/make_password_hash.py`.
Create at least an admin for you and a read-only `viewer` for your supervisor.

```toml
[mysql]
host = "your-host.aivencloud.com"
port = 12345
name = "defaultdb"
user = "rms_app"
password = "the-rms_app-password"
ssl_ca = """-----BEGIN CERTIFICATE-----
...contents of ca.pem...
-----END CERTIFICATE-----"""

[users.admin]
password_hash = "pbkdf2_sha256$..."
role = "admin"
display_name = "Your Name"

[users.supervisor]
password_hash = "pbkdf2_sha256$..."
role = "viewer"
display_name = "Supervisor"
```
`.streamlit/secrets.toml.example` in the project is a template for this.

## 6. Deploy on Streamlit Community Cloud
Official documentation: https://docs.streamlit.io/deploy/streamlit-community-cloud

1. Go to https://share.streamlit.io and sign in with GitHub. Authorise access to your repository when asked.
2. Click **Create app** > **Deploy a public app from GitHub**.
3. Repository: `YOUR_USERNAME/recruitment-erd-app`. Branch: `main`. **Main file path: `app.py`.**
4. Open **Advanced settings**: choose Python **3.12**, and paste the TOML from step 5 into **Secrets**.
5. Click **Deploy**. The first build installs `requirements.txt` and takes a few minutes. Watch the logs ("Manage app").
6. To change secrets later: app menu > **Settings** > **Secrets**. Pushing code to `main` redeploys automatically.

## 7. Verify the deployment (do all of these)
- [ ] The public URL (`https://<your-app>.streamlit.app`) shows the login page.
- [ ] Open it in a private/incognito window and on your phone (use mobile data, not your home Wi-Fi) to prove it is public.
- [ ] A wrong password is rejected; the admin login works.
- [ ] Sidebar > **About** shows *Online* and 29 tables with row counts.
- [ ] Dashboard shows numbers. Reports > any report > **Download CSV** works.
- [ ] Add a test candidate, then find them under Candidates > Browse (writes work). Delete the test candidate (admin).
- [ ] Log in as the `viewer` user: add/edit tabs show "read-only".
- [ ] Nothing secret appears in the repository (search GitHub for your password).

## 8. Share with your supervisor
Send the URL and the `viewer` username and password (separately, for example by two different messages).
Before a demonstration:
1. **Open the Aiven console and make sure the MySQL service is *Running*** (power it on if it was switched off for inactivity).
2. **Open the app URL 10 minutes early.** Community Cloud puts apps to sleep after a period without visitors
   (currently about 12 hours according to the docs); anyone can wake it with the "get this app back up" button.
3. Have the screenshots or a local copy ready in case the internet fails.

## 9. Free-tier limits to know about

| Service | Limit | What to do |
|---|---|---|
| Streamlit Community Cloud | App sleeps after about 12 hours without traffic; roughly 0.078 to 2 CPU cores and 690 MB to 2.7 GB RAM; limits may change without notice | Visit the app before a demo; keep data sets small |
| Aiven free MySQL | May power off after inactivity; 1 GB storage; 76 connections; no static IP | Power it on from the console; do not store large files |
| Both | Free tiers can change or end | Keep a local copy of the database and the SQL scripts |

## 10. Troubleshooting

| Message | Likely cause and fix |
|---|---|
| "The application cannot reach the MySQL database" | Cloud database powered off (start it in Aiven), wrong host/port, or wrong password in Secrets. The page shows the technical error underneath. |
| `Access denied for user` | Wrong user/password, or the `GRANT` statement was not run for that database name. |
| `SSL connection error` / certificate verify failed | `ssl_ca` missing or incomplete. Paste the whole certificate including the BEGIN/END lines. |
| `Unknown database` | `name` in Secrets does not match (Aiven's default is `defaultdb`). |
| "No users are configured yet" | The `[users.*]` sections are missing from Secrets. |
| ModuleNotFoundError in the cloud logs | A package is missing from `requirements.txt`. |
| App shows "Oh no" | Resource limit reached; reboot the app from Manage app. |

## Sources
* Aiven for MySQL free tier: https://aiven.io/docs/products/mysql/concepts/mysql-free-tier
* Aiven free plans overview: https://aiven.io/docs/platform/concepts/free-plan
* Streamlit Community Cloud, manage your app (limits, sleeping): https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app
* TiDB Cloud Starter (fallback): https://docs.pingcap.com/tidbcloud/select-cluster-tier
