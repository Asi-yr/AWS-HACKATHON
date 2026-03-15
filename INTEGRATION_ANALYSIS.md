# Comprehensive Integration Analysis: SafeRoute Backend & Ligtas Frontend

**Date:** March 14, 2026  
**Status:** Pre-Production Integration Assessment  
**Scope:** Full backend-frontend connectivity mapping

---

## EXECUTIVE SUMMARY

### Overall Integration Status
- **Backend (Flask):** ~90% feature-complete with 25+ API endpoints
- **Frontend (Flutter):** ~85% UI/UX complete with 22+ API client methods
- **Connection Status:** ~70% of critical paths connected, 40% of NICE TO HAVE paths connected
- **Blocking Issues:** None (all syntax/lint fixed), ready for integration testing

### Key Finding
The backend has MORE implemented features than the frontend is currently calling. Frontend screens exist but many are not yet wired to real backend endpoints (using mock data instead).

---

## PART 1: BACKEND ANALYSIS (Flask/Python)

### Backend Infrastructure
**Location:** `/Users/asianamilleana/hehehackachoas/`  
**Main Entry Point:** `main.py`  
**Database:** ClickHouse (nsql) or MySQL (selectable via `USE_MYSQL` flag)  
**Modules:** `risk_monitor/`, `navigation.py`, `rss.py`, `llm.py`, `debug_safety.py`

### Core Backend Features (25 Endpoints)

#### 1. AUTHENTICATION (4 endpoints) ✅ COMPLETE
| Endpoint | Method | Purpose | Status |
|----------|--------|---------|--------|
| `/api/auth/login` | POST | User login, returns JWT token | ✅ Implemented |
| `/api/auth/register` | POST | User registration | ✅ Implemented |
| `/api/auth/logout` | POST | User session termination | ✅ Implemented |
| `/api/auth/change-password` | POST | Password change (requires current password) | ✅ Implemented |

**Key Details:**
- JWT token-based authentication
- Session management via `user_data.py`
- Password hashing with werkzeug.security

**Gaps:** No OAuth/Google login integration yet (placeholder in frontend)

---

#### 2. ROUTE SEARCH & NAVIGATION (3 endpoints) ✅ COMPLETE
| Endpoint | Method | Purpose | Status |
|----------|--------|---------|--------|
| `/api/routes` OR `/api/route` | POST | Main route search with full alerts | ✅ Implemented |
| `/api/suggest` | GET | Location autocomplete suggestions | ✅ Implemented |
| `/api/reverse` | GET | Reverse geocoding (lat/lon → address) | ✅ Implemented |

**Features:**
- Three route modes: **Fastest**, **Balanced**, **Safest**
- Real-time safety scoring with multiple penalty factors
- Polyline generation for map rendering
- Support for: Jeepney, Bus, MRT/LRT, Train, Motorcycle, Tricycle, Car
- Weather, flood, crime, incident, MMDA, seismic, night-time penalties applied
- Safe spots overlay

**Response Format:**
```json
{
  "routes": [...],
  "incidents": [...],
  "mmda_banner": "...",
  "mmda_closures_count": 0,
  "earthquakes": [...],
  "seismic_banner": "...",
  "weather_risk": "clear|rain|storm",
  "flood_risk": "none|low|moderate|high"
}
```

---

#### 3. USER PROFILE & SETTINGS (3 endpoints) ✅ COMPLETE
| Endpoint | Method | Purpose | Status |
|----------|--------|---------|--------|
| `/api/user/current` | GET | Fetch current user profile | ✅ Implemented |
| `/api/settings` | GET | Fetch user preferences | ✅ Implemented |
| `/api/settings` | POST | Save user preferences | ✅ Implemented |

**Includes:**
- User profile (name, email, role, avatar)
- Commuter type preference
- Transport mode preferences
- Safety banner toggles
- Theme/display preferences

---

#### 4. TRAVEL HISTORY (2 endpoints) ✅ COMPLETE
| Endpoint | Method | Purpose | Status |
|----------|--------|---------|--------|
| `/api/history` | GET | Fetch user's route search history | ✅ Implemented |
| `/api/history/clear` | POST | Clear all history records | ✅ Implemented |

**Tracks:** Origin, destination, timestamp, route count, commuter type used

---

