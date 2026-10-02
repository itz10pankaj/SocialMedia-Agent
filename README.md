# 🚀 Personal Social Media Agent

An autonomous, **100% local AI agent** that discovers trending engineering topics (Hacker News, Reddit, GitHub, RSS), ranks them against your personal tech stack, crafts high-engagement LinkedIn posts using a **local LLM (Ollama)**, emails you for 1-click mobile approval, and publishes directly to LinkedIn.

Zero cloud AI API fees. Zero data leaks. Complete control.

---

```mermaid
flowchart TD
    A[Sources: HN, Reddit, GitHub, RSS] -->|Collect 250+ Trends| B(Ranking Engine)
    B -->|Filter Stack Keywords & Deduplicate| C{Top Trending Topic}
    C -->|Local LLM: Ollama qwen2.5| D[Generate Draft LinkedIn Post]
    D -->|Gmail SMTP| E[Email Notification to Your Phone]
    E --> F{Your Mobile Email Reply}
    F -->|Reply 'YES' / 'APPROVE'| G[Publish to LinkedIn REST API]
    F -->|Reply 'NO' / 'REJECT'| H[Auto-Draft Next Trending Topic]
    F -->|Reply with Feedback| I[Ollama Rewrites Post & Re-sends Email]
```

---

## ✨ Features

- **🌐 Multi-Source Trend Ingestion:** Fetches real-time tech news from:
  - **Hacker News:** Top developer stories with threshold filtering.
  - **Reddit:** Top daily discussions (`r/node`, `r/javascript`, `r/LocalLLaMA`, etc.).
  - **GitHub:** Trending repositories and fast-growing projects.
  - **Curated RSS Feeds:** Official Node.js blog, Hugging Face, GitHub Blog, Dev.to.
- **🎯 Stack-Aware Relevance Engine:** Filters and scores stories matching your stack keywords (Node.js, TypeScript, AI Agents, MCP, LLMs, etc.). Automatically avoids stories you have posted about in the last 14 days.
- **🤖 100% Local LLM Generation:** Uses **Ollama** (e.g., `qwen2.5:3b` or `llama-3.2:3b`). Automatically unloads the model from RAM after drafting to preserve your laptop's memory.
- **📱 Human-in-the-Loop Mobile Review (Zero App Install):**
  - **Reply `YES`**: Publishes to LinkedIn immediately.
  - **Reply `NO`**: Automatically generates an alternative draft on the next trending topic.
  - **Reply with instructions** (e.g., *"Make it punchier and emphasize TypeScript"*): Ollama rewrites the post and emails back a revised preview.
  - **Edit directly in email body**: Directly publishes your edited version.
- **💻 Desktop & Laptop Wake Automation:** Automatically triggers when you turn on your laptop, log in, unlock, or open your laptop lid in the morning.
- **🖥️ Live Console Monitor:** Runs in a dedicated, formatted Command Prompt window with real-time progress indicators, draft previews, and inbox status.
- **🗄️ Robust MySQL Persistence:** Complete historical tracking of every pipeline run, every fetched article, and every generated draft.
- **⚡ REST API & Swagger UI:** Includes a FastAPI dashboard to preview trends, inspect drafts, or trigger manual runs anytime.

---

## 📋 Prerequisites

Before setting up, make sure your machine has:

