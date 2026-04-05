import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:geolocator/geolocator.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import '../../core/app_colors.dart';
import '../../core/theme_controller.dart';
import '../../models/explore_models.dart';
import '../../core/session_manager.dart';
import '../../core/api_client.dart';

// ── Safety overlay models ─────────────────────────────────────────────────────
class HotspotModel {
  final double lat, lng;
  final double radiusMeters;
  final String label;
  final Color color;
  const HotspotModel({
    required this.lat,
    required this.lng,
    required this.radiusMeters,
    required this.label,
    this.color = const Color(0x33DC2626),
  });
}

class PoiModel {
  final double lat, lng;
  final String name;
  final String label;
  final String type; // 'hospital', 'police', 'pharmacy', etc.
  final IconData icon;
  final Color color;
  const PoiModel({
    required this.lat,
    required this.lng,
    this.name = '',
    required this.label,
    this.type = '',
    required this.icon,
    this.color = const Color(0xFF0D9E9E),
  });
}

class AdvisoryModel {
  final String message;
  final String type; // 'info' | 'warning' | 'danger'
  const AdvisoryModel({required this.message, this.type = 'warning'});
}

// ── MMDA status model ─────────────────────────────────────────────────────────
class MmdaStatus {
  final String? codingMessage; // e.g. "Plate ending 1 & 2 banned today 7am–8pm"
  final bool isCoded;
  final int closuresCount;
  const MmdaStatus({
    this.codingMessage,
    this.isCoded = false,
    this.closuresCount = 0,
  });
}

// ── Report incident types ─────────────────────────────────────────────────────
class ReportType {
  final String key;
  final String label;
  final String icon; // emoji from backend
  const ReportType({required this.key, required this.label, this.icon = '⚠️'});
}

class ExploreController extends ChangeNotifier {
  ExploreController() {
    _initLocation();
    loadUserPreferences();
  }

  /// Optional callback fired when GPS coordinates are first resolved.
  /// The map widget wires this up to imperatively move the camera so the
  /// initial center stays accurate on real phones where permission is granted
  /// asynchronously (after the map widget already built with a fallback center).
  VoidCallback? onLocationResolved;

  /// Optional callback fired when the user selects a search suggestion that
  /// already has known coordinates (from the /api/suggest Nominatim response).
  /// The map widget wires this to immediately pan the camera to [lat, lon]
  /// and drop the preview pin — matching the web's immediate flyTo behaviour.
  Function(double lat, double lon)? onMapPreview;

  /// Fetch saved survey prefs from backend and seed filters.
  /// Called on init and after login so prefs are always applied for the session.
  Future<void> loadUserPreferences() async {
    try {
      final token = await SessionManager.instance.getAuthToken();
      if (token == null || token.isEmpty) return;
      final data = await ApiClient.instance.getSettings(token: token);
      if (data['ok'] != true) return;
      final s = (data['settings'] as Map<String, dynamic>?) ?? {};
      final commuter = (s['commuter_types'] as List?)?.cast<String>() ?? [];
      final transport = (s['transport_modes'] as List?)?.cast<String>() ?? [];
      final safety = (s['safety_concerns'] as List?)?.cast<String>() ?? [];
      if (commuter.isNotEmpty || transport.isNotEmpty || safety.isNotEmpty) {
        setSurveyDefaults(
          commuterTypes: commuter,
          transport: transport,
          safety: safety,
        );
      }
    } catch (_) {
      // Non-fatal — fall through with empty defaults
    }
  }

  Future<void> _initLocation() async {
    final serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      _locationPopupVisible = true;
      notifyListeners();
      return;
    }

    final perm = await Geolocator.checkPermission();

