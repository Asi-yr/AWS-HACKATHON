import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/app_colors.dart';
import '../../core/custom_theme.dart';
import '../../core/api_client.dart';
import '../../core/session_manager.dart';
import '../../widgets/shared_widgets.dart';

// ── COMMUNITY VIEW ────────────────────────────────────────────
// Merged: frontend design richness  +  tetsing backend connectivity
//
// API endpoints used:
//   GET  /api/reports              → _fetchReports
//   POST /api/reports/<id>/confirm → _handleVerify (upvote)
//   POST /api/report               → report dialog (submit new)

// ─────────────────────────────────────────────────────────────
// MODELS
// ─────────────────────────────────────────────────────────────

enum _PostType { report, alert, tip }
enum _Severity { critical, high, moderate, info }
enum _Category { all, flood, typhoon, fire, quake, crime }

class _Post {
  final int id;
  final String author, reputation, content, location, timeAgo;
  final _PostType type;
  final _Severity severity;
  final String badge;
  final List<String> tags;
  final List<Color> gradient;
  final int verifyCount, verifyMax, comments;
  final bool gpsVerified;
  final bool userVerified;
  final double lat, lon;

  const _Post({
    required this.id,
    required this.author,
    required this.reputation,
    required this.content,
    required this.location,
    required this.timeAgo,
    required this.type,
    required this.severity,
    required this.badge,
    required this.tags,
    required this.gradient,
    required this.verifyCount,
    required this.verifyMax,
    required this.comments,
    required this.gpsVerified,
    required this.userVerified,
    required this.lat,
    required this.lon,
  });

  String get initials =>
      author.trim().split(' ').map((w) => w.isEmpty ? '' : w[0]).take(2).join();

  _Post copyWith({int? verifyCount, bool? userVerified}) => _Post(
    id: id,
    author: author,
    reputation: reputation,
    content: content,
    location: location,
    timeAgo: timeAgo,
    type: type,
    severity: severity,
    badge: badge,
    tags: tags,
    gradient: gradient,
    verifyMax: verifyMax,
    comments: comments,
    gpsVerified: gpsVerified,
    lat: lat,
    lon: lon,
    verifyCount: verifyCount ?? this.verifyCount,
    userVerified: userVerified ?? this.userVerified,
  );
}

class _Notif {
  final String id, body, timeAgo;
  final IconData icon;
  final Color iconColor;
  bool unread;
  _Notif({
    required this.id,
    required this.body,
    required this.timeAgo,
    required this.icon,
    required this.iconColor,
    required this.unread,
  });
}

// ─────────────────────────────────────────────────────────────
// FALLBACK MOCK DATA  (used when API is unreachable)
// ─────────────────────────────────────────────────────────────

