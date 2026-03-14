import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import '../../core/app_colors.dart';
import '../../core/theme_controller.dart';
import '../../models/explore_models.dart';
import '../../data/mock_data.dart';
import '../../core/session_manager.dart';
import '../../core/api_client.dart';

// ── Safety overlay models ─────────────────────────────────────────────────────
// BACKEND: populate these from your API responses.
// HotspotModel  → GET /api/safety/hotspots
// PoiModel      → GET /api/poi?types=hospital,police,fire
// AdvisoryModel → GET /api/advisories/active

class HotspotModel {
  final double lat, lng;
  final double radiusMeters; // how wide the danger circle is
  final String label;        // e.g. 'High Crime Risk'
  final Color  color;        // e.g. AppColors.safeRed.withValues(alpha:0.25)
  const HotspotModel({
    required this.lat, required this.lng,
    required this.radiusMeters, required this.label,
    this.color = const Color(0x33DC2626), // default: translucent red
  });
}

class PoiModel {
  final double lat, lng;
  final String label;
  final IconData icon;
  final Color  color;
  const PoiModel({
    required this.lat, required this.lng,
    required this.label, required this.icon,
    this.color = const Color(0xFF0D9E9E),
  });
}

class AdvisoryModel {
  final String message;
  final String type; // 'info' | 'warning' | 'danger'
  const AdvisoryModel({required this.message, this.type = 'warning'});
}
// ─────────────────────────────────────────────────────────────────────────────

class ExploreController extends ChangeNotifier {
  // ── App state ──────────────────────────────────────────────────
  AppState _state = AppState.state1;
  AppState get state => _state;

  void setState(AppState s) {
    _state = s;
    notifyListeners();
  }

  // ── Location ───────────────────────────────────────────────────
  bool _locationPopupVisible = true;
  bool get locationPopupVisible => _locationPopupVisible;

  bool _hasLocation = false;
  bool get hasLocation => _hasLocation;

  double? _lat, _lng;
  double? get lat => _lat;
  double? get lng => _lng;

  String _toastMsg = '';
  String _toastType = 'teal'; // 'teal' | 'green' | 'red'
  bool _toastVisible = false;
  String get toastMsg => _toastMsg;
  String get toastType => _toastType;
  bool get toastVisible => _toastVisible;

  Future<void> requestLocation() async {
    showToast('Requesting location…', 'teal');
    try {
      var perm = await Geolocator.checkPermission();
      if (perm == LocationPermission.denied) {
        perm = await Geolocator.requestPermission();
      }
      if (perm == LocationPermission.deniedForever) {
        showToast('Location permission denied', 'red');
        _locationPopupVisible = false;
        notifyListeners();
        return;
      }
      final pos = await Geolocator.getCurrentPosition(
        desiredAccuracy: LocationAccuracy.high,
      );
      _lat = pos.latitude;
      _lng = pos.longitude;
      _hasLocation = true;
      _locationPopupVisible = false;
      showToast('Location enabled', 'green');
      notifyListeners();
      // Reverse-geocode coordinates to a human-readable address label
      final addr = await ApiClient.instance.reverseGeocode(
        lat: pos.latitude,
        lon: pos.longitude,
      );
      if (addr.isNotEmpty) {
        _currentLocationText = addr;
        notifyListeners();
      }
    } catch (e) {
      showToast('Could not get location — enter manually', 'red');
      _locationPopupVisible = false;
      notifyListeners();
    }
  }

  void skipLocation() {
    _locationPopupVisible = false;
    notifyListeners();
  }

  void showToast(String msg, String type) {
    _toastMsg = msg;
    _toastType = type;
    _toastVisible = true;
    notifyListeners();
    Future.delayed(const Duration(milliseconds: 2600), () {
      _toastVisible = false;
      notifyListeners();
    });
  }

  // ── Ligtas mode ────────────────────────────────────────────────
  bool _ligtasModeOn = false;
  bool get ligtasModeOn => _ligtasModeOn;

