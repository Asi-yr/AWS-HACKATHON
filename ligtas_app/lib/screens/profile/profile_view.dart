import 'dart:io';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/app_colors.dart';
import '../../core/custom_theme.dart';
import '../../models/travel_history_model.dart';
import '../../models/user_model.dart';
import '../../widgets/shared_widgets.dart';
import 'profile_controller.dart';

class ProfileView extends StatelessWidget {
  const ProfileView({super.key});
  @override
  Widget build(BuildContext context) => ChangeNotifierProvider(
    create: (_) => ProfileController(),
    child: const _ProfileBody(),
  );
}

class _ProfileBody extends StatelessWidget {
  const _ProfileBody();
  @override
  Widget build(BuildContext context) {
    final ctrl = context.watch<ProfileController>();
    final t    = context.lt;
    return Scaffold(
      backgroundColor: t.bg,
      body: Stack(children: [
        Column(children: [
          LigtasHeader(
            title: 'Profile & Settings',
            trailing: _EditBtn(),
          ),
          Expanded(child: ListView(
            // FIX: Add bottom padding = nav height (72) + extra breathing room (16)
            // so the Log Out button is never hidden behind the bottom nav bar.
            padding: const EdgeInsets.only(bottom: 88),
            children: [
              _ProfileHero(),
              _StatsRow(),
              const SectionLabel('SAFETY & NAVIGATION'),
              SettingsCard(children: [
                ChevronRow(icon: Icons.history_rounded, title: 'Travel History', subtitle: 'Past routes and safety logs', onTap: ctrl.openTravelHistory),
              ]),
              const SectionLabel('PREFERENCES'),
              SettingsCard(children: [
                ToggleRow(
                  icon: Icons.dark_mode_rounded,
                  title: 'Night Mode',
                  subtitle: 'Switch between light and dark mode',
                  value: Theme.of(context).brightness == Brightness.dark,
                  onChanged: (_) => ctrl.toggleTheme(context),
                ),
              ]),
              const SectionLabel('EMERGENCY'),
              SettingsCard(children: [
                ChevronRow(
                  icon: Icons.emergency_share_rounded,
                  title: 'SOS Contacts',
                  subtitle: 'Trusted contacts for emergency alerts',
                  trailing: ctrl.sosContacts.isNotEmpty
                      ? '${ctrl.sosContacts.length}'
                      : null,
                  onTap: ctrl.openSosContacts,
                ),
              ]),
              const SectionLabel('ACCOUNT'),
              SettingsCard(children: [
                ChevronRow(icon: Icons.lock_rounded, title: 'Password & Security', subtitle: 'Password, Email, Two-Factor Auth', onTap: ctrl.openSecurity),
                const RowDivider(),
                ChevronRow(icon: Icons.logout_rounded, title: 'Log Out', danger: true, onTap: () => ctrl.logOut(context)),
              ]),
            ],
          )),
        ]),
        if (ctrl.travelHistoryOpen)  const _TravelHistoryPanel(),
        if (ctrl.sosContactsOpen)    const _SosContactsPanel(),
        if (ctrl.securityOpen)       const _SecurityPanel(),
        if (ctrl.passwordOpen)       const _PasswordScreen(),
        if (ctrl.emailOpen)          const _EmailScreen(),
        if (ctrl.twoFAOpen)          const _TwoFAScreen(),
        if (ctrl.comingSoon) Positioned.fill(child: ComingSoonOverlay(onDismiss: ctrl.hideComingSoon)),
        LigtasToast(visible: ctrl.toastVis, message: ctrl.toastMsg, type: ctrl.toastType),
      ]),
    );
  }
}

class _EditBtn extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final ctrl = context.read<ProfileController>();
    final t    = context.lt;
    return GestureDetector(
      onTap: () => showModalBottomSheet(
        context: context,
        isScrollControlled: true,
        backgroundColor: Colors.transparent,
        builder: (_) => ChangeNotifierProvider.value(
          value: ctrl,
          child: const _EditProfileSheet(),
        ),
      ),
      child: Container(
        width: 38, height: 38,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: AppColors.tealDim,
          border: Border.all(color: t.border)),
        child: Icon(Icons.edit_rounded,
          color: AppColors.primaryTeal(Theme.of(context).brightness == Brightness.dark), size: 17),
      ),
    );
  }
}

class _ProfileHero extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final ctrl = context.watch<ProfileController>();
    final user = ctrl.user;
    final t    = context.lt;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 28),
      child: Column(children: [
        Stack(children: [
          Container(
            width: 84, height: 84,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(color: AppColors.primaryTeal(Theme.of(context).brightness == Brightness.dark), width: 2.5)),
            child: ClipOval(child: _buildAvatar(ctrl, user, 40)),
          ),
          Positioned(bottom: 0, right: 0,
            child: Container(
              width: 22, height: 22,
              decoration: BoxDecoration(
                color: AppColors.primaryTeal(Theme.of(context).brightness == Brightness.dark),
                shape: BoxShape.circle),
              child: const Icon(Icons.check_rounded, color: Colors.white, size: 13),
            )),
        ]),
        const SizedBox(height: 12),
        Text(user.name, style: t.title(size: 20, w: FontWeight.w900)),
        const SizedBox(height: 4),
        Text(user.role, style: t.body(size: 13, color: t.text2)),
      ]),
    );
  }

  // Priority: local bytes (web+native) → network URL → file path (native only) → icon
  Widget _buildAvatar(ProfileController ctrl, dynamic user, double iconSize) {
    if (ctrl.avatarBytes != null) {
      return Image.memory(ctrl.avatarBytes!, fit: BoxFit.cover,
          errorBuilder: (_, _, _) => _fallback(iconSize));
    }
    if (user.avatarUrl != null) {
      if (user.avatarUrl!.startsWith('http')) {
        return Image.network(user.avatarUrl!, fit: BoxFit.cover,
            errorBuilder: (_, _, _) => _fallback(iconSize));
      }
      if (!kIsWeb) {
        return Image.file(File(user.avatarUrl!), fit: BoxFit.cover,
            errorBuilder: (_, _, _) => _fallback(iconSize));
      }
    }
    return _fallback(iconSize);
  }

  Widget _fallback(double size) => Container(
    color: AppColors.tealDim,
    child: Icon(Icons.person_rounded, color: AppColors.teal, size: size));
}

