// models/user_model.dart
import '../data/mock_data.dart'; // FIX: Import the file where Mateo Santos lives

class UserModel {
  final String id;
  final String name;
  final String username;
  final String role;
  final String? avatarUrl;
  final UserStats stats;
  final String? commuterType;
  final UserPreferences preferences;

  const UserModel({
    required this.id,
    required this.name,
    required this.username,
    required this.role,
    this.avatarUrl,
    required this.stats,
    this.commuterType,
    required this.preferences,
  });

  // FIX: Instead of returning generic text, this now returns the actual data 
  // from your mock_data.dart file.
  static UserModel mock() {
    return mockUser; 
  }

  UserModel copyWith({
    String? name, 
    String? username, 
    String? role,
    String? avatarUrl, 
    UserStats? stats,
    String? commuterType, 
    UserPreferences? preferences,
  }) => UserModel(
    id: id,
    name: name ?? this.name,
    username: username ?? this.username,
    role: role ?? this.role,
    avatarUrl: avatarUrl ?? this.avatarUrl,
    stats: stats ?? this.stats,
    commuterType: commuterType ?? this.commuterType,
    preferences: preferences ?? this.preferences,
  );

  TrustRank get trustRank {
    final u = stats.upvotedReports;
    if (u >= 50) return TrustRank.lighthouse;
    if (u >= 10) return TrustRank.lantern;
    return TrustRank.candle;
  }
}

class UserStats {
  final int trips;
  final int reports;
  final int upvotedReports;
  
  const UserStats({
    required this.trips,
    required this.reports,
    required this.upvotedReports,
  });

  UserStats copyWith({int? trips, int? reports, int? upvotedReports}) =>
    UserStats(
      trips: trips ?? this.trips,
      reports: reports ?? this.reports,
      upvotedReports: upvotedReports ?? this.upvotedReports,
    );
}

class UserPreferences {
  final bool aiSafety;
  final bool nightMode;
  final List<String> transport;

  const UserPreferences({
    this.aiSafety = true,
    this.nightMode = false,
    this.transport = const ['jeep', 'walk'],
  });

  UserPreferences copyWith({bool? aiSafety, bool? nightMode, List<String>? transport}) =>
    UserPreferences(
      aiSafety:  aiSafety  ?? this.aiSafety,
      nightMode: nightMode ?? this.nightMode,
      transport: transport ?? this.transport,
    );
}

enum TrustRank { candle, lantern, lighthouse }

extension TrustRankExt on TrustRank {
  String get label {
    switch (this) {
      case TrustRank.candle:     return 'Candle';
      case TrustRank.lantern:    return 'Lantern';
      case TrustRank.lighthouse: return 'Lighthouse';
    }
  }
}