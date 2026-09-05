/* 실제 digger.db 스키마(tracks / track_tags / relations)를 흉내 낸 목업 데이터.
   디자인 검증용이며 백엔드에는 연결되어 있지 않음. */

const MOCK_TRACKS = [
  {
    id: 1, artist: "Larry Heard", title: "Can You Feel It", album: "Video EP",
    bpm: 122.4, key: "A", key_scale: "minor", energy: 0.61, duration_sec: 351,
    tags: [
      { source: "discogs", raw_tag: "House", canonical_style: "house", weight: 3 },
      { source: "lastfm", raw_tag: "deep house", canonical_style: "deep-house", weight: 2 },
      { source: "musicbrainz", raw_tag: "chicago house", canonical_style: "chicago-house", weight: 1 },
    ],
  },
  {
    id: 2, artist: "Burial", title: "Archangel", album: "Untrue",
    bpm: 138.9, key: "F#", key_scale: "minor", energy: 0.44, duration_sec: 285,
    tags: [
      { source: "discogs", raw_tag: "UK Garage", canonical_style: "garage", weight: 2 },
      { source: "lastfm", raw_tag: "dubstep", canonical_style: "dubstep", weight: 3 },
      { source: "lastfm", raw_tag: "bass music", canonical_style: "bass-music", weight: 1 },
    ],
  },
  {
    id: 3, artist: "D'Angelo", title: "Left & Right", album: "Voodoo",
    bpm: 96.2, key: "D", key_scale: "minor", energy: 0.52, duration_sec: 298,
    tags: [
      { source: "discogs", raw_tag: "Neo Soul", canonical_style: "neo-soul", weight: 3 },
      { source: "lastfm", raw_tag: "rnb", canonical_style: "rnb", weight: 2 },
      { source: "musicbrainz", raw_tag: "funk", canonical_style: "funk", weight: 1 },
    ],
  },
  {
    id: 4, artist: "Brian Eno", title: "An Ending (Ascent)", album: "Apollo",
    bpm: 60.0, key: "E", key_scale: "major", energy: 0.12, duration_sec: 257,
    tags: [
      { source: "discogs", raw_tag: "Ambient", canonical_style: "ambient", weight: 3 },
      { source: "lastfm", raw_tag: "drone", canonical_style: "drone", weight: 2 },
    ],
  },
  {
    id: 5, artist: "Herbie Hancock", title: "Actual Proof", album: "Thrust",
    bpm: 128.5, key: "C", key_scale: "minor", energy: 0.69, duration_sec: 566,
    tags: [
      { source: "discogs", raw_tag: "Jazz-Funk", canonical_style: "jazz-fusion", weight: 3 },
      { source: "musicbrainz", raw_tag: "funk", canonical_style: "funk", weight: 2 },
      { source: "lastfm", raw_tag: "jazz", canonical_style: "jazz", weight: 1 },
    ],
  },
  {
    id: 6, artist: "Massive Attack", title: "Teardrop", album: "Mezzanine",
    bpm: 78.3, key: "G", key_scale: "minor", energy: 0.38, duration_sec: 330,
    tags: [
      { source: "discogs", raw_tag: "Trip Hop", canonical_style: "trip-hop", weight: 3 },
      { source: "lastfm", raw_tag: "downtempo", canonical_style: "downtempo", weight: 2 },
      { source: "musicbrainz", raw_tag: "electronic", canonical_style: "electronic", weight: 1 },
    ],
  },
  {
    id: 7, artist: "4hero", title: "Loveless", album: "Two Pages",
    bpm: 130.1, key: "B", key_scale: "minor", energy: 0.57, duration_sec: 402,
    tags: [
      { source: "discogs", raw_tag: "Broken Beat", canonical_style: "broken-beat", weight: 2 },
      { source: "lastfm", raw_tag: "nu jazz", canonical_style: "nu-jazz", weight: 2 },
      { source: "musicbrainz", raw_tag: "house", canonical_style: "house", weight: 1 },
    ],
  },
  {
    id: 8, artist: "Deepchord", title: "Providence", album: "Auratones",
    bpm: 128.0, key: "A", key_scale: "minor", energy: 0.41, duration_sec: 411,
    tags: [
      { source: "discogs", raw_tag: "Dub Techno", canonical_style: "dub-techno", weight: 3 },
      { source: "lastfm", raw_tag: "techno", canonical_style: "techno", weight: 2 },
      { source: "lastfm", raw_tag: "ambient", canonical_style: "ambient", weight: 1 },
    ],
  },
  {
    id: 9, artist: "Fela Kuti", title: "Water No Get Enemy", album: "Expensive Shit",
    bpm: 110.6, key: "E", key_scale: "minor", energy: 0.72, duration_sec: 636,
    tags: [
      { source: "discogs", raw_tag: "Afrobeat", canonical_style: "afrobeat", weight: 3 },
      { source: "musicbrainz", raw_tag: "funk", canonical_style: "funk", weight: 2 },
    ],
  },
  {
    id: 10, artist: "J Dilla", title: "Time: The Donut of the Heart", album: "Donuts",
    bpm: 90.8, key: "F", key_scale: "major", energy: 0.48, duration_sec: 95,
    tags: [
      { source: "discogs", raw_tag: "Boom Bap", canonical_style: "boom-bap", weight: 3 },
      { source: "lastfm", raw_tag: "hip hop", canonical_style: "hip-hop", weight: 2 },
      { source: "musicbrainz", raw_tag: "soul", canonical_style: "soul", weight: 1 },
    ],
  },
];