class _StatsRow extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final user = context.watch<ProfileController>().user;
    final t    = context.lt;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 4),
      child: Container(
        decoration: BoxDecoration(
          color: t.card,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: t.border)),
        child: Row(children: [
          _statCell('${user.stats.trips}',   'TRIPS',   t),
          _divider(t.border),
          _statCell('${user.stats.reports}', 'REPORTS', t),
          _divider(t.border),
          _trustCell(user.trustRank, t),
        ]),
      ),
    );
  }

  Widget _statCell(String val, String label, dynamic t) => Expanded(
    child: Padding(
      padding: const EdgeInsets.symmetric(vertical: 18),
      child: Column(children: [
        Text(val, style: GoogleFonts.plusJakartaSans(
          fontSize: 22, fontWeight: FontWeight.w900, color: t.text)),
        const SizedBox(height: 2),
        Text(label, style: t.label()),
      ]),
    ),
  );

  Widget _trustCell(TrustRank rank, dynamic t) {
    final color = rank == TrustRank.lighthouse ? AppColors.rankLighthouse
                : rank == TrustRank.lantern    ? AppColors.rankLantern
                : AppColors.rankCandle;

    // Emoji icons matching the Flaticon assets:
    // 🕯️ candle/2136679  🏮 lantern/384412  🗼 lighthouse/4971987
    final emoji = rank == TrustRank.lighthouse ? '🗼'
                : rank == TrustRank.lantern    ? '🏮'
                : '🕯️';

    return Expanded(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 14),
        child: Column(children: [
          // Coloured glow ring behind the emoji
          Container(
            width: 44, height: 44,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: color.withValues(alpha: 0.12),
              border: Border.all(color: color.withValues(alpha: 0.35), width: 1.5),
            ),
            child: Center(
              child: Text(emoji,
                style: const TextStyle(fontSize: 22),
                textAlign: TextAlign.center,
              ),
            ),
          ),
          const SizedBox(height: 4),
          Text(rank.label, style: GoogleFonts.plusJakartaSans(
            fontSize: 11, fontWeight: FontWeight.w700, color: color)),
          const SizedBox(height: 1),
          Text('TRUST RANK', style: t.label()),
        ]),
      ),
    );
  }

  Widget _divider(Color c) => Container(width: 1, height: 58, color: c);
}

class _EditProfileSheet extends StatefulWidget {
  const _EditProfileSheet();
  @override State<_EditProfileSheet> createState() => _EditProfileSheetState();
}

class _EditProfileSheetState extends State<_EditProfileSheet> {
  late final TextEditingController _name, _username;
  String _commuterType = 'Normal Commuter';
  String _gender = 'Prefer not to say';

  static const _commuterOpts = [
    'Normal Commuter','Student Commuter','Women Commuter',
    'LGBTQ+ Commuter','Disabled / Elderly Commuter','Minor Commuter',
  ];
  static const _genderOpts = [
    'Prefer not to say','Male','Female','Non-binary','Other',
  ];

  @override
  void initState() {
    super.initState();
    final u = context.read<ProfileController>().user;
    _name     = TextEditingController(text: u.name);
    _username = TextEditingController(text: u.username);
    _commuterType = _commuterOpts.contains(u.role) ? u.role : _commuterOpts.first;
  }