  void toggleLigtasMode() {
    _ligtasModeOn = !_ligtasModeOn;
    showToast(_ligtasModeOn ? 'Ligtas Mode ON' : 'Ligtas Mode OFF', 'teal');
    _applyFilters(); // FIX: re-sort/filter routes when ligtas mode changes
    notifyListeners();
  }

  // ── Safety overlays ────────────────────────────────────────────
  // These lists are empty by default. Call the fetch methods below
  // once the backend endpoints are ready.

  List<HotspotModel> hotspots = [];
  List<PoiModel>     pois     = [];
  AdvisoryModel?     advisory;

  /// BACKEND HOOK ─────────────────────────────────────────────────
  /// Call after map loads or when the user moves to a new area.
  ///   GET /api/safety/hotspots?lat=&lng=&radius=
  ///   Response: [{ lat, lng, radius_meters, label, severity }]
  /// ──────────────────────────────────────────────────────────────
  void setHotspots(List<HotspotModel> data) {
    hotspots = data;
    notifyListeners();
  }

  /// BACKEND HOOK ─────────────────────────────────────────────────
  /// Call after map loads or on area change.
  ///   GET /api/poi?lat=&lng=&types=hospital,police,fire
  ///   Response: [{ lat, lng, label, type }]
  /// Map `type` to an icon:
  ///   'hospital' → Icons.local_hospital_rounded
  ///   'police'   → Icons.local_police_rounded
  ///   'fire'     → Icons.fire_truck_rounded
  /// ──────────────────────────────────────────────────────────────
  void setPois(List<PoiModel> data) {
    pois = data;
    notifyListeners();
  }

  /// BACKEND HOOK ─────────────────────────────────────────────────
  /// Call on app launch and periodically (e.g. every 30 min).
  ///   GET /api/advisories/active
  ///   Response: { message, type } | null
  /// Pass null to clear the banner.
  /// ──────────────────────────────────────────────────────────────
  void setAdvisory(AdvisoryModel? data) {
    advisory = data;
    notifyListeners();
  }

