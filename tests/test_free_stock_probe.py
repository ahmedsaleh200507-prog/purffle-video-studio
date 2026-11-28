from free_stock_probe import Candidate,summarize

def item(w,h,d):
    return Candidate("pexels","id","video","https://example.com/v.mp4",w,h,d)

def test_portrait_and_4k_fit_but_landscape_1080_does_not():
    assert summarize([item(1080,1920,3),item(3840,2160,9),item(1920,1080,9)])=={
        "candidates":3,"portrait_quality_hints":2,"short_shot_hints":2,"eight_second_hints":1,"unknown_duration":0}

def test_unknown_or_low_resolution_not_counted():
    assert summarize([item(0,0,0),item(640,360,9)])["portrait_quality_hints"]==0

def test_unknown_duration_not_assumed_to_cover_scene():
    r=summarize([item(1080,1920,0)])
    assert r["unknown_duration"]==1 and r["short_shot_hints"]==0