  @override
  void dispose() {
    _name.dispose(); _username.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ctrl = context.read<ProfileController>();
    final t    = context.lt;
    return Container(
      decoration: BoxDecoration(
        color: t.card,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(20))),
      padding: EdgeInsets.fromLTRB(20, 0, 20,
        MediaQuery.of(context).viewInsets.bottom + 28),
      child: SingleChildScrollView(child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(width: 36, height: 4, margin: const EdgeInsets.symmetric(vertical: 14),
            decoration: BoxDecoration(color: t.border,
              borderRadius: BorderRadius.circular(2))),
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            Text('Edit Profile', style: t.title()),
            IconButton(
              icon: Icon(Icons.close_rounded, color: t.text2),
              onPressed: () => Navigator.pop(context)),
          ]),
          const SizedBox(height: 12),
          GestureDetector(
            onTap: () => ctrl.pickProfileImage(),
            child: Stack(children: [
              Container(
                width: 80, height: 80,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(color: AppColors.primaryTeal(Theme.of(context).brightness == Brightness.dark), width: 2.5)),
                child: ClipOval(child: _buildEditAvatar(ctrl)),
              ),
              Positioned.fill(child: ClipOval(child: Container(
                color: Colors.black38,
                child: const Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.camera_alt_rounded, color: Colors.white, size: 20),
                    SizedBox(height: 2),
                    Text('CHANGE', style: TextStyle(
                      color: Colors.white, fontSize: 8, fontWeight: FontWeight.w800)),
                  ],
                ),
              ))),
            ]),
          ),
          const SizedBox(height: 20),
          _field('Full Name',    _name,     'Your full name',  false, t),
          const SizedBox(height: 12),
          _field('Username',     _username, '@username',       false, t),
          const SizedBox(height: 12),
          _dropdown('Commuter Type', _commuterType, _commuterOpts, t,
            (v) => setState(() => _commuterType = v!)),
          const SizedBox(height: 12),
          _dropdown('Gender', _gender, _genderOpts, t,
            (v) => setState(() => _gender = v!)),
          const SizedBox(height: 24),
          TealButton(
            label: 'Save Changes',
            onTap: () {
              ctrl.saveProfile(
                name: _name.text.trim(),
                username: _username.text.trim(),
                commuterType: _commuterType,
              );
              Navigator.pop(context);
            },
          ),
        ],
      )),
    );
  }

  // Same priority as _ProfileHero: bytes → network → file (native only) → icon
  Widget _buildEditAvatar(ProfileController ctrl) {
    if (ctrl.avatarBytes != null) {
      return Image.memory(ctrl.avatarBytes!, fit: BoxFit.cover,
          errorBuilder: (_, _, _) => _avatarFallback());
    }
    final url = ctrl.user.avatarUrl;
    if (url != null) {
      if (url.startsWith('http')) {
        return Image.network(url, fit: BoxFit.cover,
            errorBuilder: (_, _, _) => _avatarFallback());
      }
      if (!kIsWeb) {
        return Image.file(File(url), fit: BoxFit.cover,
            errorBuilder: (_, _, _) => _avatarFallback());
      }
    }
    return _avatarFallback();
  }

  Widget _avatarFallback() => Container(
    color: AppColors.tealDim,
    child: const Icon(Icons.person_rounded, color: AppColors.teal, size: 36));

  Widget _field(String label, TextEditingController ctrl, String hint,
      bool obscure, dynamic t) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(label, style: t.body(size: 12, w: FontWeight.w600, color: t.text2)),
      const SizedBox(height: 6),
      TextField(
        controller: ctrl, obscureText: obscure,
        style: t.body(size: 14),
        decoration: InputDecoration(
          hintText: hint,
          hintStyle: t.body(size: 14, color: t.text2),
          contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(10),
            borderSide: BorderSide(color: t.border)),
          enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10),
            borderSide: BorderSide(color: t.border)),
          focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(10),
            borderSide: BorderSide(color: AppColors.primaryTeal(Theme.of(context).brightness == Brightness.dark), width: 1.5)),
          filled: true, fillColor: t.bg,
        ),
      ),
    ],
  );

  Widget _dropdown(String label, String value, List<String> opts, dynamic t,
      ValueChanged<String?> onChanged) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(label, style: t.body(size: 12, w: FontWeight.w600, color: t.text2)),
      const SizedBox(height: 6),
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 2),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: t.border),
          color: t.bg),
        child: DropdownButtonHideUnderline(
          child: DropdownButton<String>(
            value: opts.contains(value) ? value : opts.first,
            isExpanded: true,
            style: t.body(size: 14),
            dropdownColor: t.card,
            items: opts.map((o) => DropdownMenuItem(value: o,
              child: Text(o, style: t.body(size: 14)))).toList(),
            onChanged: onChanged,
          ),
        ),
      ),
    ],
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Security Sheet — Password, Email, 2FA
// ─────────────────────────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────────────────────────
// Security Panel — full-screen overlay, same layout as Travel History
// ─────────────────────────────────────────────────────────────────────────────
class _SecurityPanel extends StatelessWidget {
  const _SecurityPanel();

  @override
  Widget build(BuildContext context) {
    final ctrl = context.watch<ProfileController>();
    final t    = context.lt;
    return Positioned.fill(
      child: Material(
        color: t.bg,
        child: Column(children: [
          LigtasHeader(
            title: 'Password & Security',
            leading: GestureDetector(
              onTap: ctrl.closeSecurity,
              child: Container(
                width: 32, height: 32,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: t.border)),
                child: Icon(Icons.arrow_back_rounded, size: 16, color: t.text),
              ),
            ),
          ),
          Expanded(child: ListView(
            padding: const EdgeInsets.fromLTRB(0, 16, 0, 24),
            children: [
              Padding(
                padding: const EdgeInsets.only(left: 16, bottom: 12),
                child: _subLabel('Security', t),
              ),
              SettingsCard(children: [
                ChevronRow(
                  icon: Icons.key_rounded,
                  title: 'Password',
                  subtitle: 'Change your login password',
                  onTap: ctrl.openPassword,
                ),
                const RowDivider(),
                ChevronRow(
                  icon: Icons.email_rounded,
                  title: 'Email Address',
                  subtitle: 'Update your account email',
                  onTap: ctrl.openEmail,
                ),
                const RowDivider(),
                ChevronRow(
                  icon: Icons.security_rounded,
                  title: 'Two-Factor Authentication',
                  subtitle: ctrl.twoFactorEnabled ? 'Enabled' : 'Not enabled',
                  onTap: ctrl.openTwoFA,
                ),
              ]),
            ],
          )),
        ]),
      ),
    );
  }

  Widget _subLabel(String s, dynamic t) => Padding(
    padding: const EdgeInsets.only(bottom: 12),
    child: Text(s, style: GoogleFonts.plusJakartaSans(
      fontSize: 12, fontWeight: FontWeight.w700,
      color: t.text3, letterSpacing: 0.06)),
  );
}

