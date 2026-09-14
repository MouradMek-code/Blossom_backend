# Curated starter date spots, inserted by an admin via POST /date_spots/admin/seed
# so the page doesn't launch looking empty.
#
# Guidelines for this list:
# - Only long-established places, to keep the risk of listing somewhere that
#   has closed low. Still worth a quick review before promoting a city.
# - Descriptions are factual and evergreen: no invented personal stories, and
#   no prices or opening hours that go stale.
# - Values for category / price / best_for must match CATEGORIES, PRICES and
#   BEST_FOR in routers/date_spot.py.
# - maps_query is optional; it defaults to "<name>, <city>".
# - Seeded spots have no author and no photo; an admin can add photos later
#   with Edit.

STARTER_SPOTS = [
    {
        "name": "Jardin du Luxembourg",
        "neighborhood": "Odéon",
        "category": "Walk / Outdoors",
        "price": "Free",
        "best_for": ["First date", "Romantic"],
        "description": (
            "Pull two of the famous green chairs together near the Medici Fountain "
            "and let the conversation wander. When you're ready to move, the streets "
            "of Saint-Germain are right next door."
        ),
    },
    {
        "name": "Canal Saint-Martin",
        "neighborhood": "République",
        "category": "Walk / Outdoors",
        "price": "Free",
        "best_for": ["Casual", "First date"],
        "description": (
            "Walk along the water, cross the little iron footbridges and stop by the "
            "locks. On sunny evenings people sit along the quays, so it feels lively "
            "without being loud."
        ),
    },
    {
        "name": "Parc des Buttes-Chaumont",
        "neighborhood": None,
        "category": "Hiking / Nature",
        "price": "Free",
        "best_for": ["Adventurous", "Casual"],
        "description": (
            "Paris's most dramatic park, with steep paths, a suspension bridge and a "
            "small temple on top of a cliff overlooking the lake. Wear comfortable "
            "shoes: there are plenty of stairs, and the view is worth the climb."
        ),
    },
    {
        "name": "Île Saint-Louis",
        "neighborhood": None,
        "category": "Walk / Outdoors",
        "price": "€",
        "best_for": ["Romantic", "First date"],
        "description": (
            "A quiet island in the middle of the Seine, a short walk from Notre-Dame. "
            "Walk the quays, share an ice cream from Berthillon and watch the boats "
            "go by."
        ),
    },
    {
        "name": "Jardin du Palais-Royal",
        "neighborhood": "Louvre",
        "category": "Walk / Outdoors",
        "price": "Free",
        "best_for": ["First date", "Romantic"],
        "description": (
            "A calm garden hidden behind elegant arcades, a few minutes from the "
            "Louvre. Rows of trees, a fountain and the striped Buren columns in the "
            "courtyard make it an easy, quiet place to talk."
        ),
    },
    {
        "name": "Coulée verte René-Dumont",
        "neighborhood": "Bastille",
        "category": "Walk / Outdoors",
        "price": "Free",
        "best_for": ["First date", "Casual"],
        "description": (
            "An old railway viaduct turned into a long garden path above the streets. "
            "Perfect for walking and talking, with stairs down to the street all "
            "along the way if you want to stop for a drink."
        ),
    },
    {
        "name": "Café de Flore",
        "neighborhood": "Saint-Germain-des-Prés",
        "category": "Coffee",
        "price": "€€",
        "best_for": ["Romantic", "First date"],
        "description": (
            "One of Paris's oldest and most famous cafés, loved by writers and "
            "artists for over a century. Prices are high, but sitting on the terrace "
            "watching Saint-Germain go by makes a simple coffee feel special."
        ),
    },
    {
        "name": "Shakespeare and Company Café",
        "neighborhood": "Quartier Latin",
        "category": "Coffee",
        "price": "€",
        "best_for": ["First date", "Casual"],
        "description": (
            "A small café next to the legendary English-language bookshop, with "
            "Notre-Dame just across the river. Browse the shelves together first, "
            "then talk about what you found over coffee."
        ),
    },
    {
        "name": "Bouillon Chartier",
        "neighborhood": "Grands Boulevards",
        "category": "Restaurant",
        "price": "€",
        "best_for": ["Casual"],
        "maps_query": "Bouillon Chartier Grands Boulevards, Paris",
        "description": (
            "A spectacular Belle Époque dining hall serving classic French dishes at "
            "surprisingly low prices since 1896. It's busy and fast-paced, so expect "
            "a queue and a fun, no-pressure meal."
        ),
    },
    {
        "name": "Le Relais de l'Entrecôte",
        "neighborhood": "Saint-Germain-des-Prés",
        "category": "Restaurant",
        "price": "€€",
        "best_for": ["Casual"],
        "maps_query": "Le Relais de l'Entrecôte Saint-Germain, Paris",
        "description": (
            "No menu to agonise over: everyone gets a walnut salad and steak-frites "
            "with the famous secret sauce, plus a second serving. Easy and fun, with "
            "no awkward ordering."
        ),
    },
    {
        "name": "L'As du Fallafel",
        "neighborhood": "Le Marais",
        "category": "Restaurant",
        "price": "€",
        "best_for": ["Casual"],
        "description": (
            "A Marais institution for falafel pitas, usually with a queue on Rue des "
            "Rosiers. Grab one to take away and wander the Marais together while you "
            "eat."
        ),
    },
    {
        "name": "Rosa Bonheur",
        "neighborhood": "Buttes-Chaumont",
        "category": "Drinks / Bar",
        "price": "€",
        "best_for": ["Casual"],
        "maps_query": "Rosa Bonheur Buttes-Chaumont, Paris",
        "description": (
            "A guinguette-style bar inside the Buttes-Chaumont park, with drinks, "
            "simple food and a relaxed, festive crowd. Great to pair with a walk "
            "through the park."
        ),
    },
    {
        "name": "Le Perchoir",
        "neighborhood": "Ménilmontant",
        "category": "Drinks / Bar",
        "price": "€€",
        "best_for": ["Romantic", "Casual"],
        "maps_query": "Le Perchoir Ménilmontant, Paris",
        "description": (
            "A rooftop bar with wide views over the rooftops of eastern Paris. Go for "
            "sunset, and arrive early because it fills up fast."
        ),
    },
    {
        "name": "Candelaria",
        "neighborhood": "Haut-Marais",
        "category": "Drinks / Bar",
        "price": "€€",
        "best_for": ["Romantic", "Adventurous"],
        "description": (
            "Walk through a tiny taqueria and open the unmarked door at the back to "
            "find a buzzing cocktail bar. The hidden entrance makes a great "
            "icebreaker."
        ),
    },
    {
        "name": "Le Caveau de la Huchette",
        "neighborhood": "Quartier Latin",
        "category": "Concert / Live Music",
        "price": "€€",
        "best_for": ["Adventurous", "Romantic"],
        "description": (
            "A vaulted cellar where jazz and swing bands have played since 1946 and "
            "couples dance until late. No dance experience needed: just join in."
        ),
    },
    {
        "name": "Sunset-Sunside",
        "neighborhood": "Châtelet",
        "category": "Concert / Live Music",
        "price": "€€",
        "best_for": ["Romantic"],
        "maps_query": "Sunset-Sunside jazz club, Paris",
        "description": (
            "Two intimate jazz clubs in one on Rue des Lombards, the jazz street of "
            "Paris. Small rooms and live music make for a memorable evening right in "
            "the city centre."
        ),
    },
    {
        "name": "Musée de l'Orangerie",
        "neighborhood": "Tuileries",
        "category": "Museum / Art Gallery",
        "price": "€",
        "best_for": ["First date", "Romantic"],
        "description": (
            "Two calm oval rooms wrapped in Monet's giant Water Lilies paintings. "
            "Small enough to see in an hour, which leaves plenty of time for a walk "
            "in the Tuileries afterwards."
        ),
    },
    {
        "name": "Musée Rodin",
        "neighborhood": "Invalides",
        "category": "Museum / Art Gallery",
        "price": "€",
        "best_for": ["Romantic", "First date"],
        "description": (
            "Rodin's sculptures in an elegant mansion surrounded by a beautiful "
            "garden. Find The Kiss inside, then stroll among the statues and roses "
            "outside."
        ),
    },
    {
        "name": "Musée de la Vie Romantique",
        "neighborhood": "Pigalle",
        "category": "Museum / Art Gallery",
        "price": "Free",
        "best_for": ["First date", "Romantic"],
        "description": (
            "A charming small museum in a painter's former home at the end of a leafy "
            "lane, devoted to the Romantic era. The permanent collection is free, and "
            "the courtyard garden is lovely on a sunny day."
        ),
    },
    {
        "name": "Atelier des Lumières",
        "neighborhood": None,
        "category": "Museum / Art Gallery",
        "price": "€€",
        "best_for": ["First date", "Adventurous"],
        "description": (
            "A former foundry where huge digital art shows are projected over the "
            "walls and floor, set to music. Easy to enjoy even if you're not into "
            "museums, and it gives you plenty to talk about afterwards."
        ),
    },
    {
        "name": "Le Grand Rex",
        "neighborhood": "Grands Boulevards",
        "category": "Movie",
        "price": "€",
        "best_for": ["Casual"],
        "description": (
            "One of Europe's largest cinemas, an Art Deco landmark whose main hall "
            "has a starry-sky ceiling. Even an ordinary movie night feels like an "
            "event here."
        ),
    },
    {
        "name": "Studio 28",
        "neighborhood": "Montmartre",
        "category": "Movie",
        "price": "€",
        "best_for": ["Romantic", "Casual"],
        "maps_query": "Studio 28 cinéma Montmartre, Paris",
        "description": (
            "Montmartre's historic independent cinema, open since 1928, with its own "
            "cosy bar. Pair a film with an evening walk through the hilltop streets."
        ),
    },
    {
        "name": "Paris Plages",
        "neighborhood": None,
        "category": "Beach",
        "price": "Free",
        "best_for": ["Casual"],
        "maps_query": "Paris Plages Bassin de la Villette, Paris",
        "description": (
            "Every summer, parts of the Seine riverbanks and the Bassin de la Villette "
            "become city beaches with deckchairs, sand and activities. Summer only, "
            "usually July and August."
        ),
    },
    {
        "name": "Rowing boats on Lac Daumesnil",
        "neighborhood": "Bois de Vincennes",
        "category": "Hiking / Nature",
        "price": "€",
        "best_for": ["Romantic", "Adventurous"],
        "maps_query": "Lac Daumesnil, Paris",
        "description": (
            "Rent a rowing boat and paddle around the lake's islands, one of which "
            "hides a little romantic temple. A bit silly, very charming and a great "
            "icebreaker. Boats are available in the warmer months."
        ),
    },
    {
        "name": "Le Dernier Bar avant la Fin du Monde",
        "neighborhood": "Châtelet",
        "category": "Arcade / Gaming",
        "price": "€€",
        "best_for": ["Casual", "Adventurous"],
        "description": (
            "A geek-culture bar full of sci-fi and fantasy decor, with themed "
            "cocktails and board games to play. Playing a game together takes the "
            "pressure off a first meeting."
        ),
    },
    {
        "name": "Square du Vert-Galant",
        "neighborhood": "Île de la Cité",
        "category": "Walk / Outdoors",
        "price": "Free",
        "best_for": ["Romantic"],
        "description": (
            "A tiny tree-lined park at the western tip of Île de la Cité, right at "
            "water level under the Pont Neuf. Come at sunset to watch the light fade "
            "over the Seine."
        ),
    },
]

# Every starter spot is in Paris for now; add a city/country per entry when
# seeding other cities.
STARTER_CITY = "Paris"
STARTER_COUNTRY = "France"
