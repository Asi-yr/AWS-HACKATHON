import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/app_colors.dart';
import '../../core/custom_theme.dart';
import '../../core/api_client.dart';
import '../../core/session_manager.dart';
import '../../widgets/shared_widgets.dart';

class CommunityView extends StatelessWidget {
  const CommunityView({super.key});

  @override
  Widget build(BuildContext context) {
    final t = context.lt;
    return Scaffold(
      backgroundColor: t.bg,
      body: Column(children: [
        LigtasHeader(
          title: 'Community',
          trailing: _NotifBtn(),
        ),
        // Expanded takes the full remaining space above the RootShell's nav bar
        Expanded(child: _CommunityFeed()),
      ]),
      floatingActionButton: _ReportFab(),
    );
  }
}

class _NotifBtn extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final t = context.lt;
    return Container(
      width: 38, height: 38,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: AppColors.tealDim,
        border: Border.all(color: t.border)),
      child: Icon(Icons.notifications_rounded,
        color: AppColors.primaryTeal(context.isDark), size: 18),
    );
  }
}

class _ReportFab extends StatelessWidget {
  @override
  Widget build(BuildContext context) => FloatingActionButton.extended(
    onPressed: () => _showReportDialog(context),
    backgroundColor: AppColors.primaryTeal(context.isDark),
    foregroundColor: Colors.white,
    icon: const Icon(Icons.add_rounded),
    label: Text('Report',
      style: GoogleFonts.plusJakartaSans(fontWeight: FontWeight.w800)),
  );
}

class _CommunityFeed extends StatefulWidget {
  const _CommunityFeed();
  @override
  State<_CommunityFeed> createState() => _CommunityFeedState();
}

class _CommunityFeedState extends State<_CommunityFeed> {
  List<_Post> _reports = [];
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _fetchReports();
  }

  Future<void> _fetchReports() async {
    try {
      final token = await SessionManager.instance.getAuthToken();
      final rawReports = await ApiClient.instance.getReports(token: token);
      
      final posts = rawReports.map((r) {
        final reportType = r['report_type']?.toString().toLowerCase() ?? 'report';
        final typeLabel = reportType == 'crime' ? 'alert'
                        : reportType == 'flooding' ? 'warning'
                        : 'report';
        return _Post(
          id: (r['id'] ?? 0) as int,
          author: r['username']?.toString() ?? 'Anonymous',
          reputation: r['trust_rank']?.toString() ?? 'Candle',
          content: r['description']?.toString() ?? 'No description',
          location: r['location']?.toString() ?? 'Unknown location',
          timeAgo: _formatTime(r['reported_at']),
          upvotes: (r['confirmations'] ?? 0) as int,
          type: typeLabel,
          tags: [reportType],
          lat: (r['lat'] as num?)?.toDouble() ?? 0.0,
          lon: (r['lon'] as num?)?.toDouble() ?? 0.0,
        );
      }).toList();

      if (mounted) {
        setState(() {
          _reports = posts;
          _isLoading = false;
        });
      }
    } catch (e) {
      // On error, use fallback mock reports
      if (mounted) {
        setState(() {
          _reports = _getMockReports();
          _isLoading = false;
        });
      }
    }
  }

  String _formatTime(dynamic timestamp) {
    // Simple time formatting - "X minutes ago", "X hours ago"
    try {
      return 'recently';
    } catch (_) {
      return 'recently';
    }
  }

  List<_Post> _getMockReports() {
    return [
      _Post(
        id: 1,
        author: 'Ana Reyes',
        reputation: 'Lantern',
        content: 'Flooded underpass near Tandang Sora. Depth around knee-level. Avoid C5 northbound.',
        location: 'Tandang Sora, QC',
        timeAgo: '12m ago',
        upvotes: 24,
        type: 'report',
        tags: ['flood', 'road'],
        lat: 14.62,
        lon: 121.02,
      ),
      _Post(
        id: 2,
        author: 'Rico Bautista',
        reputation: 'Lighthouse',
        content: 'Snatching incident reported near Commonwealth MRT station exit. Stay alert and keep bags in front.',
        location: 'Commonwealth Ave, QC',
        timeAgo: '38m ago',
        upvotes: 41,
        type: 'alert',
        tags: ['crime', 'mrt'],
        lat: 14.62,
        lon: 121.05,
      ),
      _Post(
        id: 3,
        author: 'Leni Cruz',
        reputation: 'Candle',
        content: 'Alternative route: Cut through Batasan Hills via Constitution Hills road. Clear and well-lit.',
        location: 'Batasan Hills, QC',
        timeAgo: '2h ago',
        upvotes: 8,
        type: 'tip',
        tags: ['route', 'safe'],
        lat: 14.63,
        lon: 121.04,
      ),
    ];
  }

  @override
  Widget build(BuildContext context) {
    return _isLoading
      ? const Center(
          child: CircularProgressIndicator(
            valueColor: AlwaysStoppedAnimation<Color>(AppColors.teal)),
        )
      : ListView(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 100),
          children: [
            _AlertBanner(),
            const SizedBox(height: 12),
            const SectionLabel('COMMUNITY REPORTS', padding: EdgeInsets.only(bottom: 8)),
            ..._reports.map((p) => _PostCard(post: p)),
          ],
        );
  }
}