// ── Password Screen ──────────────────────────────────────────────────────────
class _PasswordScreen extends StatefulWidget {
  const _PasswordScreen();
  @override State<_PasswordScreen> createState() => _PasswordScreenState();
}
class _PasswordScreenState extends State<_PasswordScreen> {
  final _currentPw  = TextEditingController();
  final _newPw      = TextEditingController();
  final _confirmPw  = TextEditingController();
  bool _showCurrent = false, _showNew = false, _showConfirm = false;

  @override
  void dispose() {
    _currentPw.dispose(); _newPw.dispose(); _confirmPw.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ctrl = context.read<ProfileController>();
    final t    = context.lt;
    return Positioned.fill(
      child: Material(
        color: t.bg,
        child: Column(children: [
          LigtasHeader(
            title: 'Change Password',
            leading: GestureDetector(
              onTap: ctrl.closePassword,
              child: Container(
                width: 32, height: 32,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: t.border)),
                child: Icon(Icons.arrow_back_rounded, size: 16, color: t.text),
              ),
            ),
          ),
          Expanded(child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(16, 24, 16, 24),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              _pwField('Current Password', _currentPw, _showCurrent,
                () => setState(() => _showCurrent = !_showCurrent), t, context),
              const SizedBox(height: 14),
              _pwField('New Password', _newPw, _showNew,
                () => setState(() => _showNew = !_showNew), t, context),
              const SizedBox(height: 14),
              _pwField('Confirm New Password', _confirmPw, _showConfirm,
                () => setState(() => _showConfirm = !_showConfirm), t, context),
              const SizedBox(height: 28),
              TealButton(
                label: 'Update Password',
                onTap: () => ctrl.changePassword(
                  context: context,
                  currentPassword: _currentPw.text,
                  newPassword:     _newPw.text,
                  confirmPassword: _confirmPw.text,
                  onSuccess: () {
                    _currentPw.clear(); _newPw.clear(); _confirmPw.clear();
                    ctrl.closePassword();
                  },
                ),
              ),
            ]),
          )),
        ]),
      ),
    );
  }
}

// ── Email Screen ──────────────────────────────────────────────────────────────
class _EmailScreen extends StatefulWidget {
  const _EmailScreen();
  @override State<_EmailScreen> createState() => _EmailScreenState();
}
class _EmailScreenState extends State<_EmailScreen> {
  final _newEmail = TextEditingController();
  final _emailPw  = TextEditingController();
  bool  _showPw   = false;

  @override
  void dispose() { _newEmail.dispose(); _emailPw.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    final ctrl = context.read<ProfileController>();
    final t    = context.lt;
    return Positioned.fill(
      child: Material(
        color: t.bg,
        child: Column(children: [
          LigtasHeader(
            title: 'Change Email',
            leading: GestureDetector(
              onTap: ctrl.closeEmail,
              child: Container(
                width: 32, height: 32,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: t.border)),
                child: Icon(Icons.arrow_back_rounded, size: 16, color: t.text),
              ),
            ),
          ),
          Expanded(child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(16, 24, 16, 24),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              _inputField('New Email Address', _newEmail, Icons.email_outlined,
                false, null, t, context),
              const SizedBox(height: 14),
              _pwField('Current Password', _emailPw, _showPw,
                () => setState(() => _showPw = !_showPw), t, context),
              const SizedBox(height: 14),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: AppColors.tealDim,
                  borderRadius: BorderRadius.circular(10)),
                child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Icon(Icons.info_outline_rounded,
                    size: 15, color: AppColors.primaryTeal(Theme.of(context).brightness == Brightness.dark)),
                  const SizedBox(width: 8),
                  Expanded(child: Text(
                    'Your email will be updated directly after verifying your password.',
                    style: t.body(size: 12, color: t.text2))),
                ]),
              ),
              const SizedBox(height: 28),
              TealButton(
                label: 'Update Email',
                onTap: () => ctrl.changeEmail(
                  context: context,
                  newEmail:        _newEmail.text.trim(),
                  currentPassword: _emailPw.text,
                  onSuccess: () {
                    _newEmail.clear(); _emailPw.clear();
                    ctrl.closeEmail();
                  },
                ),
              ),
            ]),
          )),
        ]),
      ),
    );
  }
}

// ── 2FA Screen ────────────────────────────────────────────────────────────────
class _TwoFAScreen extends StatelessWidget {
  const _TwoFAScreen();