  /// Fetch safety overlay data from backend for a given location.
  /// Populates hotspots (earthquake circles), POIs (safe spots), and advisory.
  ///
  /// Called after routes are fetched in [searchRoutes].
  ///
  /// BACKEND ENDPOINTS USED:
  ///   GET /api/safety?lat=&lon=              → weather, crime, flood penalties + advisory
  ///   GET /api/safe-spots/flutter?lat=&lon=  → hospital, police, fire, pharmacy markers
  Future<void> fetchSafetyOverlays({
    required double lat,
    required double lon,
  }) async {
    try {
      final token = await SessionManager.instance.getAuthToken();

      // ── 1. Fetch area safety data (weather / crime / flood / seismic) ────────
      final safetyData = await ApiClient.instance.getSafety(
        lat: lat,
        lon: lon,
        token: token,
      );

      final newHotspots = <HotspotModel>[];
      final newPois     = <PoiModel>[];

      if (safetyData['ok'] == true) {
        // ── Community reports → hotspot circles ──────────────────────────────
        final reports = safetyData['reports'] as List? ?? [];
        for (final report in reports) {
          if (report is Map<String, dynamic>) {
            final rLat  = (report['lat']  as num?)?.toDouble() ?? 0.0;
            final rLon  = (report['lon']  as num?)?.toDouble() ?? 0.0;
            final label = report['label'] as String? ?? 'Safety Alert';
            final color = _colorFromReportType(report['type'] as String? ?? '');
            newHotspots.add(HotspotModel(
              lat: rLat, lng: rLon,
              radiusMeters: 200,
              label: label, color: color,
            ));
          }
        }

        // ── Seismic circles from /api/safety seismic block ───────────────────
        // Each earthquake gets a translucent circle scaled to its damage radius.
        final seismicBlock = safetyData['seismic'] as Map? ?? {};
        final quakeList    = seismicBlock['earthquakes'] as List? ?? [];
        for (final eq in quakeList) {
          if (eq is Map<String, dynamic>) {
            final eqLat    = (eq['lat']       as num?)?.toDouble();
            final eqLon    = (eq['lon']       as num?)?.toDouble();
            final radiusKm = (eq['radius_km'] as num?)?.toDouble() ?? 20.0;
            final mag      = (eq['magnitude'] as num?)?.toDouble() ?? 0.0;
            final severity = eq['severity']   as String? ?? 'moderate';
            if (eqLat == null || eqLon == null) continue;
            newHotspots.add(HotspotModel(
              lat: eqLat, lng: eqLon,
              radiusMeters: radiusKm * 1000,
              label: 'M$mag Earthquake',
              color: _colorFromEqSeverity(severity),
            ));
          }
        }

        // ── Advisory banner logic ─────────────────────────────────────────────
        final crimePenalty  = safetyData['crime']?['penalty']    as int? ?? 0;
        final floodPenalty  = safetyData['flood']?['penalty']    as int? ?? 0;
        final weatherRisk   = safetyData['weather']?['risk_level'] as String? ?? 'clear';
        final seismicCount  = seismicBlock['count'] as int? ?? 0;

        AdvisoryModel? newAdvisory;
        if (crimePenalty > 15) {
          newAdvisory = const AdvisoryModel(
            message: 'High crime risk in this area — exercise caution.',
            type: 'danger',
          );
        } else if (floodPenalty > 15) {
          newAdvisory = const AdvisoryModel(
            message: 'Flood risk detected — consider alternate routes.',
            type: 'warning',
          );
        } else if (weatherRisk == 'storm' || weatherRisk == 'heavy_rain') {
          newAdvisory = AdvisoryModel(
            message: 'Severe weather in the area — stay safe.',
            type: weatherRisk == 'storm' ? 'danger' : 'warning',
          );
        } else if (seismicCount > 0) {
          newAdvisory = const AdvisoryModel(
            message: 'Recent earthquake activity near your route.',
            type: 'warning',
          );
        }

        setAdvisory(newAdvisory);
      }
    } catch (e) {
      debugPrint('[ExploreController] Error fetching safety overlays: $e');
    }
  }

  // ── Earthquake severity → translucent map circle color ──────────────────────
  Color _colorFromEqSeverity(String severity) {
    switch (severity) {
      case 'critical': return const Color(0x556C1A1A);
      case 'high':     return const Color(0x44E74C3C);
      case 'moderate': return const Color(0x33E67E22);
      default:         return const Color(0x22F39C12);
    }
  }

  // ── Safe-spot type → Flutter IconData ───────────────────────────────────────
  // Must match the OSM amenity `type` strings returned by safe_spots.py.
  IconData _iconForSpotType(String type) {
    switch (type) {
      case 'hospital':         return Icons.local_hospital_rounded;
      case 'clinic':           return Icons.local_hospital_outlined;
      case 'pharmacy':         return Icons.medical_services_rounded;
      case 'police':           return Icons.local_police_rounded;
      case 'fire_station':     return Icons.fire_truck_rounded;
      case 'barangay_hall':    return Icons.account_balance_rounded;
      case 'community_centre': return Icons.people_rounded;
      case 'convenience':
      case 'supermarket':      return Icons.store_rounded;
      default:                 return Icons.place_rounded;
    }
  }

  // ── Safe-spot type → map marker color ───────────────────────────────────────
  Color _colorForSpotType(String type) {
    switch (type) {
      case 'hospital':
      case 'clinic':           return const Color(0xFFE74C3C);
      case 'pharmacy':         return const Color(0xFF27AE60);
      case 'police':           return const Color(0xFF2980B9);
      case 'fire_station':     return const Color(0xFFE67E22);
      case 'barangay_hall':
      case 'community_centre': return const Color(0xFF8E44AD);
      default:                 return const Color(0xFF0D9E9E);
    }
  }



  Color _colorFromReportType(String type) {
    switch (type.toLowerCase()) {
      case 'crime':
        return const Color(0x33DC2626);
      case 'flood':
        return const Color(0x333B82F6);
      case 'accident':
        return const Color(0x33F59E0B);
      default:
        return const Color(0x33DC2626);
    }
  }