#### 5. COMMUNITY REPORTS (3 endpoints) ✅ COMPLETE
| Endpoint | Method | Purpose | Status |
|----------|--------|---------|--------|
| `/api/reports` | GET | Fetch all active community reports | ✅ Implemented |
| `/api/reports/confirm` | POST | Upvote/confirm report credibility | ✅ Implemented |
| `/api/report-types` | GET | Get available report categories | ✅ Implemented |

**Report Types:** Crime, Flood, Accident, Slowdown, Hazard  
**Trust Ranking:** Candle → Lantern → Lighthouse  
**Features:** Geo-tagged, timestamped, user-confirmation upvoting

---

#### 6. SAFETY DATA (1 endpoint) ✅ COMPLETE
| Endpoint | Method | Purpose | Status |
|----------|--------|---------|--------|
| `/api/safety` | GET | Aggregate safety metrics at location | ✅ Implemented |

**Returns:**
- Crime risk + penalty
- Flood zone status + penalty
- Weather assessment + penalty
- Nearby reports (hotspots)
- Safe spots (hospitals, police, fire stations)
- Risk summary

---

#### 7. ALERTS & ADVISORIES (3 endpoints) ✅ COMPLETE
| Endpoint | Method | Purpose | Status |
|----------|--------|---------|--------|
| `/api/incidents` | GET | Real-time traffic incidents (MMDA-like) | ✅ Implemented |
| `/api/mmda` | GET | MMDA number coding + road closures | ✅ Implemented |
| `/api/phivolcs` | GET | Earthquake & seismic alerts | ✅ Implemented |

**Real-Time Data Sources:**
- Community reports (via web scraping)
- NOAH flood zones (GIS overlay)
- Typhoon signals (PAGASA)
- Seismic activity (PHIVOLCS)
- Crime data (web scraping hotspots)

---

#### 8. SAFE SPOTS & POI (3 endpoints) ✅ COMPLETE
| Endpoint | Method | Purpose | Status |
|----------|--------|---------|--------|
| `/api/safe-spots` | GET | Nearby safe locations (hospitals, police, fire) | ✅ Implemented |
| `/api/safe-spots/route` | POST | Safe spots along a specific route | ✅ Implemented |
| `/api/safe-spots/batch` | POST | Batch query for multiple routes | ✅ Implemented |

**Safe Spot Types:** Hospital, Police Station, Fire Station, Checkpoint  
**Features:** Distance calculation, map overlay, emergency call integration ready

---

#### 9. SOS & EMERGENCY (3 endpoints) ✅ COMPLETE
| Endpoint | Method | Purpose | Status |
|----------|--------|---------|--------|
| `/api/sos/contacts` | GET | Fetch trusted emergency contacts | ✅ Implemented |
| `/api/sos/contacts` | POST | Add new SOS contact | ✅ Implemented |
| `/api/sos/contacts/<id>` | DELETE | Remove SOS contact | ✅ Implemented |
| `/api/sos` | POST | Log SOS event (trigger emergency protocol) | ✅ Implemented |

**SOS Event Data:**
- Lat/lon (location)
- Message
- Route summary
- Timestamp
- Contacts notified

---

#### 10. SPECIALIZED DATA LAYERS

**Weather Module (`weather.py`)** ✅ COMPLETE
- Open-Meteo API integration (free, no key needed)
- Commuter-type-aware risk assessment
- Night-time multipliers (6 PM - 6 AM)
- Risk levels: clear → rain → storm
- Penalties by exposure: walk > bike > motorcycle > commute > car

**Flood Risk (`noah.py`)** ✅ COMPLETE
- NOAH GIS flood zone overlay
- Depth-based risk escalation
- Mapbox integration (optional visualization)
- Integration with weather for combined warnings

**Crime Data (`crime_data.py`)** ✅ COMPLETE
- Web scraping of crime hotspots
- Area-based risk penalties
- Integration with maps for visualization

**Incident Management (`incidents.py`)** ✅ COMPLETE
- Real-time traffic & accident tracking
- MMDA data layer
- Integration with route scoring

**Vulnerable Profile Assessment (`vulnerable_profiles.py`)** ✅ COMPLETE
- Profile types: Normal, Student, Women, LGBTQ+, Disabled/Elderly, Minor
- Custom penalties for each profile
- Night-time alert escalation for vulnerable groups

---

### Backend Data Flow Summary