// sync-listening + boredom 명령 결과를 흉내 낸 질림 스코어 (트랙 id -> score)
const MOCK_BOREDOM_SCORES = {
  1: 4.2, 2: 0.8, 3: 2.1, 4: 0.3, 5: 1.5,
  6: 3.0, 7: 0.6, 8: 0.2, 9: 1.0, 10: 3.8,
};

// collect-relations 결과를 흉내 낸 관계 그래프. mb_recording_id가 없는 트랙(관계 미수집)도
// 일부 남겨 두어 CLI와 동일하게 "데이터 없음" 상태를 보여줌.
const MOCK_RELATIONS = {
  1: {
    collab: [
      { entity_name: "Robert Owens", path: "Can You Feel It → vocals → Robert Owens", already_known: false },
      { entity_name: "Mr. Fingers", path: "Can You Feel It → remix → Mr. Fingers", already_known: true },
    ],
    label: [
      { entity_name: "Alleviated Records", path: "Can You Feel It → released_on_label → Alleviated Records", already_known: false },
    ],
    samples: [],
    influence: [
      { entity_name: "Ron Hardy", path: "Larry Heard → influenced_by → Ron Hardy", already_known: false },
    ],
  },
  2: {
    collab: [
      { entity_name: "Kode9", path: "Archangel → mix → Kode9", already_known: true },
    ],
    label: [
      { entity_name: "Hyperdub", path: "Archangel → released_on_label → Hyperdub", already_known: true },
    ],
    samples: [
      { entity_name: "Ray J - One Wish", path: "Archangel → samples → Ray J - One Wish", already_known: false },
    ],
    influence: [],
  },
  5: {
    collab: [
      { entity_name: "Paul Jackson", path: "Actual Proof → bass → Paul Jackson", already_known: false },
      { entity_name: "Mike Clark", path: "Actual Proof → drums → Mike Clark", already_known: false },
    ],
    label: [
      { entity_name: "Columbia Records", path: "Actual Proof → released_on_label → Columbia Records", already_known: true },
    ],
    samples: [],
    influence: [
      { entity_name: "Miles Davis", path: "Herbie Hancock → influenced_by → Miles Davis", already_known: true },
    ],
  },
  6: {
    collab: [
      { entity_name: "Horace Andy", path: "Teardrop → vocals(alt) → Horace Andy", already_known: false },
    ],
    label: [],
    samples: [],
    influence: [],
  },
  9: {
    collab: [
      { entity_name: "Tony Allen", path: "Water No Get Enemy → drums → Tony Allen", already_known: false },
    ],
    label: [
      { entity_name: "EMI Nigeria", path: "Water No Get Enemy → released_on_label → EMI Nigeria", already_known: false },
    ],
    samples: [],
    influence: [],
  },
};
