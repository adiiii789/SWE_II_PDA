"""Kuratierte Titel mit Cover-URLs aus Spotifys oEmbed-Metadaten."""
from __future__ import annotations

from datetime import date

_GENRES = {
    "pop": ("Pop", (
        ("Levitating", "Dua Lipa", "39LLxExYz6ewLAcYrzQQyP",
         "https://image-cdn-fa.spotifycdn.com/image/ab67616d00001e02c88bae7846e62a8ba59ee0bd"),
        ("As It Was", "Harry Styles", "4LRPiXqCikLlN15c3yImP7",
         "https://image-cdn-fa.spotifycdn.com/image/ab67616d00001e02b46f74097655d7f353caab14"),
        ("Can't Get You Out of My Head", "Kylie Minogue", "3E7ZwUMJFqpsDOJzEkBrQ7",
         "https://image-cdn-fa.spotifycdn.com/image/ab67616d00001e025d6121285c42ea4535e59048"),
    )),
    "rock": ("Rock", (
        ("Here Comes the Sun", "The Beatles", "6dGnYIeXmHdcikdzNNDMm2",
         "https://image-cdn-fa.spotifycdn.com/image/ab67616d00001e02dc30583ba717007b00cceb25"),
        ("Beautiful Day", "U2", "0gzqZ9d1jIKo9psEIthwXe",
         "https://image-cdn-ak.spotifycdn.com/image/ab67616d00001e0238fa0dfe55b1ff2e8c962bae"),
        ("Dreams", "Fleetwood Mac", "0ofHAoxe9vBkTCp2UQIavz",
         "https://image-cdn-fa.spotifycdn.com/image/ab67616d00001e02e52a59a28efa4773dd2bfe1b"),
    )),
    "indie": ("Indie", (
        ("Lisztomania", "Phoenix", "4esUVfYnFcCCVHntx9FQCb",
         "https://image-cdn-ak.spotifycdn.com/image/ab67616d00001e0262cbc442278eefdde1a93efd"),
        ("Electric Feel", "MGMT", "3FtYbEfBqAlGO46NUDQSAt",
         "https://image-cdn-ak.spotifycdn.com/image/ab67616d00001e02abdf7749aeb5229dbf305f03"),
        ("A-Punk", "Vampire Weekend", "1595LW73XBxkRk2ciQOHfr",
         "https://image-cdn-fa.spotifycdn.com/image/ab67616d00001e029cca0d695187fbeed4ee301b"),
    )),
    "soul": ("Soul & Funk", (
        ("Lovely Day", "Bill Withers", "0ACACkoHUwgfgY5CxVIL4N",
         "https://image-cdn-ak.spotifycdn.com/image/ab67616d00001e02f8560af696925c50080dcc35"),
        ("September", "Earth, Wind & Fire", "2grjqo0Frpf2okIBiifQKs",
         "https://image-cdn-fa.spotifycdn.com/image/ab67616d00001e022e7558daae7a80e1f5819aa1"),
        ("Sir Duke", "Stevie Wonder", "4pNiE4LCVV74vfIBaUHm1b",
         "https://image-cdn-fa.spotifycdn.com/image/ab67616d00001e022fee61bfec596bb6f5447c50"),
    )),
    "hip_hop": ("Hip-Hop", (
        ("Hey Ya!", "Outkast", "2PpruBYCo4H7WOBJ7Q2EwM",
         "https://image-cdn-fa.spotifycdn.com/image/ab67616d00001e026e88eb6508fd94cd1b745ce2"),
        ("Can I Kick It?", "A Tribe Called Quest", "1pdi3al4evV4cNTIl3CGM1",
         "https://image-cdn-ak.spotifycdn.com/image/ab67616d00001e0206da4b1d64833d79387593a1"),
        ("Me Myself and I", "De La Soul", "6mH6EBEvnlY1SQaFQH3WxE",
         "https://image-cdn-ak.spotifycdn.com/image/ab67616d00001e027e887f2bdffa2158e33d9446"),
    )),
    "electronic": ("Elektronisch", (
        ("Digital Love", "Daft Punk", "2VEZx7NWsZ1D0eJ4uv5Fym",
         "https://image-cdn-ak.spotifycdn.com/image/ab67616d00001e021e81bff9807a9e629fce5ade"),
        ("D.A.N.C.E.", "Justice", "33yAEqzKXexYM3WlOYtTfQ",
         "https://image-cdn-ak.spotifycdn.com/image/ab67616d00001e021c0bcf8b536295438d26c70d"),
        ("Galvanize", "The Chemical Brothers", "29IxsvOCnAwQpt95Xymgkb",
         "https://image-cdn-fa.spotifycdn.com/image/ab67616d00001e0204334cc2b0872cfa2b963267"),
    )),
    "jazz": ("Jazz", (
        ("Take Five", "The Dave Brubeck Quartet", "5UbLKRX1qVROlwDFOooEvG",
         "https://image-cdn-ak.spotifycdn.com/image/ab67616d00001e026ca90aff3927a8b212258770"),
        ("So What", "Miles Davis", "7jeR2pp25RQz7zZBK8H9sl",
         "https://image-cdn-ak.spotifycdn.com/image/ab6742d3000052b78468cf49750c515bfef2cbb4"),
        ("Feeling Good", "Nina Simone", "6Rqn2GFlmvmV4w9Ala0I1e",
         "https://image-cdn-ak.spotifycdn.com/image/ab67616d00001e02892abb1ade35b4863b29e051"),
    )),
}
MUSIC_GENRES = (("mixed", "Gemischt"), *((key, label) for key, (label, _) in _GENRES.items()))
_MIXED = tuple(song for _, tracks in _GENRES.values() for song in tracks)


def song_for(day: date, genre: str) -> tuple[str, str, str, str]:
    """Titel, Interpret, Tracklink und Cover-URL für den ausgewählten Tag."""
    tracks = _GENRES[genre][1] if genre in _GENRES else _MIXED
    title, artist, track_id, cover = tracks[day.toordinal() % len(tracks)]
    return title, artist, f"https://open.spotify.com/track/{track_id}", cover