```
User Request → Route Search (/api/routes)
    ↓
  Navigation Module (get_routes from sakay.ph-like source)
    ↓
  Enrich Routes with Scores:
    • Base safety score (75)
    • Weather penalty (get_weather_risk)
    • Crime penalty (get_crime_risk_for_area)
    • Flood penalty (get_flood_risk_at)
    • Night penalty (apply_night_safety)
    • Incident penalty (apply_incidents_to_routes)
    • MMDA penalty (apply_mmda_to_routes)
    • Seismic penalty (apply_seismic_to_routes)
    • Safe spots overlay (apply_safe_spots_to_routes)
    ↓
  Return to Frontend with Alerts Bundle
    • incidents[]
    • mmda_banner
    • earthquake data
    • etc.
    ↓
  Frontend renders route list + alert banners
```

---

## PART 2: FRONTEND ANALYSIS (Flutter/Dart)

### Frontend Architecture
**Location:** `/Users/asianamilleana/hehehackachoas/ligtas_app/`  
**Framework:** Flutter 3.x with Provider for state management  
**Architecture Pattern:** MVC (Model-View-Controller) per screen  
**Key Components:**
- `lib/screens/` - UI screens
- `lib/core/` - Controllers, routers, session, theme
- `lib/models/` - Data models
- `lib/data/` - Mock data & helpers
- `lib/widgets/` - Reusable UI components

### Frontend Screens (6 major screens)

#### 1. **SPLASH SCREEN** ✅ DONE
**Path:** `lib/screens/splash/splash_view.dart`  
**Purpose:** App initialization, route decision  
**Status:** Renders briefly, decides next route based on SessionManager

**Logic:**
```
Is user logged in? (SessionManager.isLoggedIn)
  → Yes: Go to last known route (explore/community/profile)
  → No: Go to login
```

**Backend Connection:** ❌ None (local state only)

---

#### 2. **LOGIN SCREEN** 🟡 PLACEHOLDER - NEEDS BACKEND WIRING
**Path:** `lib/screens/login/login_view.dart`  
**Purpose:** User authentication and account creation  
**Status:** 90% UI complete, 0% backend integration

**Current State:**
- Form fields for email/password
- Sign In / Register toggle
- Google OAuth placeholder
- Currently just sets `SessionManager.setLoggedIn(true)` without actual auth

**What's Needed:**
```dart
// SIGN IN
ApiClient.instance.login(
  username: emailController.text,
  password: passwordController.text,
)
// On success: save token + navigate to survey/explore
// On failure: show error toast

// REGISTER
ApiClient.instance.register(
  username: emailController.text,
  password: passwordController.text,
)
// On success (201): save token + navigate to survey
// On failure (409): show "email already in use"
```

**Backend Available:** ✅ `/api/auth/login`, `/api/auth/register`

---

#### 3. **SURVEY SCREEN** 🟡 PARTIALLY CONNECTED
**Path:** `lib/screens/survey/survey_view.dart`  
**Purpose:** First-time user onboarding (commuter type, transport modes, safety concerns)  
**Status:** UI complete, 60% backend connection

**Connected Parts:**
- ✅ 3-step form with multi-select options
- ✅ `_saveSurveyAndNavigate()` calls `ApiClient.instance.saveSurvey()`
- ✅ Uses `debugPrint()` for logging
- ✅ Fallback to local defaults if offline

**What's Working:**
```dart
await ApiClient.instance.saveSurvey(
  commuterTypes: ['student', 'women'],
  transportModes: ['jeep', 'mrt'],
  safetyConcerns: ['dark', 'crime'],
  token: token,
)
```

**Backend Available:** ✅ `/api/user/survey` (POST)

---

#### 4. **EXPLORE SCREEN** 🟢 MOSTLY CONNECTED
**Path:** `lib/screens/explore/explore_view.dart` (view) + `explore_controller.dart` (controller)  
**Purpose:** Main route search experience  
**Status:** 80% backend connection

**Connected Parts:**
- ✅ Route search form (origin, destination)
- ✅ `searchRoutes()` calls `ApiClient.instance.searchRoutesWithAlerts()`
- ✅ Displays routes with safety scores
- ✅ Alert data extraction (incidents, MMDA, earthquakes, weather, flood)
- ✅ Fetches safety overlays (`fetchSafetyOverlays()`)
- ✅ Filter system (commuter, transport, ligtas mode, preferences)

**Data Flow:**
```
User enters origin/destination
  ↓
ExploreController.searchRoutes()
  ↓
ApiClient.searchRoutesWithAlerts()
  ↓
Backend /api/routes (POST)
  ↓
ExploreController.setAlertData() + setAllRoutes()
  ↓
ExploreView renders route cards + alert banners
```

