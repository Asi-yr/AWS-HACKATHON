### SafeRouteAI/Ligtas Application (Flutter)

## Folder Structure
lib/
├── main.dart                     ← App entry point & ThemeMode wiring
├── core/
│   ├── app_colors.dart           ← Color token palette
│   ├── app_theme.dart            ← Light & Dark ThemeData configurations
│   ├── app_router.dart           ← Centralized named routes
│   ├── theme_controller.dart     ← Global theme state using SharedPreferences
│   └── custom_theme.dart         ← Context extension for easy theme access
├── models/
│   ├── user_model.dart           ← User profiles, TrustRank, and Preferences
│   └── travel_history_model.dart ← Route data and travel step definitions
├── data/
│   └── mock_data.dart            ← Central repository for all mock routes, users, and filters
├── widgets/
│   ├── bottom_nav.dart           ← Custom 3-tab navigation shell
│   ├── shared_widgets.dart       ← Reusable components (Buttons, Cards, Headers)
│   └── toast_widget.dart         ← Global notification system
└── screens/
    ├── splash/                   ← Animated entrance and auto-navigation logic
    ├── explore/                  ← The core Map-based route planner and navigation
    ├── profile/                  ← User settings, personal stats, and travel history
    ├── community/                ← Crowdsourced alerts and social safety feed
    ├── login/                    ← User authentication and onboarding entry
    ├── survey/                   ← 3-step safety and preference questionnaire

## Folder Summary
core/: Contains the "brain" of the app's look and feel, handling theme switching and centralized routing logic.

models/: Defines the data structures used throughout the app, ensuring consistency between the UI and backend data.

data/: A temporary storage for mock data (routes, markers, user info) intended to be swapped with real API calls. 

widgets/: Houses global UI components that appear on multiple screens, like the persistent bottom navigation bar.

screens/: Organizes the application by feature. Each feature typically follows an MVC/MVVM pattern with a View for UI and a Controller for logic.


## Notes
# State & Navigation
Explore States: The app uses a state machine to manage the map UI:

    state1: Landing/Search entry.
    state2: Route suggestions drawer.
    state3: Detailed route breakdown (Safety Score, Steps, Fare).
    state4: Active navigation mode with "Stop Route" controls.

Navigation Shell: The _RootShell in main.dart handles the IndexedStack for seamless switching between Explore, Community, and Profile.

# Dark Mode & Theming
The app uses a ThemeController providing a ChangeNotifier.

Performance Fix: The RootShell watches the theme to ensure the BottomNav and Body rebuild in the same frame, eliminating "color lag" during toggles.


## Backend Integration Points
Look for // BACKEND: comments in the following files to replace mock data with API calls:
   explore_controller.dart: Connect to routing and safety-score APIs.
   profile_controller.dart: Connect to GET /api/user/current and PATCH for settings.
   community_view.dart: Swap mock feed with GET /api/feed.

Key endpoints to implement:
- `GET  /api/user/current`            → populate `mockUser`
- `PATCH /api/user/current`           → `saveProfile()`
- `GET  /api/user/travel-history`     → populate `mockTravelHistory`
- `POST /api/user/survey`             → `SurveyView._next()` on step 3
- `POST /api/auth/logout`             → `ProfileController.logOut()`
- `GET  /api/feed?limit=20`           → `CommunityView` mock posts
- `GET  /api/alerts/active`           → `CommunityView._AlertBanner`


## Run
flutter pub get
flutter run

# Run on Mobile (Wireless)
- open terminal or cmd
- type ipconfig
- look for 'IPv4 Address' under your active connection
- It will look something like: 192.168.1.XX or 10.0.0.XX
- type 'flutter run -d web-server --web-hostname 0.0.0.0 --web-port 8080 --dart-define=FLUTTER_WEB_CANVASKIT_URL=false'
- Once the terminal says the app is running, open the browser on your mobile device (which must be on the same WiFi/Data Connection)
- type 'http://YOUR_IP:8080', for example 'http://192.168.1.15:8080' (Wait for it to load)


