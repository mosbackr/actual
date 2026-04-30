BATCH_LOCATIONS = [
    # US Tier 1 — Major tech/VC hubs
    {"city": "San Francisco", "state": "CA", "country": "US"},
    {"city": "New York", "state": "NY", "country": "US"},
    {"city": "Boston", "state": "MA", "country": "US"},
    {"city": "Los Angeles", "state": "CA", "country": "US"},
    {"city": "Seattle", "state": "WA", "country": "US"},
    {"city": "Austin", "state": "TX", "country": "US"},
    {"city": "Chicago", "state": "IL", "country": "US"},
    {"city": "Miami", "state": "FL", "country": "US"},
    {"city": "Denver", "state": "CO", "country": "US"},
    {"city": "Washington", "state": "DC", "country": "US"},
    {"city": "San Jose", "state": "CA", "country": "US"},
    # US Tier 2 — Strong startup ecosystems
    {"city": "San Diego", "state": "CA", "country": "US"},
    {"city": "Atlanta", "state": "GA", "country": "US"},
    {"city": "Dallas", "state": "TX", "country": "US"},
    {"city": "Houston", "state": "TX", "country": "US"},
    {"city": "Philadelphia", "state": "PA", "country": "US"},
    {"city": "Minneapolis", "state": "MN", "country": "US"},
    {"city": "Detroit", "state": "MI", "country": "US"},
    {"city": "Pittsburgh", "state": "PA", "country": "US"},
    {"city": "Nashville", "state": "TN", "country": "US"},
    {"city": "Raleigh-Durham", "state": "NC", "country": "US"},
    {"city": "Salt Lake City", "state": "UT", "country": "US"},
    {"city": "Portland", "state": "OR", "country": "US"},
    {"city": "Phoenix", "state": "AZ", "country": "US"},
    {"city": "Columbus", "state": "OH", "country": "US"},
    {"city": "Indianapolis", "state": "IN", "country": "US"},
    {"city": "St. Louis", "state": "MO", "country": "US"},
    {"city": "Baltimore", "state": "MD", "country": "US"},
    {"city": "Tampa", "state": "FL", "country": "US"},
    {"city": "Charlotte", "state": "NC", "country": "US"},
    {"city": "Las Vegas", "state": "NV", "country": "US"},
    {"city": "Cincinnati", "state": "OH", "country": "US"},
    {"city": "Kansas City", "state": "MO", "country": "US"},
    {"city": "Birmingham", "state": "AL", "country": "US"},
    {"city": "Madison", "state": "WI", "country": "US"},
    {"city": "Omaha", "state": "NE", "country": "US"},
    {"city": "Sacramento", "state": "CA", "country": "US"},
    {"city": "Oakland", "state": "CA", "country": "US"},
    {"city": "Orlando", "state": "FL", "country": "US"},
    {"city": "Cleveland", "state": "OH", "country": "US"},
    {"city": "Irvine", "state": "CA", "country": "US"},
    # US Tier 3 — 300K+ cities
    {"city": "San Antonio", "state": "TX", "country": "US"},
    {"city": "Jacksonville", "state": "FL", "country": "US"},
    {"city": "Fort Worth", "state": "TX", "country": "US"},
    {"city": "Oklahoma City", "state": "OK", "country": "US"},
    {"city": "El Paso", "state": "TX", "country": "US"},
    {"city": "Memphis", "state": "TN", "country": "US"},
    {"city": "Louisville", "state": "KY", "country": "US"},
    {"city": "Milwaukee", "state": "WI", "country": "US"},
    {"city": "Albuquerque", "state": "NM", "country": "US"},
    {"city": "Tucson", "state": "AZ", "country": "US"},
    {"city": "Fresno", "state": "CA", "country": "US"},
    {"city": "Colorado Springs", "state": "CO", "country": "US"},
    {"city": "Virginia Beach", "state": "VA", "country": "US"},
    {"city": "Tulsa", "state": "OK", "country": "US"},
    {"city": "New Orleans", "state": "LA", "country": "US"},
    {"city": "Wichita", "state": "KS", "country": "US"},
    {"city": "Honolulu", "state": "HI", "country": "US"},
    {"city": "Lexington", "state": "KY", "country": "US"},
    {"city": "Corpus Christi", "state": "TX", "country": "US"},
    {"city": "Riverside", "state": "CA", "country": "US"},
    {"city": "Newark", "state": "NJ", "country": "US"},
    {"city": "Bakersfield", "state": "CA", "country": "US"},
    {"city": "Stockton", "state": "CA", "country": "US"},
    # International - North America
    {"city": "Toronto", "state": None, "country": "Canada"},
    {"city": "Vancouver", "state": None, "country": "Canada"},
    {"city": "Montreal", "state": None, "country": "Canada"},
    # International - Europe
    {"city": "London", "state": None, "country": "UK"},
    {"city": "Berlin", "state": None, "country": "Germany"},
    {"city": "Paris", "state": None, "country": "France"},
    {"city": "Amsterdam", "state": None, "country": "Netherlands"},
    {"city": "Stockholm", "state": None, "country": "Sweden"},
    # International - Asia-Pacific
    {"city": "Singapore", "state": None, "country": "Singapore"},
    {"city": "Sydney", "state": None, "country": "Australia"},
    {"city": "Bangalore", "state": None, "country": "India"},
    {"city": "Tel Aviv", "state": None, "country": "Israel"},
    # International - Latin America
    {"city": "Sao Paulo", "state": None, "country": "Brazil"},
    {"city": "Mexico City", "state": None, "country": "Mexico"},
    {"city": "Bogota", "state": None, "country": "Colombia"},
]

BATCH_STAGES = ["pre_seed", "seed", "series_a", "series_b", "series_c", "growth"]

STAGE_LABELS = {
    "pre_seed": "Pre-Seed",
    "seed": "Seed",
    "series_a": "Series A",
    "series_b": "Series B",
    "series_c": "Series C",
    "growth": "Growth",
}


def format_location(loc: dict) -> str:
    """Format a location dict as a display string like 'Austin, TX' or 'London, UK'."""
    if loc["state"]:
        return f"{loc['city']}, {loc['state']}"
    return f"{loc['city']}, {loc['country']}"