class _AlertBanner extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final t = context.lt;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.red.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.red.withValues(alpha: 0.25))),
      child: Row(children: [
        Container(
          width: 36, height: 36,
          decoration: BoxDecoration(
            color: AppColors.red.withValues(alpha: 0.12),
            borderRadius: BorderRadius.circular(10)),
          child: Icon(Icons.warning_rounded,
            color: context.isDark ? AppColors.redDark : AppColors.red, size: 18),
        ),
        const SizedBox(width: 12),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Flash Flood Warning',
            style: GoogleFonts.plusJakartaSans(
              fontSize: 13, fontWeight: FontWeight.w800,
              color: context.isDark ? AppColors.redDark : AppColors.red)),
          Text('PAGASA: Low-lying areas in QC · 30m ago',
            style: GoogleFonts.dmSans(fontSize: 11, color: t.text2)),
        ])),
      ]),
    );
  }
}

class _PostCard extends StatefulWidget {
  final _Post post;
  const _PostCard({required this.post});
  @override State<_PostCard> createState() => _PostCardState();
}

class _PostCardState extends State<_PostCard> {
  late int _upvotes;
  bool _upvoted = false;

  @override void initState() { super.initState(); _upvotes = widget.post.upvotes; }

  @override
  Widget build(BuildContext context) {
    final t     = context.lt;
    final post  = widget.post;
    final isDark = context.isDark;

    final typeColor = post.type == 'alert' ? (isDark ? AppColors.redDark : AppColors.red)
                    : post.type == 'warning'   ? AppColors.safeAmber
                    : AppColors.primaryTeal(isDark);
    final typeLabel = post.type == 'alert' ? 'ALERT' : post.type == 'warning' ? 'WARNING' : 'REPORT';
    final repColor  = post.reputation == 'lighthouse' ? AppColors.rankLighthouse
                    : post.reputation == 'lantern'    ? AppColors.rankLantern
                    : AppColors.rankCandle;
    final repIcon   = post.reputation == 'lighthouse' ? Icons.wb_sunny_rounded
                    : post.reputation == 'lantern'    ? Icons.flashlight_on_rounded
                    : Icons.local_fire_department_rounded;

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: t.card,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: t.border)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          CircleAvatar(
            radius: 18,
            backgroundColor: AppColors.tealDim,
            child: Text(post.author.isNotEmpty ? post.author[0] : 'A', style: GoogleFonts.plusJakartaSans(fontWeight: FontWeight.w800, color: AppColors.primaryTeal(isDark))),
          ),
          const SizedBox(width: 10),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(post.author, style: t.title(size: 13)),
            Row(children: [
              Icon(repIcon, color: repColor, size: 11),
              const SizedBox(width: 3),
              Text(post.reputation.capitalize(), style: GoogleFonts.plusJakartaSans(fontSize: 10, fontWeight: FontWeight.w700, color: repColor)),
            ]),
          ])),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(color: typeColor.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(50)),
            child: Text(typeLabel, style: GoogleFonts.plusJakartaSans(fontSize: 9, fontWeight: FontWeight.w800, color: typeColor)),
          ),
        ]),
        const SizedBox(height: 10),
        Text(post.content, style: t.body(size: 13, color: t.text)),
        const SizedBox(height: 8),
        Row(children: [
          Icon(Icons.place_rounded, size: 13, color: t.text2),
          const SizedBox(width: 3),
          Text(post.location, style: t.body(size: 11, color: t.text2)),
          const Spacer(),
          Text(post.timeAgo, style: t.body(size: 11, color: t.text3)),
        ]),
        const SizedBox(height: 10),
        Row(children: [
          ...post.tags.map((tag) => Container(
            margin: const EdgeInsets.only(right: 6),
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(color: t.iconBg, borderRadius: BorderRadius.circular(50)),
            child: Text('#$tag', style: t.body(size: 10, color: t.text2, w: FontWeight.w600)),
          )),
          const Spacer(),
          GestureDetector(
            onTap: () async {
              if (_upvoted) return; // Allow only one upvote per session
              try {
                final token = await SessionManager.instance.getAuthToken();
                await ApiClient.instance.confirmReport(reportId: post.id, token: token);
                setState(() { _upvoted = true; _upvotes += 1; });
              } catch (e) {
                print('Error confirming report: $e');
              }
            },
            child: Row(children: [
              Icon(_upvoted ? Icons.thumb_up_rounded : Icons.thumb_up_outlined, size: 15, color: _upvoted ? AppColors.primaryTeal(isDark) : t.text2),
              const SizedBox(width: 4),
              Text('$_upvotes', style: t.body(size: 12, color: _upvoted ? AppColors.primaryTeal(isDark) : t.text2, w: FontWeight.w600)),
            ]),
          ),
        ]),
      ]),
    );
  }
}