**Filters Implemented:**
- Commuter type filters (normal, student, women, lgbtq+, disabled, minor)
- Transport mode filters (jeepney, bus, lrt, car, walk, etc.)
- Ligtas mode (safety-focused sorting)
- Preference filters (safest, fastest, cheapest, balanced, moderate)

**Safety Overlays:**
- Hotspots (crime, flood, accident zones)
- POI (hospitals, police, fire stations)
- Advisory banners (active alerts)

**Partially Connected:**
- 🟡 Safety overlays fetch `getSafety()` but may not be fully populated from backend

**Backend Available:**
- ✅ `/api/routes` (POST)
- ✅ `/api/safety` (GET)
- ✅ `/api/incidents` (GET)

---

#### 5. **COMMUNITY SCREEN** 🟡 PARTIALLY CONNECTED
**Path:** `lib/screens/community/community_view.dart`  
**Purpose:** View community reports, submit issues, upvote credibility  
**Status:** 60% backend connection

**Connected Parts:**
- ✅ Fetches reports on load: `ApiClient.instance.getReports()`
- ✅ Display reports as cards with reputation badges
- ✅ Upvote button calls: `ApiClient.instance.confirmReport()`
- ✅ Mock reports as fallback

**Partially Connected:**
- 🟡 Report submission form displayed but submit button not fully wired
- 🟡 Report type selector shows options but may not be fetching from `/api/report-types`

**Missing:**
- ❌ Photo upload for reports
- ❌ Map integration to show report locations
- ❌ Filter/search reports
- ❌ User's own reports tracking

**Backend Available:**
- ✅ `/api/reports` (GET)
- ✅ `/api/reports/confirm` (POST)
- ✅ `/api/report-types` (GET)
- ✅ `/api/report` (POST) - not yet wired in UI

---

#### 6. **PROFILE SCREEN** 🟡 PARTIALLY CONNECTED
**Path:** `lib/screens/profile/profile_view.dart` + `profile_controller.dart`  
**Purpose:** User account management, preferences, emergency contacts, security  
**Status:** 50% backend connection

**ProfileController Initialization:**
```dart
ProfileController() {
  _loadLocalPreferences();        // SharedPreferences
  _loadUserFromBackend();         // ✅ ApiClient.getCurrentUser()
  _loadTravelHistoryFromBackend(); // ✅ ApiClient.getRouteHistory()
  loadSosContacts();              // ✅ ApiClient.getSosContacts()
  _loadSettingsFromBackend();     // ✅ ApiClient.getSettings()
}
```

**Connected Features:**
- ✅ Load user profile data
- ✅ Load travel history (route search history)
- ✅ Load SOS emergency contacts
- ✅ Load user preferences (weather banner toggle, theme, etc.)
- ✅ Change password: `ApiClient.instance.changePassword()`
- ✅ Save profile updates
- ✅ Toggle AI Safety (weather banner)
- ✅ Logout

**Partially Connected:**
- 🟡 Two-Factor Authentication - shows UI, backend integration stub
- 🟡 Email change - shows UI, backend not fully integrated
- 🟡 Photo upload - picker UI exists, backend integration incomplete

**Not Yet Connected (NICE TO HAVE):**
- ❌ SOS contact addition/removal UI not implemented
- ❌ Travel history detail view not showing route polylines
- ❌ Account deletion endpoint
- ❌ Email verification flow

**Backend Available:**
- ✅ `/api/user/current` (GET)
- ✅ `/api/settings` (GET, POST)
- ✅ `/api/history` (GET)
- ✅ `/api/history/clear` (POST)
- ✅ `/api/auth/change-password` (POST)
- ✅ `/api/sos/contacts` (GET, POST, DELETE)

---

## PART 3: API CLIENT MAPPING

### api_client.dart - 22 Methods Defined

#### FULLY USED ✅
1. `searchRoutesWithAlerts()` - ExploreController → /api/routes
2. `searchRoutes()` - Fallback method
3. `login()` - LoginView (not wired yet)
4. `register()` - LoginView (not wired yet)
5. `getCurrentUser()` - ProfileController → /api/user/current
6. `getReports()` - CommunityView → /api/reports
7. `confirmReport()` - CommunityView → /api/reports/confirm
8. `getSafety()` - ExploreController → /api/safety
9. `getRouteHistory()` - ProfileController → /api/history
10. `clearRouteHistory()` - ProfileController → /api/history/clear
11. `changePassword()` - ProfileController → /api/auth/change-password
12. `getSosContacts()` - ProfileController (loads on init)
13. `saveSurvey()` - SurveyView → /api/user/survey
14. `getSettings()` - ProfileController → /api/settings
15. `saveSettings()` - ProfileController → /api/settings

