"""consent: CMP table shape + multilingual generic button matching."""
import consent


def test_every_cmp_entry_is_complete():
    names = set()
    for cmp in consent.CMPS:
        assert set(cmp) >= {"name", "detect", "accept", "deny", "dismiss"}, cmp
        assert cmp["name"] not in names, f"duplicate {cmp['name']}"
        names.add(cmp["name"])
        assert cmp["detect"] and cmp["accept"] and cmp["deny"], cmp["name"]
    for required in ("complianz", "cookiebot", "cookieyes", "onetrust", "borlabs",
                     "usercentrics", "didomi", "osano", "iubenda", "klaro"):
        assert required in names


def test_generic_text_matches_common_languages():
    acc, den = consent.GENERIC_TEXT["accept"], consent.GENERIC_TEXT["deny"]
    for label in ("Sprejmi vse", "Alle akzeptieren", "Accept all cookies", "Prihvati", "Accetta"):
        assert acc.search(label), label
        assert not den.search(label), label
    for label in ("Samo nujni", "Nur notwendige", "Reject all", "Zavrni", "Only necessary"):
        assert den.search(label), label
        assert not acc.search(label), label


def test_invalid_action_rejected():
    import asyncio
    r = asyncio.new_event_loop().run_until_complete(consent.apply(None, "maybe"))
    assert r["success"] is False and "accept" in r["error"]
