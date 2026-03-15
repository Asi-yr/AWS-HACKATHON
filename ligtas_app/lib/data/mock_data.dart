import '../models/user_model.dart';
import '../models/travel_history_model.dart';

import 'package:flutter/material.dart';
import '../models/explore_models.dart';

// ── Mock User ────────────────────────────────────────────────────
// BACKEND: GET /api/user/current
const mockUser = UserModel(
  id: 'usr_mateo_001',
  name: 'Full Name',
  username: '@fullName123',
  role: 'Verified Commuter',
  avatarUrl: 'https://cdn.pixabay.com/photo/2023/02/18/11/00/icon-7797704_1280.png',
  stats: UserStats(trips: 246, reports: 12, upvotedReports: 55),
  commuterType: 'Normal',
  preferences: UserPreferences(aiSafety: true, nightMode: false, transport: ['jeep', 'walk']),
);

// ── Mock Travel History ───────────────────────────────────────────
// BACKEND: GET /api/user/travel-history
const mockTravelHistory = TravelHistory(
  saved: [
    TravelRoute(
      id: 'sav_001',
      origin: 'Cubao', destination: 'UP Diliman',
      modes: 'Jeepney + Walk', minutes: 25, fare: 15,
      safetyScore: 92, date: 'Daily route', saved: true,
      safetyNote: 'Consistently safe corridor. High foot traffic throughout the day, well-lit streets, no incidents in the past 60 days. Patrol presence near campus gates.',
      steps: [
        TravelStep(name: 'Jeepney — Commonwealth to Katipunan', desc: '18 min · ₱13 · Araneta – P. Tuazon – Katipunan Ave'),
        TravelStep(name: 'Walk — Katipunan to UP Main Gate',   desc: '7 min · 550 m · Well-lit campus road with roving guards'),
      ],
    ),
    TravelRoute(
      id: 'sav_002',
      origin: 'Quezon Ave MRT', destination: 'Trinoma Mall',
      modes: 'MRT-3 + Walk', minutes: 18, fare: 28,
      safetyScore: 88, date: 'Weekend route', saved: true,
      safetyNote: 'MRT-3 corridor is CCTV-monitored and has visible personnel. Walk from North Ave station to Trinoma is fully covered — safe even at night.',
      steps: [
        TravelStep(name: 'MRT-3 — Quezon Ave to North Ave', desc: '8 min · ₱28 · 2 stops, air-conditioned, CCTV throughout'),
        TravelStep(name: 'Walk — North Ave Station to Trinoma', desc: '10 min · 800 m · Covered walkway, always busy'),
      ],
    ),
  ],
  history: [
    TravelRoute(
      id: 'his_001',
      origin: 'Philcoa', destination: 'SM North EDSA',
      modes: 'Bus + Walk', minutes: 42, fare: 20,
      safetyScore: 76, date: 'Mar 7, 2026 · 6:45 PM', saved: false,
      safetyNote: 'Generally safe during daytime. Some stretches near the EDSA flyover have poor lighting at night. Recommend taking this route before 8 PM.',
      steps: [
        TravelStep(name: 'Bus — Philcoa to North Ave via EDSA', desc: '30 min · ₱20 · Aircon bus, busy but monitored'),
        TravelStep(name: 'Walk — North Ave to SM North EDSA',   desc: '12 min · 950 m · EDSA sidewalk, use footbridge'),
      ],
    ),
    TravelRoute(
      id: 'his_002',
      origin: 'Cubao', destination: 'UP Diliman',
      modes: 'Jeepney + Walk', minutes: 25, fare: 15,
      safetyScore: 92, date: 'Mar 6, 2026 · 8:10 AM', saved: false,
      safetyNote: 'Consistently safe corridor. High foot traffic throughout the day, well-lit streets, no incidents in the past 60 days.',
      steps: [
        TravelStep(name: 'Jeepney — Commonwealth to Katipunan', desc: '18 min · ₱13 · Araneta – P. Tuazon – Katipunan Ave'),
        TravelStep(name: 'Walk — Katipunan to UP Main Gate',    desc: '7 min · 550 m · Campus road with guards'),
      ],
    ),
    TravelRoute(
      id: 'his_003',
      origin: 'Monumento', destination: 'Cubao',
      modes: 'LRT-1 + Jeepney', minutes: 35, fare: 45,
      safetyScore: 85, date: 'Mar 5, 2026 · 7:30 PM', saved: false,
      safetyNote: 'LRT-1 is well-patrolled with uniform personnel on every platform. Jeepney transfer at Cubao is busy but safe during peak hours.',
      steps: [
        TravelStep(name: 'LRT-1 — Monumento to Roosevelt', desc: '20 min · ₱35 · 3 stops, CCTV-monitored platform'),
        TravelStep(name: 'Jeepney — Roosevelt to Cubao',   desc: '15 min · ₱10 · EDSA route, busy daytime corridor'),
      ],
    ),
    TravelRoute(
      id: 'his_004',
      origin: 'Novaliches', destination: 'Quezon City Hall',
      modes: 'UV Express + Walk', minutes: 50, fare: 55,
      safetyScore: 71, date: 'Mar 3, 2026 · 9:00 AM', saved: false,
      safetyNote: 'UV Express route is registered and has GPS tracking. The walking stretch near City Hall has mixed lighting. Stay alert near the market area.',
      steps: [
        TravelStep(name: 'UV Express — Novaliches to Quezon Ave', desc: '38 min · ₱55 · Registered, GPS-tracked, A/C'),
        TravelStep(name: 'Walk — Quezon Ave to City Hall',         desc: '12 min · 900 m · Market area, stay on main road'),
      ],
    ),
  ],
);

