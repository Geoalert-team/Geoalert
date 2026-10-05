// Content for the "What to do" page.
// Edit the text here; the page layout is in src/pages/WhatToDo.jsx.

export const GUIDES = {
  Flood: {
    title: 'Flood response',
    intro:
      'Floods can develop fast. Whether from heavy rain, storm surge or an overflowing river, knowing when to evacuate and how to stay safe around water can save your life.',
    supplies: [
      'Waterproof first-aid kit',
      '3-day water supply',
      'Non-perishable food',
      'Flashlight and batteries',
      'Whistle',
      'Life jackets',
      'Important documents in a sealed bag',
      'Phone charger and power bank',
      'Medicines (7-day supply)',
    ],
    phases: {
      before: [
        'Follow PAGASA and DRRMO advisories when heavy rain or a typhoon is coming.',
        'Pack your go-bag and keep it where everyone can grab it.',
        'Move valuables and appliances to a higher floor or shelf.',
        'Know your evacuation center and the safest route to get there.',
        'Put important documents in a sealed plastic bag.',
      ],
      during: [
        'Evacuate early when barangay officials tell you to. Do not wait for the water to rise.',
        'Switch off electricity at the main breaker if you can do it safely.',
        'Do not walk or drive through floodwater. Even shallow moving water can knock you down.',
        'Move to higher ground and keep children away from the water.',
        'Stay tuned to official updates on radio or your phone.',
      ],
      after: [
        'Go home only when officials say it is safe.',
        'Do not touch electrical equipment that got wet until it has been checked.',
        'Clean and disinfect everything that touched floodwater.',
        'Boil drinking water until your water supply is declared safe.',
        'Report damage and injuries to your barangay.',
      ],
      firstaid: [
        'Wash any wound that touched floodwater with soap and clean water, then cover it.',
        'If you get a fever, headache or muscle pain after wading in floodwater, see a doctor. It can be a sign of leptospirosis.',
        'Keep wet and cold people warm and dry.',
        'If someone is not breathing, call 911 and start CPR if you are trained.',
      ],
    },
  },

  Landslide: {
    title: 'Landslide response',
    intro:
      'Landslides often follow days of heavy rain and can happen with little warning. Knowing the warning signs and leaving early is the best way to stay safe.',
    supplies: [
      'First-aid kit',
      '3-day water supply',
      'Non-perishable food',
      'Flashlight and batteries',
      'Whistle',
      'Dust masks',
      'Sturdy shoes',
      'Important documents in a sealed bag',
      'Phone charger and power bank',
      'Medicines (7-day supply)',
    ],
    phases: {
      before: [
        'Find out if your home is near a slope or landslide-prone area on the hazard map.',
        'Learn the warning signs: new cracks in the ground, tilting trees or posts, and doors or windows that suddenly stick.',
        'Plan a route to stable, higher ground away from slopes and river channels.',
        'Pack your go-bag and keep it by the door during the rainy season.',
      ],
      during: [
        'Leave right away if you notice warning signs or hear rumbling. Do not wait for an order.',
        'Move away from the path of the slide and toward stable ground to the side.',
        'Stay away from river valleys and channels where debris can flow.',
        'If you cannot get out, shelter under sturdy furniture and protect your head.',
      ],
      after: [
        'Stay away from the slide area. More slides can follow.',
        'Check for injured or trapped people nearby without entering the slide area, and report them.',
        'Watch for flooding, which often follows landslides.',
        'Return only when the DRRMO says the area is safe.',
      ],
      firstaid: [
        'Do not move a seriously injured person unless they are in immediate danger.',
        'Stop bleeding by pressing firmly on the wound with a clean cloth.',
        'Keep people with crush injuries still and calm until responders arrive.',
        'Clean small cuts and scrapes and cover them.',
      ],
    },
  },

  Fire: {
    title: 'Fire response',
    intro:
      'In closely built neighborhoods, fire can spread from house to house in minutes. Preventing fires and knowing how to get out fast are what keep families safe.',
    supplies: [
      'Fire extinguisher',
      'First-aid kit with clean dressings',
      'Flashlight and batteries',
      'Whistle',
      'Face masks',
      'Sturdy shoes by the bed',
      'Important documents in a grab bag',
      'Phone charger and power bank',
      'Medicines (7-day supply)',
    ],
    phases: {
      before: [
        'Keep doorways, stairs and alleys clear so everyone can get out.',
        'Avoid overloaded sockets and "octopus" connections. Have old wiring checked.',
        'Never leave cooking unattended, and turn off the LPG tank after use.',
        'Plan two ways out of your home and a meeting place outside.',
        'Keep a fire extinguisher where adults can reach it.',
      ],
      during: [
        'Shout to warn everyone and get out immediately.',
        'Stay low under smoke and cover your nose and mouth.',
        'Touch doors with the back of your hand. If a door is hot, use another way out.',
        'Call the fire station or 911 once you are outside.',
        'Never go back inside for belongings.',
      ],
      after: [
        'Do not go back in until fire officers say it is safe.',
        'Count everyone at your meeting place and tell responders if anyone is missing.',
        'Get checked by a health worker if you breathed in smoke.',
        'Ask your barangay about temporary shelter and assistance.',
      ],
      firstaid: [
        'Cool a burn under cool running water for 20 minutes.',
        'Do not put ice, toothpaste, butter or oil on a burn.',
        'Remove rings or tight items near the burn before it swells.',
        'Cover the burn loosely with a clean, non-stick cloth or plastic wrap.',
        'Get medical help for large burns or burns on the face, hands or genitals.',
      ],
    },
  },
};

// Order and labels for the four response steps
export const PHASES = [
  { key: 'before', title: 'Before', subtitle: 'Prepare and watch alerts', number: 1 },
  { key: 'during', title: 'During', subtitle: 'Evacuate and stay safe', number: 2 },
  { key: 'after', title: 'After', subtitle: 'Return safely and report', number: 3 },
  { key: 'firstaid', title: 'First aid', subtitle: 'Treat common injuries', number: null },
];

export const UNIVERSAL_TIPS = [
  {
    key: 'connected',
    title: 'Stay connected',
    text: 'Save emergency hotlines in your phone and keep it charged when a storm is coming.',
  },
  {
    key: 'routes',
    title: 'Know your routes',
    text: 'Walk the way to your evacuation center at least once, before you ever need it.',
  },
  {
    key: 'family',
    title: 'Make a family plan',
    text: 'Agree on a meeting point and one relative everyone will contact if you get separated.',
  },
  {
    key: 'kit',
    title: 'Keep a 72-hour kit',
    text: 'Pack enough water, food and medicine to last your family at least three days.',
  },
];

// PLACEHOLDER VIDEOS. Replace with the DRRMO's chosen videos later.
// "id" is the part after watch?v= in a YouTube link.
export const VIDEOS = [
  { id: '3JvRPfpQtYc', hazard: 'Flood', title: 'NDRRMC safety measures before a typhoon' },
  { id: 'Ed3g9WWD6xM', hazard: 'Flood', title: 'Flood and water safety' },
  { id: 'DSYDjSDRU2U', hazard: 'Flood', title: 'Flash flood safety' },
  { id: 'NhdiMVgJfSw', hazard: 'Flood', title: 'NDRRMC rescue teams in flooded areas' },
  { id: 'kJ4U5Kxkx-c', hazard: 'Landslide', title: 'Landslide after a tropical storm in the Philippines' },
];