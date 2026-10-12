from source_locations import locate_value

def test_source_location_prefers_matching_row():
    blocks=[{'text':'4.49','box':[100,0,140,20]}, {'text':'WBC','box':[0,40,60,60]}, {'text':'4.49','box':[100,40,140,60]}]
    assert locate_value(blocks,{'name':'白细胞','code':'WBC','value':'4.49'})==[100,40,140,60]
    assert locate_value(blocks,{'name':'未知项目','code':'','value':'4.49'})==[]