final _mockPosts = <_Post>[
  _Post(
    id: 1,
    author: 'Juan Dela Cruz',
    reputation: 'Lantern',
    content: 'Knee-deep flooding along Taft Avenue near DLSU. Vehicles advised to take alternate routes immediately.',
    location: 'Pasay City',
    timeAgo: '5m ago',
    type: _PostType.report,
    severity: _Severity.critical,
    badge: 'Flood Watch',
    tags: ['flood', 'road'],
    gradient: const [Color(0xFFE63946), Color(0xFFC1121F)],
    verifyCount: 124,
    verifyMax: 150,
    comments: 12,
    gpsVerified: true,
    userVerified: false,
    lat: 14.5647,
    lon: 120.9930,
  ),
  _Post(
    id: 2,
    author: 'Ana Reyes',
    reputation: 'Lantern',
    content: 'Flooded underpass near Tandang Sora. Depth around knee-level. Avoid C5 northbound.',
    location: 'Tandang Sora, QC',
    timeAgo: '12m ago',
    type: _PostType.report,
    severity: _Severity.high,
    badge: 'Flood',
    tags: ['flood', 'road'],
    gradient: const [Color(0xFF3B9ED4), Color(0xFF1A6FA0)],
    verifyCount: 24,
    verifyMax: 150,
    comments: 5,
    gpsVerified: false,
    userVerified: false,
    lat: 14.62,
    lon: 121.02,
  ),
  _Post(
    id: 3,
    author: 'Rico Bautista',
    reputation: 'Lighthouse',
    content: 'Snatching incident reported near Commonwealth MRT station exit. Stay alert and keep bags in front.',
    location: 'Commonwealth Ave, QC',
    timeAgo: '38m ago',
    type: _PostType.alert,
    severity: _Severity.high,
    badge: 'Crime Alert',
    tags: ['crime', 'mrt'],
    gradient: const [Color(0xFFFACC15), Color(0xFFD4A017)],
    verifyCount: 41,
    verifyMax: 150,
    comments: 9,
    gpsVerified: false,
    userVerified: false,
    lat: 14.62,
    lon: 121.05,
  ),
  _Post(
    id: 4,
    author: 'PAGASA Official',
    reputation: 'Lighthouse',
    content: 'Typhoon Signal No. 2 raised over Metro Manila and nearby provinces. Prepare emergency kits.',
    location: 'Metro Manila',
    timeAgo: '30m ago',
    type: _PostType.alert,
    severity: _Severity.info,
    badge: 'Official',
    tags: ['typhoon', 'official'],
    gradient: const [Color(0xFF1A7FC1), Color(0xFF1A6FA0)],
    verifyCount: 341,
    verifyMax: 9999,
    comments: 89,
    gpsVerified: false,
    userVerified: true,
    lat: 14.5995,
    lon: 120.9842,
  ),
  _Post(
    id: 5,
    author: 'Leni Cruz',
    reputation: 'Candle',
    content: 'Alternative route: Cut through Batasan Hills via Constitution Hills road. Clear and well-lit.',
    location: 'Batasan Hills, QC',
    timeAgo: '2h ago',
    type: _PostType.tip,
    severity: _Severity.moderate,
    badge: 'Safe Route',
    tags: ['route', 'safe'],
    gradient: const [Color(0xFF34D399), Color(0xFF059669)],
    verifyCount: 8,
    verifyMax: 150,
    comments: 3,
    gpsVerified: false,
    userVerified: false,
    lat: 14.63,
    lon: 121.04,
  ),
];

final _mockNotifs = <_Notif>[
  _Notif(id: 'n1', body: 'Flash Flood Warning for low-lying areas in QC',
      timeAgo: '30m ago', icon: Icons.water, iconColor: AppColors.blue, unread: true),
  _Notif(id: 'n2', body: 'Your report was verified by 12 people',
      timeAgo: '1h ago', icon: Icons.thumb_up_rounded, iconColor: AppColors.teal, unread: true),
  _Notif(id: 'n3', body: 'Typhoon Signal No. 2 raised over Metro Manila',
      timeAgo: '2h ago', icon: Icons.cyclone, iconColor: AppColors.redDark, unread: false),
  _Notif(id: 'n4', body: 'New crime alert near your saved location',
      timeAgo: '3h ago', icon: Icons.security, iconColor: AppColors.yellow, unread: false),
];

// ─────────────────────────────────────────────────────────────
// HELPERS — map raw API response → _Post
// ─────────────────────────────────────────────────────────────

_PostType _typeFromString(String raw) {
  switch (raw.toLowerCase()) {
    case 'crime':
    case 'alert':
      return _PostType.alert;
    case 'tip':
    case 'safe route':
      return _PostType.tip;
    default:
      return _PostType.report;
  }
}

_Severity _severityFromType(_PostType type, String raw) {
  if (raw == 'flooding') return _Severity.critical;
  if (type == _PostType.alert) return _Severity.high;
  if (type == _PostType.tip) return _Severity.moderate;
  return _Severity.high;
}

List<Color> _gradientForType(_PostType type, _Severity severity) {
  if (type == _PostType.alert) {
    if (severity == _Severity.critical) {
      return const [Color(0xFFE63946), Color(0xFFC1121F)];
    }
    return const [Color(0xFFFACC15), Color(0xFFD4A017)];
  }
  if (type == _PostType.tip) return const [Color(0xFF34D399), Color(0xFF059669)];
  return const [Color(0xFF3B9ED4), Color(0xFF1A6FA0)];
}

