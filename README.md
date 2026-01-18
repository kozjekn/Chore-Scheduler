# Simple Chores Scheduler
This is simple house chore scheduler with Google Sheets as database for home tasks.

## Dev Setup
1. Install Node.js (`v24.13.0`)
2. `cd frontend` && `npm install`
   1. Run frontent with command `npm run dev`
3. From root of project create virtual python env
    ``` bash
    python3 -m venv ./.venv
    ```
4. Install requirements
   ```bash
    ./.venv/bin/pip install -r requirements.txt
   ```
   > Use `source .venv/bin/activate` to always run from virtual enviroment
5. Setup enviroment variables
   Copy `.env.example` to `.env` and setup env varaiables
   ```bash
   cp .env.example .env
   ```
6. Setup IDE 
   ```bash
   cp ./misc/.vscode ./.vscode
   ```
   1. Run with vs code debugger
7. Open http://localhost:5173/


## Google Cloud Setup

### Generate API credentials (`creds.json`)
1. Go to the [Google Cloud Console](https://console.cloud.google.com/welcome?project=protean-chassis-476607-n8).
2. Create a new project.
3. Enable the Google Sheets API and Google Drive API.
4. Create a Service Account:
   - Go to Credentials -> Create Credentials -> Service Account.
   - Download the JSON key file. Rename it to creds.json.
5. Share your Spreadsheet:
   - Open your Google Sheet.
   - Click "Share" and paste the client_email found inside your creds.json file. Give it Editor access.

### Genarate e-mail password for app
1. Enable 2FA: Ensure 2-Step Verification is turned ON in your [Google Account Security settings](https://myaccount.google.com/security).
2. Generate App Password:
   - Search for "App Passwords" in the search bar at the top of your Google Account page.
   - App Name: Call it "Chore Manager" or "Python Script".
   - Click Create.
   - Google will give you a 16-character code (e.g., abcd efgh ijkl mnop).


## Docker container creation
1. Build image
   ```
   docker build -t nejek16/chore-manager:latest .
   ```
2. Push to Docker Hub
   ```
   docker push nejc198/chore-manager:latest
   ```

### Docker Compose Example
```yaml
version: '3.8'
services:
  app:
    image: nejc198/chore-manager:latest
    container_name: chore-app
    ports:
      - "8000:8000"
    volumes:
      - ./creds.json:/app/creds.json
    env_file:
      - .env
    restart: always
```
> Note that `creds.json` file should to be created from [Google Cloud Console](https://console.cloud.google.com/welcome?project=protean-chassis-476607-n8) (look up at docs for more info) 