  @override
  Widget build(BuildContext context) {
    final ctrl    = context.watch<ProfileController>();
    final t       = context.lt;
    final enabled = ctrl.twoFactorEnabled;
    final teal    = AppColors.primaryTeal(Theme.of(context).brightness == Brightness.dark);
    return Positioned.fill(
      child: Material(
        color: t.bg,
        child: Column(children: [
          LigtasHeader(
            title: 'Two-Factor Authentication',
            leading: GestureDetector(
              onTap: ctrl.closeTwoFA,
              child: Container(
                width: 32, height: 32,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: t.border)),
                child: Icon(Icons.arrow_back_rounded, size: 16, color: t.text),
              ),
            ),
          ),
          Expanded(child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(16, 24, 16, 24),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              // Status badge
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                decoration: BoxDecoration(
                  color: enabled ? teal.withValues(alpha: 0.10) : t.card,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: enabled ? teal.withValues(alpha: 0.4) : t.border)),
                child: Row(children: [
                  Icon(
                    enabled ? Icons.verified_user_rounded : Icons.shield_outlined,
                    size: 22, color: enabled ? teal : t.text2),
                  const SizedBox(width: 12),
                  Expanded(child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(enabled ? '2FA is enabled' : '2FA is disabled',
                        style: t.title(size: 15)),
                      Text(
                        enabled
                          ? 'Your account has extra protection.'
                          : 'Enable 2FA for stronger account security.',
                        style: t.body(size: 12, color: t.text2)),
                    ],
                  )),
                ]),
              ),
              if (!enabled) ...[
                const SizedBox(height: 24),
                Text('How it works', style: t.title(size: 14)),
                const SizedBox(height: 12),
                _step('1', 'You log in with your password as usual.', t, teal),
                _step('2', 'A one-time code is sent to your registered email.', t, teal),
                _step('3', 'Enter the code to complete sign-in.', t, teal),
              ],
              const SizedBox(height: 28),
              if (!enabled)
                TealButton(label: 'Enable 2FA', onTap: () => ctrl.toggle2FA(context))
              else
                SizedBox(
                  width: double.infinity,
                  child: OutlinedButton(
                    style: OutlinedButton.styleFrom(
                      foregroundColor: const Color(0xFFDC2626),
                      side: const BorderSide(color: Color(0xFFDC2626), width: 1.5),
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(10)),
                    ),
                    onPressed: () => ctrl.toggle2FA(context),
                    child: Text('Disable 2FA',
                      style: GoogleFonts.plusJakartaSans(
                        fontWeight: FontWeight.w700, fontSize: 14)),
                  ),
                ),
              if (enabled)
                Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Text(
                    'To fully remove 2FA, confirm via the link sent to your email.',
                    style: t.body(size: 12, color: t.text2),
                    textAlign: TextAlign.center)),
            ]),
          )),
        ]),
      ),
    );
  }

  Widget _step(String n, String text, dynamic t, Color teal) => Padding(
    padding: const EdgeInsets.only(bottom: 12),
    child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Container(
        width: 24, height: 24,
        decoration: BoxDecoration(
          color: teal.withValues(alpha: 0.12),
          shape: BoxShape.circle,
          border: Border.all(color: teal.withValues(alpha: 0.3))),
        child: Center(child: Text(n, style: TextStyle(
          color: teal, fontSize: 11, fontWeight: FontWeight.w800)))),
      const SizedBox(width: 10),
      Expanded(child: Padding(
        padding: const EdgeInsets.only(top: 3),
        child: Text(text, style: t.body(size: 13, color: t.text2)))),
    ]),
  );
}

// ── Shared field helpers ──────────────────────────────────────────────────────

Widget _pwField(String label, TextEditingController c, bool visible,
    VoidCallback onToggle, dynamic t, BuildContext context) =>
  _inputField(label, c, Icons.lock_outline_rounded, !visible,
    IconButton(
      icon: Icon(visible ? Icons.visibility_off_rounded : Icons.visibility_rounded,
        size: 18, color: t.text2),
      onPressed: onToggle,
    ), t, context);

Widget _inputField(String label, TextEditingController c,
    IconData prefixIcon, bool obscure, Widget? suffix,
    dynamic t, BuildContext context) =>
  Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
    Text(label, style: t.body(size: 12, w: FontWeight.w600, color: t.text2)),
    const SizedBox(height: 6),
    TextField(
      controller: c,
      obscureText: obscure,
      style: t.body(size: 14),
      decoration: InputDecoration(
        prefixIcon: Icon(prefixIcon, size: 18, color: t.text2),
        suffixIcon: suffix,
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: BorderSide(color: t.border)),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: BorderSide(color: t.border)),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(10),
          borderSide: BorderSide(
            color: AppColors.primaryTeal(Theme.of(context).brightness == Brightness.dark), width: 1.5)),
        filled: true, fillColor: t.bg,
      ),
    ),
  ]);

// ─────────────────────────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────────────────────────
// SOS Contacts Panel
// ─────────────────────────────────────────────────────────────────────────────
class _SosContactsPanel extends StatelessWidget {
  const _SosContactsPanel();