String _formatTime(dynamic timestamp) {
  if (timestamp == null) return 'recently';
  try {
    final dt = DateTime.parse(timestamp.toString()).toLocal();
    final diff = DateTime.now().difference(dt);
    if (diff.inMinutes < 1) return 'just now';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    if (diff.inHours < 24) return '${diff.inHours}h ago';
    return '${diff.inDays}d ago';
  } catch (_) {
    return 'recently';
  }
}

_Post _postFromApi(Map<String, dynamic> r) {
  final rawType = r['report_type']?.toString().toLowerCase() ?? 'report';
  final type = _typeFromString(rawType);
  final severity = _severityFromType(type, rawType);
  return _Post(
    id: (r['id'] ?? 0) as int,
    author: r['username']?.toString() ?? 'Anonymous',
    reputation: r['trust_rank']?.toString() ?? 'Candle',
    content: r['description']?.toString() ?? 'No description',
    location: r['location']?.toString() ?? 'Unknown location',
    timeAgo: _formatTime(r['reported_at']),
    type: type,
    severity: severity,
    badge: rawType.isNotEmpty
        ? '${rawType[0].toUpperCase()}${rawType.substring(1)}'
        : 'Report',
    tags: [rawType],
    gradient: _gradientForType(type, severity),
    verifyCount: (r['confirmations'] ?? 0) as int,
    verifyMax: 150,
    comments: 0,
    gpsVerified: r['has_photo'] == true,
    userVerified: false,
    lat: (r['lat'] as num?)?.toDouble() ?? 0.0,
    lon: (r['lon'] as num?)?.toDouble() ?? 0.0,
  );
}

// ─────────────────────────────────────────────────────────────
// MAIN VIEW
// ─────────────────────────────────────────────────────────────

class CommunityView extends StatefulWidget {
  const CommunityView({super.key});

  @override
  State<CommunityView> createState() => _CommunityViewState();
}

class _CommunityViewState extends State<CommunityView> {
  List<_Post> _posts = [];
  final List<_Notif> _notifs = List.from(_mockNotifs);
  _Category _activeCategory = _Category.all;
  bool _isLoading = true;
  List<Map<String, dynamic>> _reportTypes = [];

  @override
  void initState() {
    super.initState();
    _fetchReports();
    _fetchReportTypes();
  }

  Future<void> _fetchReportTypes() async {
    try {
      final token = await SessionManager.instance.getAuthToken();
      final types = await ApiClient.instance.getReportTypes(token: token);
      if (mounted && types.isNotEmpty) setState(() => _reportTypes = types);
    } catch (_) {
      // Keep empty — dialog will use fallback list
    }
  }

  Future<void> _fetchReports() async {
    try {
      final token = await SessionManager.instance.getAuthToken();
      final raw = await ApiClient.instance.getReports(token: token);
      final posts = raw.map(_postFromApi).toList();
      if (mounted) setState(() { _posts = posts; _isLoading = false; });
    } catch (_) {
      if (mounted) setState(() { _posts = List.from(_mockPosts); _isLoading = false; });
    }
  }

  int get _unreadCount => _notifs.where((n) => n.unread).length;

  List<_Post> get _filtered {
    if (_activeCategory == _Category.all) return _posts;
    final name = _activeCategory.name;
    return _posts.where((p) =>
        p.tags.any((t) => t.contains(name)) ||
        p.badge.toLowerCase().contains(name)).toList();
  }

  @override
  Widget build(BuildContext context) {
    // No Scaffold — _RootShell in main.dart owns Scaffold + bottom nav
    return Stack(children: [
      Column(children: [
        LigtasHeader(
          title: 'Community',
          trailing: _NotifBtn(
            unread: _unreadCount,
            onTap: () => _showNotifSheet(context),
          ),
        ),
        Expanded(child: _buildFeed()),
      ]),
      Positioned(
        bottom: 88,
        right: 16,
        child: FloatingActionButton.extended(
          onPressed: () => _showReportDialog(context),
          backgroundColor: AppColors.primaryTeal(context.isDark),
          foregroundColor: Colors.white,
          icon: const Icon(Icons.add_rounded),
          label: Text('Report',
              style: GoogleFonts.plusJakartaSans(fontWeight: FontWeight.w800)),
        ),
      ),
    ]);
  }

