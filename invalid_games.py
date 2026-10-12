"""Explicitly voided season-four records; never infer invalidity from counts."""
INVALID_GAMES = {
    "261009-ca826183-2165-481c-bf27-686455ccc9f3": {"players": [101665767, 101939586, 108312204], "start": 1791556200, "end": 1791557366, "occurrence": 4},
    "261009-2ba8c271-6f7c-4902-9d06-326a8e358b06": {"players": [68348480, 101939586, 108386176], "start": 1791561187, "end": 1791561989, "occurrence": 4},
    "261010-3faa9290-8d23-431b-89b8-7390eb73b9f2": {"players": [68348480, 101665767, 108312204], "start": 1791639681, "end": 1791640486, "occurrence": 4},
    "261010-e3255290-ba38-4fc8-ad01-4af1e8deb650": {"players": [68348480, 101665767, 108312204], "start": 1791640548, "end": 1791641687, "occurrence": 5},
}


def is_invalid(uuid):
    return uuid in INVALID_GAMES