// ── Mock Routes ──────────────────────────────────────────────────
const mockRoutes = [
  RouteModel(
    id: 'route_001', modes: 'Jeepney → Walk',
    minutes: 32, fare: 18, safetyScore: 92, tag: 'fastest',
    safetyNote: 'Well-lit roads with active community monitoring. High foot traffic during daytime. No incidents reported in the past 30 days.',
    steps: [
      RouteStep(title: 'Walk to Commonwealth Ave',  description: '5 min walk · 400m · Well-lit path'),
      RouteStep(title: 'Take Jeepney to UP Diliman', description: '20 min ride · ₱13 · Commonwealth–Katipunan'),
      RouteStep(title: 'Walk to destination',        description: '7 min walk · 550m · Campus path with guards'),
      RouteStep(title: 'Take the MRT-3 towards Taft Avenue', description: '12 min ride · ₱28 · 3 stops', vehicleName: 'MRT-3 Line'),
    ],
    polyline: [[14.6507,121.0494],[14.6540,121.0470],[14.6580,121.0440],[14.6620,121.0400],[14.6658,121.0654],[14.6560,121.0590],[14.6530,121.0680]],
    commuterTags: ['normal', 'student'],
    ligtasTags:   ['lit', 'crowded'],
  ),
  RouteModel(
    id: 'route_002', modes: 'Bus → Jeepney → Walk',
    minutes: 45, fare: 25, safetyScore: 78, tag: 'balanced',
    safetyNote: 'Route passes through moderately busy areas. Some stretches have limited lighting at night. Exercise caution during off-peak hours.',
    steps: [
      RouteStep(title: 'Walk to EDSA bus stop', description: '3 min walk · 250m'),
      RouteStep(title: 'Take Bus along EDSA',   description: '25 min ride · ₱15 · EDSA Southbound'),
      RouteStep(title: 'Transfer to Jeepney',   description: '12 min ride · ₱10'),
      RouteStep(title: 'Walk to destination',   description: '5 min walk · 400m'),
      RouteStep(title: 'Take the MRT-3 towards Taft Avenue', description: '12 min ride · ₱28 · 3 stops', vehicleName: 'MRT-3 Line'),
    ],
    polyline: [[14.6507,121.0494],[14.6460,121.0390],[14.6420,121.0370],[14.6500,121.0550],[14.6570,121.0620],[14.6530,121.0680]],
    commuterTags: ['normal', 'student', 'disabled'],
    ligtasTags:   ['crowded'],
  ),
  RouteModel(
    id: 'route_003', modes: 'Tricycle → Walk',
    minutes: 28, fare: 35, safetyScore: 89, tag: 'cheapest',
    safetyNote: 'Short route through residential streets with regular tricycle patrols. Well-known area with low crime rate.',
    steps: [
      RouteStep(title: 'Board tricycle near you',    description: '1 min wait'),
      RouteStep(title: 'Tricycle to Katipunan Ave',  description: '20 min ride · ₱35'),
      RouteStep(title: 'Walk to destination',        description: '7 min walk · 550m'),
    ],
    polyline: [[14.6507,121.0494],[14.6520,121.0530],[14.6545,121.0570],[14.6530,121.0680]],
    commuterTags: ['normal', 'women', 'minor'],
    ligtasTags:   ['patrol', 'lit'],
  ),
  RouteModel(
    id: 'route_004', modes: 'MRT → Walk',
    minutes: 22, fare: 28, safetyScore: 95, tag: 'safest',
    safetyNote: 'Fully elevated MRT corridor with CCTV coverage throughout. Short walk on well-patrolled university avenue.',
    steps: [
      RouteStep(title: 'Walk to MRT Station', description: '4 min walk · 320m · Covered walkway'),
      RouteStep(title: 'MRT-3 Northbound',    description: '12 min ride · ₱28 · 3 stops'),
      RouteStep(title: 'Walk to destination', description: '6 min walk · 480m · Katipunan Ave'),
    ],
    polyline: [[14.6507,121.0494],[14.6555,121.0320],[14.6590,121.0350],[14.6530,121.0680]],
    commuterTags: ['normal', 'student', 'women', 'lgbtq', 'disabled', 'minor'],
    ligtasTags:   ['cctv', 'lit', 'patrol', 'crowded'],
  ),
  RouteModel(
    id: 'route_005', modes: 'Bus → Walk',
    minutes: 38, fare: 15, safetyScore: 74, tag: 'moderate',
    safetyNote: 'Bus route covers busy commercial areas. Some stops near Cubao have elevated snatching risk during peak hours. Stay alert.',
    steps: [
      RouteStep(title: 'Walk to Bus Stop',      description: '2 min walk · 150m'),
      RouteStep(title: 'P2P Bus to Katipunan',  description: '30 min ride · ₱15 · via Aurora Blvd'),
      RouteStep(title: 'Walk to destination',   description: '6 min walk · 500m'),
    ],
    polyline: [[14.6507,121.0494],[14.6470,121.0430],[14.6510,121.0600],[14.6530,121.0680]],
    commuterTags: ['normal', 'student'],
    ligtasTags:   ['emergency'],
  ),
];