  Widget _buildFeed() {
    if (_isLoading) {
      return const Center(
        child: CircularProgressIndicator(
            valueColor: AlwaysStoppedAnimation<Color>(AppColors.teal)),
      );
    }

    return RefreshIndicator(
      color: AppColors.teal,
      onRefresh: _fetchReports,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 100),
        children: [
          _AlertBanner(),
          const SizedBox(height: 12),
          _buildCategoryPills(),
          const SizedBox(height: 4),
          _buildSectionHeader(),
          if (_filtered.isEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 40),
              child: Center(
                child: Text('No reports in this category.',
                    style: context.lt.body(size: 13, color: context.lt.text2)),
              ),
            )
          else
            ..._filtered.map((p) => _PostCard(
              post: p,
              onVerifyToggled: (updated) => setState(() {
                final idx = _posts.indexWhere((r) => r.id == updated.id);
                if (idx >= 0) _posts[idx] = updated;
              }),
            )),
        ],
      ),
    );
  }

  Widget _buildCategoryPills() {
    final cats = [
      (_Category.all,     Icons.bolt,                  'All'),
      (_Category.flood,   Icons.water,                 'Flood'),
      (_Category.typhoon, Icons.cyclone,               'Typhoon'),
      (_Category.fire,    Icons.local_fire_department, 'Fire'),
      (_Category.quake,   Icons.crisis_alert,          'Quake'),
      (_Category.crime,   Icons.security,              'Crime'),
    ];
    final teal = AppColors.primaryTeal(context.isDark);
    final t = context.lt;

    return SizedBox(
      height: 44,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: EdgeInsets.zero,
        itemCount: cats.length,
        separatorBuilder: (a, b) => const SizedBox(width: 8),
        itemBuilder: (_, i) {
          final (cat, icon, label) = cats[i];
          final active = _activeCategory == cat;
          return GestureDetector(
            onTap: () => setState(() => _activeCategory = cat),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 180),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
              decoration: BoxDecoration(
                color: active ? teal : t.card,
                borderRadius: BorderRadius.circular(999),
                border: Border.all(
                    color: active ? teal : t.border, width: 1.5),
              ),
              child: Row(children: [
                Icon(icon, size: 13,
                    color: active ? Colors.white : t.text2),
                const SizedBox(width: 5),
                Text(label, style: GoogleFonts.dmSans(
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  color: active ? Colors.white : t.text2,
                )),
              ]),
            ),
          );
        },
      ),
    );
  }

  Widget _buildSectionHeader() {
    final t = context.lt;
    return Padding(
      padding: const EdgeInsets.fromLTRB(0, 12, 0, 8),
      child: Row(children: [
        Text('Community Reports', style: t.title(size: 16)),
        const Spacer(),
        Text('Recent First', style: GoogleFonts.dmSans(
          fontSize: 12,
          color: AppColors.primaryTeal(context.isDark),
          fontWeight: FontWeight.w600,
        )),
      ]),
    );
  }

  void _showNotifSheet(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (_) => _NotifSheet(
        notifs: _notifs,
        unreadCount: _unreadCount,
        onMarkRead: (id) => setState(() {
          final idx = _notifs.indexWhere((n) => n.id == id);
          if (idx >= 0) _notifs[idx].unread = false;
        }),
        onClose: () => Navigator.pop(context),
      ),
    );
  }

  // Fallback types used when API hasn't loaded yet
  static const _fallbackReportTypes = [
    {'value': 'crime',    'label': 'Crime / Safety'},
    {'value': 'flooding', 'label': 'Flooding'},
    {'value': 'traffic',  'label': 'Traffic'},
    {'value': 'accident', 'label': 'Accident'},
    {'value': 'other',    'label': 'Other'},
  ];

  void _showReportDialog(BuildContext context) {
    final descCtrl = TextEditingController();
    String? selectedType;
    bool isSubmitting = false;
    final types = _reportTypes.isNotEmpty
        ? _reportTypes
        : _fallbackReportTypes;

    showDialog(
      context: context,
      builder: (_) => StatefulBuilder(
        builder: (ctx, setDlgState) => AlertDialog(
          backgroundColor: context.lt.card,
          shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(18)),
          title: Text('Report an Issue',
              style: GoogleFonts.plusJakartaSans(
                  fontWeight: FontWeight.w700, fontSize: 16)),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Type of Issue',
                    style: GoogleFonts.plusJakartaSans(
                        fontWeight: FontWeight.w600, fontSize: 13,
                        color: context.lt.text)),
                const SizedBox(height: 8),
                DropdownButtonFormField<String>(
                  initialValue: selectedType,
                  hint: const Text('Select report type'),
                  decoration: InputDecoration(
                    border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(10)),
                    contentPadding: const EdgeInsets.symmetric(
                        horizontal: 12, vertical: 10),
                  ),
                  items: types.map((t) => DropdownMenuItem<String>(
                    value: t['value']?.toString() ?? '',
                    child: Text(t['label']?.toString() ?? ''),
                  )).toList(),
                  onChanged: (v) => setDlgState(() => selectedType = v),
                ),
                const SizedBox(height: 16),
                Text('Description',
                    style: GoogleFonts.plusJakartaSans(
                        fontWeight: FontWeight.w600, fontSize: 13,
                        color: context.lt.text)),
                const SizedBox(height: 8),
                TextField(
                  controller: descCtrl,
                  maxLines: 3,
                  decoration: InputDecoration(
                    hintText: 'Describe what happened…',
                    border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(10)),
                    contentPadding: const EdgeInsets.all(12),
                  ),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: isSubmitting ? null : () => Navigator.pop(ctx),
              child: const Text('Cancel'),
            ),
            ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.primaryTeal(context.isDark),
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10)),
              ),
              onPressed: isSubmitting
                  ? null
                  : () async {
                      if (selectedType == null ||
                          descCtrl.text.trim().isEmpty) {
                        ScaffoldMessenger.of(ctx).showSnackBar(const SnackBar(
                            content: Text('Please fill in all fields.')));
                        return;
                      }
                      setDlgState(() => isSubmitting = true);
                      try {
                        final token =
                            await SessionManager.instance.getAuthToken();
                        if (token == null || token.isEmpty) {
                          if (ctx.mounted) {
                            ScaffoldMessenger.of(ctx).showSnackBar(
                                const SnackBar(
                                    content: Text(
                                        'Please log in to submit reports.')));
                            Navigator.pop(ctx);
                          }
                          return;
                        }
                        await ApiClient.instance.submitReportJson(
                          lat: 14.5995,
                          lon: 120.9842,
                          reportType: selectedType!,
                          description: descCtrl.text.trim(),
                          token: token,
                        );
                        if (ctx.mounted) {
                          ScaffoldMessenger.of(ctx).showSnackBar(const SnackBar(
                              content:
                                  Text('Report submitted successfully!')));
                          Navigator.pop(ctx);
                          await _fetchReports(); // refresh feed
                        }
                      } catch (e) {
                        if (ctx.mounted) {
                          ScaffoldMessenger.of(ctx).showSnackBar(
                              SnackBar(content: Text('Error: $e')));
                          setDlgState(() => isSubmitting = false);
                        }
                      }
                    },
              child: isSubmitting
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: Colors.white))
                  : const Text('Submit'),
            ),
          ],
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────
// NOTIF BUTTON
// ─────────────────────────────────────────────────────────────