    if (perm == LocationPermission.always ||
        perm == LocationPermission.whileInUse) {
      // Already granted — silently load location, keep popup hidden
      try {
        final pos = await Geolocator.getCurrentPosition(
          desiredAccuracy: LocationAccuracy.high,
          timeLimit: const Duration(seconds: 15),
        );
        _lat = pos.latitude;
        _lng = pos.longitude;
        _hasLocation = true;

        try {
          final token = await SessionManager.instance.getAuthToken();
          final rev = await ApiClient.instance.reverseGeocode(
            lat: _lat!,
            lon: _lng!,
            token: token,
          );
          final address = rev['address'] as String? ?? '';
          _currentLocationText = address.isNotEmpty
              ? address
              : '${_lat!.toStringAsFixed(5)}, ${_lng!.toStringAsFixed(5)}';
        } catch (_) {
          _currentLocationText =
              '${_lat!.toStringAsFixed(5)}, ${_lng!.toStringAsFixed(5)}';
        }
        // Re-center the map now that we have a real GPS fix
        onLocationResolved?.call();
        // ── Silently warm up the map on first open ────────────────────────
        // Mirrors web: loadSafetyOverlay() + fetchAndDrawNearby() are called
        // immediately after GPS is obtained on page load, so the map shows
        // transit stops and safety circles without the user doing anything.
        unawaited(fetchNearbyStops(_lat!, _lng!));
        unawaited(fetchSafetyOverlays(lat: _lat!, lon: _lng!));
      } catch (_) {
        // Couldn't get position even with permission — leave popup hidden,
        // user can still type manually
      }
    } else {
      // Not yet granted — show the enable location popup
      _locationPopupVisible = true;
    }
    notifyListeners();
  }

  // ── App state ──────────────────────────────────────────────────
  AppState _state = AppState.state1;
  AppState get state => _state;

  bool _isLoadingRoutes = false;
  bool get isLoadingRoutes => _isLoadingRoutes;

  void setState(AppState s) {
    _state = s;
    recordActivity(); // any state change = user is active
    notifyListeners();
  }

  // ── Idle session management ────────────────────────────────────
  // After 30 minutes of no explore interaction, return to the landing
  // screen the next time the user opens this tab. The timer is NOT
  // automatic — it only triggers when the user switches back here.
  static const int _idleMinutes = 30;
  int _lastActivityMs = 0; // 0 = never set (first open always shows state1)

  /// Call this whenever the user does something on the Explore screen.
  void recordActivity() {
    _lastActivityMs = DateTime.now().millisecondsSinceEpoch;
  }

  /// Called when the Explore tab becomes active. Resets to the landing
  /// screen only if the user has been idle for 30+ minutes.
  void checkAndRestoreIfIdle() {
    // First open (never recorded) → already state1, nothing to do.
    if (_lastActivityMs == 0) return;
    // Currently on the landing screen → nothing to restore.
    if (_state == AppState.state1) return;
    final idleMs = DateTime.now().millisecondsSinceEpoch - _lastActivityMs;
    if (idleMs >= _idleMinutes * 60 * 1000) {
      _state = AppState.state1;
      notifyListeners();
    }
  }

  // ── Location ───────────────────────────────────────────────────
  bool _locationPopupVisible = false;
  bool get locationPopupVisible => _locationPopupVisible;

  bool _hasLocation = false;
  bool get hasLocation => _hasLocation;

  double? _lat, _lng;
  double? get lat => _lat;
  double? get lng => _lng;

  String _toastMsg = '';
  String _toastType = 'teal';
  bool _toastVisible = false;
  String get toastMsg => _toastMsg;
  String get toastType => _toastType;
  bool get toastVisible => _toastVisible;

  // ── GPS + reverse-geocode into the "Current location" field ───
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
        timeLimit: const Duration(seconds: 15),
      );
      _lat = pos.latitude;
      _lng = pos.longitude;
      _hasLocation = true;
      _locationPopupVisible = false;

      // ── Reverse-geocode → fill "Current location" text field ──
      // Calls GET /api/reverse?lat=&lon= which proxies Nominatim.
      // Falls back to coordinates string if the call fails.
      try {
        final token = await SessionManager.instance.getAuthToken();
        final rev = await ApiClient.instance.reverseGeocode(
          lat: _lat!,
          lon: _lng!,
          token: token,
        );
        final address = rev['address'] as String? ?? '';
        if (address.isNotEmpty) {
          _currentLocationText = address;
        } else {
          _currentLocationText =
              '${_lat!.toStringAsFixed(5)}, ${_lng!.toStringAsFixed(5)}';
        }
      } catch (_) {
        _currentLocationText =
            '${_lat!.toStringAsFixed(5)}, ${_lng!.toStringAsFixed(5)}';
      }

      showToast('Location enabled', 'green');
      // Re-center the map to the real GPS position
      onLocationResolved?.call();
      notifyListeners();
    } catch (e) {
      showToast('Could not get location — enter manually', 'red');
      _locationPopupVisible = false;
      notifyListeners();
    }
  }

  /// Called by the teal GPS icon inside the search pill/overlay.
  /// Gets GPS position, reverse-geocodes it, fills the origin field,
  /// then returns so the caller can open the search screen.
  ///
  /// Mirrors web setOrigin(): shows "My Location" immediately, drops the
  /// A-pin, flies to the position, then async-updates the label with the
  /// real geocoded address (GET /api/reverse) and kicks off nearby-stop
  /// and safety-overlay fetches (GET /api/nearby, GET /api/safety,
  /// GET /api/safe-spots/flutter) — matching every side-effect of the
  /// Flask locate-origin-btn click.
  Future<void> useCurrentLocationAsOrigin() async {
    showToast('Getting your location…', 'teal');
    try {
      var perm = await Geolocator.checkPermission();
      if (perm == LocationPermission.denied) {
        perm = await Geolocator.requestPermission();
      }
      if (perm == LocationPermission.deniedForever) {
        showToast('Location permission denied — enter manually', 'red');
        return;
      }
      final pos = await Geolocator.getCurrentPosition(
        desiredAccuracy: LocationAccuracy.high,
        timeLimit: const Duration(seconds: 15),
      );
      _lat = pos.latitude;
      _lng = pos.longitude;
      _hasLocation = true;

      // ── Immediate feedback (mirrors web: input.value = 'My Location') ──
      // Drop the A-pin and show "My Location" right away so the UI
      // feels responsive — the label will be overwritten once /api/reverse
      // comes back with the real address, exactly as the web does.
      _resolvedOrigLat = _lat;
      _resolvedOrigLon = _lng;
      _currentLocationText = 'My Location';
      notifyListeners();
      // Pan/zoom the map to the GPS fix immediately (mirrors map.setView zoom 15)
      onLocationResolved?.call();

      // ── Kick off all three backend calls in parallel ──────────────────
      // 1. Reverse-geocode → update origin label with real address
      // 2. Nearby transit stops → coloured dot markers near origin
      // 3. Safety overlays → community-report circles + safe-spot POIs
      final token = await SessionManager.instance.getAuthToken();

      unawaited(
        ApiClient.instance
            .reverseGeocode(lat: _lat!, lon: _lng!, token: token)
            .then((rev) {
          final address = (rev['address'] as String?) ?? '';
          _currentLocationText = address.isNotEmpty
              ? address
              : '${_lat!.toStringAsFixed(5)}, ${_lng!.toStringAsFixed(5)}';
          notifyListeners();
        }).catchError((_) {
          _currentLocationText =
              '${_lat!.toStringAsFixed(5)}, ${_lng!.toStringAsFixed(5)}';
          notifyListeners();
        }),
      );

      unawaited(fetchNearbyStops(_lat!, _lng!));

      unawaited(
        fetchSafetyOverlays(lat: _lat!, lon: _lng!),
      );

      showToast('Location set', 'green');
      notifyListeners();
    } catch (e) {
      showToast('Could not get location', 'red');
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
    _applyFilters();
    notifyListeners();
  }

  // ── Safety overlays ────────────────────────────────────────────
  List<HotspotModel> hotspots = [];
  List<PoiModel> _allPois = []; // full unfiltered list
  List<PoiModel> get pois => _allPois
      .where((p) => p.type.isEmpty || _selectedSpotTypes.contains(p.type))
      .toList();
  AdvisoryModel? advisory;

  void setHotspots(List<HotspotModel> data) {
    hotspots = data;
    notifyListeners();
  }

  void setPois(List<PoiModel> data) {
    _allPois = data;
    notifyListeners();
  }

  void setAdvisory(AdvisoryModel? data) {
    advisory = data;
    notifyListeners();
  }

  // ── MMDA banner ────────────────────────────────────────────────
  MmdaStatus _mmdaStatus = const MmdaStatus();
  MmdaStatus get mmdaStatus => _mmdaStatus;

  /// Fetch MMDA number-coding + road-closure status.
  /// Call once after login/app resume (data refreshes itself server-side).
  /// GET /api/mmda  →  { coding, closures, closures_count }
  Future<void> fetchMmdaStatus() async {
    try {
      final token = await SessionManager.instance.getAuthToken();
      // Pass stored plate digit so the backend can check number-coding status
      // for the user's specific plate (matches web ?plate= query param).
      final plate = _plateDigit.isNotEmpty ? int.tryParse(_plateDigit) : null;
      final data = await ApiClient.instance.getMmda(token: token, plateDigit: plate);
      final coding = data['coding'] as Map?;
      final closures = (data['closures'] as List?)?.length ?? 0;
      if (coding != null && coding['is_coded'] == true) {
        _mmdaStatus = MmdaStatus(
          codingMessage: coding['message'] as String? ?? '',
          isCoded: true,
          closuresCount: closures,
        );
        // Surface as advisory if there's an active coding restriction
        if (_mmdaStatus.codingMessage != null &&
            _mmdaStatus.codingMessage!.isNotEmpty &&
            advisory == null) {
          setAdvisory(
            AdvisoryModel(
              message: '🚦 MMDA: ${_mmdaStatus.codingMessage}',
              type: 'warning',
            ),
          );
        }
      } else {
        _mmdaStatus = MmdaStatus(closuresCount: closures);
      }
      notifyListeners();
    } catch (_) {
      // MMDA is optional — silently degrade
    }
  }

  /// Fetch safety overlay data from backend for a given location.
  /// Populates hotspots (earthquake + report circles), POIs (safe spots),
  /// and the advisory banner.
  ///
  /// BACKEND ENDPOINTS USED:
  ///   GET /api/safety?lat=&lon=              → weather, crime, flood, seismic + advisory
  ///   GET /api/safe-spots/flutter?lat=&lon=  → hospital, police, fire, pharmacy markers
  Future<void> fetchSafetyOverlays({
    required double lat,
    required double lon,
    List<List<double>> polyline = const [],
  }) async {
    try {
      final token = await SessionManager.instance.getAuthToken();

      final safetyData = await ApiClient.instance.getSafety(
        lat: lat,
        lon: lon,
        token: token,
      );

      final newHotspots = <HotspotModel>[];
      final newPois = <PoiModel>[];

      if (safetyData['ok'] == true) {
        // ── Community reports → hotspot circles ──────────────────
        final reports = safetyData['reports'] as List? ?? [];
        for (final report in reports) {
          if (report is Map<String, dynamic>) {
            final rLat = (report['lat'] as num?)?.toDouble() ?? 0.0;
            final rLon = (report['lon'] as num?)?.toDouble() ?? 0.0;
            final label = report['label'] as String? ?? 'Safety Alert';
            final color = _colorFromReportType(report['type'] as String? ?? '');
            newHotspots.add(
              HotspotModel(
                lat: rLat,
                lng: rLon,
                radiusMeters: 200,
                label: label,
                color: color,
              ),
            );
          }
        }

        // ── Seismic circles ───────────────────────────────────────
        final seismicBlock = safetyData['seismic'] as Map? ?? {};
        final quakeList = seismicBlock['earthquakes'] as List? ?? [];
        for (final eq in quakeList) {
          if (eq is Map<String, dynamic>) {
            final eqLat = (eq['lat'] as num?)?.toDouble();
            final eqLon = (eq['lon'] as num?)?.toDouble();
            final radiusKm = (eq['radius_km'] as num?)?.toDouble() ?? 20.0;
            final mag = (eq['magnitude'] as num?)?.toDouble() ?? 0.0;
            final severity = eq['severity'] as String? ?? 'moderate';
            if (eqLat == null || eqLon == null) continue;
            newHotspots.add(
              HotspotModel(
                lat: eqLat,
                lng: eqLon,
                radiusMeters: radiusKm * 1000,
                label: 'M$mag Earthquake',
                color: _colorFromEqSeverity(severity),
              ),
            );
          }
        }

        // ── Advisory banner logic ─────────────────────────────────
        final crimePenalty = safetyData['crime']?['penalty'] as int? ?? 0;
        final floodPenalty = safetyData['flood']?['penalty'] as int? ?? 0;
        final weatherRisk =
            safetyData['weather']?['risk_level'] as String? ?? 'clear';
        final seismicCount = seismicBlock['count'] as int? ?? 0;

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

        if (newAdvisory != null) setAdvisory(newAdvisory);
      }

      // ── Safe spots → PoiModel markers ───────────────────────────
      // Sample 5 evenly-spaced points along the combined polyline so POIs
      // cover the full route, not just one midpoint.
      try {
        final seenIds = <String>{};
        final sampleCoords = <Map<String, double>>[];
        if (polyline.length >= 2) {
          final total = polyline.length;
          for (final idx in <int>{
            0,
            total ~/ 4,
            total ~/ 2,
            (total * 3) ~/ 4,
            total - 1,
          }) {
            sampleCoords.add({
              'lat': polyline[idx][0],
              'lon': polyline[idx][1],
            });
          }
        } else {
          sampleCoords.add({'lat': lat, 'lon': lon});
        }
        for (final coord in sampleCoords) {
          try {
            final spotsData = await ApiClient.instance.getSafeSpots(
              lat: coord['lat']!,
              lon: coord['lon']!,
              token: token,
              radiusMeters: 800,
            );
            if (spotsData['ok'] == true) {
              for (final spot in (spotsData['spots'] as List? ?? [])) {
                if (spot is! Map<String, dynamic>) continue;
                final sid = spot['id']?.toString() ?? '';
                if (sid.isNotEmpty) {
                  if (seenIds.contains(sid)) continue;
                  seenIds.add(sid);
                }
                newPois.add(PoiModel(
                  lat: (spot['lat'] as num?)?.toDouble() ?? 0.0,
                  lng: (spot['lon'] as num?)?.toDouble() ?? 0.0,
                  name: spot['name'] as String? ?? '',
                  label: spot['label'] as String? ?? 'Safe Spot',
                  type: spot['type'] as String? ?? '',
                  icon: _iconForSpotType(spot['type'] as String? ?? ''),
                  color: _colorForSpotType(spot['type'] as String? ?? ''),
                ));
              }
            }
          } catch (_) {}
        }
      } catch (_) {
        // Safe spots are optional — silently degrade
      }

      setHotspots(newHotspots);
      setPois(newPois);
      if (newPois.isNotEmpty && !_safeSpotsVisible) {
        _safeSpotsVisible = true;
      }
    } catch (e) {
      debugPrint('[ExploreController] Error fetching safety overlays: $e');
    }
  }

  // ── Color helpers ───────────────────────────────────────────────
  Color _colorFromEqSeverity(String severity) {
    switch (severity) {
      case 'critical':
        return const Color(0x556C1A1A);
      case 'high':
        return const Color(0x44E74C3C);
      case 'moderate':
        return const Color(0x33E67E22);
      default:
        return const Color(0x22F39C12);
    }
  }

  IconData _iconForSpotType(String type) {
    switch (type) {
      case 'hospital':
        return Icons.local_hospital_rounded;
      case 'clinic':
        return Icons.local_hospital_outlined;
      case 'pharmacy':
        return Icons.medical_services_rounded;
      case 'police':
        return Icons.local_police_rounded;
      case 'fire_station':
        return Icons.fire_truck_rounded;
      case 'barangay_hall':
        return Icons.account_balance_rounded;
      case 'community_centre':
        return Icons.people_rounded;
      case 'convenience':
      case 'supermarket':
        return Icons.store_rounded;
      default:
        return Icons.place_rounded;
    }
  }

  Color _colorForSpotType(String type) {
    switch (type) {
      case 'hospital':
      case 'clinic':
        return const Color(0xFFE74C3C);
      case 'pharmacy':
        return const Color(0xFF27AE60);
      case 'police':
        return const Color(0xFF2980B9);
      case 'fire_station':
        return const Color(0xFFE67E22);
      case 'barangay_hall':
      case 'community_centre':
        return const Color(0xFF8E44AD);
      default:
        return const Color(0xFF0D9E9E);
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

  // ── Safe spots toggle ─────────────────────────────────────────
  bool _safeSpotsVisible = false;
  bool get safeSpotsVisible => _safeSpotsVisible;

  void toggleSafeSpots() {
    _safeSpotsVisible = !_safeSpotsVisible;
    showToast(
      _safeSpotsVisible ? 'Safe spots shown' : 'Safe spots hidden',
      'teal',
    );
    notifyListeners();
  }

  void setSafeSpotsVisible(bool v) {
    if (_safeSpotsVisible == v) return;
    _safeSpotsVisible = v;
    notifyListeners();
  }

  // ── Transport mode ─────────────────────────────────────────────
  // 'transit' | 'walk' | 'car' | 'motorcycle'
  String _activeMode = 'transit';
  String get activeMode => _activeMode;

  void setMode(String mode) {
    _activeMode = mode;
    notifyListeners();
    // Re-run route search with the new mode so the user sees updated results
    // immediately — mirrors the web's behaviour when the Transit/Walk/Car
    // selector is clicked while a destination is already set.
    if (_currentLocationText.isNotEmpty && _destinationText.isNotEmpty) {
      searchRoutes();
    }
  }

  // ── Transit sub-toggles (web parity) ──────────────────────────
  // When _activeMode == 'transit', these three flags determine which
  // transit modes are requested from the backend — matching the web's
  // Train / Jeepney / Bus ON/OFF tiles under the Transit selector.
  bool _transitTrainOn   = true;
  bool _transitJeepneyOn = true;
  bool _transitBusOn     = true;
  bool get transitTrainOn   => _transitTrainOn;
  bool get transitJeepneyOn => _transitJeepneyOn;
  bool get transitBusOn     => _transitBusOn;

  /// Computes the backend `mode` string from the three sub-toggle flags.
  /// Mirrors resolvedTransitMode() in the web frontend.
  String get resolvedTransitMode {
    final t = _transitTrainOn, j = _transitJeepneyOn, b = _transitBusOn;
    if (t && j && b) return 'transit';
    if (t && j)      return 'train_jeepney';
    if (t && b)      return 'train_bus';
    if (j && b)      return 'jeepney_bus';
    if (t)           return 'train';
    if (j)           return 'jeepney';
    if (b)           return 'bus';
    return 'transit'; // fallback: all on
  }

  void toggleTransitSub(String key) {
    final onCount = [_transitTrainOn, _transitJeepneyOn, _transitBusOn]
        .where((v) => v)
        .length;
    switch (key) {
      case 'train':
        if (_transitTrainOn && onCount == 1) return; // keep at least one on
        _transitTrainOn = !_transitTrainOn;
        break;
      case 'jeepney':
        if (_transitJeepneyOn && onCount == 1) return;
        _transitJeepneyOn = !_transitJeepneyOn;
        break;
      case 'bus':
        if (_transitBusOn && onCount == 1) return;
        _transitBusOn = !_transitBusOn;
        break;
    }
    notifyListeners();
    // Re-search when the user flips a transit sub-toggle while a destination
    // is already set — resolvedTransitMode has changed so the backend needs
    // to re-run with the new mode string (mirrors web sub-toggle behaviour).
    if (_activeMode == 'transit' &&
        _currentLocationText.isNotEmpty &&
        _destinationText.isNotEmpty) {
      searchRoutes();
    }
  }

  // ── Safe spot type filter (web parity) ─────────────────────────
  // The web shows 10 per-type checkboxes when "Include Safe Spots" is on.
  // Flutter mirrors this: pois getter filters _allPois by these types.
  static const Set<String> _kDefaultSpotTypes = {
    'police', 'hospital', 'fire_station', 'clinic', 'pharmacy',
    'barangay_hall', 'evacuation_centre',
  };
  Set<String> _selectedSpotTypes = {..._kDefaultSpotTypes};
  Set<String> get selectedSpotTypes => Set.unmodifiable(_selectedSpotTypes);

  void toggleSpotType(String type) {
    if (_selectedSpotTypes.contains(type)) {
      _selectedSpotTypes = {..._selectedSpotTypes}..remove(type);
    } else {
      _selectedSpotTypes = {..._selectedSpotTypes, type};
    }
    notifyListeners(); // pois getter re-filters automatically
  }

  // ── Plate digit (MMDA coding check, web parity) ────────────────
  String _plateDigit = '';
  String get plateDigit => _plateDigit;

  void setPlateDigit(String v) {
    _plateDigit = v.trim();
    notifyListeners();
  }

  // ── Map pinpoint-destination mode (web parity: 📌 locate-dest-btn) ──────────
  // When true, the next single tap on the map sets the destination.
  // Activated by the 📌 button in the filter row; auto-cancelled on set or dismiss.
  bool _pinpointDestMode = false;
  bool get pinpointDestMode => _pinpointDestMode;

  void togglePinpointDestMode() {
    _pinpointDestMode = !_pinpointDestMode;
    notifyListeners();
  }

  void cancelPinpointDestMode() {
    if (_pinpointDestMode) {
      _pinpointDestMode = false;
      notifyListeners();
    }
  }

  // ── Resolved geocoded coordinates from last route search ──────
  // Populated from orig_lat/orig_lon/dest_lat/dest_lon in API response.
  // Used by _MapLayer to place the A and B pins accurately.
  double? _resolvedOrigLat, _resolvedOrigLon;
  double? _resolvedDestLat, _resolvedDestLon;
  double? get resolvedOrigLat => _resolvedOrigLat;
  double? get resolvedOrigLon => _resolvedOrigLon;
  double? get resolvedDestLat => _resolvedDestLat;
  double? get resolvedDestLon => _resolvedDestLon;

  // ── Nearby transit stops (web parity: fetchAndDrawNearby) ──────
  // Populated from /api/nearby when origin is set.
  // Shown as coloured dot markers on the map (J/B/T icons, 800m radius).
  List<Map<String, dynamic>> _nearbyStops = [];
  List<Map<String, dynamic>> get nearbyStops => List.unmodifiable(_nearbyStops);

  Future<void> fetchNearbyStops(double lat, double lon) async {
    try {
      final stops = await ApiClient.instance.getNearby(lat: lat, lon: lon);
      _nearbyStops = stops;
      notifyListeners();
    } catch (_) {
      // Nearby stops are optional — silently degrade
    }
  }

  // ── Search inputs ──────────────────────────────────────────────
  String _currentLocationText = '';
  String _destinationText = '';
  bool _miniCurrentFocused = true;

  String get currentLocationText => _currentLocationText;
  String get destinationText => _destinationText;

  // Backward-compat getters
  String get originText => _currentLocationText;
  String get destText => _destinationText;
  bool get miniOriginFocused => _miniCurrentFocused;

  void setCurrentLocationText(String v) {
    _currentLocationText = v;
    notifyListeners();
  }

  void setDestinationText(String v) {
    _destinationText = v;
    notifyListeners();
  }

  // Backward-compat setters
  void setOriginText(String v) {
    _currentLocationText = v;
    notifyListeners();
  }

  void setDestText(String v) {
    _destinationText = v;
    notifyListeners();
  }

  /// Called when the user taps a suggestion that already has lat/lon from
  /// the backend Nominatim proxy. Pre-seeds the resolved coordinates so
  /// the map can show the pin immediately without waiting for searchRoutes().
  void previewLocation({
    required bool isOrigin,
    required double lat,
    required double lon,
    required String label,
  }) {
    if (isOrigin) {
      _currentLocationText = label;
      _resolvedOrigLat = lat;
      _resolvedOrigLon = lon;
      // Fetch nearby transit stops around the new origin (web parity)
      fetchNearbyStops(lat, lon);
      // Refresh safety overlays for the new origin — mirrors web setOrigin()
      // which calls loadSafetyOverlay() every time origin is set so hotspot
      // circles and safe-spot POIs always reflect the current area.
      unawaited(fetchSafetyOverlays(lat: lat, lon: lon));
    } else {
      _destinationText = label;
      _resolvedDestLat = lat;
      _resolvedDestLon = lon;
    }
    onMapPreview?.call(lat, lon);
    notifyListeners();
  }

  void setMiniFocus(bool current) {
    _miniCurrentFocused = current;
    notifyListeners();
  }

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

  // ── Live autocomplete (calls GET /api/suggest?q=) ──────────────
  Future<List<Map<String, dynamic>>> suggestLocations(String query) async {
    if (query.length < 3) return [];
    try {
      final token = await SessionManager.instance.getAuthToken();
      final results = await ApiClient.instance.suggestLocations(
        query: query,
        token: token,
      );
      return results;
    } catch (_) {
      return [];
    }
  }

  // ── Route search ───────────────────────────────────────────────
  Future<void> searchRoutes() async {
    if (_currentLocationText.isEmpty || _destinationText.isEmpty) {
      showToast(
        _currentLocationText.isEmpty
            ? 'Please enter your current location'
            : 'Please enter your destination',
        'red',
      );
      return;
    }
    _state = AppState.state2;
    _isLoadingRoutes = true;
    _allRoutes = [];
    _filteredRoutes = [];
    showToast('Finding routes...', 'teal');
    notifyListeners();

    // ── STEP 1: Geocode both endpoints immediately so A/B pins appear
    // on the map right away, before the full /api/routes pipeline completes.
    try {
      final token = await SessionManager.instance.getAuthToken();

      // Origin: prefer live GPS coords when user is at current location
      if (_lat != null &&
          _lng != null &&
          (_currentLocationText.isEmpty ||
              _currentLocationText.startsWith('14.') ||
              _currentLocationText.startsWith('My location') ||
              _currentLocationText == 'Current location')) {
        _resolvedOrigLat = _lat;
        _resolvedOrigLon = _lng;
        debugPrint('[searchRoutes] Origin: using live GPS ($_lat, $_lng)');
      } else {
        final origGeo = await ApiClient.instance.geocodeText(
          query: _currentLocationText,
          token: token,
        );
        if (origGeo != null) {
          _resolvedOrigLat = origGeo['lat'];
          _resolvedOrigLon = origGeo['lon'];
          debugPrint(
            '[searchRoutes] Origin geocoded: $_resolvedOrigLat, $_resolvedOrigLon',
          );
        } else {
          debugPrint(
            '[searchRoutes] Origin geocode FAILED for: $_currentLocationText',
          );
        }
      }

      final destGeo = await ApiClient.instance.geocodeText(
        query: _destinationText,
        token: token,
      );
      if (destGeo != null) {
        _resolvedDestLat = destGeo['lat'];
        _resolvedDestLon = destGeo['lon'];
        debugPrint(
          '[searchRoutes] Dest geocoded: $_resolvedDestLat, $_resolvedDestLon',
        );
      } else {
        debugPrint('[searchRoutes] Dest geocode FAILED for: $_destinationText');
      }

      // Paint pins immediately — user sees A/B markers while routes load
      notifyListeners();
    } catch (e) {
      debugPrint('[searchRoutes] Geocode step threw: $e');
      // Non-fatal: pins will appear later from the /api/routes response coords
    }

    try {
      // Build request body — include vulnerable profile and GPS coords if available
      final extraParams = <String, dynamic>{};
      if (_activeVulnerableProfile != null) {
        extraParams['vulnerable_profile'] = _activeVulnerableProfile;
      }
      if (_lat != null && _lng != null) {
        extraParams['orig_coords'] = {'lat': _lat, 'lon': _lng};
      }
      // If Step 1 geocoded the dest, pass it to the backend so it skips
      // its own geocoding (which may also fail for brand names).
      if (_resolvedDestLat != null && _resolvedDestLon != null) {
        extraParams['dest_coords'] = {
          'lat': _resolvedDestLat,
          'lon': _resolvedDestLon,
        };
      }
      // Plate digit → MMDA number coding check (web parity)
      final parsedPlate = int.tryParse(_plateDigit);
      if (parsedPlate != null) {
        extraParams['plate_last_digit'] = parsedPlate;
      }
      // Preference filter → send to backend so it can factor it into route scoring
      if (preferenceFilters.isNotEmpty) {
        extraParams['prefer'] = preferenceFilters.first;
      }

      // Resolve transit mode from sub-toggles (web parity)
      final effectiveMode =
          _activeMode == 'transit' ? resolvedTransitMode : _activeMode;

      final response = await ApiClient.instance.searchRoutesWithAlerts(
        origin: _currentLocationText,
        destination: _destinationText,
        mode: effectiveMode,
        extraParams: extraParams,
      );

      final rawRoutes = response['routes'];
      final routes = rawRoutes is List<RouteModel>
          ? rawRoutes
          : (rawRoutes as List?)?.whereType<RouteModel>().toList() ?? [];

      if (routes.isNotEmpty) {
        setAllRoutes(routes);

        // Store server-resolved geocoded coordinates for map pins.
        // Only overwrite Step 1 geocoded coords if the server gives a non-null
        // value — never replace a good geocoded coord with null.
        final apiOrigLat = (response['orig_lat'] as num?)?.toDouble();
        final apiOrigLon = (response['orig_lon'] as num?)?.toDouble();
        final apiDestLat = (response['dest_lat'] as num?)?.toDouble();
        final apiDestLon = (response['dest_lon'] as num?)?.toDouble();
        if (apiOrigLat != null) _resolvedOrigLat = apiOrigLat;
        if (apiOrigLon != null) _resolvedOrigLon = apiOrigLon;
        if (apiDestLat != null) _resolvedDestLat = apiDestLat;
        if (apiDestLon != null) _resolvedDestLon = apiDestLon;

        // Last resort: if dest is still null, extract it from the end of
        // the first route polyline — guaranteed to be near the destination.
        if (_resolvedDestLat == null && routes.isNotEmpty) {
          final poly = routes.first.polyline;
          if (poly.isNotEmpty) {
            _resolvedDestLat = poly.last[0];
            _resolvedDestLon = poly.last[1];
            debugPrint(
              '[searchRoutes] Dest from polyline end: $_resolvedDestLat,$_resolvedDestLon',
            );
          }
        }
        if (_resolvedOrigLat == null && routes.isNotEmpty) {
          final poly = routes.first.polyline;
          if (poly.isNotEmpty) {
            _resolvedOrigLat = poly.first[0];
            _resolvedOrigLon = poly.first[1];
            debugPrint(
              '[searchRoutes] Orig from polyline start: $_resolvedOrigLat,$_resolvedOrigLon',
            );
          }
        }
        debugPrint(
          '[searchRoutes] Final coords → orig=($_resolvedOrigLat,$_resolvedOrigLon) dest=($_resolvedDestLat,$_resolvedDestLon)',
        );
        // If dest was null after Step 1 (Nominatim couldn't resolve brand name
        // like "Jollibee MCU EDSA") but the backend resolved it, this notify
        // triggers _fitBoundsIfNewPins which now handles partial coords.
        notifyListeners(); // repaint map with A/B pins

        setAlertData(
          incidents:
              (response['incidents'] as List?)?.cast<Map<String, dynamic>>() ??
              [],
          mmdaBanner: response['mmda_banner']?.toString() ?? '',
          mmdaClosuresCount: response['mmda_closures_count'] as int? ?? 0,
          earthquakes:
              (response['earthquakes'] as List?)
                  ?.cast<Map<String, dynamic>>() ??
              [],
          seismicBanner: response['seismic_banner']?.toString() ?? '',
          weatherRisk: response['weather_risk']?.toString() ?? 'clear',
          floodRisk: response['flood_risk']?.toString() ?? 'none',
        );

        // ── Earthquake circles from /api/routes ─────────────────
        final eqList =
            (response['earthquakes'] as List?)?.cast<Map<String, dynamic>>() ??
            [];
        final eqHotspots = <HotspotModel>[];
        for (final eq in eqList) {
          final eqLat = (eq['lat'] as num?)?.toDouble();
          final eqLon = (eq['lon'] as num?)?.toDouble();
          final radiusKm = (eq['radius_km'] as num?)?.toDouble() ?? 20.0;
          final mag = (eq['magnitude'] as num?)?.toDouble() ?? 0.0;
          final severity = eq['severity'] as String? ?? 'moderate';
          if (eqLat == null || eqLon == null) continue;
          eqHotspots.add(
            HotspotModel(
              lat: eqLat,
              lng: eqLon,
              radiusMeters: radiusKm * 1000,
              label: 'M$mag Earthquake',
              color: _colorFromEqSeverity(severity),
            ),
          );
        }
        if (eqHotspots.isNotEmpty) setHotspots(eqHotspots);

        // ── Advisory from route-level risk ───────────────────────
        final seismicBannerText = response['seismic_banner']?.toString() ?? '';
        final wRisk = response['weather_risk']?.toString() ?? 'clear';
        // Show MMDA advisory if closures were found (overrides weather)
        if (_mmdaBanner.isNotEmpty && advisory == null) {
          setAdvisory(
            const AdvisoryModel(
              message: 'MMDA road closures are active — check route details.',
              type: 'warning',
            ),
          );
        } else if (seismicBannerText.isNotEmpty) {
          setAdvisory(
            const AdvisoryModel(
              message: 'Recent earthquake activity detected near your route.',
              type: 'warning',
            ),
          );
        } else if (wRisk == 'storm' || wRisk == 'heavy_rain') {
          setAdvisory(
            AdvisoryModel(
              message: 'Severe weather detected — travel with caution.',
              type: wRisk == 'storm' ? 'danger' : 'warning',
            ),
          );
        }

        // ── Fetch safe-spot POIs along ALL routes combined ────────
        // Merge every route polyline so POIs cover whichever route
        // the user selects, not just the first one.
        final allPoly = <List<double>>[];
        for (final r in routes) {
          allPoly.addAll(r.polyline);
        }
        final midIdx = allPoly.length ~/ 2;
        final safeLat = allPoly.isNotEmpty ? allPoly[midIdx][0] : (_lat ?? 14.5995);
        final safeLon = allPoly.isNotEmpty ? allPoly[midIdx][1] : (_lng ?? 120.9842);
        await fetchSafetyOverlays(
          lat: safeLat,
          lon: safeLon,
          polyline: allPoly,
        );

        return;
      }

      // No routes found
      _isLoadingRoutes = false;
      final apiOrigLat = (response['orig_lat'] as num?)?.toDouble();
      final apiOrigLon = (response['orig_lon'] as num?)?.toDouble();
      final apiDestLat = (response['dest_lat'] as num?)?.toDouble();
      final apiDestLon = (response['dest_lon'] as num?)?.toDouble();
      if (apiOrigLat != null) _resolvedOrigLat = apiOrigLat;
      if (apiOrigLon != null) _resolvedOrigLon = apiOrigLon;
      if (apiDestLat != null) _resolvedDestLat = apiDestLat;
      if (apiDestLon != null) _resolvedDestLon = apiDestLon;
      if (apiDestLat != null || apiOrigLat != null) notifyListeners();
      debugPrint(
        '[searchRoutes] No routes — coords: orig=($_resolvedOrigLat,$_resolvedOrigLon) dest=($_resolvedDestLat,$_resolvedDestLon)',
      );

      // Surface the backend's own error message (e.g. "No route found near your
      // origin/destination") so the user sees something actionable.
      final backendError = response['error'] as String?;
      setAllRoutes([]);
      setAlertData(
        incidents: [],
        mmdaBanner: '',
        mmdaClosuresCount: 0,
        earthquakes: [],
        seismicBanner: '',
        weatherRisk: 'clear',
        floodRisk: 'none',
      );
      showToast(
        (backendError != null && backendError.isNotEmpty)
            ? backendError
            : 'No routes found — try a more specific destination',
        'teal',
      );
    } catch (e, stack) {
      debugPrint('[searchRoutes] ERROR: $e');
      debugPrint('[searchRoutes] STACK: $stack');
      _isLoadingRoutes = false;
      _allRoutes = [];
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
      showToast('Could not reach server — check connection', 'red');
      notifyListeners();
    }
  }

  void clearSearch() {
    // If GPS location was already obtained, keep the origin address so that
    // the next search pre-fills "Your Location" automatically (mirrors web).
    if (!(_hasLocation && _lat != null)) {
      _currentLocationText = '';
    }
    // Always clear destination and route state
    _destinationText = '';
    _state = AppState.state1;
    _activeRoute = null;
    _isLoadingRoutes = false;
    _filteredRoutes = List.from(_allRoutes);
    advisory = null;
    // Keep origin pin on map if GPS is available, otherwise clear it
    if (_hasLocation && _lat != null) {
      _resolvedOrigLat = _lat;
      _resolvedOrigLon = _lng;
    } else {
      _resolvedOrigLat = null;
      _resolvedOrigLon = null;
    }
    _resolvedDestLat = null;
    _resolvedDestLon = null;
    _nearbyStops = [];
    showToast('Search cleared', 'teal');
    notifyListeners();
  }

  // ── Filters ────────────────────────────────────────────────────
  List<String> commuterFilters = [];
  List<String> transportFilters = [];
  List<String> ligtasFilters = [];
  List<String> preferenceFilters = [];

  bool get hasFilters =>
      commuterFilters.isNotEmpty ||
      transportFilters.isNotEmpty ||
      ligtasFilters.isNotEmpty ||
      preferenceFilters.isNotEmpty;

  void setSurveyDefaults({
    List<String> commuterTypes = const [],
    List<String> transport = const [],
    List<String> safety = const [],
  }) {
    // Seed active routing mode from survey transport preference so the first
    // automatic search uses the correct mode.  Do NOT seed transportFilters
    // as a post-filter — see _applyFilters() comment above.
    if (transport.isNotEmpty) {
      const valid = {
        'transit', 'walk', 'car', 'motorcycle', 'train', 'jeepney', 'bus',
      };
      final first = transport.first.toLowerCase();
      if (valid.contains(first)) {
        _activeMode = first;
        transportFilters = [first]; // UI chip only — not a route post-filter
      }
    }
    commuterFilters = List.of(commuterTypes); // UI chips only
    ligtasFilters = List.of(safety);          // UI chips only
    _applyFilters();
    notifyListeners();
  }

  void toggleFilter(String group, String key) {
    List<String> list;
    if (group == 'commuter') {
      list = commuterFilters;
    } else if (group == 'transport') {
      // Radio-style: one transport mode active at a time.
      // Selecting a mode also updates the active routing mode so routes
      // re-search immediately with the correct backend mode param.
      if (transportFilters.contains(key)) {
        transportFilters.remove(key);
        _activeMode = 'transit'; // revert to default when deselected
      } else {
        transportFilters.clear(); // clear any previous selection
        transportFilters.add(key);
        _activeMode = key; // sync routing mode
      }
      _applyFilters();
      notifyListeners();
      // Re-search with new mode if route endpoints are already set
      if (_currentLocationText.isNotEmpty && _destinationText.isNotEmpty) {
        searchRoutes();
      }
      return;
    } else if (group == 'ligtas') {
      list = ligtasFilters;
    } else {
      // Preference filters are radio-button style — only one active
      if (preferenceFilters.contains(key)) {
        preferenceFilters.remove(key);
      } else {
        preferenceFilters
          ..clear()
          ..add(key);
      }
      _applyFilters();
      notifyListeners();
      return;
    }
    if (list.contains(key)) {
      list.remove(key);
    } else {
      list.add(key);
    }
    _applyFilters();
    notifyListeners();
  }

  void removeFilter(String group, String key) {
    if (group == 'commuter') {
      commuterFilters.remove(key);
    } else if (group == 'transport') {
      transportFilters.remove(key);
      _activeMode = 'transit'; // reset routing mode to default on chip removal
    } else if (group == 'ligtas') {
      ligtasFilters.remove(key);
    } else {
      preferenceFilters.remove(key);
    }
    _applyFilters();
    notifyListeners();
  }

  void applyFilters() {
    final total =
        commuterFilters.length +
        transportFilters.length +
        ligtasFilters.length +
        preferenceFilters.length;
    showToast(total > 0 ? 'Filters applied' : 'No filters active', 'teal');
    _applyFilters();
    // Re-search so backend-level changes (plate digit, profile) take effect
    // immediately when the user taps "Apply Filters".
    if (_currentLocationText.isNotEmpty && _destinationText.isNotEmpty) {
      searchRoutes(); // async — searchRoutes() calls notifyListeners() itself
    } else {
      notifyListeners();
    }
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

  // ── Vulnerable commuter profile ────────────────────────────────
  // Stored locally + sent to /api/routes as `vulnerable_profile`.
  // The backend (vulnerable_profiles.py) applies extra safety penalties
  // and generates profile-specific warnings per route.
  String?
  _activeVulnerableProfile; // 'senior' | 'pwd' | 'women' | 'child' | null
  String? get activeVulnerableProfile => _activeVulnerableProfile;

  void setVulnerableProfile(String? profile) {
    _activeVulnerableProfile = profile;
    final label = _profileLabel(profile);
    showToast(
      profile != null ? '$label mode active' : 'Profile cleared',
      'teal',
    );
    // Re-search if we already have a destination so the backend re-applies
    // the new profile's penalties to the current route set.
    if (_currentLocationText.isNotEmpty && _destinationText.isNotEmpty) {
      searchRoutes();
    }
    notifyListeners();
  }

  String _profileLabel(String? p) {
    switch (p) {
      case 'senior':
        return '🧓 Senior';
      case 'pwd':
        return '♿ PWD';
      case 'women':
        return '👩 Women\'s Safety';
      case 'child':
        return '🎒 Child/Student';
      default:
        return 'Profile';
    }
  }

  // ── Rain active flag (drives flood zone visibility on map) ───
  // True when weather_risk is light_rain / rain / heavy_rain / storm.
  bool get isRaining {
    const rainyLevels = {'light_rain', 'rain', 'heavy_rain', 'storm'};
    return rainyLevels.contains(_weatherRisk);
  }

  // ── Routes ─────────────────────────────────────────────────────
  List<RouteModel> _allRoutes = [];
  List<RouteModel> get allRoutes => _allRoutes;

  List<RouteModel> _filteredRoutes = [];
  List<RouteModel> get routes => _filteredRoutes;

  // ── Alert data ─────────────────────────────────────────────────
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

  String _weatherRisk = 'clear';
  String get weatherRisk => _weatherRisk;

  String _floodRisk = 'none';
  String get floodRisk => _floodRisk;

  void setAllRoutes(List<RouteModel> newRoutes) {
    _allRoutes = newRoutes;
    _isLoadingRoutes = false;
    _applyFilters();
    // Auto-select the first route so the map draws it immediately on load
    if (newRoutes.isNotEmpty) {
      _activeRoute = _allRoutes.first;
    }
    notifyListeners();
  }

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

  void _applyFilters() {
    List<RouteModel> result = List.from(_allRoutes);

    // Transport mode, commuter type, and ligtas features are applied at the
    // backend level (mode=, vulnerable_profile=). Post-filtering by route label
    // or tag lists here would silently hide valid routes because:
    //   • route.modes is a display string ("Route 1", "Jeepney via EDSA")
    //     that never matches filter keys like "transit"
    //   • route.commuterTags and route.ligtasTags are always [] from the API
    // These filters are kept as chip UI state only — not used to cull results.

    if (preferenceFilters.isNotEmpty) {
      final pref = preferenceFilters.first;
      if (pref == 'avoid_flood') {
        // Push flooded routes to the bottom; prefer routes with no flood warning
        result.sort((a, b) {
          final aFlooded = (a.floodWarning != null && a.floodWarning!.isNotEmpty) ? 1 : 0;
          final bFlooded = (b.floodWarning != null && b.floodWarning!.isNotEmpty) ? 1 : 0;
          if (aFlooded != bFlooded) return aFlooded.compareTo(bFlooded);
          return b.safetyScore.compareTo(a.safetyScore); // secondary: safest first
        });
      } else if (pref == 'safest') {
        result.sort((a, b) => b.safetyScore.compareTo(a.safetyScore));
      } else if (pref == 'fastest') {
        result.sort((a, b) => a.minutes.compareTo(b.minutes));
      } else if (pref == 'cheapest') {
        result.sort((a, b) => a.fare.compareTo(b.fare));
      } else if (pref == 'balanced') {
        result.sort((a, b) {
          final aScore =
              (a.safetyScore / 100) - (a.minutes / 120) - (a.fare / 100);
          final bScore =
              (b.safetyScore / 100) - (b.minutes / 120) - (b.fare / 100);
          return bScore.compareTo(aScore);
        });
      } else if (pref == 'moderate') {
        result.sort(
          (a, b) => _calculateVariance(a).compareTo(_calculateVariance(b)),
        );
      }
    }

    if (_ligtasModeOn && preferenceFilters.isEmpty) {
      result.sort((a, b) => b.safetyScore.compareTo(a.safetyScore));
    }

    if (result.isEmpty && hasFilters) {
      result = List.from(_allRoutes);
      showToast('No routes match filters — showing all', 'teal');
    }

    _filteredRoutes = result;
  }

  RouteModel? _activeRoute;
  RouteModel? get activeRoute => _activeRoute;

  void selectRoute(RouteModel r) {
    _activeRoute = _allRoutes.firstWhere(
      (route) => route.id == r.id,
      orElse: () => r,
    );
    _state = AppState.state3;
    SessionManager.instance.setHasActiveRoute(false);
    notifyListeners();

    // Re-fetch safe spots along the newly selected route so markers
    // always follow the route the user is actually viewing.
    final poly = _activeRoute!.polyline;
    if (poly.isNotEmpty) {
      final mid = poly[poly.length ~/ 2];
      fetchSafetyOverlays(lat: mid[0], lon: mid[1], polyline: poly);
    }
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
                Container(
                  width: 44,
                  height: 44,
                  decoration: const BoxDecoration(
                    color: AppColors.redDim,
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(
                    Icons.stop_circle_outlined,
                    color: AppColors.safeRed,
                    size: 22,
                  ),
                ),
                const SizedBox(height: 14),
                Text(
                  'Stop Navigation?',
                  style: GoogleFonts.plusJakartaSans(
                    fontSize: 17,
                    fontWeight: FontWeight.w800,
                    color: AppColors.text(isDark),
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  'Are you sure you want to stop? This will end your current route navigation.',
                  style: GoogleFonts.plusJakartaSans(
                    fontSize: 13,
                    color: AppColors.text2(isDark),
                    height: 1.5,
                  ),
                ),
                const SizedBox(height: 24),
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton(
                        style: OutlinedButton.styleFrom(
                          foregroundColor: AppColors.text2(isDark),
                          side: BorderSide(color: AppColors.border(isDark)),
                          padding: const EdgeInsets.symmetric(vertical: 13),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                        ),
                        onPressed: () => Navigator.of(dialogContext).pop(),
                        child: Text(
                          'Cancel',
                          style: GoogleFonts.plusJakartaSans(
                            fontWeight: FontWeight.w700,
                          ),
                        ),
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
                            borderRadius: BorderRadius.circular(12),
                          ),
                        ),
                        onPressed: () {
                          Navigator.of(dialogContext).pop();
                          stopNavigation();
                        },
                        child: Text(
                          'Stop Route',
                          style: GoogleFonts.plusJakartaSans(
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  void backToRoutes() {
    _state = AppState.state2;
    // Keep first route selected so polylines remain visible on the map
    if (_activeRoute == null && _allRoutes.isNotEmpty) {
      _activeRoute = _allRoutes.first;
    }
    SessionManager.instance.setHasActiveRoute(false);
    notifyListeners();
  }

  // ── Map zoom ───────────────────────────────────────────────────
  int _mapZoom = 14;
  int get mapZoom => _mapZoom;
  void zoomIn() {
    _mapZoom = (_mapZoom + 1).clamp(3, 19);
    notifyListeners();
  }

  void zoomOut() {
    _mapZoom = (_mapZoom - 1).clamp(3, 19);
    notifyListeners();
  }

  // ── Report incident ────────────────────────────────────────────
  // Report types are fetched from GET /api/report-types on first open.
  List<ReportType> _reportTypes = const [
    ReportType(key: 'crime', label: 'Crime', icon: '🚨'),
    ReportType(key: 'flood', label: 'Flooding', icon: '🌊'),
    ReportType(key: 'accident', label: 'Accident', icon: '🚗'),
    ReportType(key: 'hazard', label: 'Road Hazard', icon: '⚠️'),
  ];
  List<ReportType> get reportTypes => _reportTypes;
  bool _reportTypesLoaded = false;

  /// Fetch report type options from backend (cached after first call).
  /// GET /api/report-types → [{ key, label, icon }]
  Future<void> loadReportTypes() async {
    if (_reportTypesLoaded) return;
    try {
      final token = await SessionManager.instance.getAuthToken();
      final types = await ApiClient.instance.getReportTypes(token: token);
      if (types.isNotEmpty) {
        _reportTypes = types
            .map(
              (t) => ReportType(
                key: t['key'] as String? ?? '',
                label: t['label'] as String? ?? '',
                icon: t['icon'] as String? ?? '⚠️',
              ),
            )
            .where((t) => t.key.isNotEmpty)
            .toList();
        _reportTypesLoaded = true;
        notifyListeners();
      }
    } catch (_) {
      // Keep default hardcoded types on failure
    }
  }

  /// Submit a community incident report.
  /// POST /report  →  { ok, message }
  Future<bool> submitReport({
    required String reportType,
    required double lat,
    required double lon,
    required String description,
  }) async {
    try {
      final token = await SessionManager.instance.getAuthToken();
      final result = await ApiClient.instance.submitReport(
        reportType: reportType,
        lat: lat,
        lon: lon,
        description: description,
        token: token,
      );
      final ok = result['ok'] == true;
      showToast(
        result['message'] as String? ??
            (ok ? 'Report submitted!' : 'Failed to submit'),
        ok ? 'green' : 'red',
      );
      return ok;
    } catch (e) {
      showToast('Could not submit report', 'red');
      return false;
    }
  }

  // ── SOS ────────────────────────────────────────────────────────
  bool _sosSending = false;
  bool get sosSending => _sosSending;

  /// Trigger SOS: logs the event with current GPS coords + active route summary.
  /// POST /api/sos  →  { ok, message, share_link }
  Future<void> triggerSos(BuildContext context) async {
    if (_sosSending) return;
    _sosSending = true;
    showToast('Sending SOS…', 'red');
    notifyListeners();

    try {
      final token = await SessionManager.instance.getAuthToken();
      final lat = _lat ?? 0.0;
      final lon = _lng ?? 0.0;
      final routeSummary = _activeRoute?.modes ?? '';

      final result = await ApiClient.instance.triggerSos(
        lat: lat,
        lon: lon,
        message: 'SOS from Ligtas app',
        routeSummary: routeSummary,
        token: token,
      );

      _sosSending = false;
      notifyListeners();

      if (result['ok'] == true) {
        final shareLink = result['share_link'] as String? ?? '';
        if (!context.mounted) return;
        _showSosSuccessDialog(context, shareLink);
      } else {
        showToast(result['message'] as String? ?? 'SOS failed', 'red');
      }
    } catch (e) {
      _sosSending = false;
      showToast('Could not send SOS', 'red');
      notifyListeners();
    }
  }

  void _showSosSuccessDialog(BuildContext context, String shareLink) {
    final isDark = context.read<ThemeController>().isDark;
    showDialog(
      context: context,
      builder: (ctx) => Dialog(
        backgroundColor: Colors.transparent,
        child: Container(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            color: AppColors.card(isDark),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: AppColors.border(isDark)),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 56,
                height: 56,
                decoration: const BoxDecoration(
                  color: Color(0x22DC2626),
                  shape: BoxShape.circle,
                ),
                child: const Icon(
                  Icons.emergency_rounded,
                  color: Color(0xFFDC2626),
                  size: 28,
                ),
              ),
              const SizedBox(height: 16),
              Text(
                'SOS Sent',
                style: GoogleFonts.plusJakartaSans(
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                  color: AppColors.text(isDark),
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'Your trusted contacts have been alerted with your location.',
                style: GoogleFonts.plusJakartaSans(
                  fontSize: 13,
                  color: AppColors.text2(isDark),
                  height: 1.5,
                ),
                textAlign: TextAlign.center,
              ),
              // ── Share link (backend provides a public emergency URL) ──────
              // Shown only when the server returned a non-empty share_link.
              // Tapping "Copy Link" copies the URL to the clipboard so the
              // user can paste it into a message to helpers nearby.
              if (shareLink.isNotEmpty) ...[
                const SizedBox(height: 14),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                    color: AppColors.bg(isDark),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: AppColors.border(isDark)),
                  ),
                  child: Text(
                    shareLink,
                    style: GoogleFonts.plusJakartaSans(
                      fontSize: 11,
                      color: AppColors.text2(isDark),
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
              const SizedBox(height: 20),
              if (shareLink.isNotEmpty)
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton(
                        style: OutlinedButton.styleFrom(
                          foregroundColor: AppColors.teal,
                          side: const BorderSide(color: AppColors.teal),
                          padding: const EdgeInsets.symmetric(vertical: 13),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                        ),
                        onPressed: () {
                          Clipboard.setData(ClipboardData(text: shareLink));
                          showToast('Link copied!', 'teal');
                        },
                        child: Text(
                          'Copy Link',
                          style: GoogleFonts.plusJakartaSans(
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: ElevatedButton(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: AppColors.teal,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(vertical: 13),
                          elevation: 0,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                        ),
                        onPressed: () => Navigator.of(ctx).pop(),
                        child: Text(
                          'OK',
                          style: GoogleFonts.plusJakartaSans(
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                    ),
                  ],
                )
              else
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.teal,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 13),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                  onPressed: () => Navigator.of(ctx).pop(),
                  child: Text(
                    'OK',
                    style: GoogleFonts.plusJakartaSans(
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  // ── Helper ─────────────────────────────────────────────────────
  double _calculateVariance(RouteModel route) {
    final normalizedSafety = route.safetyScore / 100;
    final normalizedTime = 1 - (route.minutes / 120);
    final normalizedCost = 1 - (route.fare / 100);
    final mean = (normalizedSafety + normalizedTime + normalizedCost) / 3;
    return ((normalizedSafety - mean).abs() +
            (normalizedTime - mean).abs() +
            (normalizedCost - mean).abs()) /
        3;
  }
}