class _Post {
  final int id;
  final String author, reputation, content, location, timeAgo, type;
  final int upvotes;
  final List<String> tags;
  final double lat, lon;
  const _Post({
    required this.id,
    required this.author,
    required this.reputation,
    required this.content,
    required this.location,
    required this.timeAgo,
    required this.upvotes,
    required this.type,
    required this.tags,
    required this.lat,
    required this.lon,
  });
}

extension StringExt on String {
  String capitalize() => '${this[0].toUpperCase()}${substring(1)}';
}

/// Show dialog for submitting community report
void _showReportDialog(BuildContext context) {
  final descriptionController = TextEditingController();
  String? selectedType;
  bool isSubmitting = false;

  showDialog(
    context: context,
    builder: (_) => StatefulBuilder(
      builder: (context, setState) => AlertDialog(
        backgroundColor: AppColors.cardDark,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        title: Text('Report an Issue', style: GoogleFonts.plusJakartaSans(fontWeight: FontWeight.w700)),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Report type dropdown
              Text('Type of Issue', style: GoogleFonts.plusJakartaSans(fontWeight: FontWeight.w600, fontSize: 13)),
              const SizedBox(height: 8),
              DropdownButton<String>(
                isExpanded: true,
                value: selectedType,
                hint: const Text('Select report type'),
                items: const [
                  DropdownMenuItem(value: 'crime', child: Text('Crime/Safety')),
                  DropdownMenuItem(value: 'flooding', child: Text('Flooding')),
                  DropdownMenuItem(value: 'traffic', child: Text('Traffic')),
                  DropdownMenuItem(value: 'accident', child: Text('Accident')),
                  DropdownMenuItem(value: 'other', child: Text('Other')),
                ]
                    .map((item) => DropdownMenuItem(
                          value: item.value,
                          child: item.child,
                        ))
                    .toList(),
                onChanged: (value) => setState(() => selectedType = value),
              ),
              const SizedBox(height: 24),
              // Description text field
              Text('Description', style: GoogleFonts.plusJakartaSans(fontWeight: FontWeight.w600, fontSize: 13)),
              const SizedBox(height: 8),
              TextField(
                controller: descriptionController,
                maxLines: 3,
                decoration: InputDecoration(
                  hintText: 'Describe what happened...',
                  border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
                  contentPadding: const EdgeInsets.all(12),
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: isSubmitting ? null : () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: isSubmitting
                ? null
                : () async {
                    if (selectedType == null || descriptionController.text.isEmpty) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('Please fill in all fields')),
                      );
                      return;
                    }

                    setState(() => isSubmitting = true);

                    try {
                      final token = await SessionManager.instance.getAuthToken();
                      if (token == null || token.isEmpty) {
                        if (context.mounted) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(content: Text('Please log in to submit reports')),
                          );
                          Navigator.pop(context);
                        }
                        return;
                      }

                      // Use a default location or get from device
                      const lat = 14.5995;
                      const lon = 120.9842;

                      await ApiClient.instance.submitReportJson(
                        lat: lat,
                        lon: lon,
                        reportType: selectedType!,
                        description: descriptionController.text,
                        token: token,
                      );

                      if (context.mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('Report submitted successfully!')),
                        );
                        Navigator.pop(context);
                      }
                    } catch (e) {
                      if (context.mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(content: Text('Error: ${e.toString()}')),
                        );
                        setState(() => isSubmitting = false);
                      }
                    }
                  },
            child: isSubmitting ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)) : const Text('Submit'),
          ),
        ],
      ),
    ),
  );
}