class _NotifBtn extends StatelessWidget {
  final int unread;
  final VoidCallback onTap;
  const _NotifBtn({required this.unread, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final t = context.lt;
    final teal = AppColors.primaryTeal(context.isDark);
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 38,
        height: 38,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: AppColors.tealDim,
          border: Border.all(color: t.border),
        ),
        child: Stack(alignment: Alignment.center, children: [
          Icon(Icons.notifications_rounded, color: teal, size: 18),
          if (unread > 0)
            Positioned(
              top: 6,
              right: 6,
              child: Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                  color: AppColors.red,
                  shape: BoxShape.circle,
                  border: Border.all(color: t.card, width: 1.5),
                ),
              ),
            ),
        ]),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────
// ALERT BANNER
// ─────────────────────────────────────────────────────────────

class _AlertBanner extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final t = context.lt;
    final redColor = context.isDark ? AppColors.redDark : AppColors.red;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.red.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.red.withValues(alpha: 0.25)),
      ),
      child: Row(children: [
        Container(
          width: 36,
          height: 36,
          decoration: BoxDecoration(
            color: AppColors.red.withValues(alpha: 0.12),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Icon(Icons.warning_rounded, color: redColor, size: 18),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('Flash Flood Warning',
                style: GoogleFonts.plusJakartaSans(
                    fontSize: 13, fontWeight: FontWeight.w800, color: redColor)),
            Text('PAGASA: Low-lying areas in QC · 30m ago',
                style: t.body(size: 11, color: t.text2)),
          ]),
        ),
      ]),
    );
  }
}

