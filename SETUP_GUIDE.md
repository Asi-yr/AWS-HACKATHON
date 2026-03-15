# 🚀 SafeRoute Project - Setup & Testing Guide

## 📋 Prerequisites
- Python 3.8+ installed
- Git configured
- Flutter SDK (for mobile app testing)

---

## 🌐 **Web Backend Setup (Flask)**

### **For Windows Users:**

```powershell
# 1. Change to project directory
cd path\to\hehehackachoas

# 2. Create virtual environment
py -m venv .venv

# 3. Activate virtual environment
.venv\Scripts\Activate.ps1

# 4. Install dependencies
py -m pip install -r requirements.txt

# 5. Run Flask backend
py main.py
```

Backend runs at: **http://localhost:5000**

### **For macOS/Linux Users:**

```bash
# 1. Change to project directory
cd /path/to/hehehackachoas

# 2. Create virtual environment
python3 -m venv .venv

# 3. Activate virtual environment
source .venv/bin/activate

# 4. Install dependencies
python3 -m pip install -r requirements.txt

# 5. Run Flask backend
python3 main.py
```

Backend runs at: **http://localhost:5000**

---

## 🔑 **API Key Setup (Google AI)**

### **Why?**
The project uses Google GenAI for intelligent safety analysis. You need an API key for the grounding tool feature.

### **Steps:**

1. **Visit Google AI Studio**
   - Go to: https://aistudio.google.com
   - Sign in with your personal account

2. **Create API Key**
   - Click "Get API key" in the navigation menu
   - Select "Create API key" for this project
   - Copy the generated API key

3. **Create `.env` File**
   - Navigate to: `grounding_tool/` folder
   - Create a new file named `.env`
   - Add this line:
   ```
   exclusive_genai_key=YOUR_API_KEY_HERE
   ```
   - Replace `YOUR_API_KEY_HERE` with your copied API key
   - Save the file

⚠️ **Important:** The `.env` file is ignored by git (see `.gitignore`). Never commit API keys to the repository.

---

## 📱 **Mobile App Setup (Flutter)**

### **Prerequisites:**
- Android Studio with Flutter SDK
- Android Emulator (API 24+) or connected device

### **Steps:**

```bash
# 1. Navigate to Flutter app
cd ligtas_app

# 2. Get dependencies
flutter pub get

# 3. Run app
flutter run

# OR for release build
flutter build apk --release
```

### **Backend Configuration:**
Edit `ligtas_app/lib/core/api_client.dart` - Line 20:

```dart
// For Android Emulator (connects to host machine)
static const String baseUrl = 'http://10.0.2.2:5000';

// For iOS Simulator or Real Device
// static const String baseUrl = 'http://192.168.1.X:5000'; // Use your machine's LAN IP
```

---

## ✅ **Testing Checklist**

### **Backend Tests**
- [ ] Start Flask: `py main.py` (Windows) or `python3 main.py` (macOS)
- [ ] Check backend is running: Visit http://localhost:5000 in browser
- [ ] Test registration: `POST /api/auth/register` with JSON
- [ ] Test settings: `GET /api/settings` with Bearer token
- [ ] Test report: `POST /api/report` with JSON

### **Frontend Tests**
- [ ] Start Android Emulator
- [ ] Run Flutter app: `flutter run`
- [ ] Register new account
- [ ] Complete survey onboarding
- [ ] Submit a community report
- [ ] Check profile settings sync

### **End-to-End Test**
1. Register on mobile app
2. Complete survey → Settings should load from backend
3. Go to Profile → Toggle settings → Should sync to backend
4. Go to Community → Submit report → Should appear in backend database

---

## 🗂️ **Project Structure**

```
hehehackachoas/
├── .venv/                   ← Python virtual environment (NOT committed)
├── .env                     ← Environment variables (NOT committed)
├── .gitignore              ← Git ignore rules (COMMITTED)
├── main.py                 ← Flask backend entry point
├── requirements.txt        ← Python dependencies
├── ligtas_app/             ← Flutter mobile app
│   ├── lib/
│   │   ├── core/
│   │   │   ├── api_client.dart      ← API calls
│   │   │   └── session_manager.dart ← Auth tokens
│   │   └── screens/
│   └── pubspec.yaml        ← Flutter dependencies
├── risk_monitor/           ← Safety data modules
├── grounding_tool/         ← AI grounding features
│   └── .env               ← API key (NOT committed)
├── static/                 ← Static web files
└── templates/              ← HTML templates
```

---

## 🛑 **Troubleshooting**

### **Error: ModuleNotFoundError: No module named 'flask'**
- Make sure virtual environment is activated
- Windows: `.venv\Scripts\Activate.ps1`
- macOS: `source .venv/bin/activate`

### **Error: Address already in use (Port 5000)**
- Flask is already running somewhere
- Windows: `netstat -ano | findstr :5000` then kill process
- macOS: `lsof -ti:5000 | xargs kill -9`

### **Error: Android emulator cannot reach backend**
- Ensure using `http://10.0.2.2:5000` (not `localhost`)
- Check firewall isn't blocking port 5000

### **Error: Missing API key for AI features**
- Follow API Key Setup above
- Ensure `.env` is in `grounding_tool/` folder
- Restart Flask after adding `.env`

---

## 📝 **.gitignore - What Gets Ignored**

These files/folders are automatically excluded from git commits:

- `venv/`, `.venv/` - Virtual environments
- `__pycache__/` - Python cache
- `*.pyc`, `*.db` - Compiled and database files
- `.env` - Environment variables and API keys ⚠️
- `*.bck`, `*.backup` - Backup files
- `.DS_Store`, `Thumbs.db` - OS files
- IDE files (`.vscode/`, `.idea/`)

✅ This ensures no accidental commits of sensitive files or large environments.

---

## 🔄 **Git Workflow**

### **After Making Changes:**

```bash
# 1. Check status
git status

# 2. Add files (only core code, NOT venv or .env)
git add .

# 3. Commit
git commit -m "Your commit message"

# 4. Push to repository
git push origin tetsing
```

✅ The `.gitignore` file automatically excludes unnecessary files from being added.

---

## 📞 **Support**

If you encounter issues:
1. Check this guide first
2. Verify all prerequisites are installed
3. Ensure virtual environment is activated
4. Check API key is properly configured
5. Review error messages carefully

Good luck! 🚀
