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
  {
    id: 11, artist: "Kraftwerk", title: "Trans-Europe Express", album: "Trans-Europe Express",
    bpm: 120.0, key: "A", key_scale: "minor", energy: 0.55, duration_sec: 385,
    tags: [
      { source: "discogs", raw_tag: "Electronic", canonical_style: "electronic", weight: 3 },
      { source: "lastfm", raw_tag: "krautrock", canonical_style: "krautrock", weight: 2 },
      { source: "musicbrainz", raw_tag: "synth-pop", canonical_style: "synth-pop", weight: 1 },
    ],
  },
  {
    id: 12, artist: "Goldie", title: "Inner City Life", album: "Timeless",
    bpm: 172.0, key: "D", key_scale: "minor", energy: 0.66, duration_sec: 410,
    tags: [
      { source: "discogs", raw_tag: "Drum n Bass", canonical_style: "drum-and-bass", weight: 3 },
      { source: "lastfm", raw_tag: "jungle", canonical_style: "jungle", weight: 2 },
      { source: "lastfm", raw_tag: "electronic", canonical_style: "electronic", weight: 1 },
    ],
  },
  {
    id: 13, artist: "Tatsuro Yamashita", title: "Sparkle", album: "For You",
    bpm: 124.0, key: "G", key_scale: "major", energy: 0.7, duration_sec: 379,
    tags: [
      { source: "discogs", raw_tag: "City Pop", canonical_style: "city-pop", weight: 3 },
      { source: "lastfm", raw_tag: "funk", canonical_style: "funk", weight: 1 },
      { source: "lastfm", raw_tag: "soul", canonical_style: "soul", weight: 1 },
    ],
  },
  {
    id: 14, artist: "Wiley", title: "Eskimo", album: "Treddin' on Thin Ice",
    bpm: 140.0, key: "C", key_scale: "minor", energy: 0.6, duration_sec: 224,
    tags: [
      { source: "discogs", raw_tag: "Grime", canonical_style: "grime", weight: 3 },
      { source: "lastfm", raw_tag: "uk garage", canonical_style: "garage", weight: 1 },
      { source: "lastfm", raw_tag: "bass music", canonical_style: "bass-music", weight: 1 },
    ],
  },
  {
    id: 15, artist: "João Gilberto", title: "Águas de Março", album: "João Gilberto",
    bpm: 100.0, key: "F", key_scale: "major", energy: 0.3, duration_sec: 210,
    tags: [
      { source: "discogs", raw_tag: "Bossa Nova", canonical_style: "bossa-nova", weight: 3 },
      { source: "lastfm", raw_tag: "jazz", canonical_style: "jazz", weight: 1 },
    ],
  },
  {
    id: 16, artist: "Joy Division", title: "Disorder", album: "Unknown Pleasures",
    bpm: 130.0, key: "A", key_scale: "minor", energy: 0.65, duration_sec: 231,
    tags: [
      { source: "discogs", raw_tag: "Post-Punk", canonical_style: "post-punk", weight: 3 },
      { source: "lastfm", raw_tag: "new wave", canonical_style: "new-wave", weight: 1 },
    ],
  },
  {
    id: 17, artist: "Chic", title: "Good Times", album: "Risqué",
    bpm: 118.0, key: "D", key_scale: "minor", energy: 0.75, duration_sec: 501,
    tags: [
      { source: "discogs", raw_tag: "Disco", canonical_style: "disco", weight: 3 },
      { source: "musicbrainz", raw_tag: "funk", canonical_style: "funk", weight: 2 },
    ],
  },
  {
    id: 18, artist: "King Tubby", title: "Natty Dub", album: "Dub Gone Crazy",
    bpm: 78.0, key: "G", key_scale: "minor", energy: 0.5, duration_sec: 300,
    tags: [
      { source: "discogs", raw_tag: "Dub", canonical_style: "dub", weight: 3 },
      { source: "lastfm", raw_tag: "reggae", canonical_style: "reggae", weight: 2 },
    ],
  },
  {
    id: 19, artist: "RP Boo", title: "Baby Come On", album: "Legacy",
    bpm: 160.0, key: "C", key_scale: "minor", energy: 0.68, duration_sec: 280,
    tags: [
      { source: "discogs", raw_tag: "Footwork", canonical_style: "footwork", weight: 3 },
      { source: "lastfm", raw_tag: "juke", canonical_style: "juke", weight: 1 },
      { source: "lastfm", raw_tag: "electronic", canonical_style: "electronic", weight: 1 },
    ],
  },
  {
    id: 20, artist: "Aretha Franklin", title: "Rock Steady", album: "Young, Gifted and Black",
    bpm: 116.0, key: "E", key_scale: "major", energy: 0.8, duration_sec: 296,
    tags: [
      { source: "discogs", raw_tag: "Soul", canonical_style: "soul", weight: 3 },
      { source: "musicbrainz", raw_tag: "funk", canonical_style: "funk", weight: 2 },
      { source: "lastfm", raw_tag: "gospel", canonical_style: "gospel", weight: 1 },
    ],
  },
];

// sync-listening + boredom 명령 결과를 흉내 낸 질림 스코어 (트랙 id -> score)
const MOCK_BOREDOM_SCORES = {
  1: 4.2, 2: 0.8, 3: 2.1, 4: 0.3, 5: 1.5,
  6: 3.0, 7: 0.6, 8: 0.2, 9: 1.0, 10: 3.8,
  11: 1.8, 12: 2.6, 13: 0.5, 14: 3.3, 15: 0.1,
  16: 1.2, 17: 4.5, 18: 0.4, 19: 2.9, 20: 0.7,
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
  12: {
    collab: [
      { entity_name: "Diane Charlemagne", path: "Inner City Life → vocals → Diane Charlemagne", already_known: false },
    ],
    label: [
      { entity_name: "FFRR", path: "Inner City Life → released_on_label → FFRR", already_known: false },
    ],
    samples: [],
    influence: [
      { entity_name: "4hero", path: "Goldie → influenced_by → 4hero", already_known: true },
    ],
  },
  17: {
    collab: [
      { entity_name: "Nile Rodgers", path: "Good Times → guitar → Nile Rodgers", already_known: true },
      { entity_name: "Bernard Edwards", path: "Good Times → bass → Bernard Edwards", already_known: false },
    ],
    label: [
      { entity_name: "Atlantic Records", path: "Good Times → released_on_label → Atlantic Records", already_known: true },
    ],
    samples: [],
    influence: [],
  },
  19: {
    collab: [],
    label: [
      { entity_name: "Planet Mu", path: "Baby Come On → released_on_label → Planet Mu", already_known: false },
    ],
    samples: [
      { entity_name: "DJ Slugo - Juke Track", path: "Baby Come On → samples → DJ Slugo - Juke Track", already_known: false },
    ],
    influence: [],
  },
};