  @override
  Widget build(BuildContext context) {
    final ctrl = context.watch<ProfileController>();
    final t    = context.lt;
    return Positioned.fill(
      child: Material(
        color: t.bg,
        child: Column(children: [
          LigtasHeader(
            title: 'SOS Contacts',
            leading: GestureDetector(
              onTap: ctrl.closeSosContacts,
              child: Container(
                width: 32, height: 32,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: t.border)),
                child: Icon(Icons.arrow_back_rounded, size: 16, color: t.text),
              ),
            ),
            trailing: GestureDetector(
              onTap: () => _showAddContactSheet(context, ctrl, t),
              child: Container(
                width: 32, height: 32,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(8),
                  color: AppColors.tealDim,
                  border: Border.all(color: AppColors.teal.withValues(alpha: 0.4))),
                child: Icon(Icons.add_rounded, size: 18, color: AppColors.teal),
              ),
            ),
          ),
          Expanded(child: ctrl.sosContacts.isEmpty
            ? Center(child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 56, height: 56,
                    decoration: BoxDecoration(
                      color: AppColors.redDim,
                      borderRadius: BorderRadius.circular(16)),
                    child: Icon(Icons.emergency_share_rounded,
                      color: AppColors.safeRed, size: 28)),
                  const SizedBox(height: 14),
                  Text('No Emergency Contacts',
                    style: t.title(size: 15)),
                  const SizedBox(height: 6),
                  Text('Add trusted contacts who will be\nalerted in an SOS emergency.',
                    style: t.body(size: 13, color: t.text2),
                    textAlign: TextAlign.center),
                  const SizedBox(height: 20),
                  TealButton(
                    label: 'Add Contact',
                    fullWidth: false,
                    onTap: () => _showAddContactSheet(context, ctrl, t),
                  ),
                ],
              ))
            : ListView.separated(
                padding: const EdgeInsets.all(16),
                itemCount: ctrl.sosContacts.length,
                separatorBuilder: (context, index) => const SizedBox(height: 8),
                itemBuilder: (_, i) {
                  final c = ctrl.sosContacts[i];
                  final name  = c['name']?.toString() ?? '';
                  final type  = c['contact_type']?.toString() ?? 'phone';
                  final value = c['contact_value']?.toString() ?? '';
                  final id    = c['id'] as int? ?? 0;
                  return Container(
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                    decoration: BoxDecoration(
                      color: t.card2,
                      borderRadius: BorderRadius.circular(13),
                      border: Border.all(color: t.border)),
                    child: Row(children: [
                      Container(
                        width: 40, height: 40,
                        decoration: BoxDecoration(
                          color: AppColors.redDim,
                          borderRadius: BorderRadius.circular(11)),
                        child: Icon(
                          type == 'email' ? Icons.email_rounded : Icons.phone_rounded,
                          color: AppColors.safeRed, size: 20)),
                      const SizedBox(width: 12),
                      Expanded(child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(name, style: t.title(size: 13)),
                          Text(value, style: t.body(size: 12, color: t.text2)),
                        ],
                      )),
                      IconButton(
                        icon: Icon(Icons.delete_outline_rounded,
                          size: 18, color: t.text2),
                        onPressed: () => ctrl.removeSosContact(contactId: id),
                      ),
                    ]),
                  );
                },
              )
          ),
        ]),
      ),
    );
  }

  void _showAddContactSheet(
      BuildContext context, ProfileController ctrl, dynamic t) {
    final nameCtrl  = TextEditingController();
    final valueCtrl = TextEditingController();
    String contactType = 'phone';

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => ChangeNotifierProvider.value(
        value: ctrl,
        child: StatefulBuilder(
          builder: (ctx, setS) => Container(
            padding: EdgeInsets.fromLTRB(
              20, 0, 20,
              MediaQuery.of(ctx).viewInsets.bottom + 28),
            decoration: BoxDecoration(
              color: t.card,
              borderRadius: const BorderRadius.vertical(top: Radius.circular(20))),
            child: SingleChildScrollView(child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Center(child: Container(
                  width: 36, height: 4,
                  margin: const EdgeInsets.symmetric(vertical: 14),
                  decoration: BoxDecoration(
                    color: t.border,
                    borderRadius: BorderRadius.circular(2)))),
                Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
                  Text('Add SOS Contact', style: t.title()),
                  IconButton(
                    icon: Icon(Icons.close_rounded, color: t.text2),
                    onPressed: () => Navigator.pop(ctx)),
                ]),
                const SizedBox(height: 16),
                _inputField('Full Name', nameCtrl, Icons.person_outline_rounded,
                  false, null, t, ctx),
                const SizedBox(height: 12),
                Text('Contact Type',
                  style: t.body(size: 12, w: FontWeight.w600, color: t.text2)),
                const SizedBox(height: 6),
                Row(children: [
                  _typeChip('Phone', 'phone', contactType, AppColors.teal, t,
                    () => setS(() => contactType = 'phone')),
                  const SizedBox(width: 8),
                  _typeChip('Email', 'email', contactType, AppColors.teal, t,
                    () => setS(() => contactType = 'email')),
                ]),
                const SizedBox(height: 12),
                _inputField(
                  contactType == 'email' ? 'Email Address' : 'Phone Number',
                  valueCtrl,
                  contactType == 'email'
                    ? Icons.email_outlined
                    : Icons.phone_outlined,
                  false, null, t, ctx),
                const SizedBox(height: 24),
                TealButton(
                  label: 'Add Contact',
                  onTap: () {
                    final n = nameCtrl.text.trim();
                    final v = valueCtrl.text.trim();
                    if (n.isEmpty || v.isEmpty) return;
                    Navigator.pop(ctx);
                    ctrl.addSosContact(
                      name: n,
                      contactType: contactType,
                      contactValue: v,
                    );
                  },
                ),
              ],
            )),
          ),
        ),
      ),
    );
  }

  Widget _typeChip(String label, String value, String current,
      Color teal, dynamic t, VoidCallback onTap) {
    final active = current == value;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 9),
        decoration: BoxDecoration(
          color: active ? teal.withValues(alpha: 0.12) : t.card2,
          borderRadius: BorderRadius.circular(50),
          border: Border.all(
            color: active ? teal.withValues(alpha: 0.5) : t.border,
            width: active ? 1.5 : 1)),
        child: Text(label,
          style: GoogleFonts.plusJakartaSans(
            fontSize: 13, fontWeight: FontWeight.w700,
            color: active ? teal : t.text2)),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Travel History Panel
