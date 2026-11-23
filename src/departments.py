"""Department names as the curriculum PDF prints them -> the slugs used in the site's URLs."""

_KEYS = [("chemical and biochemical", "chemical-engineering"), ("chemical engineering", "chemical-engineering"),
         ("civil", "civil-engineering"), ("chemistry", "chemistry"), ("computer science", "computer-science-engineering"),
         ("electrical", "electrical-engineering"), ("humanities", "humanities-social-sciences"),
         ("mathematics", "mathematics"), ("mechanical", "mechanical-engineering"),
         ("metallurgical", "metallurgical-engineering"), ("physics", "physics")]


def department_slug(name):
    """'Chemical and Biochemical Engineering' -> 'chemical-engineering'; '' when nothing matches."""
    low = (name or "").lower()
    return next((slug for key, slug in _KEYS if key in low), "")
