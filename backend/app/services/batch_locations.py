BATCH_LOCATIONS = [
    # US Tier 1
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
    # US Tier 2
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
