// models/travel_history_model.dart

class TravelStep {
  final String name;
  final String desc;
  const TravelStep({required this.name, required this.desc});
}

class TravelRoute {
  final String id;
  final String origin;
  final String destination;
  final String modes;
  final int minutes;
  final int fare;
  final int safetyScore;
  final String safetyNote;
  final String date;
  final bool saved;
  final List<TravelStep> steps;

  const TravelRoute({
    required this.id,
    required this.origin,
    required this.destination,
    required this.modes,
    required this.minutes,
    required this.fare,
    required this.safetyScore,
    required this.safetyNote,
    required this.date,
    required this.saved,
    required this.steps,
  });

  TravelSafetyMeta get safetyMeta {
    if (safetyScore >= 85) return const TravelSafetyMeta(color: 0xFF12D9C0, label: 'Safe');
    if (safetyScore >= 70) return const TravelSafetyMeta(color: 0xFFD97706, label: 'Moderate');
    return const TravelSafetyMeta(color: 0xFFFB7185, label: 'Caution');
  }
}

class TravelSafetyMeta {
  final int color;
  final String label;
  const TravelSafetyMeta({required this.color, required this.label});
}

class TravelHistory {
  final List<TravelRoute> saved;
  final List<TravelRoute> history;
  const TravelHistory({required this.saved, required this.history});

  // FIX: Added the missing mock() method
  static TravelHistory mock() {
    return const TravelHistory(
      saved: [
        TravelRoute(
          id: 'r1',
          origin: 'Ayala Heights',
          destination: 'UP Diliman',
          modes: 'Jeepney',
          minutes: 15,
          fare: 13,
          safetyScore: 94,
          safetyNote: 'High visibility and active community patrols.',
          date: 'Saved',
          saved: true,
          steps: [
            TravelStep(name: 'Board Jeepney', desc: 'Katipunan-UP route'),
            TravelStep(name: 'Alight at Gate', desc: 'University Ave entrance'),
          ],
        ),
      ],
      history: [
        TravelRoute(
          id: 'r2',
          origin: 'SM North',
          destination: 'Trinoma',
          modes: 'Walk',
          minutes: 8,
          fare: 0,
          safetyScore: 68,
          safetyNote: 'Construction area nearby, stay on the main path.',
          date: 'Yesterday',
          saved: false,
          steps: [
            TravelStep(name: 'Cross Bridge', desc: 'Use the overpass'),
          ],
        ),
      ],
    );
  }
}