// ── Commuter Options ─────────────────────────────────────────────
const commuterOptions = [
  FilterOption(key: 'women',    label: 'Women',    icon: Icons.woman_rounded),
  FilterOption(key: 'seniors',  label: 'Seniors',  icon: Icons.elderly_rounded),
  FilterOption(key: 'students', label: 'Students', icon: Icons.school_rounded),
  FilterOption(key: 'pwd',      label: 'PWD',      icon: Icons.accessible_rounded),
];

// ── Transport Options ────────────────────────────────────────────
const transportOptions = [
  FilterOption(key: 'car',        label: 'Car',        icon: Icons.directions_car_rounded),
  FilterOption(key: 'motorcycle', label: 'Motorcycle', icon: Icons.two_wheeler_rounded),
  FilterOption(key: 'train',      label: 'Train',      icon: Icons.train_rounded),
  FilterOption(key: 'jeepney',    label: 'Jeepney',    icon: Icons.directions_bus_rounded),
  FilterOption(key: 'bus',        label: 'Bus',        icon: Icons.airport_shuttle_rounded),
  FilterOption(key: 'walk',       label: 'Walk',       icon: Icons.directions_walk_rounded),
];

// ── Ligtas Features ──────────────────────────────────────────────
const ligtasFeatures = [
  FilterOption(key: 'dark',     label: 'Dark Areas',     icon: Icons.wb_sunny_rounded),
  FilterOption(key: 'crime',    label: 'Crime Hotspots', icon: Icons.warning_amber_rounded),
  FilterOption(key: 'flooding', label: 'Flood-Prone',    icon: Icons.water_rounded),
  FilterOption(key: 'traffic',  label: 'Heavy Traffic',  icon: Icons.traffic_rounded),
];

// ── Mini State Items ─────────────────────────────────────────────
const miniItems = [
  MiniItem(type: MiniItemType.clock, name: '6014, Del Mundo Street, Ugong',  sub: '3.05km · Valenzuela City'),
  MiniItem(type: MiniItemType.clock, name: 'Starbucks, Greenhills 1',        sub: '9.67km · Ortigas Ave, San Juan'),
  MiniItem(type: MiniItemType.clock, name: 'Jollibee, MCU EDSA',             sub: '2.33km · N. Loreto St, Caloocan'),
  MiniItem(type: MiniItemType.clock, name: 'Careline Drug Store',             sub: '2.62km · L. Bustamante St, Caloocan'),
  MiniItem(type: MiniItemType.clock, name: 'SM City North EDSA',             sub: '3.45km · EDSA, Quezon City'),
  MiniItem(type: MiniItemType.pin,   name: 'UP Town Center, Katipunan Ave',   sub: 'Shopping Mall'),
  MiniItem(type: MiniItemType.pin,   name: 'Ateneo de Manila University',     sub: 'University'),
  MiniItem(type: MiniItemType.pin,   name: 'Miriam College, Quezon City',     sub: 'School'),
  MiniItem(type: MiniItemType.pin,   name: 'SM City Fairview, Quezon City',   sub: 'Shopping Mall'),
  MiniItem(type: MiniItemType.pin,   name: 'Trinoma Mall, Quezon City',       sub: 'Shopping Mall'),
];