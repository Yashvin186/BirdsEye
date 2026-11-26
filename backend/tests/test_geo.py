import numpy as np
from app.services.geo_service import GeoService as G

SRT_NEW = """1
00:00:00,000 --> 00:00:00,033
<font size="28">SrtCnt : 1, DiffTime : 33ms
[iso : 100] [latitude: 12.970000] [longitude: 77.590000] [rel_alt: 40.500 abs_alt: 930.200] </font>

2
00:00:01,000 --> 00:00:01,033
[latitude: 12.970100] [longitude: 77.590200] [rel_alt: 41.000 abs_alt: 930.700]

3
00:00:02,000 --> 00:00:02,033
[latitude: 12.970200] [longitude: 77.590400] [rel_alt: 41.000 abs_alt: 930.700]
"""
SRT_OLD = """1
00:00:00,000 --> 00:00:00,033
GPS (77.590000, 12.970000, 30) BAROMETER:40.5

2
00:00:01,000 --> 00:00:01,033
GPS (77.590100, 12.970100, 31) BAROMETER:41.5

3
00:00:02,000 --> 00:00:02,033
GPS (77.590200, 12.970200, 32) BAROMETER:42.5
"""


def test_parse_new_and_old_dji_formats(tmp_path):
    a = tmp_path / "a.srt"; a.write_text(SRT_NEW)
    s = G.parse_srt(a)
    assert len(s) == 3 and abs(s[0]["lat"] - 12.97) < 1e-9 and s[0]["alt"] == 40.5 and s[1]["t"] == 1.0
    b = tmp_path / "b.srt"; b.write_text(SRT_OLD)
    s = G.parse_srt(b)
    assert len(s) == 3 and abs(s[0]["lon"] - 77.59) < 1e-9 and abs(s[0]["lat"] - 12.97) < 1e-9


def test_similarity_recovers_scale_rotation_and_survives_gps_outliers():
    rng = np.random.default_rng(1)
    src = rng.uniform(-5, 5, (40, 3))
    ang = np.radians(33)
    R = np.array([[np.cos(ang), -np.sin(ang), 0], [np.sin(ang), np.cos(ang), 0], [0, 0, 1]])
    dst = 12.5 * (src @ R.T) + np.array([100, -50, 20]) + rng.normal(0, 0.3, (40, 3))
    dst[:3] += 80                                          # three wild GPS fixes
    s, Rr, t, inl, err = G.robust_similarity(src, dst)
    assert abs(s - 12.5) < 0.1
    assert inl.sum() >= 36
    assert np.allclose(Rr, R, atol=0.02)


def test_enu_distance_is_metric():
    e = G.to_enu(np.array([12.0, 12.001]), np.array([77.0, 77.0]), np.array([0, 0]), 12.0, 77.0, 0)
    assert abs(e[1, 1] - 110.6) < 1.0                      # 0.001 deg latitude ~ 110.6 m