  // ── Search inputs ──────────────────────────────────────────────
  String _currentLocationText = ''; // Updated: was _originText
  String _destinationText = '';     // Updated: was _destText
  bool   _miniCurrentFocused = true; // Updated: was _miniOriginFocused

  String get currentLocationText => _currentLocationText;
  String get destinationText => _destinationText;
  
  // Keep old getters for backward compatibility
  String get originText => _currentLocationText;
  String get destText => _destinationText;
  bool   get miniOriginFocused => _miniCurrentFocused;

  void setCurrentLocationText(String v) { _currentLocationText = v; notifyListeners(); }
  void setDestinationText(String v) { _destinationText = v; notifyListeners(); }
  
  // Keep old setters for backward compatibility
  void setOriginText(String v)  { _currentLocationText = v; notifyListeners(); }
  void setDestText(String v)    { _destinationText   = v; notifyListeners(); }
  void setMiniFocus(bool current){ _miniCurrentFocused = current; notifyListeners(); }

  void openMiniState({bool focusDest = true}) {
    _miniCurrentFocused = !focusDest;
    _state = AppState.mini;
    notifyListeners();
  }

  void selectMiniItem(MiniItem item) {
    if (_miniCurrentFocused) {
      _currentLocationText = item.name;
    } else {
      _destinationText = item.name;
    }
    notifyListeners();
  }

  Future<void> searchRoutes() async {
    // Both fields should be filled to search
    if (_currentLocationText.isEmpty || _destinationText.isEmpty) {
      if (_currentLocationText.isEmpty) {
        showToast('Please enter your current location', 'red');
      } else {
        showToast('Please enter your destination', 'red');
      }
      return;
    }
    _state = AppState.state2;
    showToast('Finding routes...', 'teal');
    notifyListeners();

    // Attempt to fetch live routes from the Flask backend WITH alerts.
    try {
      final response = await ApiClient.instance.searchRoutesWithAlerts(
        origin: _currentLocationText,
        destination: _destinationText,
        mode: 'commute',
      );

      final routes = (response['routes'] as List?)?.cast<RouteModel>() ?? [];

      if (routes.isNotEmpty) {
        setAllRoutes(routes);

        // ── Store all alert data from /api/routes ───────────────────────────
        setAlertData(
          incidents:         (response['incidents'] as List?)?.cast<Map<String, dynamic>>() ?? [],
          mmdaBanner:        response['mmda_banner']?.toString() ?? '',
          mmdaClosuresCount: response['mmda_closures_count'] as int? ?? 0,
          earthquakes:       (response['earthquakes'] as List?)?.cast<Map<String, dynamic>>() ?? [],
          seismicBanner:     response['seismic_banner']?.toString() ?? '',
          weatherRisk:       response['weather_risk']?.toString() ?? 'clear',
          floodRisk:         response['flood_risk']?.toString() ?? 'none',
        );

        // ── Earthquake circles from /api/routes payload ─────────────────────
        // /api/routes now includes lat, lon, radius_km, severity per quake.
        // We build HotspotModel circles immediately — no extra network call.
        final eqList = (response['earthquakes'] as List?)
            ?.cast<Map<String, dynamic>>() ?? [];
        final eqHotspots = <HotspotModel>[];
        for (final eq in eqList) {
          final eqLat    = (eq['lat']       as num?)?.toDouble();
          final eqLon    = (eq['lon']       as num?)?.toDouble();
          final radiusKm = (eq['radius_km'] as num?)?.toDouble() ?? 20.0;
          final mag      = (eq['magnitude'] as num?)?.toDouble() ?? 0.0;
          final severity = eq['severity']   as String? ?? 'moderate';
          if (eqLat == null || eqLon == null) continue;
          eqHotspots.add(HotspotModel(
            lat: eqLat, lng: eqLon,
            radiusMeters: radiusKm * 1000,
            label: 'M$mag Earthquake',
            color: _colorFromEqSeverity(severity),
          ));
        }
        if (eqHotspots.isNotEmpty) setHotspots(eqHotspots);

        // ── Advisory banners from route-level risk data ─────────────────────
        final seismicBannerText = response['seismic_banner']?.toString() ?? '';
        final wRisk             = response['weather_risk']?.toString() ?? 'clear';
        if (seismicBannerText.isNotEmpty) {
          setAdvisory(const AdvisoryModel(
            message: 'Recent earthquake activity detected near your route.',
            type: 'warning',
          ));
        } else if (wRisk == 'storm' || wRisk == 'heavy_rain') {
          setAdvisory(AdvisoryModel(
            message: 'Severe weather detected — travel with caution.',
            type: wRisk == 'storm' ? 'danger' : 'warning',
          ));
        }

        // ── Fetch safe-spot POIs + full area safety overlays ────────────────
        // Runs after routes are shown — does not block the route list UI.
        final safeLat = _lat ?? 14.5995;
        final safeLon = _lng ?? 120.9842;
        await fetchSafetyOverlays(lat: safeLat, lon: safeLon);

        return;
      }

      // No routes returned – fall back to the built-in mock routes
      // so the UI remains usable.
      setAllRoutes(mockRoutes);
      setAlertData(
        incidents: [],
        mmdaBanner: '',
        mmdaClosuresCount: 0,
        earthquakes: [],
        seismicBanner: '',
        weatherRisk: 'clear',
        floodRisk: 'none',
      );
      showToast('No routes from server — showing sample routes', 'teal');
    } catch (_) {
      // On any error (offline, server down, bad JSON), keep the existing
      // mock behaviour and surface a gentle message.
      _allRoutes = mockRoutes;
      _applyFilters();
      setAlertData(
        incidents: [],
        mmdaBanner: '',
        mmdaClosuresCount: 0,
        earthquakes: [],
        seismicBanner: '',
        weatherRisk: 'clear',
        floodRisk: 'none',
      );
      showToast('Could not reach server — using sample routes', 'red');
      notifyListeners();
    }
  }