1. **Python 3.11+** installed ([python.org](https://www.python.org/downloads/)) — ensure **"Add Python to PATH"** is checked during installation.
2. **Node.js & npm** (v18+) installed ([nodejs.org](https://nodejs.org/)) — used for convenient shortcut scripts (`npm start`, `npm run draft`, etc.).
3. **MySQL Server 8.0+** running locally (or XAMPP / Docker / Remote MySQL).
4. **Ollama** installed ([ollama.com](https://ollama.com/download)).
5. **Gmail Account** with 2-Step Verification enabled (to generate a 16-character **App Password**).
6. **LinkedIn Developer Account** (for official LinkedIn API posting access).

---

## 🛠️ Step-by-Step Installation Guide

### Step 1: Clone the Repository

Open Command Prompt or PowerShell and clone the project:

```bash
git clone https://github.com/itz10pankaj/SocialMedia-Agent.git
cd SocialMedia-Agent
```

---

### Step 2: Set Up Python Virtual Environment

Create and activate a virtual environment, then install dependencies:

#### Windows (cmd / PowerShell):
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

*(Or simply run `npm run install:py` if you have Node.js installed).*

---

### Step 3: Install & Prepare Ollama

1. Download and install Ollama from [ollama.com](https://ollama.com).
2. *(Optional)* By default, Ollama stores models on drive `C:`. If you want to store models on another drive (e.g. `E:`), set the environment variable:
   ```powershell
   [Environment]::SetEnvironmentVariable('OLLAMA_MODELS', 'E:\OllamaModels', 'User')
   ```
3. Start Ollama and pull your desired lightweight LLM (we recommend `qwen2.5:3b` for fast, high-quality generation on standard laptops):
   ```bash
   ollama pull qwen2.5:3b
   ```
4. Verify Ollama is running:
   ```bash
   curl http://localhost:11434/api/version
   ```

---

### Step 4: Create MySQL Database

Open MySQL command line, MySQL Workbench, or phpMyAdmin:

```sql
CREATE DATABASE IF NOT EXISTS social_agent CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

---

### Step 5: Configure Environment Variables (`.env`)

Copy `.env.example` to `.env`:

```bash
copy .env.example .env
```

Open `.env` in your text editor and fill in your credentials:

```ini
# --- Local LLM (Ollama) ---
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
OLLAMA_FALLBACK_URL=http://localhost:11434
OLLAMA_FALLBACK_MODEL=qwen2.5:3b

# --- Database (MySQL) ---
# Note: If your password contains special characters like '@', URL-encode them (e.g. '@' becomes '%40')
DATABASE_URL=mysql+pymysql://root:YOUR_PASSWORD@localhost:3306/social_agent?charset=utf8mb4

# --- Gmail Review & Mobile Approval ---
GMAIL_ADDRESS=your_email@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
NOTIFY_EMAIL=your_email@gmail.com

# --- LinkedIn REST API ---
LINKEDIN_CLIENT_ID=your_linkedin_client_id
LINKEDIN_CLIENT_SECRET=your_linkedin_client_secret
LINKEDIN_ACCESS_TOKEN=your_linkedin_access_token
LINKEDIN_PERSON_URN=
```

#### How to get Gmail App Password:
1. Go to [Google Account Security](https://myaccount.google.com/security).
2. Enable **2-Step Verification**.
3. Search for **"App Passwords"** in the top search bar.
4. Name it `Social Agent` and click **Create**.
5. Copy the 16-character generated password (e.g., `abcd efgh ijkl mnop`) into `GMAIL_APP_PASSWORD`.

#### How to get LinkedIn API Access Token:
1. Go to the [LinkedIn Developer Portal](https://www.linkedin.com/developers/) and create an App.
2. In the **Products** tab, request access to:
   - **Share on LinkedIn** (`w_member_social`)
   - **Sign In with LinkedIn using OpenID Connect** (`openid`, `profile`, `email`)
3. Use the Developer Portal **OAuth 2.0 Tools** to generate an Access Token with `w_member_social` permission.
4. Paste the token into `LINKEDIN_ACCESS_TOKEN`.
5. *(Leave `LINKEDIN_PERSON_URN` empty — the agent will automatically detect your person URN!)*.

---

### Step 6: Customize Your Profile & Keywords (`config.yaml`)

Open `config.yaml` to adjust the agent to your technical domain:

```yaml
profile:
  role: "Software developer working with Node.js and AI agents"
  tone: "friendly, practical, opinionated but humble; short paragraphs; no buzzword soup"

# Keywords the agent scans for (case-insensitive)
stack_keywords:
  - node
  - javascript
  - typescript
  - ai agents
  - mcp
  - llm
  - ollama

sources:
  hackernews:
    enabled: true
    min_points: 40
  reddit:
    enabled: true
    subreddits: [node, javascript, typescript, LocalLLaMA, AI_Agents]
  github:
    enabled: true
    queries:
      - "topic:ai-agents"
      - "topic:nodejs"
  rss:
    enabled: true
    feeds:
      - https://nodejs.org/en/feed/blog.xml
      - https://huggingface.co/blog/feed.xml

ranking:
  top_n: 8              # Top articles forwarded to Ollama
  avoid_repeat_days: 14 # Never reuse URLs from the last 14 days

post:
  min_words: 150
  max_words: 250
  hashtags: 3
```

---

## 🚀 How to Run the Agent

Choose the mode that best fits your workflow:

### Mode 1: One-Click Desktop Runner (Easiest)
Run the batch file directly:
```bash
scripts\run_agent.bat
```
*(Or double-click the **Personal Social Agent** shortcut created on your Desktop).*

A live, styled Command Prompt window will open displaying:
- Connection & Ollama readiness check
- Real-time trend collection from all sources
- Ollama draft generation progress
- Instant **Draft Preview box**
- Live Gmail inbox listener waiting for your mobile approval reply

---

### Mode 2: Auto-Pilot (Runs on Boot & Laptop Lid Open)
Configure the agent to automatically wake up with your laptop:

1. Right-click [`scripts/setup_autostart.bat`](file:///e:/PersonalSocialAgent/scripts/setup_autostart.bat) and choose **"Run as Administrator"** (or double-click and accept the Windows UAC elevation prompt).
2. This configures:
   - **Windows Startup Shortcut:** Automatically launches the live runner when your computer boots or you log in.
   - **Windows Task Scheduler:** Registers `PersonalSocialAgentTask` to automatically wake and run whenever you **open your laptop lid from sleep** or **unlock your screen**.
   - **Desktop Shortcut:** Adds a quick launcher icon to your Desktop.

To uninstall auto-start anytime, right-click and run [`scripts/remove_autostart.bat`](file:///e:/PersonalSocialAgent/scripts/remove_autostart.bat).

---

### Mode 3: Terminal One-Off Test Run
To test the pipeline immediately in your terminal and print the generated draft:

```bash
npm run draft
```
*(Or run `.venv\Scripts\python.exe -m app.orchestrator --force`)*.

---

### Mode 4: Web API & Interactive Documentation
Start the FastAPI server:

```bash
npm start
```
- Open **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health check:** `GET /health`
- **View latest drafts:** `GET /drafts`
- **Inspect ranked trends:** `GET /trends`
- **Run pipeline on demand:** `POST /run?force=true`

---

## 📱 Mobile Review & Approval Workflow

Once the agent generates today's draft, you will receive an email on your phone with the subject:
> **[Personal Social Agent] Daily Post Draft #X for <Date>**

You can review and control everything directly from your Gmail mobile app:

| What you reply in email | What the Agent does |
|---|---|
| **`YES`**, **`APPROVE`**, **`OK`**, **`POST`** | Immediately publishes the post to your LinkedIn profile and marks the draft `POSTED`. |
| **`NO`**, **`REJECT`**, **`CANCEL`** | Rejects the draft, automatically picks the *next* best trending topic, and emails you an **Alternative Draft** (up to 3 per day). |
| **Revision Feedback** *(e.g. "Make the hook punchier, focus on performance")* | Ollama rewrites the post incorporating your feedback and sends back an updated preview email. |
| **Direct Post Edits** *(15+ words)* | Updates the draft with your exact edits and immediately publishes to LinkedIn. |

---

## ⌨️ NPM Command Reference

All primary commands are mapped in `package.json` for rapid execution:

| Command | Purpose |
|---|---|
| `npm run auto` | Launches the live console auto-runner (`app.auto_runner`) |
| `npm run draft` | Runs the pipeline once via CLI, bypassing the once-per-day lock |
| `npm start` | Starts the production FastAPI server on port 8000 |
| `npm run dev` | Starts the FastAPI server with auto-reload for development |
| `npm run autostart:setup` | Sets up Task Scheduler (Lid open/Wake) and Startup shortcuts |
| `npm run autostart:remove` | Completely uninstalls auto-start shortcuts and tasks |
| `npm run ollama:status` | Checks if Ollama server is up and lists models in RAM |
| `npm run ollama:unload` | Frees laptop RAM by unloading the active Ollama model |
| `npm run ollama:start` | Launches the Ollama tray service |
| `npm run ollama:stop` | Terminates Ollama background processes |

---

## 📂 Project Structure

```text
PersonalSocialAgent/
├── app/
│   ├── collectors/          # Multi-source data extractors
│   │   ├── github.py        # GitHub search & trending repos
│   │   ├── hackernews.py    # Hacker News top stories
│   │   ├── reddit.py        # Reddit RSS multi-subreddit reader
│   │   └── rss.py           # Custom RSS feed parser
│   ├── auto_runner.py       # Live console auto-runner & sleep/wake handler
│   ├── config.py            # Pydantic settings & config loader
│   ├── db.py                # SQLModel database models & helpers
│   ├── inbox.py             # IMAP email reply listener & AI feedback reviser
│   ├── linkedin.py          # Official LinkedIn REST API publishing client
│   ├── mailer.py            # SMTP HTML draft email sender
│   ├── main.py              # FastAPI web server & endpoints
│   ├── models.py            # Shared data structures (TrendItem, RankItem)
│   ├── orchestrator.py      # Core pipeline: collect -> rank -> write -> draft
│   ├── ranking.py           # Keyword matching & deduplication engine
│   └── writer.py            # Ollama prompt builder & generation logic
├── docs/                    # Technical architecture & code walkthroughs
├── scripts/
│   ├── agent_task.xml       # Windows Task Scheduler XML configuration
│   ├── run_agent.bat        # Styled UTF-8 CMD launcher
│   ├── setup_autostart.bat  # Auto-elevating task installer
│   ├── setup_tasks.ps1      # PowerShell shortcut & scheduler configurator
│   ├── remove_autostart.bat # Uninstaller wrapper
│   └── remove_tasks.ps1     # Cleanup script
├── .env.example             # Template for API keys & secrets
├── config.yaml              # Domain keywords, sources, & generation rules
├── package.json             # NPM task runner definitions
└── requirements.txt         # Python dependencies
```

---

## ❓ Troubleshooting & FAQs

### 1. "Ollama is not running / Connection refused"
- Make sure Ollama is running in your taskbar.
- Run `npm run ollama:start` or launch `ollama app.exe`.
- Test reachability with: `curl http://localhost:11434/api/version`.

### 2. "MySQL Access Denied or Connection Failed"
- Verify MySQL service is active (`Get-Service *mysql*` in PowerShell).
- If your password has an `@` or `#`, URL-encode it (e.g., `P@ssword` $\rightarrow$ `P%40ssword`).
- Confirm database exists: `CREATE DATABASE social_agent;`.

### 3. "Gmail Authentication / IMAP Error"
- Make sure you are using an **App Password**, NOT your regular Google account password.
- Verify 2-Step Verification is active on your Google account.
- In Gmail Settings $\rightarrow$ Forwarding and POP/IMAP, ensure **IMAP Access** is enabled.

### 4. "Wake from Sleep / Lid Open is not triggering"
- Windows requires Administrator rights to register Event Triggers on the System event log.
- Right-click [`scripts/setup_autostart.bat`](file:///e:/PersonalSocialAgent/scripts/setup_autostart.bat) and select **"Run as Administrator"**.
- Verify registration by running: `schtasks /query /TN "PersonalSocialAgentTask"`.

### 5. "Another instance is already running"
- The agent includes OS-level single-instance file locking (`.auto_runner.lock`).
- If an agent window is already open, new instances exit automatically to prevent duplicate posts or conflicting model requests.

---

## 📄 License

This project is licensed under the MIT License — feel free to customize and use it for your personal or commercial brand automation!