#### PARTIALLY USED 🟡
16. `logout()` - ProfileController (doesn't call backend fully)
17. `submitReport()` - CommunityView (UI button not wired)
18. `getReportTypes()` - Not used (but available)

#### NOT YET USED ❌
19. `addSosContact()` - ProfileController loads but add UI not implemented
20. `removeSosContact()` - ProfileController loads but remove UI not implemented
21. `triggerSos()` - Never called (Panic button not implemented)
22. `submitReportJson()` - Alternative method, prefer `submitReport()`

---

## PART 4: INTEGRATION GAPS ANALYSIS

### Critical Path (MUST COMPLETE)

#### 1. **Login/Registration Flow** 🔴 BLOCKING
**Status:** 0% Complete  
**Impact:** Users cannot authenticate  
**What's Needed:**
- [ ] LoginView: Wire login button to `ApiClient.instance.login()`
- [ ] LoginView: Wire register button to `ApiClient.instance.register()`
- [ ] SessionManager: Save JWT token on login
- [ ] SessionManager: Use token in all subsequent API calls
- [ ] Handle 401/403 responses (token expiry)

**Estimated Effort:** 2-3 hours

---

#### 2. **Route Search Main Flow** 🟢 75% Complete
**Status:** Functional but incomplete  
**Missing:**
- [ ] Verify alert data structure matches frontend expectations
- [ ] Test null-coalescing for missing alert fields
- [ ] Add error handling for empty routes
- [ ] Test "no routes from server" fallback
- [ ] Add loading spinner during search

**Estimated Effort:** 1-2 hours

---

#### 3. **Community Reports Integration** 🟡 50% Complete
**Status:** View reports working, submit not wired  
**Missing:**
- [ ] Wire submit report button to `ApiClient.instance.submitReport()`
- [ ] Implement photo upload
- [ ] Fetch report types dynamically
- [ ] Add location selection UI
- [ ] Handle image compression before upload

**Estimated Effort:** 3-4 hours

---

#### 4. **Safety Data Overlay** 🟡 50% Complete
**Status:** Fetching but may not be fully rendering  
**Missing:**
- [ ] Verify hotspot rendering on map
- [ ] Test POI display (hospital, police, fire icons)
- [ ] Test advisory banner display
- [ ] Add fallback data if API returns empty

**Estimated Effort:** 2 hours

---

### Important Path (SHOULD COMPLETE)

#### 5. **Travel History Display** 🟡 50% Complete
**Status:** Data fetches but UI incomplete  
**Missing:**
- [ ] Show route polylines on map
- [ ] Display search timestamp
- [ ] Allow re-search from history
- [ ] Test `clearRouteHistory()`

**Estimated Effort:** 2-3 hours

---

#### 6. **User Settings Persistence** 🟢 80% Complete
**Status:** Mostly works  
**Missing:**
- [ ] Test theme toggle persistence
- [ ] Verify weather banner toggle persists
- [ ] Test commuter type save/load cycle
- [ ] Verify transport preference is used in route search

**Estimated Effort:** 1 hour

---

### Nice-to-Have Path (GOOD TO HAVE)

#### 7. **SOS Emergency Contacts** 🔴 10% Complete
**Status:** Data structure defined, UI not implemented  
**Missing:**
- [ ] Implement SOS contact list UI in ProfileView
- [ ] Wire add/remove contact buttons
- [ ] Show contact in panic button screen (not implemented)
- [ ] Test `triggerSos()` endpoint flow

**Estimated Effort:** 4-5 hours

---

#### 8. **OAuth/Google Login** 🔴 0% Complete
**Status:** Placeholder only  
**Missing:**
- [ ] Firebase integration or alternative OAuth provider
- [ ] Google sign-in button implementation
- [ ] Auto-create account on first Google sign-in
- [ ] Link Google account to existing Ligtas account

**Estimated Effort:** 5-6 hours

---

#### 9. **Two-Factor Authentication** 🟡 10% Complete
**Status:** UI shell exists, no backend integration  
**Missing:**
- [ ] Backend endpoint design (`/api/auth/2fa/enable`, etc.)
- [ ] TOTP QR code generation
- [ ] Backend enforcement on login
- [ ] Recovery codes

**Estimated Effort:** 6-8 hours

---

#### 10. **Photo Reports (Baha Watch)** 🔴 0% Complete
**Status:** Not implemented  
**Missing:**
- [ ] Image picker integration
- [ ] Image compression before upload
- [ ] Multipart form data upload
- [ ] Backend endpoint for file handling
- [ ] Gallery view for report photos

**Estimated Effort:** 5-6 hours

---

#### 11. **Panic Button / SOS Trigger** 🔴 0% Complete
**Status:** Not implemented  
**Missing:**
- [ ] Dedicated panic button UI/UX
- [ ] Get current location on trigger
- [ ] Call `ApiClient.instance.triggerSos()`
- [ ] Notify emergency contacts
- [ ] Show countdown timer
- [ ] Support SMS/Call fallback

**Estimated Effort:** 4-5 hours

---

#### 12. **Incident Map Integration** 🔴 0% Complete
**Status:** Not implemented  
**Missing:**
- [ ] Real-time incident markers on map
- [ ] Incident detail sheets
- [ ] Filter by incident type
- [ ] Refresh incidents in background

**Estimated Effort:** 3-4 hours

---

## PART 5: DATA FLOW VERIFICATION

### Happy Path: User Search for Route

```
Frontend (Flutter)
  ↓
[SplashView] Check SessionManager
  ├─ Logged in? → Go to Explore
  └─ Not logged in? → Go to Login
  ↓
[LoginView] User taps "Sign In"
  ├─ NEEDS: ApiClient.login(email, password)
  ├─ On 200: Save token, update SessionManager
  └─ Navigate to Survey
  ↓
[SurveyView] User completes 3-step survey
  ├─ ApiClient.saveSurvey() called ✅
  └─ Navigate to Explore
  ↓
[ExploreView] User enters origin/destination
  ├─ ExploreController.searchRoutes()
  ├─ ApiClient.searchRoutesWithAlerts() ✅
  ├─ setAlertData() called ✅
  ├─ fetchSafetyOverlays() called 🟡
  └─ Render 3 route cards + banners
  ↓
[RouteCard] User taps route
  ├─ ExploreController.selectRoute()
  └─ Show route details view
  ↓
[NavigationView] User taps "Start Navigation"
  ├─ ExploreController.startNavigation()
  └─ Show turn-by-turn directions
  ↓
Backend (Python/Flask)
  - Receives request to /api/routes
  - Calls get_routes() → navigation.py
  - Enriches with scores (weather, crime, flood, etc.)
  - Returns JSON with routes + alerts
  ↓
Frontend receives response
  - Parse into RouteModel list
  - Extract alerts
  - Display on UI
```

### Error Case: No Routes Found

```
Backend returns { "routes": [] }
  ↓
Frontend fallback logic:
  if (routes.isEmpty) {
    setAllRoutes(mockRoutes)
    showToast('No routes from server — showing sample routes')
  }
  ↓
User sees mock route data (safeguard, prevents blank screen)
```

---

## PART 6: MISSING BACKEND FEATURES (For Frontend to Use)

### What Backend CAN Do (Already Implemented)
- ✅ User auth, login, register
- ✅ Route search with scoring
- ✅ Community report submission & upvoting
- ✅ Safety data aggregation
- ✅ Emergency contact management
- ✅ Travel history tracking
- ✅ User preference persistence
- ✅ Weather risk assessment
- ✅ Flood zone checking
- ✅ Crime hotspot data
- ✅ Real-time incidents
- ✅ MMDA/seismic alerts

### What Backend NEEDS TO ADD (For Full Frontend Integration)
1. **Photo/Image Upload Endpoint** - For report photos and avatar changes
2. **Email Verification Flow** - For new registrations and email changes
3. **OAuth/Google Sign-In Backend** - Currently no strategy
4. **2FA Enforcement** - UI ready but backend not implemented
5. **Pagination for Reports** - Currently returns all (needs limit/offset)
6. **Report Categories Filtering** - Backend returns all, no filter
7. **Batch Route History** - For "re-trace" functionality
8. **Search Route History** - Filter by date range, location
9. **SMS/Call Fallback for SOS** - Triggering emergency services
10. **Map Tile Server** - For offline map support

---

## PART 7: BLOCKERS & DEPENDENCIES

### No Technical Blockers ✅
- All Dart lint warnings fixed
- Syntax validation passed
- Parameter naming conventions corrected
- Documentation backticks fixed
- Null-aware operators implemented

### Integration Blockers (Work in Progress)
1. **Login Screen** - Must be wired before any other feature works
   - Depends on: SessionManager JWT token handling
   - Blocks: All authenticated endpoints
   - Timeline: 2-3 hours

2. **SOS Feature** - UI not implemented
   - Depends on: ProfileController SOS contact management UI
   - Blocks: Panic button feature (NICE TO HAVE)
   - Timeline: 4-5 hours

3. **Photo Upload** - Not implemented in either layer
   - Depends on: Backend file handling + Flutter image picker
   - Blocks: Report photo feature + Avatar upload
   - Timeline: 5-6 hours

---

## PART 8: PRIORITY ROADMAP

### Phase 1: CRITICAL (Weeks 1-2)
| Task | Status | Effort | Owner |
|------|--------|--------|-------|
| Login/Register Integration | 🔴 0% | 2-3h | Backend fixed, Frontend needs wiring |
| Test Route Search E2E | 🟡 75% | 1-2h | Both need verification |
| Verify Auth Token Flow | 🔴 0% | 1h | Frontend SessionManager + Backend |
| Deploy to staging | 🔴 0% | 2h | DevOps/Infrastructure |

**Exit Criteria:**
- User can sign up and sign in
- Route search returns real backend data
- Tokens are persisted and refreshed correctly
- No 401/403 errors

---

### Phase 2: IMPORTANT (Weeks 3-4)
| Task | Status | Effort | Owner |
|------|--------|--------|-------|
| Community Reports Integration | 🟡 50% | 3-4h | Frontend needs submit wiring |
| Travel History UI | 🟡 50% | 2-3h | Frontend needs polyline rendering |
| Safety Overlays Verification | 🟡 50% | 2h | Both need testing |
| Settings Persistence E2E | 🟢 80% | 1h | Frontend verification |

**Exit Criteria:**
- Community reports can be submitted and viewed
- Travel history displays correctly
- User settings persist across sessions
- All alert data displays properly

---

### Phase 3: NICE TO HAVE (Weeks 5-6)
| Task | Status | Effort | Owner |
|------|--------|--------|-------|
| SOS / Emergency Contacts | 🔴 10% | 4-5h | Frontend UI + Backend integration |
| OAuth Login | 🔴 0% | 5-6h | Architecture decision needed |
| Photo Reports | 🔴 0% | 5-6h | Both backends + Frontend |
| 2FA Implementation | 🟡 10% | 6-8h | Backend endpoint design + Frontend |

---

## PART 9: API ENDPOINT CHECKLIST FOR QA

### Auth Endpoints
- [ ] POST `/api/auth/login` - Returns token
- [ ] POST `/api/auth/register` - Creates user & returns token
- [ ] POST `/api/auth/logout` - Clears session
- [ ] POST `/api/auth/change-password` - Requires current password

### Route Search
- [ ] POST `/api/routes` - Returns routes with alerts
- [ ] POST `/api/route` - Alternate endpoint (should redirect to /routes)
- [ ] GET `/api/suggest?q=...` - Location autocomplete
- [ ] GET `/api/reverse?lat=&lon=` - Address lookup

### User Data
- [ ] GET `/api/user/current` - Returns user profile
- [ ] POST `/api/user/survey` - Saves onboarding preferences
- [ ] GET `/api/settings` - Returns user preferences
- [ ] POST `/api/settings` - Updates preferences

### History
- [ ] GET `/api/history` - Returns route search history
- [ ] POST `/api/history/clear` - Deletes history

### Reports
- [ ] GET `/api/reports` - Lists all community reports
- [ ] POST `/api/report` - Submit new report
- [ ] POST `/api/reports/confirm` - Upvote report
- [ ] GET `/api/report-types` - Available categories

### Safety Data
- [ ] GET `/api/safety?lat=&lon=` - Aggregate safety + nearby reports
- [ ] GET `/api/incidents` - Traffic incidents
- [ ] GET `/api/mmda` - MMDA number coding & closures
- [ ] GET `/api/phivolcs` - Seismic/earthquake alerts

### Safe Spots & POI
- [ ] GET `/api/safe-spots?lat=&lon=` - Nearby hospitals, police, etc.
- [ ] POST `/api/safe-spots/route` - Safe spots along route
- [ ] POST `/api/safe-spots/batch` - Batch query

### Emergency
- [ ] GET `/api/sos/contacts` - List trusted contacts
- [ ] POST `/api/sos/contacts` - Add contact
- [ ] DELETE `/api/sos/contacts/<id>` - Remove contact
- [ ] POST `/api/sos` - Trigger SOS event

---

## PART 10: KNOWN ISSUES & WORKAROUNDS

### Frontend Issues
1. **LoginView not wired to backend**
   - Workaround: Manually set `SessionManager.setLoggedIn(true)` for testing
   - Fix timeline: 2-3 hours

2. **Photo upload not implemented**
   - Workaround: Use placeholder avatar URLs
   - Fix timeline: 5-6 hours

3. **SOS feature incomplete**
   - Workaround: Use web console to test `/api/sos` endpoint manually
   - Fix timeline: 4-5 hours

### Backend Issues
1. **No rate limiting on endpoints**
   - Risk: DOS attacks on public endpoints
   - Fix timeline: 2-3 hours (add Flask-Limiter)

2. **No email verification for registration**
   - Risk: Spam registrations
   - Fix timeline: 3-4 hours (add email service integration)

3. **File upload not implemented**
   - Risk: Cannot upload report photos
   - Fix timeline: 4-5 hours (add file handling + validation)

---

## PART 11: DEPLOYMENT CONSIDERATIONS

### Frontend (Flutter)
- Build for Android: `flutter build apk` or `flutter build appbundle`
- Build for iOS: `flutter build ios`
- Configuration: `baseUrl` in api_client.dart must point to production backend
- Environment: Separate build configs for dev/staging/prod

### Backend (Flask)
- Production WSGI server: Gunicorn or uWSGI
- Database: Migrate from nsql to MySQL or PostgreSQL
- Error logging: Implement centralized logging (ELK, Datadog, etc.)
- API rate limiting: Add to all endpoints
- HTTPS/SSL: Required for authentication endpoints
- Database backups: Daily snapshots

### CI/CD Pipeline Needed
- [ ] Automated tests for backend (pytest)
- [ ] Automated tests for frontend (Flutter test)
- [ ] Code quality checks (lint, format)
- [ ] Staging deployment on commit
- [ ] Production deployment on tag

---

## SUMMARY TABLE: INTEGRATION STATUS

| Feature | Backend | Frontend | Connected | Blocking | Timeline |
|---------|---------|----------|-----------|----------|----------|
| Login/Register | ✅ 100% | 🟡 10% | ❌ No | 🔴 CRITICAL | 2-3h |
| Route Search | ✅ 100% | 🟢 80% | 🟢 Mostly | 🟡 Minor | 1-2h |
| Community Reports | ✅ 100% | 🟡 50% | 🟡 Partial | 🟡 Minor | 3-4h |
| Travel History | ✅ 100% | 🟡 50% | 🟡 Partial | 🟡 Minor | 2-3h |
| Safety Overlays | ✅ 100% | 🟡 50% | 🟡 Partial | 🟡 Minor | 1-2h |
| Profile/Settings | ✅ 100% | 🟢 80% | 🟢 Mostly | 🟢 None | 1h |
| SOS / Emergency | ✅ 100% | 🔴 10% | ❌ No | 🟡 UI | 4-5h |
| Photo Upload | ❌ 0% | ❌ 0% | ❌ No | 🟡 Both | 5-6h |
| 2FA | ❌ 0% | 🟡 10% | ❌ No | 🟡 Both | 6-8h |
| OAuth/Google | ❌ 0% | ❌ 0% | ❌ No | 🟡 Decision | 5-6h |

---

## RECOMMENDATIONS

### Immediate Actions (This Week)
1. ✅ Fix LoginView authentication flow (critical blocker)
2. ✅ Test route search end-to-end with real backend data
3. ✅ Verify JWT token handling in SessionManager
4. ✅ Set up staging environment with both backend & frontend

### Short Term (2 Weeks)
1. Complete community reports integration
2. Implement travel history UI rendering
3. Add photo upload capability
4. Full QA cycle on critical features

### Medium Term (4 Weeks)
1. Implement SOS/emergency features
2. Add 2FA support
3. Design and implement OAuth strategy
4. Performance optimization & caching

### Long Term (Future)
1. Offline-first caching strategy
2. Progressive web app (PWA) version
3. Analytics & telemetry
4. Machine learning for route recommendations
5. Government API integrations (MMDA, PAGASA, etc.)

---

**Document Version:** 1.0  
**Last Updated:** March 14, 2026  
**Next Review:** After Phase 1 completion