  void clearSearch() {
    _currentLocationText = '';
    _destinationText = '';
    _state = AppState.state1;
    _activeRoute = null;
    _filteredRoutes = List.from(_allRoutes); // reset to full list
    showToast('Search cleared', 'teal');
    notifyListeners();
  }

  // ── Filters ────────────────────────────────────────────────────
  List<String> commuterFilters  = [];
  List<String> transportFilters = [];
  List<String> ligtasFilters    = [];
  List<String> preferenceFilters = []; // NEW: Route preferences (safest, fastest, cheapest, balanced, moderate)

  bool get hasFilters =>
      commuterFilters.isNotEmpty || transportFilters.isNotEmpty || 
      ligtasFilters.isNotEmpty || preferenceFilters.isNotEmpty;

  // ── Survey defaults ───────────────────────────────────────────
  // Called once by SurveyView on finish. Seeds the filter lists with the
  // user's onboarding answers so they show up pre-selected in the explore
  // filter panel without the user having to set them again.
  //
  // BACKEND: call this after a successful POST /api/user/survey response,
  // passing the values confirmed by the server rather than raw local state.
  // Key values must match the keys in mock_data.dart:
  //   commuterTypes → commuterFilters (e.g. ['student', 'women'])
  //   transport    → transportFilters (e.g. 'jeep', 'bus', 'walk')
  //   safety       → ligtasFilters    (e.g. 'dark', 'crime', 'flooding')
  void setSurveyDefaults({
    List<String> commuterTypes = const [],
    List<String> transport     = const [],
    List<String> safety        = const [],
  }) {
    commuterFilters = List.of(commuterTypes);
    transportFilters = List.of(transport);
    ligtasFilters    = List.of(safety);
    _applyFilters();
    notifyListeners();
  }