// ─────────────────────────────────────────────────────────────
// POST CARD
// ─────────────────────────────────────────────────────────────

class _PostCard extends StatefulWidget {
  final _Post post;
  final ValueChanged<_Post> onVerifyToggled;
  const _PostCard({required this.post, required this.onVerifyToggled});
  @override
  State<_PostCard> createState() => _PostCardState();
}

class _PostCardState extends State<_PostCard> {
  bool _showPlusOne = false;

  void _handleVerify() async {
    final p = widget.post;
    final wasVerified = p.userVerified;
    // Optimistic UI update
    widget.onVerifyToggled(p.copyWith(
      verifyCount: wasVerified ? p.verifyCount - 1 : p.verifyCount + 1,
      userVerified: !wasVerified,
    ));
    if (!wasVerified) {
      setState(() => _showPlusOne = true);
      Future.delayed(const Duration(milliseconds: 700), () {
        if (mounted) setState(() => _showPlusOne = false);
      });
      // Persist to backend
      try {
        final token = await SessionManager.instance.getAuthToken();
        await ApiClient.instance.confirmReport(reportId: p.id, token: token);
      } catch (_) {
        // Silently revert on failure
        if (mounted) {
          widget.onVerifyToggled(p.copyWith(
            verifyCount: p.verifyCount,
            userVerified: false,
          ));
        }
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = widget.post;
    final t = context.lt;
    final isDark = context.isDark;
    final teal = AppColors.primaryTeal(isDark);
    final isOfficial = p.severity == _Severity.info;
    final pct = (p.verifyCount / p.verifyMax).clamp(0.0, 1.0);

    final typeColor = p.type == _PostType.alert
        ? (isDark ? AppColors.redDark : AppColors.red)
        : p.type == _PostType.tip
            ? AppColors.green
            : teal;
    final typeLabel = p.type == _PostType.alert
        ? 'ALERT'
        : p.type == _PostType.tip
            ? 'TIP'
            : 'REPORT';

    final repColor = p.reputation == 'Lighthouse'
        ? AppColors.rankLighthouse
        : p.reputation == 'Lantern'
            ? AppColors.rankLantern
            : AppColors.rankCandle;
    final repIcon = p.reputation == 'Lighthouse'
        ? Icons.wb_sunny_rounded
        : p.reputation == 'Lantern'
            ? Icons.flashlight_on_rounded
            : Icons.local_fire_department_rounded;

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: t.card,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
            color: isOfficial
                ? AppColors.blue.withValues(alpha: 0.3)
                : t.border),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: isDark ? 0.18 : 0.05),
            blurRadius: 12,
            offset: const Offset(0, 2),
          )
        ],
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [

        // ── Header ──────────────────────────────────────
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 14, 14, 8),
          child: Row(children: [
            Container(
              width: 38,
              height: 38,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: p.gradient,
                ),
                shape: BoxShape.circle,
              ),
              child: Center(
                child: Text(p.initials,
                    style: GoogleFonts.plusJakartaSans(
                        fontSize: 12,
                        fontWeight: FontWeight.w800,
                        color: Colors.white)),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(p.author, style: t.title(size: 13)),
                    Row(children: [
                      Icon(repIcon, color: repColor, size: 11),
                      const SizedBox(width: 3),
                      Text(p.reputation,
                          style: GoogleFonts.plusJakartaSans(
                              fontSize: 10,
                              fontWeight: FontWeight.w700,
                              color: repColor)),
                    ]),
                  ]),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
              decoration: BoxDecoration(
                color: typeColor.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(50),
                border: Border.all(color: typeColor.withValues(alpha: 0.3)),
              ),
              child: Text(typeLabel,
                  style: GoogleFonts.plusJakartaSans(
                      fontSize: 9,
                      fontWeight: FontWeight.w800,
                      color: typeColor)),
            ),
          ]),
        ),

        // ── Content ─────────────────────────────────────
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 0, 14, 8),
          child: Text(p.content, style: t.body(size: 13, color: t.text)),
        ),

        // ── GPS photo placeholder ────────────────────────
        if (p.gpsVerified)
          Container(
            margin: const EdgeInsets.fromLTRB(14, 0, 14, 10),
            height: 120,
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                  colors: [Color(0xFFB2DDE2), Color(0xFF8ECCD4)]),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Stack(children: [
              const Center(
                  child: Text('🌊', style: TextStyle(fontSize: 36))),
              Positioned(
                bottom: 8,
                right: 8,
                child: Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: Colors.black.withValues(alpha: 0.45),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: const Row(mainAxisSize: MainAxisSize.min, children: [
                    Icon(Icons.location_on, size: 11, color: Colors.white),
                    SizedBox(width: 3),
                    Text('GPS Verified',
                        style: TextStyle(
                            fontSize: 10,
                            color: Colors.white,
                            fontWeight: FontWeight.w700)),
                  ]),
                ),
              ),
            ]),
          ),

        // ── Location + time ──────────────────────────────
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 0, 14, 8),
          child: Row(children: [
            Icon(Icons.place_rounded, size: 13, color: t.text2),
            const SizedBox(width: 3),
            Text(p.location, style: t.body(size: 11, color: t.text2)),
            const Spacer(),
            Text(p.timeAgo, style: t.body(size: 11, color: t.text3)),
          ]),
        ),

        // ── Tags ────────────────────────────────────────
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 0, 14, 10),
          child: Wrap(
            spacing: 6,
            children: p.tags
                .map((tag) => Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                          color: t.iconBg,
                          borderRadius: BorderRadius.circular(50)),
                      child: Text('#$tag',
                          style: t.body(
                              size: 10,
                              color: t.text2,
                              w: FontWeight.w600)),
                    ))
                .toList(),
          ),
        ),

        // ── Verify bar ──────────────────────────────────
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 0, 14, 8),
          child: Column(children: [
            Row(children: [
              Text(
                  isOfficial
                      ? 'Official government source'
                      : 'Community verification',
                  style: t.body(size: 10, color: t.text2)),
              const Spacer(),
              Text(
                  isOfficial
                      ? '✓ Verified'
                      : '${p.verifyCount} / ${p.verifyMax}',
                  style: t.body(size: 10, color: teal)),
            ]),
            const SizedBox(height: 5),
            ClipRRect(
              borderRadius: BorderRadius.circular(99),
              child: LinearProgressIndicator(
                value: pct,
                minHeight: 3,
                backgroundColor: AppColors.tealDim,
                valueColor: AlwaysStoppedAnimation<Color>(teal),
              ),
            ),
          ]),
        ),

        // ── Actions ─────────────────────────────────────
        Container(
          padding: const EdgeInsets.fromLTRB(14, 10, 14, 14),
          decoration: BoxDecoration(
            border: Border(
                top: BorderSide(
                    color: AppColors.teal.withValues(alpha: 0.12))),
          ),
          child: Row(children: [
            Stack(clipBehavior: Clip.none, children: [
              GestureDetector(
                onTap: _handleVerify,
                child: Row(children: [
                  Icon(
                    p.userVerified
                        ? Icons.thumb_up_rounded
                        : Icons.thumb_up_outlined,
                    size: 17,
                    color: p.userVerified ? teal : t.text2,
                  ),
                  const SizedBox(width: 5),
                  Text(
                    '${p.verifyMax == 9999 ? 'Helpful' : 'Verify'} (${p.verifyCount})',
                    style: t.body(
                      size: 11,
                      color: p.userVerified ? teal : t.text2,
                      w: FontWeight.w700,
                    ),
                  ),
                ]),
              ),
              if (_showPlusOne)
                Positioned(
                  top: -10,
                  left: 0,
                  child: TweenAnimationBuilder<double>(
                    tween: Tween(begin: 0, end: 1),
                    duration: const Duration(milliseconds: 650),
                    builder: (ctx2, v, child2) => Opacity(
                      opacity: (1 - v).clamp(0.0, 1.0),
                      child: Transform.translate(
                        offset: Offset(0, -28 * v),
                        child: Text('+1',
                            style: GoogleFonts.plusJakartaSans(
                                fontSize: 11,
                                fontWeight: FontWeight.w800,
                                color: teal)),
                      ),
                    ),
                  ),
                ),
            ]),
            const SizedBox(width: 16),
            Row(children: [
              Icon(Icons.chat_bubble_outline, size: 17, color: t.text2),
              const SizedBox(width: 5),
              Text('${p.comments}',
                  style: t.body(
                      size: 11, color: t.text2, w: FontWeight.w700)),
            ]),
            const Spacer(),
            Icon(Icons.share_outlined, size: 17, color: t.text2),
          ]),
        ),
      ]),
    );
  }
}