// ─────────────────────────────────────────────────────────────────────────────
class _TravelHistoryPanel extends StatelessWidget {
  const _TravelHistoryPanel();

  @override
  Widget build(BuildContext context) {
    final ctrl = context.watch<ProfileController>();
    final t    = context.lt;
    final hasHistory = ctrl.history.history.isNotEmpty;
    final hasSaved   = ctrl.history.saved.isNotEmpty;

    return Positioned.fill(
      child: Material(
        color: t.bg,
        child: Column(children: [
          LigtasHeader(
            title: 'Travel History',
            leading: GestureDetector(
              onTap: ctrl.closeTravelHistory,
              child: Container(
                width: 32, height: 32,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: t.border)),
                child: Icon(Icons.arrow_back_rounded, size: 16, color: t.text),
              ),
            ),
            // ── Clear history button — only shown when there is history ──
            trailing: hasHistory && !ctrl.isLoadingHistory
                ? GestureDetector(
                    onTap: () => _confirmClear(context, ctrl, t),
                    child: Container(
                      width: 32, height: 32,
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(8),
                        color: AppColors.redDim,
                        border: Border.all(color: AppColors.safeRed.withValues(alpha: 0.35))),
                      child: Icon(Icons.delete_outline_rounded,
                        size: 17, color: AppColors.safeRed),
                    ),
                  )
                : null,
          ),

          // ── Loading spinner ────────────────────────────────────────────
          if (ctrl.isLoadingHistory)
            Expanded(
              child: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    SizedBox(
                      width: 28, height: 28,
                      child: CircularProgressIndicator(
                        strokeWidth: 2.5,
                        color: AppColors.teal,
                      ),
                    ),
                    const SizedBox(height: 14),
                    Text('Loading history…',
                      style: t.body(size: 13, color: t.text2)),
                  ],
                ),
              ),
            )

          // ── Empty state ────────────────────────────────────────────────
          else if (!hasHistory && !hasSaved)
            Expanded(
              child: Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 56, height: 56,
                      decoration: BoxDecoration(
                        color: AppColors.tealDim,
                        borderRadius: BorderRadius.circular(16)),
                      child: Icon(Icons.history_rounded,
                        color: AppColors.teal, size: 28)),
                    const SizedBox(height: 14),
                    Text('No travel history yet',
                      style: t.title(size: 15)),
                    const SizedBox(height: 6),
                    Text(
                      'Routes you search will appear here.',
                      style: t.body(size: 13, color: t.text2),
                      textAlign: TextAlign.center),
                  ],
                ),
              ),
            )

          // ── History list ───────────────────────────────────────────────
          else
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
                children: [
                  if (hasSaved) ...[
                    _subLabel('Saved Routes', t),
                    ...ctrl.history.saved.map((r) => _TravelCard(route: r)),
                    const SizedBox(height: 8),
                    Container(height: 1, color: t.divider),
                    const SizedBox(height: 16),
                  ],
                  if (hasHistory) ...[
                    _subLabel('History', t),
                    ...ctrl.history.history.map((r) => _TravelCard(route: r)),
                  ],
                ],
              ),
            ),
        ]),
      ),
    );
  }

  Widget _subLabel(String s, dynamic t) => Padding(
    padding: const EdgeInsets.only(bottom: 10),
    child: Text(s, style: GoogleFonts.plusJakartaSans(
      fontSize: 12, fontWeight: FontWeight.w700,
      color: t.text3, letterSpacing: 0.06)),
  );

  void _confirmClear(BuildContext context, ProfileController ctrl, dynamic t) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: t.card,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: Text('Clear History',
          style: GoogleFonts.plusJakartaSans(
            fontWeight: FontWeight.w800, fontSize: 16, color: t.text)),
        content: Text(
          'This will permanently delete all your route history. This cannot be undone.',
          style: GoogleFonts.plusJakartaSans(fontSize: 13, color: t.text2)),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: Text('Cancel',
              style: GoogleFonts.plusJakartaSans(
                fontWeight: FontWeight.w700, color: t.text2)),
          ),
          TextButton(
            onPressed: () {
              Navigator.pop(ctx);
              ctrl.clearTravelHistory();
            },
            child: Text('Clear',
              style: GoogleFonts.plusJakartaSans(
                fontWeight: FontWeight.w700,
                color: AppColors.safeRed)),
          ),
        ],
      ),
    );
  }
}

class _TravelCard extends StatelessWidget {
  final TravelRoute route;
  const _TravelCard({required this.route});