  void toggleFilter(String group, String key) {
    List<String> list;
    if (group == 'commuter') { list = commuterFilters; }
    else if (group == 'transport') { list = transportFilters; }
    else if (group == 'ligtas') { list = ligtasFilters; }
    else { 
      // Preference filters work like radio buttons - only one can be selected
      if (preferenceFilters.contains(key)) {
        preferenceFilters.remove(key);
      } else {
        preferenceFilters.clear(); // Clear all others
        preferenceFilters.add(key); // Add only this one
      }
      _applyFilters();
      notifyListeners();
      return;
    }

    if (list.contains(key)) { list.remove(key); } else { list.add(key); }
    _applyFilters();  // FIX: recompute routes on every filter change
    notifyListeners();
  }

  void removeFilter(String group, String key) {
    if (group == 'commuter') { commuterFilters.remove(key); }
    else if (group == 'transport') { transportFilters.remove(key); }
    else if (group == 'ligtas') { ligtasFilters.remove(key); }
    else { preferenceFilters.remove(key); }
    _applyFilters();  // FIX: recompute routes on every filter removal
    notifyListeners();
  }

  void applyFilters() {
    final total = commuterFilters.length + transportFilters.length + 
                  ligtasFilters.length + preferenceFilters.length;
    showToast(total > 0 ? 'Filters applied' : 'No filters active', 'teal');
    _applyFilters();
    notifyListeners();
  }

  void clearAllFilters() {
    commuterFilters.clear();
    transportFilters.clear();
    ligtasFilters.clear();
    preferenceFilters.clear();
    _applyFilters();
    showToast('All filters cleared', 'teal');
    notifyListeners();
  }

  // ── Routes ─────────────────────────────────────────────────────

  // All available routes. When the backend is ready, replace the body of
  // this getter (or call setAllRoutes()) with real API data.
  List<RouteModel> _allRoutes = mockRoutes;
  List<RouteModel> get allRoutes => _allRoutes;

  // The currently displayed (filtered) route list — what the UI binds to.
  List<RouteModel> _filteredRoutes = mockRoutes;
  List<RouteModel> get routes => _filteredRoutes;

  // ── WHAT NEEDS CONNECTION 🔗: Incident & Alert Data ──────────────────────
  List<Map<String, dynamic>> _incidents = [];
  List<Map<String, dynamic>> get incidents => _incidents;

  String _mmdaBanner = '';
  String get mmdaBanner => _mmdaBanner;

  int _mmdaClosuresCount = 0;
  int get mmdaClosuresCount => _mmdaClosuresCount;

  List<Map<String, dynamic>> _earthquakes = [];
  List<Map<String, dynamic>> get earthquakes => _earthquakes;

  String _seismicBanner = '';
  String get seismicBanner => _seismicBanner;

  String _weatherRisk = 'clear';  // clear, rain, storm, etc.
  String get weatherRisk => _weatherRisk;

  String _floodRisk = 'none';  // none, low, moderate, high
  String get floodRisk => _floodRisk;

  /// BACKEND HOOK ─────────────────────────────────────────────────────────────
  /// Call this from your API layer to swap in real routes.
  /// Example:
  ///   final data = await routeApi.search(origin, dest);
  ///   ctrl.setAllRoutes(data.map(RouteModel.fromJson).toList());
  /// ──────────────────────────────────────────────────────────────────────────
  void setAllRoutes(List<RouteModel> newRoutes) {
    _allRoutes = newRoutes;
    _applyFilters();
    notifyListeners();
  }

  /// Set alert data from API response (incidents, MMDA, earthquakes, etc.)
  void setAlertData({
    required List<Map<String, dynamic>> incidents,
    required String mmdaBanner,
    required int mmdaClosuresCount,
    required List<Map<String, dynamic>> earthquakes,
    required String seismicBanner,
    required String weatherRisk,
    required String floodRisk,
  }) {
    _incidents = incidents;
    _mmdaBanner = mmdaBanner;
    _mmdaClosuresCount = mmdaClosuresCount;
    _earthquakes = earthquakes;
    _seismicBanner = seismicBanner;
    _weatherRisk = weatherRisk;
    _floodRisk = floodRisk;
    notifyListeners();
  }

