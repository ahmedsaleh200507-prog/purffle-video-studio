from scene_interval_review_proof import verdict
from portrait_render_proof import crop_geometry,coverage
def test_title_veto_and_unknown():
    assert verdict("postfire",[True,True,True])!="candidate"
    assert verdict("shore",[True,None,False])!="candidate"
    assert verdict("postfire",[True,True,False])=="candidate"
def test_crop_bounds_even_and_portrait():
    for w,h in ((1920,1080),(3840,2160),(720,1280),(1080,1920)):
        for f in (0,.5,1):
            cw,ch,x,y=crop_geometry(w,h,f)
            assert all(n%2==0 for n in (cw,ch,x,y))
            assert x>=0 and y>=0 and x+cw<=w and y+ch<=h
            assert abs(cw/ch-9/16)<.003
def test_coverage_not_invented_when_missing():
    assert coverage([[],[],[]],1920,(608,1080,656,0))["mean"] is None
def test_coverage_actual_box_intersection():
    rows=[[{"box":[.4,.2,.6,.9]}]]
    assert coverage(rows,1000,(400,800,300,0))["mean"]==1
    assert coverage(rows,1000,(200,800,0,0))["mean"]==0