// ─────────────────────────────────────────────────────────────
// NOTIFICATION SHEET
// ─────────────────────────────────────────────────────────────

class _NotifSheet extends StatelessWidget {
  final List<_Notif> notifs;
  final int unreadCount;
  final ValueChanged<String> onMarkRead;
  final VoidCallback onClose;

  const _NotifSheet({
    required this.notifs,
    required this.unreadCount,
    required this.onMarkRead,
    required this.onClose,
  });

  @override
  Widget build(BuildContext context) {
    final t = context.lt;
    final teal = AppColors.primaryTeal(context.isDark);

    return Container(
      constraints:
          BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.55),
      decoration: BoxDecoration(
        color: t.card,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        boxShadow: [
          BoxShadow(
              color: Colors.black.withValues(alpha: 0.2),
              blurRadius: 24,
              offset: const Offset(0, -4))
        ],
      ),
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        Center(
          child: Container(
            width: 40,
            height: 4,
            margin: const EdgeInsets.symmetric(vertical: 12),
            decoration: BoxDecoration(
                color: t.border, borderRadius: BorderRadius.circular(2)),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 0, 16, 12),
          child: Row(children: [
            Text('Notifications', style: t.title(size: 16)),
            if (unreadCount > 0) ...[
              const SizedBox(width: 8),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                decoration: BoxDecoration(
                  color: teal.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(50),
                ),
                child: Text('$unreadCount new',
                    style: GoogleFonts.plusJakartaSans(
                        fontSize: 10,
                        fontWeight: FontWeight.w700,
                        color: teal)),
              ),
            ],
            const Spacer(),
            GestureDetector(
              onTap: onClose,
              child: Container(
                width: 30,
                height: 30,
                decoration: BoxDecoration(
                  color: t.iconBg,
                  shape: BoxShape.circle,
                  border: Border.all(color: t.border),
                ),
                child: Icon(Icons.close, size: 16, color: t.text2),
              ),
            ),
          ]),
        ),
        Divider(height: 1, color: t.border),
        Flexible(
          child: ListView.builder(
            shrinkWrap: true,
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
            itemCount: notifs.length,
            itemBuilder: (_, i) {
              final n = notifs[i];
              return GestureDetector(
                onTap: () => onMarkRead(n.id),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  margin: const EdgeInsets.only(bottom: 8),
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: n.unread ? teal.withValues(alpha: 0.06) : t.card,
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(
                        color: n.unread
                            ? teal.withValues(alpha: 0.2)
                            : t.border),
                  ),
                  child: Row(children: [
                    Container(
                      width: 36,
                      height: 36,
                      decoration: BoxDecoration(
                        color: n.iconColor.withValues(alpha: 0.12),
                        shape: BoxShape.circle,
                      ),
                      child: Icon(n.icon, size: 17, color: n.iconColor),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(n.body,
                                style: t.body(
                                  size: 12,
                                  w: n.unread
                                      ? FontWeight.w600
                                      : FontWeight.w400,
                                  color: t.text,
                                )),
                            const SizedBox(height: 2),
                            Text(n.timeAgo,
                                style: t.body(size: 10, color: t.text3)),
                          ]),
                    ),
                    if (n.unread)
                      Container(
                        width: 8,
                        height: 8,
                        decoration: BoxDecoration(
                            color: teal, shape: BoxShape.circle),
                      ),
                  ]),
                ),
              );
            },
          ),
        ),
      ]),
    );
  }
}