  /// Core filtering engine — runs every time filters or ligtas mode change.
  /// 
  /// HOW IT WORKS (mock mode):
  ///   • commuterFilters → matched against route.commuterTags (List< String >)
  ///   • transportFilters → matched against route.modes (String contains check)
  ///   • preferenceFilters → sorting/prioritization by route characteristics
  ///   • ligtasFilters → only applied when ligtasModeOn; matched against route.ligtasTags
  ///   • If no filters are active → show all routes
  ///   • ligtasModeOn with no ligtas filters → boost safety-sorted routes to top
  ///
  /// BACKEND HOOK ─────────────────────────────────────────────────────────────
  /// Replace or extend the body below with your real filtering/ranking logic.
  /// The signature stays the same — just populate _filteredRoutes differently.
  /// For preference filters, you can either:
  ///   1. Sort routes based on preference (safest → by safetyScore, fastest → by minutes)
  ///   2. Or use these as ranking signals in your backend route recommendation API
  /// ──────────────────────────────────────────────────────────────────────────
  void _applyFilters() {
    List<RouteModel> result = List.from(_allRoutes);

    // 1. Commuter filter — keep routes that support ANY selected commuter type
    if (commuterFilters.isNotEmpty) {
      result = result.where((r) =>
        commuterFilters.any((f) => r.commuterTags.contains(f))
      ).toList();
    }

    // 2. Transport filter — keep routes whose modes string contains ANY selected mode
    if (transportFilters.isNotEmpty) {
      result = result.where((r) {
        final modesLower = r.modes.toLowerCase();
        return transportFilters.any((f) => modesLower.contains(f.toLowerCase()));
      }).toList();
    }

    // 3. Ligtas features filter — only active when ligtas mode is ON
    if (_ligtasModeOn && ligtasFilters.isNotEmpty) {
      result = result.where((r) =>
        ligtasFilters.any((f) => r.ligtasTags.contains(f))
      ).toList();
    }

    // 4. Preference filter — sort/prioritize based on user preference
    //    BACKEND: Replace with your ranking algorithm or API parameter
    if (preferenceFilters.isNotEmpty) {
      final pref = preferenceFilters.first; // Using first preference if multiple selected
      if (pref == 'safest') {
        result.sort((a, b) => b.safetyScore.compareTo(a.safetyScore));
      } else if (pref == 'fastest') {
        result.sort((a, b) => a.minutes.compareTo(b.minutes));
      } else if (pref == 'cheapest') {
        // Sort by fare (lowest first)
        result.sort((a, b) => a.fare.compareTo(b.fare));
      } else if (pref == 'balanced') {
        // Balanced approach: normalize and combine safety, speed, and cost
        result.sort((a, b) {
          final aScore = (a.safetyScore / 100) - (a.minutes / 120) - (a.fare / 100);
          final bScore = (b.safetyScore / 100) - (b.minutes / 120) - (b.fare / 100);
          return bScore.compareTo(aScore); // Higher balanced score is better
        });
      } else if (pref == 'moderate') {
        // Moderate preference: favor mid-range routes (not extreme in any dimension)
        result.sort((a, b) {
          final aVariance = _calculateVariance(a);
          final bVariance = _calculateVariance(b);
          return aVariance.compareTo(bVariance); // Lower variance = more moderate
        });
      }
    }

    // 5. Ligtas mode ON (no ligtas filters, no preference filters) → sort by safety score descending
    if (_ligtasModeOn && preferenceFilters.isEmpty) {
      result.sort((a, b) => b.safetyScore.compareTo(a.safetyScore));
    }

    // 6. If nothing matched, fall back to all routes with a toast
    if (result.isEmpty && hasFilters) {
      result = List.from(_allRoutes);
      showToast('No routes match filters — showing all', 'teal');
    }

    _filteredRoutes = result;
  }

  RouteModel? _activeRoute;
  RouteModel? get activeRoute => _activeRoute;

  void selectRoute(RouteModel r) {
    _activeRoute = r;
    _state = AppState.state3;
    SessionManager.instance.setHasActiveRoute(false);
    notifyListeners();
  }

