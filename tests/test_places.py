"""Venue text -> UBC building for the map."""
import json

import pytest

from app import places


@pytest.mark.parametrize("venue, building", [
    ("ICICS X150", "icics"),
    ("DMP 110", "dmp"),
    ("Hugh Dempster Pavilion, room 310", "dmp"),
    ("Irving K. Barber 261", "ikb"),
    ("Chapman Learning Commons", "ikb"),
    ("Henry Angus 335", "angus"),
    ("Sauder Atrium", "angus"),
    ("Hebb Theatre", "hebb"),
    ("Life Building", "life"),
    ("UBC Life Sciences Centre 2201", "lsc"),
    ("AMS Nest Great Hall", "nest"),
    ("Nest Room 2306", "nest"),
    ("The Norm Theatre", "nest"),
    ("Osborne Gym A", "osborne"),
    ("Meet at the Bus Loop", "exchange"),
    ("BUCH A101", "buchanan"),
    ("Demo Hall 204", "demo-hall"),
])
def test_known_venues(venue, building):
    assert places.locate(venue)["id"] == building


@pytest.mark.parametrize("venue", [None, "", "Rose Garden", "Online", "Somewhere downtown", "Mathematics of music talk"])
def test_unknown_venues_are_not_guessed(venue):
    assert places.locate(venue) is None


def test_building_codes_need_a_room_number():
    # "LIFE" as a word in a venue name is not the Life Building unless it's the code + room.
    assert places.locate("Student Life Lounge") is None
    assert places.locate("LIFE 2201")["id"] == "life"


def test_every_building_is_on_campus():
    for b in json.loads(places.BUILDINGS.read_text(encoding="utf-8"))["buildings"]:
        assert 49.24 < b["lat"] < 49.28 and -123.27 < b["lng"] < -123.23, b["id"]
