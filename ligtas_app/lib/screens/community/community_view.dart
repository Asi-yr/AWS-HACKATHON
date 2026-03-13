import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/app_colors.dart';
import '../../core/custom_theme.dart';
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
    onPressed: () => _showComingSoon(context),
    backgroundColor: AppColors.primaryTeal(context.isDark),
    foregroundColor: Colors.white,
    icon: const Icon(Icons.add_rounded),
    label: Text('Report',
      style: GoogleFonts.plusJakartaSans(fontWeight: FontWeight.w800)),
  );
}

class _CommunityFeed extends StatelessWidget {
  static const _mockPosts = [
    _MockPost(
      author: 'Ana Reyes',
      reputation: 'Lantern',
      content: 'Flooded underpass near Tandang Sora. Depth around knee-level. Avoid C5 northbound.',
      location: 'Tandang Sora, QC',
      timeAgo: '12m ago',
      upvotes: 24,
      type: 'report',
      tags: ['flood', 'road'],
    ),
    _MockPost(
      author: 'Rico Bautista',
      reputation: 'Lighthouse',
      content: 'Snatching incident reported near Commonwealth MRT station exit. Stay alert and keep bags in front.',
      location: 'Commonwealth Ave, QC',
      timeAgo: '38m ago',
      upvotes: 41,
      type: 'alert',
      tags: ['crime', 'mrt'],
    ),
    _MockPost(
      author: 'Leni Cruz',
      reputation: 'Candle',
      content: 'Alternative route: Cut through Batasan Hills via Constitution Hills road. Clear and well-lit.',
      location: 'Batasan Hills, QC',
      timeAgo: '2h ago',
      upvotes: 8,
      type: 'tip',
      tags: ['route', 'safe'],
    ),
  ];

  @override
  Widget build(BuildContext context) {
    return ListView(
      // Added padding at bottom to ensure FAB doesn't cover content
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 100),
      children: [
        _AlertBanner(),
        const SizedBox(height: 12),
        const SectionLabel('COMMUNITY REPORTS', padding: EdgeInsets.only(bottom: 8)),
        ..._mockPosts.map((p) => _PostCard(post: p)),
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
  final _MockPost post;
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
                    : post.type == 'tip'   ? AppColors.green
                    : AppColors.primaryTeal(isDark);
    final typeLabel = post.type == 'alert' ? 'ALERT' : post.type == 'tip' ? 'TIP' : 'REPORT';
    final repColor  = post.reputation == 'Lighthouse' ? AppColors.rankLighthouse
                    : post.reputation == 'Lantern'    ? AppColors.rankLantern
                    : AppColors.rankCandle;
    final repIcon   = post.reputation == 'Lighthouse' ? Icons.wb_sunny_rounded
                    : post.reputation == 'Lantern'    ? Icons.flashlight_on_rounded
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
            child: Text(post.author[0], style: GoogleFonts.plusJakartaSans(fontWeight: FontWeight.w800, color: AppColors.primaryTeal(isDark))),
          ),
          const SizedBox(width: 10),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(post.author, style: t.title(size: 13)),
            Row(children: [
              Icon(repIcon, color: repColor, size: 11),
              const SizedBox(width: 3),
              Text(post.reputation, style: GoogleFonts.plusJakartaSans(fontSize: 10, fontWeight: FontWeight.w700, color: repColor)),
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
            onTap: () => setState(() { _upvoted = !_upvoted; _upvotes += _upvoted ? 1 : -1; }),
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

class _MockPost {
  final String author, reputation, content, location, timeAgo, type;
  final int upvotes;
  final List<String> tags;
  const _MockPost({required this.author, required this.reputation, required this.content, required this.location, required this.timeAgo, required this.upvotes, required this.type, required this.tags});
}

void _showComingSoon(BuildContext context) => showDialog(
  context: context,
  builder: (_) => AlertDialog(
    backgroundColor: AppColors.cardDark,
    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
    content: ComingSoonOverlay(onDismiss: () => Navigator.pop(context)),
  ),
);