  void startNavigation() {
    if (_activeRoute == null) return;
    _state = AppState.state4;
    SessionManager.instance.setHasActiveRoute(true);
    notifyListeners();
  }

  void stopNavigation() {
    _state = AppState.state2;
    SessionManager.instance.setHasActiveRoute(false);
    notifyListeners();
  }

  void confirmStopNavigation(BuildContext context) {
    final isDark = context.read<ThemeController>().isDark;
    showDialog(
      context: context,
      barrierColor: Colors.black.withValues(alpha: 0.6),
      builder: (BuildContext dialogContext) {
        return Dialog(
          backgroundColor: Colors.transparent,
          elevation: 0,
          child: Container(
            padding: const EdgeInsets.fromLTRB(24, 28, 24, 20),
            decoration: BoxDecoration(
              color: AppColors.card(isDark),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: AppColors.border(isDark)),
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Icon
                Container(
                  width: 44, height: 44,
                  decoration: const BoxDecoration(
                    color: AppColors.redDim,
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(Icons.stop_circle_outlined,
                    color: AppColors.safeRed, size: 22),
                ),
                const SizedBox(height: 14),
                Text(
                  'Stop Navigation?',
                  style: GoogleFonts.plusJakartaSans(
                    fontSize: 17, fontWeight: FontWeight.w800,
                    color: AppColors.text(isDark)),
                ),
                const SizedBox(height: 8),
                Text(
                  'Are you sure you want to stop? This will end your current route navigation.',
                  style: GoogleFonts.plusJakartaSans(
                    fontSize: 13, color: AppColors.text2(isDark), height: 1.5),
                ),
                const SizedBox(height: 24),
                Row(children: [
                  Expanded(
                    child: OutlinedButton(
                      style: OutlinedButton.styleFrom(
                        foregroundColor: AppColors.text2(isDark),
                        side: BorderSide(color: AppColors.border(isDark)),
                        padding: const EdgeInsets.symmetric(vertical: 13),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12)),
                      ),
                      onPressed: () => Navigator.of(dialogContext).pop(),
                      child: Text('Cancel',
                        style: GoogleFonts.plusJakartaSans(fontWeight: FontWeight.w700)),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: ElevatedButton(
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppColors.safeRed,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 13),
                        elevation: 0,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12)),
                      ),
                      onPressed: () {
                        Navigator.of(dialogContext).pop();
                        stopNavigation();
                      },
                      child: Text('Stop Route',
                        style: GoogleFonts.plusJakartaSans(fontWeight: FontWeight.w700)),
                    ),
                  ),
                ]),
              ],
            ),
          ),
        );
      },
    );
  }

  void backToRoutes() {
    _state = AppState.state2;
    SessionManager.instance.setHasActiveRoute(false);
    notifyListeners();
  }

  // ── Map zoom (passed to view) ───────────────────────────────────
  int _mapZoom = 14;
  int get mapZoom => _mapZoom;
  void zoomIn()  { _mapZoom = (_mapZoom + 1).clamp(3, 19); notifyListeners(); }
  void zoomOut() { _mapZoom = (_mapZoom - 1).clamp(3, 19); notifyListeners(); }

  // ── Helper methods for preference filters ──────────────────────

  /// Calculate variance for moderate filter (lower = more moderate/balanced)
  /// BACKEND: Replace with your own balanced scoring algorithm
  double _calculateVariance(RouteModel route) {
    // Normalize each metric to 0-1 scale, then calculate variance
    final normalizedSafety = route.safetyScore / 100;
    final normalizedTime = 1 - (route.minutes / 120); // Invert so lower is better
    final normalizedCost = 1 - (route.fare / 100); // Invert so lower is better
    
    final mean = (normalizedSafety + normalizedTime + normalizedCost) / 3;
    final variance = ((normalizedSafety - mean).abs() + 
                      (normalizedTime - mean).abs() + 
                      (normalizedCost - mean).abs()) / 3;
    
    return variance;
  }
}