  @override
  Widget build(BuildContext context) {
    final ctrl = context.read<ProfileController>();
    final t    = context.lt;
    final iconColor = route.saved ? AppColors.yellow : AppColors.primaryTeal(Theme.of(context).brightness == Brightness.dark);
    return GestureDetector(
      onTap: () => showModalBottomSheet(
        context: context,
        isScrollControlled: true,
        backgroundColor: Colors.transparent,
        builder: (_) => ChangeNotifierProvider.value(
          value: ctrl,
          child: _TravelDetailSheet(route: route)),
      ),
      child: Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
        decoration: BoxDecoration(
          color: t.card2,
          borderRadius: BorderRadius.circular(13),
          border: Border.all(color: t.border)),
        child: Row(children: [
          Container(
            width: 38, height: 38,
            decoration: BoxDecoration(
              color: iconColor.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(10)),
            child: Icon(route.saved ? Icons.star_rounded : Icons.history_rounded,
              color: iconColor, size: 20),
          ),
          const SizedBox(width: 12),
          Expanded(child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('${route.origin} → ${route.destination}',
                style: t.title(size: 13)),
              Text('${route.modes} · ${route.date}',
                style: t.body(size: 11, color: t.text2)),
            ],
          )),
          Icon(Icons.chevron_right_rounded, size: 18, color: t.text2),
        ]),
      ),
    );
  }
}

class _TravelDetailSheet extends StatelessWidget {
  final TravelRoute route;
  const _TravelDetailSheet({required this.route});

  @override
  Widget build(BuildContext context) {
    final t          = context.lt;
    final meta       = route.safetyMeta;
    final safeColor  = Color(meta.color);

    return DraggableScrollableSheet(
      initialChildSize: 0.78, maxChildSize: 0.95, minChildSize: 0.4,
      builder: (_, scrollCtrl) => Container(
        decoration: BoxDecoration(
          color: t.card,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
          border: Border(top: BorderSide(color: t.border))),
        child: ListView(
          controller: scrollCtrl,
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 32),
          children: [
            Center(child: Container(
              width: 36, height: 4, margin: const EdgeInsets.symmetric(vertical: 12),
              decoration: BoxDecoration(color: t.border, borderRadius: BorderRadius.circular(2)))),
            Row(children: [
              GestureDetector(
                onTap: () => Navigator.pop(context),
                child: Container(
                  width: 32, height: 32,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: t.border)),
                  child: Icon(Icons.arrow_back_rounded, size: 15, color: t.text)),
              ),
              const SizedBox(width: 10),
              Expanded(child: Text('${route.origin} → ${route.destination}',
                style: t.title(size: 14),
                overflow: TextOverflow.ellipsis)),
            ]),
            const SizedBox(height: 14),
            Container(
              height: 110,
              decoration: BoxDecoration(
                color: safeColor.withValues(alpha: 0.09),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: safeColor.withValues(alpha: 0.25))),
              child: Center(child: Icon(Icons.map_rounded, color: safeColor, size: 44)),
            ),
            const SizedBox(height: 12),
            Text('via ${route.modes}',
              style: t.body(size: 13, color: t.text2)),
            const SizedBox(height: 12),
            Row(children: [
              _glance('₱${route.fare}',       'Fare', t),
              _glance('${route.minutes} min', 'Time', t),
              _glance(route.date,             'Date', t),
            ]),
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: safeColor.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: safeColor.withValues(alpha: 0.25))),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Text('${route.safetyScore}%',
                    style: GoogleFonts.plusJakartaSans(
                      fontSize: 22, fontWeight: FontWeight.w900, color: safeColor)),
                  const SizedBox(width: 10),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: safeColor.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(50)),
                    child: Text(meta.label,
                      style: GoogleFonts.plusJakartaSans(
                        fontSize: 11, fontWeight: FontWeight.w700, color: safeColor)),
                  ),
                ]),
                const SizedBox(height: 6),
                Text(route.safetyNote,
                  style: t.body(size: 12, color: t.text2)),
              ]),
            ),
            const SizedBox(height: 16),
            Text('Route Breakdown', style: t.title(size: 13)),
            const SizedBox(height: 10),
            ...route.steps.asMap().entries.map((e) => _StepRow(
              step: e.value, index: e.key,
              isLast: e.key == route.steps.length - 1, t: t,
            )),
          ],
        ),
      ),
    );
  }

  Widget _glance(String val, String label, dynamic t) => Expanded(
    child: Column(children: [
      Text(val, style: t.title(size: 13),
        maxLines: 1, overflow: TextOverflow.ellipsis),
      Text(label, style: t.body(size: 11, color: t.text2)),
    ]),
  );
}

class _StepRow extends StatelessWidget {
  final TravelStep step;
  final int index;
  final bool isLast;
  final dynamic t;
  const _StepRow({required this.step, required this.index,
    required this.isLast, required this.t});
  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 12),
    child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Column(children: [
        Container(
          width: 26, height: 26,
          decoration: BoxDecoration(
            color: AppColors.primaryTeal(Theme.of(context).brightness == Brightness.dark),
            shape: BoxShape.circle),
          child: Center(child: Text('${index + 1}',
            style: GoogleFonts.plusJakartaSans(
              color: Colors.white, fontSize: 11, fontWeight: FontWeight.w800))),
        ),
        if (!isLast)
          Container(width: 2, height: 26, color: t.divider),
      ]),
      const SizedBox(width: 12),
      Expanded(child: Padding(
        padding: const EdgeInsets.only(top: 3),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(step.name, style: t.title(size: 13)),
          Text(step.desc, style: t.body(size: 11, color: t.text2)),
        ]),
      )),
    ]),
  );
}